"""Replay a trade's price path under different exit rules. Pure pandas/numpy — no I/O.

Conventions
- `path`: 5m OHLC bars that START after the entry (the bar containing the entry is skipped, since part of
  it happened before you were in). Prices are the data vendor's mid prices, not FTMO's bid/ask.
- A bar that touches both the stop and the target is counted as a stop (we can't know which came first):
  pessimistic, and reported as "ambiguous".
- A bar that opens beyond the stop fills at its open (gap). Stop changes (breakeven, trailing) take effect
  from the next bar.
- R is measured against the stop distance used by that rule (lots are sized from the stop, so a wider stop
  means smaller lots and the same money at risk).
"""
from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class Result:
    exit_price: float
    reason: str        # TP / SL / BE / Trail / Time
    ambiguous: bool
    exit_time: pd.Timestamp


def simulate(path: pd.DataFrame, long: bool, entry: float, stop: float, target=None,
             breakeven_at=None, trail=None) -> Result:
    """breakeven_at: move the stop to entry once price has gone this far in favour (price units).
    trail: trailing distance (price units) behind the best price since entry; never loosens the stop."""
    d = 1 if long else -1
    best, moved = entry, None
    o, h, l, c = (path[k].to_numpy() for k in ("open", "high", "low", "close"))
    for i in range(len(path)):
        adverse, favour = (l[i], h[i]) if long else (h[i], l[i])
        if d * (o[i] - stop) <= 0:                                        # gapped through the stop
            return Result(o[i], moved or "SL", False, path.index[i])
        hit_stop = d * (adverse - stop) <= 0
        hit_tp = target is not None and d * (favour - target) >= 0
        if hit_stop:
            return Result(stop, moved or "SL", bool(hit_tp), path.index[i])
        if hit_tp:
            return Result(target, "TP", False, path.index[i])
        best = max(best, h[i]) if long else min(best, l[i])
        if breakeven_at is not None and d * (best - entry) >= breakeven_at and d * (stop - entry) < 0:
            stop, moved = entry, "BE"
        if trail is not None:
            cand = best - d * trail
            if d * (cand - stop) > 0:
                stop, moved = cand, "Trail"
    return Result(c[-1] if len(path) else entry, "Time", False, path.index[-1] if len(path) else None)


def r_multiple(res: Result, long: bool, entry: float, risk: float) -> float:
    return (1 if long else -1) * (res.exit_price - entry) / risk


def excursions(path: pd.DataFrame, long: bool, entry: float, risk: float, until=None):
    """(MAE, MFE) in R up to `until` (inclusive): how far price went against you / for you."""
    p = path if until is None else path[path.index <= until]
    if p.empty:
        return np.nan, np.nan
    if long:
        return (entry - p["low"].min()) / risk, (p["high"].max() - entry) / risk
    return (p["high"].max() - entry) / risk, (entry - p["low"].min()) / risk


def horizon_end(entry_time: pd.Timestamp, max_days: float = 5) -> pd.Timestamp:
    """Latest exit for the replay: 5 days, or Friday 16:50 New York (positions are closed before the weekend)."""
    ny = entry_time.tz_convert("America/New_York")
    friday = (ny + pd.Timedelta(days=(4 - ny.dayofweek) % 7)).normalize() + pd.Timedelta(hours=16, minutes=50)
    if friday < ny:
        friday += pd.Timedelta(days=7)
    return min(friday.tz_convert("UTC"), entry_time + pd.Timedelta(days=max_days))


def path_after(bars: pd.DataFrame, entry_time: pd.Timestamp, end: pd.Timestamp, bar="5min") -> pd.DataFrame:
    start = entry_time.ceil(bar)
    return bars[(bars.index >= start) & (bars.index < end)]


# ---------------------------------------------------------------------------------------------------------
def variants(t: dict) -> dict:
    """Exit rules to compare for one trade: name -> (stop, target, breakeven_at, trail, risk). Price units.
    t needs: long, entry, sl, tp, atr_day, bands (dict like the snapshot's)."""
    d = 1 if t["long"] else -1
    risk = abs(t["entry"] - t["sl"])
    out = {"Actual SL/TP": (t["sl"], t["tp"], None, None, risk)}
    for m in (0.75, 1.25, 1.5, 2.0):
        out[f"Stop x{m:g}, same TP"] = (t["entry"] - d * m * risk, t["tp"], None, None, m * risk)
    out["Breakeven after +1R"] = (t["sl"], t["tp"], risk, None, risk)
    for k in (1.5, 2.0, 3.0):
        out[f"Target {k:g}R"] = (t["sl"], t["entry"] + d * k * risk, None, None, risk)
    side = "Up" if t["long"] else "Down"
    for p in ("P50", "P75", "P90"):
        lvl = (t.get("bands") or {}).get(f"{side} {p}")
        if lvl is not None and d * (lvl - t["entry"]) > 0:
            out[f"Target band {p}"] = (t["sl"], lvl, None, None, risk)
    atr = t.get("atr_day")
    if atr and atr > 0:
        for k in (0.3, 0.5, 0.75):
            out[f"No TP, trail {k:g} ATR"] = (t["sl"], None, None, k * atr, risk)
    return out


def summarise(df: pd.DataFrame) -> pd.DataFrame:
    """Per-rule table from a long frame with columns rule, R, ambiguous (one row per trade x rule)."""
    def streak(r):
        worst = run = 0
        for x in r:
            run = run + 1 if x <= 0 else 0
            worst = max(worst, run)
        return worst
    g = df.groupby("rule", sort=False)
    out = pd.DataFrame({
        "trades": g["R"].size(), "win %": g["R"].apply(lambda r: 100 * (r > 0).mean()),
        "avg R": g["R"].mean(), "total R": g["R"].sum(), "worst losing run": g["R"].apply(streak),
        "ambiguous": g["ambiguous"].sum(),
    })
    return out.round({"win %": 0, "avg R": 2, "total R": 1})

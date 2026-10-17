"""Trade-log logic: snapshot of the dashboard at entry, trade results. Pure pandas — no Streamlit, no I/O."""
import math

import numpy as np
import pandas as pd

import config
from indicators import currency


def session_name(ts: pd.Timestamp) -> str:
    """Trading session for a UTC timestamp (config.SESSIONS: (start hour UTC, name), ascending)."""
    hour = ts.tz_convert("UTC").hour if ts.tzinfo else ts.hour
    name = config.SESSIONS[-1][1]
    for start, label in config.SESSIONS:
        if hour >= start:
            name = label
    return name


def band_position(price: float, levels: dict) -> str:
    """Where a price sits among the distribution bands, e.g. 'Anchor – Up P25' or 'above Up P90'."""
    if not levels:
        return None
    ordered = sorted(levels.items(), key=lambda kv: kv[1])
    if price < ordered[0][1]:
        return f"below {ordered[0][0]}"
    if price > ordered[-1][1]:
        return f"above {ordered[-1][0]}"
    for (lo_name, lo), (hi_name, hi) in zip(ordered, ordered[1:]):
        if lo <= price <= hi:
            return f"{lo_name} – {hi_name}"
    return None


def trade_result(side: str, entry: float, sl: float, exit_price: float, risk_money: float):
    """(R multiple, P&L in account currency). P&L = R x the money risked at entry (costs not included)."""
    sign = 1 if side == "Long" else -1
    r = sign * (exit_price - entry) / abs(entry - sl)
    return r, r * risk_money


def currency_snapshot(history: dict, smap: dict) -> dict:
    """Latest strength, rank (1 = strongest) and Record high % per currency, plus XAU from gold's own pairs.
    history: {display name: indicator frame}; smap: {display: (group, vendor)}."""
    def pairs_in(groups):
        return {v: n for n, (g, v) in smap.items() if g in groups and n in history}

    def measure(pairs):
        st = currency.strength({v: history[n]["score"] for v, n in pairs.items()})
        _, _, pct = currency.record_high({
            v: currency.pair_breakouts(history[n], config.RECORD_LOOKBACK_BARS, config.RECORD_WINDOW_BARS)
            for v, n in pairs.items()
        })
        last = st.apply(lambda s: s.dropna().iloc[-1] if s.notna().any() else np.nan)
        rec = pct.iloc[-1] if not pct.empty else pd.Series(dtype=float)
        return last, rec

    fx = pairs_in(config.CURRENCY_GROUPS)
    if not fx:
        return {}
    strength, record = measure(fx)
    ranks = strength.rank(ascending=False, method="min")
    out = {c: {"strength": strength[c], "rank": ranks[c], "record_high": record.get(c, np.nan)}
           for c in strength.index}
    metal = pairs_in(config.CURRENCY_METAL_GROUPS)
    fx_codes = set(strength.index)
    metal_codes = sorted({c for v in metal for c in currency.parse_pair(v)} - fx_codes)
    m_strength, m_record = measure(metal) if metal_codes else (pd.Series(dtype=float), pd.Series(dtype=float))
    for code in metal_codes:
        if code in m_strength.index:
            out[code] = {"strength": m_strength[code],
                         "rank": int((strength > m_strength[code]).sum()) + 1,   # where it would sit among the 8
                         "record_high": m_record.get(code, np.nan)}
    return out


def clean(value):
    """JSON-safe: numpy -> python, NaN/inf -> None, timestamps -> ISO strings."""
    if isinstance(value, dict):
        return {k: clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [clean(v) for v in value]
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if isinstance(value, (np.bool_, bool)):
        return bool(value)
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating, float)):
        return None if math.isnan(value) or math.isinf(value) else float(value)
    if value is pd.NA or value is pd.NaT:
        return None
    return value


def build_snapshot(name: str, vendor: str, ind: pd.DataFrame, now: pd.Timestamp, ccy: dict, dist: dict,
                   entry: float, atr_day, pair_breakout) -> dict:
    """Every dashboard value worth analysing later, at the moment of logging."""
    last = ind.iloc[-1]
    base, quote = currency.parse_pair(vendor)
    b, q = ccy.get(base, {}), ccy.get(quote, {})
    return clean({
        "symbol": name,
        "bar_time": ind.index[-1],
        "bar_age_min": (now - ind.index[-1]).total_seconds() / 60 - 10,
        "session": session_name(now),
        "state": last.get("state"),
        "score": last.get("score"),
        "adx": last.get("adx"),
        "plus_di": last.get("plus_di"),
        "minus_di": last.get("minus_di"),
        "di_spread": last.get("di_spread"),
        "natr": last.get("natr"),
        "ema_lag": last.get("ema_lag"),
        "adr_used": last.get("adr_used"),
        "prev_day_zone": last.get("prev_day_zone"),
        "prev_day_pos": last.get("prev_day_pos"),
        "atr_10m": last.get("atr"),
        "atr_day": atr_day,
        "pair_breakout": pair_breakout,               # +1 new 24h high in the last hour, -1 new low, 0 none
        "base": base, "base_strength": b.get("strength"), "base_rank": b.get("rank"),
        "base_record_high": b.get("record_high"),
        "quote": quote, "quote_strength": q.get("strength"), "quote_rank": q.get("rank"),
        "quote_record_high": q.get("record_high"),
        "band_anchor": dist["anchor"] if dist else None,
        "band_position": band_position(entry, dist["levels"]) if dist else None,
        "bands": dist["levels"] if dist else None,
        "data_provider": config.DATA_PROVIDER,
    })

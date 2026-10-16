"""Position sizing and stop levels. Pure pandas — no Streamlit — so the robot can reuse it.

Money maths, for one lot:
    money per 1.0 price move = contract size x (quote currency -> account currency rate)
    lots = risk money / (|entry - stop| x money per 1.0 move), rounded DOWN to the lot step
Spread and commission are not included.
"""
import math

import numpy as np
import pandas as pd

import config
from indicators import daily, trend


def parse(vendor: str) -> tuple[str, str]:
    """'EUR/USD' -> ('EUR', 'USD')."""
    base, quote = vendor.split("/")
    return base, quote


def to_usd(ccy: str, prices: dict) -> float:
    """USD value of one unit of `ccy`, from the latest pair prices {'EUR/USD': 1.08, ...}."""
    if ccy == "USD":
        return 1.0
    if f"{ccy}/USD" in prices:
        return float(prices[f"{ccy}/USD"])
    if f"USD/{ccy}" in prices:
        return 1.0 / float(prices[f"USD/{ccy}"])
    raise KeyError(f"No USD pair loaded for {ccy}")


def quote_to_account(vendor: str, prices: dict, account: str = config.ACCOUNT_CURRENCY) -> float:
    """How much one unit of the pair's quote currency is worth in the account currency."""
    _, quote = parse(vendor)
    return to_usd(quote, prices) / to_usd(account, prices)


def contract_size(vendor: str) -> float:
    return config.CONTRACT_SIZES.get(vendor, config.FX_CONTRACT_SIZE)


def pip_size(vendor: str) -> float:
    if vendor in config.PIP_SIZES:
        return config.PIP_SIZES[vendor]
    return 0.01 if parse(vendor)[1] == "JPY" else 0.0001


def price_decimals(vendor: str) -> int:
    """Decimals to show: one more than the pip (EURUSD 5, USDJPY 3, XAUUSD 2)."""
    return max(0, round(-math.log10(pip_size(vendor)))) + 1


def money_per_unit(vendor: str, prices: dict) -> float:
    """Account money gained or lost per 1.0 price move, per 1 lot."""
    return contract_size(vendor) * quote_to_account(vendor, prices)


def size_position(risk_money: float, entry: float, stop: float, per_unit: float,
                  lot_step: float = config.LOT_STEP, min_lot: float = config.MIN_LOT) -> dict:
    """Largest lot size (rounded down to lot_step) whose loss at the stop is within risk_money.

    Returns lots (0 if even min_lot risks too much), raw_lots, risk_per_lot and risk (actual, after rounding).
    """
    distance = abs(entry - stop)
    if distance <= 0:
        raise ValueError("Stop must differ from entry")
    if risk_money <= 0 or per_unit <= 0:
        raise ValueError("Risk and money per unit must be positive")
    risk_per_lot = distance * per_unit
    raw = risk_money / risk_per_lot
    steps = math.floor(raw / lot_step + 1e-9)
    lots = round(steps * lot_step, 8)
    if lots < min_lot - 1e-12:
        lots = 0.0
    return {"lots": lots, "raw_lots": raw, "risk_per_lot": risk_per_lot, "risk": lots * risk_per_lot}


def stop_on_correct_side(side: str, entry: float, stop: float) -> bool:
    return stop < entry if side == "Long" else stop > entry


def targets(entry: float, stop: float, multiples=None) -> dict:
    """Prices at R multiples: 1R = the stop distance, in the trade's direction."""
    multiples = multiples or config.RISK_TARGETS_R
    return {r: entry + r * (entry - stop) for r in multiples}


def rma(values: pd.Series, length: int) -> pd.Series:
    """Wilder's moving average as TradingView's ATR uses it: seeded with the simple mean of the first `length`."""
    x = values.dropna()
    out = pd.Series(np.nan, index=x.index)
    if len(x) < length:
        return out
    acc = x.iloc[:length].mean()
    out.iloc[length - 1] = acc
    for i in range(length, len(x)):
        acc = (acc * (length - 1) + x.iloc[i]) / length
        out.iloc[i] = acc
    return out


def current_trading_day(now: pd.Timestamp) -> pd.Timestamp:
    """Trading day (17:00 New York rollover) that `now` falls in."""
    return daily.trading_day(pd.DatetimeIndex([now])).iloc[0]


def _complete_days(days: pd.DataFrame, today) -> pd.DataFrame:
    """Finished days only: drops today (still forming) and the first day (may be partial)."""
    done = days[days.index < today] if today is not None else days.iloc[:-1]
    return done.iloc[1:]


def daily_atr(days: pd.DataFrame, today=None, length: int = None):
    """Daily ATR(length) through the last complete day (TradingView-style Wilder average)."""
    length = length or config.DIST_ATR_DAYS
    before_today = days[days.index < today] if today is not None else days.iloc[:-1]
    atr = rma(trend.true_range(before_today).iloc[1:], length)    # first day: no previous close
    return None if atr.dropna().empty else float(atr.iloc[-1])


def distribution(days: pd.DataFrame, today=None, lookback: int = None, min_sample: int = None,
                 percentiles=None, anchor: str = None, scale_days: int = None):
    """Today's ATR-scaled distribution bands (same method as the updated TradingView indicator).

    For each complete day s in the last `lookback`:
        up   = (high[s] - reference) / ATR      down = (reference - low[s]) / ATR
    reference = the previous day's close (anchor "close") or day s's own open (anchor "open");
    ATR = mean true range of the `scale_days` days before s (what was known when day s started).
    Bands = today's anchor +/- percentile(up or down) x today's ATR (the last `scale_days` complete days).
    Scaling keeps the shape of past moves but sizes them to current volatility (tested on the MT5 dev
    data: on volatile days a P90 band was crossed ~15% of the time instead of ~22% unscaled).

    days: daily OHLC indexed by trading day (17:00 New York), today's forming day last if the market is open.
    today: the current trading day; days before it are complete. None = treat the last row as forming.
    Returns None without enough history, else
    {"anchor", "anchor_type", "n", "atr", "up": {p: dist}, "down": {p: dist}, "levels": {label: price}}.
    """
    lookback = lookback or config.DIST_LOOKBACK
    min_sample = min_sample or config.DIST_MIN_SAMPLE
    percentiles = percentiles or config.DIST_PERCENTILES
    anchor = anchor or config.DIST_ANCHOR
    scale_days = scale_days or config.DIST_SCALE_DAYS

    before_today = days[days.index < today] if today is not None else days.iloc[:-1]
    if len(before_today) < scale_days + 2:
        return None
    tr = trend.true_range(before_today)
    tr.iloc[0] = np.nan                                       # first day may be partial
    atr_known = tr.rolling(scale_days, min_periods=scale_days).mean()   # through each day's close
    scale_at_start = atr_known.shift(1)                       # what was known when each day started

    ref = before_today["close"].shift(1) if anchor == "close" else before_today["open"]
    up = ((before_today["high"] - ref) / scale_at_start).iloc[1:].dropna().tail(lookback)
    down = ((ref - before_today["low"]) / scale_at_start).iloc[1:].dropna().tail(lookback)
    atr_now = atr_known.iloc[-1]
    if len(up) < min_sample or pd.isna(atr_now):
        return None
    atr_now = float(atr_now)

    if anchor == "close":
        anchor_price = float(before_today["close"].iloc[-1])
    else:
        if today is None or today not in days.index:
            return None          # today's open not known yet
        anchor_price = float(days.loc[today, "open"])

    up_q = {p: float(np.percentile(up, p)) * atr_now for p in percentiles}      # linear interpolation
    down_q = {p: float(np.percentile(down, p)) * atr_now for p in percentiles}
    levels = {f"Up P{p:g}": anchor_price + up_q[p] for p in reversed(percentiles)}
    levels["Anchor"] = anchor_price
    levels.update({f"Down P{p:g}": anchor_price - down_q[p] for p in percentiles})
    return {"anchor": anchor_price, "anchor_type": anchor, "n": len(up), "atr": atr_now,
            "up": up_q, "down": down_q, "levels": levels}

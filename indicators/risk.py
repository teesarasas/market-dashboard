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


def distribution(df: pd.DataFrame, length: int = None, multiples=None):
    """Today's distribution bands: today's open +/- k x the previous day's daily ATR(length).

    df: intraday OHLC bars. Daily bars use the 17:00 New York rollover. The first day in the data
    (may be partial) and today (still forming) are left out of the ATR.
    Returns None if there are not enough complete days, else
    {"open", "atr", "levels": {k: price}} with k = -3..-1, 1..3.
    """
    length = length or config.DIST_ATR_DAYS
    multiples = multiples or config.DIST_LEVELS
    days = daily.daily_ohlc(df)
    if len(days) < length + 2:
        return None
    tr = trend.true_range(days).iloc[1:-1]       # complete days only
    atr = rma(tr, length)
    if atr.dropna().empty:
        return None
    prev_atr = float(atr.iloc[-1])
    today_open = float(days["open"].iloc[-1])
    levels = {}
    for k in multiples:
        levels[k] = today_open + k * prev_atr
        levels[-k] = today_open - k * prev_atr
    return {"open": today_open, "atr": prev_atr, "levels": dict(sorted(levels.items()))}

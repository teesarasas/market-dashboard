"""FX trading-day metrics. Pure pandas — no Streamlit — so they can be reused in backtests."""
import numpy as np
import pandas as pd

import config

ABOVE_PDH = "Above PDH"
BELOW_PDL = "Below PDL"
INSIDE = "Inside"


def _shifted(index: pd.DatetimeIndex) -> pd.DatetimeIndex:
    """New York time moved forward so the rollover lands on midnight.
    A bar at 17:00 NY belongs to the next calendar date's trading day."""
    ny = index.tz_convert(config.DAY_ROLLOVER_TZ)
    return ny + pd.Timedelta(hours=24 - config.DAY_ROLLOVER_HOUR)


def trading_day(index: pd.DatetimeIndex) -> pd.Series:
    """FX trading date for each bar (rollover 17:00 New York, DST-aware)."""
    return pd.Series(_shifted(index).tz_localize(None).normalize(), index=index)


def is_weekend(index: pd.DatetimeIndex) -> pd.Series:
    """True for bars between the Friday and Sunday rollovers (market closed)."""
    return pd.Series(_shifted(index).dayofweek >= 5, index=index)


def daily_ohlc(df: pd.DataFrame) -> pd.DataFrame:
    """Intraday bars -> one row per trading day. Days with no bars don't appear."""
    return df.groupby(trading_day(df.index)).agg(
        open=("open", "first"), high=("high", "max"), low=("low", "min"), close=("close", "last")
    )


def compute(df: pd.DataFrame) -> pd.DataFrame:
    """Adds per-bar daily columns to an intraday OHLC frame:
    adr, adr_used (%), pdh, pdl, prev_day_pos (%), prev_day_zone."""
    out = df.copy()
    day = trading_day(out.index)
    daily = daily_ohlc(out)
    rng = daily["high"] - daily["low"]

    # First day in the data may start mid-session; the last is still forming.
    # Each day's ADR uses only complete days before it.
    complete_rng = rng.copy()
    complete_rng.iloc[0] = np.nan
    adr = complete_rng.shift(1).rolling(config.ADR_DAYS, min_periods=config.ADR_DAYS).mean()

    prev = daily[["high", "low"]].shift(1)
    out["adr"] = day.map(adr).to_numpy()
    out["pdh"] = day.map(prev["high"]).to_numpy()
    out["pdl"] = day.map(prev["low"]).to_numpy()

    # Today's range so far, bar by bar
    grouped = out.groupby(day.to_numpy())
    range_so_far = grouped["high"].cummax() - grouped["low"].cummin()
    out["adr_used"] = range_so_far / out["adr"] * 100

    out["prev_day_pos"] = (out["close"] - out["pdl"]) / (out["pdh"] - out["pdl"]) * 100
    out["prev_day_zone"] = np.select(
        [out["close"] > out["pdh"], out["close"] < out["pdl"], out["pdh"].notna()],
        [ABOVE_PDH, BELOW_PDL, INSIDE],
        default=None,
    )
    return out

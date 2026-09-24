"""FX trading-day helpers. Pure pandas — no Streamlit — so they can be reused in backtests."""
import pandas as pd

import config


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

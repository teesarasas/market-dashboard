"""Synthetic prices for testing the UI offline. Not market data."""
import zlib

import numpy as np
import pandas as pd

from indicators.daily import is_weekend


def _session_index(end: pd.Timestamp, periods: int, freq: str) -> pd.DatetimeIndex:
    """Last `periods` bars ending at `end`, skipping the FX weekend."""
    # Weekends drop ~2/7 of calendar bars; over-generate, then trim
    candidates = pd.date_range(end=end, periods=periods * 7 // 5 + 600, freq=freq)
    return candidates[~is_weekend(candidates).to_numpy()][-periods:]


def fetch_bars(symbols, api_key=None, interval="5min", outputsize=5000, batch_size=8, pages=1):
    periods = outputsize * pages
    end = pd.Timestamp.now(tz="UTC").floor("5min")
    index = _session_index(end, periods, "5min")
    bars = {}

    for s in symbols:
        rng = np.random.default_rng(zlib.crc32(s.encode()))
        drift = rng.normal(0, 0.00006)             # some symbols trend, some don't
        rets = rng.normal(drift, 0.0015, periods)
        close = 100 * np.exp(np.cumsum(rets))
        open_ = np.roll(close, 1)
        open_[0] = close[0]
        wiggle = np.abs(rng.normal(0, 0.0008, periods)) * close
        bars[s] = pd.DataFrame(
            {
                "open": open_,
                "high": np.maximum(open_, close) + wiggle,
                "low": np.minimum(open_, close) - wiggle,
                "close": close,
            },
            index=index,
        )
    return bars, {}

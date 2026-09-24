"""Synthetic prices for testing the UI offline. Not market data."""
import zlib

import numpy as np
import pandas as pd


def fetch_bars(symbols, api_key=None, interval="5min", outputsize=1200, batch_size=8):
    end = pd.Timestamp.now(tz="UTC").floor("5min")
    index = pd.date_range(end=end, periods=outputsize, freq="5min")
    bars = {}

    for s in symbols:
        rng = np.random.default_rng(zlib.crc32(s.encode()))
        drift = rng.normal(0, 0.00006)             # some symbols trend, some don't
        rets = rng.normal(drift, 0.0015, outputsize)
        close = 100 * np.exp(np.cumsum(rets))
        open_ = np.roll(close, 1)
        open_[0] = close[0]
        wiggle = np.abs(rng.normal(0, 0.0008, outputsize)) * close
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

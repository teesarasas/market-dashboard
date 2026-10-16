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


def _base_price(symbol: str) -> float:
    """Rough real-world price level, so pips and lot sizes look realistic in demo mode."""
    if symbol.startswith("XAU/"):
        return 2400.0
    return 150.0 if symbol.endswith("/JPY") else 1.2


def _path_5min(symbol: str, end: pd.Timestamp, n: int) -> pd.DataFrame:
    """n 5-minute bars ending at `end`. Generated backwards from `end`, so the recent part of the
    path is the same whatever n is (5m and 1h requests then agree with each other)."""
    rng = np.random.default_rng(zlib.crc32(symbol.encode()))
    drift = rng.normal(0, 0.00001)                  # some symbols trend, some don't
    rets_back = rng.normal(drift, 0.0004, n)        # ~0.04% per 5m bar, FX-like; [0] = latest bar
    wiggle_back = np.abs(rng.normal(0, 0.0002, n))
    log_from_end = np.concatenate([[0.0], -np.cumsum(rets_back[:-1])])
    close = (_base_price(symbol) * np.exp(log_from_end))[::-1]
    wiggle = wiggle_back[::-1] * close
    open_ = np.roll(close, 1)
    open_[0] = close[0]
    index = _session_index(end, n, "5min")
    return pd.DataFrame(
        {
            "open": open_,
            "high": np.maximum(open_, close) + wiggle,
            "low": np.minimum(open_, close) - wiggle,
            "close": close,
        },
        index=index,
    )


def fetch_bars(symbols, api_key=None, interval="5min", outputsize=5000, batch_size=8, pages=1):
    periods = outputsize * pages
    step = pd.Timedelta(interval)
    per_bar = max(1, int(step / pd.Timedelta("5min")))
    end = pd.Timestamp.now(tz="UTC").floor("5min")
    bars = {}
    for s in symbols:
        df = _path_5min(s, end, periods * per_bar)
        if per_bar > 1:
            df = df.resample(step, label="left", closed="left").agg(
                {"open": "first", "high": "max", "low": "min", "close": "last"}
            ).dropna().tail(periods)
        bars[s] = df
    return bars, {}

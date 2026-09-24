import numpy as np
import pandas as pd

import config
from indicators import trend


def _ohlc(close):
    close = np.asarray(close, dtype=float)
    idx = pd.date_range("2026-01-05", periods=len(close), freq="10min", tz="UTC")
    return pd.DataFrame(
        {"open": close, "high": close + 0.05, "low": close - 0.05, "close": close}, index=idx
    )


def test_ema_lag_flags_cross_against_ema_slope():
    n_up = 300
    up = 100 + 0.1 * np.arange(n_up)
    drop = np.full(3, up[-1] - 10)                    # sharp drop below a still-rising EMA
    out = trend.compute(_ohlc(np.concatenate([up, drop])))

    assert not out["ema_lag"].iloc[config.EMA_LENGTH:n_up].any()   # price and slope agree
    assert out["ema_lag"].iloc[-1]
    assert out["close"].iloc[-1] < out["ema"].iloc[-1]
    assert out["ema_slope_atr"].iloc[-1] > config.SLOPE_MIN_ATR


def test_ema_lag_ignores_flat_ema():
    flat = 100 + 0.02 * np.sin(np.arange(400))
    out = trend.compute(_ohlc(flat))
    assert not out["ema_lag"].any()


def test_natr_is_atr_percent_of_close():
    out = trend.compute(_ohlc(100 + 0.1 * np.arange(200)))
    last = out.iloc[-1]
    assert last["natr"] == last["atr"] / last["close"] * 100

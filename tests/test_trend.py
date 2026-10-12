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


def test_adx_regime_hysteresis():
    on, off = config.ADX_TREND_ON, config.ADX_TREND_OFF          # 30, 25
    values = [off + 2, on + 1, on - 1, off + 0.5, off - 1]
    regime = trend.adx_regime(pd.Series(values, dtype=float)).tolist()
    assert regime[0] == "neutral"       # below 30: not yet trending
    assert regime[1] == "trend"         # crossing 30 enters trend
    assert regime[2] == "trend"         # back under 30 but above 25: stays
    assert regime[3] == "trend"
    assert regime[4] != "trend"         # below 25 exits


def test_adx_regime_range_hysteresis():
    on, off = config.ADX_RANGE_ON, config.ADX_RANGE_OFF          # 20, 23
    regime = trend.adx_regime(pd.Series([on - 1, off - 0.5, off + 1], dtype=float)).tolist()
    assert regime == ["range", "range", "neutral"]


def test_di_spread_range_and_sign():
    plus = pd.Series([30.0, 10.0, 20.0, 0.0])
    minus = pd.Series([10.0, 30.0, 20.0, 0.0])
    s = trend.di_spread(plus, minus)
    assert s.iloc[0] == 50 and s.iloc[1] == -50 and s.iloc[2] == 0
    assert np.isnan(s.iloc[3])          # no movement at all


def test_di_direction_threshold():
    plus = pd.Series([30.0, 22.0, 10.0, 18.0])
    minus = pd.Series([10.0, 18.0, 30.0, 22.0])
    s = trend.di_spread(plus, minus)     # +50, +10, -50, -10
    up, down = trend.di_direction(plus, minus, s, 20)
    assert up.tolist() == [True, False, False, False]
    assert down.tolist() == [False, False, True, False]   # +-10 is too weak either way


def test_di_direction_zero_matches_old_rule():
    rng = np.random.default_rng(0)
    plus = pd.Series(rng.uniform(0, 40, 500))
    minus = pd.Series(rng.uniform(0, 40, 500))
    plus.iloc[:3] = minus.iloc[:3]                       # ties
    plus.iloc[3] = minus.iloc[3] = 0.0                   # no movement
    up, down = trend.di_direction(plus, minus, trend.di_spread(plus, minus), 0)
    old_up = plus > minus
    assert up.equals(old_up)
    assert down.equals(~old_up)


def test_weak_dominance_becomes_conflict(monkeypatch):
    monkeypatch.setattr(config, "DI_SPREAD_MIN", 101)    # impossible threshold
    out = trend.compute(_ohlc(100 + 0.1 * np.arange(400)))
    assert not out["state"].isin([trend.TREND_UP, trend.TREND_DOWN]).any()
    assert (out["state"] == trend.CONFLICT).any()

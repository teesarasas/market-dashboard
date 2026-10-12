"""Trend indicators. Pure pandas — no Streamlit — so they can be reused in backtests."""
import numpy as np
import pandas as pd

import config

TREND_UP = "Trend up"
TREND_DOWN = "Trend down"
CONFLICT = "Conflict"      # ADX says trend, but EMA side and DI spread do not clearly agree
RANGE = "Range"
NEUTRAL = "Neutral"        # between thresholds: do nothing


def wilder(series: pd.Series, length: int) -> pd.Series:
    return series.ewm(alpha=1 / length, adjust=False, min_periods=length).mean()


def true_range(df: pd.DataFrame) -> pd.Series:
    prev_close = df["close"].shift(1)
    return pd.concat(
        [
            df["high"] - df["low"],
            (df["high"] - prev_close).abs(),
            (df["low"] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)


def adx(df: pd.DataFrame, length: int):
    up = df["high"].diff()
    down = -df["low"].diff()
    plus_dm = pd.Series(np.where((up > down) & (up > 0), up, 0.0), index=df.index)
    minus_dm = pd.Series(np.where((down > up) & (down > 0), down, 0.0), index=df.index)

    atr = wilder(true_range(df), length)
    plus_di = 100 * wilder(plus_dm, length) / atr
    minus_di = 100 * wilder(minus_dm, length) / atr
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    return wilder(dx, length), plus_di, minus_di


def di_spread(plus_di: pd.Series, minus_di: pd.Series) -> pd.Series:
    """Signed DX: 100 x (+DI - -DI) / (+DI + -DI), from -100 (all down) to +100 (all up)."""
    return 100 * (plus_di - minus_di) / (plus_di + minus_di).replace(0, np.nan)


def di_direction(plus_di: pd.Series, minus_di: pd.Series, spread: pd.Series, spread_min: float):
    """(clearly up, clearly down). With spread_min = 0 this is exactly the old +DI > -DI rule."""
    up = (plus_di > minus_di) & (spread >= spread_min)
    down = ~(plus_di > minus_di) & ~(spread > -spread_min)
    return up, down


def adx_regime(adx_values: pd.Series) -> pd.Series:
    """'trend' / 'range' / 'neutral' with hysteresis."""
    regime, out = "neutral", []
    for v in adx_values:
        if np.isnan(v):
            regime = "neutral"
        elif regime == "trend":
            if v < config.ADX_TREND_OFF:
                regime = "range" if v < config.ADX_RANGE_ON else "neutral"
        elif regime == "range":
            if v > config.ADX_RANGE_OFF:
                regime = "trend" if v > config.ADX_TREND_ON else "neutral"
        else:
            if v > config.ADX_TREND_ON:
                regime = "trend"
            elif v < config.ADX_RANGE_ON:
                regime = "range"
        out.append(regime)
    return pd.Series(out, index=adx_values.index)


def compute(df: pd.DataFrame) -> pd.DataFrame:
    """Adds all indicator columns to a 10m OHLC frame."""
    out = df.copy()
    out["ema"] = out["close"].ewm(span=config.EMA_LENGTH, adjust=False).mean()
    out["atr"] = wilder(true_range(out), config.ATR_LENGTH)
    out["adx"], out["plus_di"], out["minus_di"] = adx(out, config.ADX_LENGTH)
    out["di_spread"] = di_spread(out["plus_di"], out["minus_di"])
    out["score"] = (out["close"] - out["ema"]) / out["atr"]
    out["natr"] = out["atr"] / out["close"] * 100
    out["regime"] = adx_regime(out["adx"])

    # EMA lag: price has crossed the EMA but the EMA still slopes the other way
    out["ema_slope_atr"] = (out["ema"] - out["ema"].shift(config.SLOPE_BARS)) / out["atr"]
    out["ema_lag"] = (
        (np.sign(out["close"] - out["ema"]) != np.sign(out["ema_slope_atr"]))
        & (out["ema_slope_atr"].abs() > config.SLOPE_MIN_ATR)
    )

    above = out["close"] > out["ema"]
    di_up, di_down = di_direction(out["plus_di"], out["minus_di"], out["di_spread"], config.DI_SPREAD_MIN)
    is_trend = out["regime"] == "trend"

    out["state"] = np.select(
        [
            is_trend & above & di_up,
            is_trend & ~above & di_down,
            is_trend,
            out["regime"] == "range",
        ],
        [TREND_UP, TREND_DOWN, CONFLICT, RANGE],
        default=NEUTRAL,
    )

    # EMA needs warm-up before it means anything
    out.loc[out.index[: config.EMA_LENGTH], ["score", "state", "ema_slope_atr", "ema_lag"]] = [
        np.nan, NEUTRAL, np.nan, False
    ]
    return out

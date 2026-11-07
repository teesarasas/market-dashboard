import numpy as np
import pandas as pd

from indicators import screen


def snap(rows):
    cols = ["Symbol", "State", "ADX", "DI spread", "ADR used %", "Prev-day pos %"]
    return pd.DataFrame(rows, columns=cols)


S = snap([
    ["UP_OK",    "Trend up",   32, 35, 40, 105],    # passes everything
    ["DOWN_OK",  "Trend down", 30, -28, 20, -4],    # passes everything (short side)
    ["DOWN_DI",  "Trend down", 30, 25, 20, -4],     # DI spread points the wrong way
    ["WEAK_ADX", "Trend up",   24, 35, 40, 105],    # ADX too low
    ["RANGE",    "Range",      18, 30, 20, 105],    # not a trend state
    ["HIGH_ADR", "Trend up",   32, 35, 55, 105],    # ADR used too high
    ["INSIDE",   "Trend up",   32, 35, 40, 80],     # inside yesterday's range
    ["WRONG_PD", "Trend up",   32, 35, 40, -3],     # below PDL in an uptrend
    ["MISSING",  "Trend up",   32, 35, np.nan, 105],
])


def passed(selected):
    return list(S.loc[screen.setup_mask(S, selected), "Symbol"])


def test_all_conditions():
    assert passed(screen.CONDITIONS) == ["UP_OK", "DOWN_OK"]


def test_default_trend_conditions_only():
    assert passed(["adx", "di", "trend"]) == ["UP_OK", "DOWN_OK", "HIGH_ADR", "INSIDE", "WRONG_PD", "MISSING"]


def test_single_conditions():
    assert "DOWN_DI" not in passed(["di"])                   # +25 is against a Trend down
    pd_pass = passed(["pdhl"])
    assert "INSIDE" not in pd_pass and "WRONG_PD" not in pd_pass and "UP_OK" in pd_pass
    assert "MISSING" not in passed(["adr"])                  # missing values fail


def test_no_condition_shows_everything():
    assert passed([]) == list(S["Symbol"])


def test_direction_falls_back_to_di_sign():
    d = screen.direction(S)
    assert d[S.Symbol == "RANGE"].item() == 1                # not trending: DI spread +30 -> up
    assert d[S.Symbol == "DOWN_DI"].item() == -1             # trend state wins over DI sign

import numpy as np
import pandas as pd

from indicators import screen


def snap(rows):
    cols = ["Symbol", "State", "ADX", "DI spread", "ADR used %", "Prev-day pos %"]
    df = pd.DataFrame(rows, columns=cols)
    df["H1 side"] = np.where(df["DI spread"] > 0, "Above", "Below")   # H1 agrees with the DI direction
    return df


S = snap([
    ["UP_OK",    "Trend up",   32, 35, 55, 105],    # passes everything
    ["DOWN_OK",  "Trend down", 30, -28, 60, -4],    # passes everything (short side)
    ["DOWN_DI",  "Trend down", 30, 25, 20, -4],     # DI spread points the wrong way
    ["WEAK_ADX", "Trend up",   24, 35, 40, 105],    # ADX too low
    ["RANGE",    "Range",      18, 30, 20, 105],    # not a trend state
    ["LOW_ADR",  "Trend up",   32, 35, 40, 105],    # ADR used not above 50%
    ["INSIDE",   "Trend up",   32, 35, 55, 80],     # inside yesterday's range
    ["WRONG_PD", "Trend up",   32, 35, 55, -3],     # below PDL in an uptrend
    ["MISSING",  "Trend up",   32, 35, np.nan, 105],
])


def passed(selected):
    return list(S.loc[screen.setup_mask(S, selected), "Symbol"])


def test_all_conditions():
    assert passed(screen.CONDITIONS) == ["UP_OK", "DOWN_OK"]


def test_default_trend_conditions_only():
    assert passed(["adx", "di", "trend"]) == ["UP_OK", "DOWN_OK", "LOW_ADR", "INSIDE", "WRONG_PD", "MISSING"]


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


def test_adr_above_and_h1_side():
    s = pd.DataFrame({
        "Symbol": ["UP_ABOVE", "UP_BELOW", "DOWN_BELOW", "DOWN_ABOVE", "NO_H1"],
        "State": ["Trend up", "Trend up", "Trend down", "Trend down", "Trend up"],
        "ADX": [32] * 5, "DI spread": [35, 35, -35, -35, 35],
        "ADR used %": [60, 40, 51, 50, 70], "Prev-day pos %": [50] * 5,
        "H1 side": ["Above", "Below", "Below", "Above", None],
    })
    got = lambda sel: list(s.loc[screen.setup_mask(s, sel), "Symbol"])
    assert got(["adr"]) == ["UP_ABOVE", "DOWN_BELOW", "NO_H1"]        # strictly above 50%
    assert got(["h1"]) == ["UP_ABOVE", "DOWN_BELOW"]                  # missing H1 fails

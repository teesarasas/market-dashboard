import pandas as pd
import pytest

from indicators import currency, trend


def test_parse_pair():
    assert currency.parse_pair("EUR/USD") == ("EUR", "USD")


def test_strength_decomposition_signs():
    idx = pd.date_range("2026-01-05", periods=3, freq="10min", tz="UTC")
    s = currency.strength(
        {"EUR/USD": pd.Series(2.0, index=idx), "USD/JPY": pd.Series(1.0, index=idx)}
    )
    last = s.iloc[-1]
    assert last["EUR"] == pytest.approx(2)
    assert last["JPY"] == pytest.approx(-1)
    assert last["USD"] == pytest.approx((-2 + 1) / 2)


def test_strength_forward_fills_one_bar_then_drops_thin_rows():
    idx = pd.date_range("2026-01-05", periods=4, freq="10min", tz="UTC")
    eur = pd.Series(2.0, index=idx)
    jpy = pd.Series(1.0, index=idx[:1])       # USD/JPY stops after the first bar
    s = currency.strength({"EUR/USD": eur, "USD/JPY": jpy})
    assert list(s.index) == list(idx[:2])      # bar 2 forward-filled; bars 3-4 have too few pairs
    assert s["JPY"].tolist() == [-1, -1]


def test_breadth_counts_for_and_against():
    b = currency.breadth(
        {"EUR/USD": trend.TREND_UP, "USD/JPY": trend.TREND_UP, "EUR/JPY": trend.RANGE}
    )
    assert b.loc["EUR"].to_dict() == {"in_favour": 1, "against": 0, "total": 2, "breadth": 0.5}
    assert b.loc["USD"][["in_favour", "against", "total"]].tolist() == [1, 1, 2]
    assert b.loc["JPY"][["in_favour", "against", "total"]].tolist() == [0, 1, 2]


def _bars(highs, lows):
    idx = pd.date_range("2026-01-05", periods=len(highs), freq="10min", tz="UTC")
    return pd.DataFrame({"high": highs, "low": lows}, index=idx)


def test_pair_breakouts_new_high_low_and_window():
    #       warm-up (3 bars)    new high  quiet  quiet  new low  quiet
    highs = [10, 10, 10,        11,       10.5,  10.5,  10.5,    10.5]
    lows = [9, 9, 9,            9.5,      9.5,   9.5,   8,       8.5]
    b = currency.pair_breakouts(_bars(highs, lows), lookback=3, window=2)
    assert b.iloc[:3].isna().all()             # not enough history yet
    assert b.iloc[3] == 1                      # broke the 3-bar high
    assert b.iloc[4] == 1                      # still within the 2-bar window
    assert b.iloc[5] == 0                      # window expired
    assert b.iloc[6] == -1                     # new 3-bar low
    assert b.iloc[7] == -1


def test_pair_breakouts_outside_bar_counts_as_neither():
    b = currency.pair_breakouts(_bars([10, 10, 12], [9, 9, 8]), lookback=2, window=1)
    assert b.iloc[2] == 0


def test_record_high_decomposition():
    idx = pd.date_range("2026-01-05", periods=2, freq="10min", tz="UTC")
    highs, lows, pct = currency.record_high({
        "EUR/USD": pd.Series(1.0, index=idx),     # new high: EUR up, USD down
        "USD/JPY": pd.Series(1.0, index=idx),     # new high: USD up, JPY down
        "EUR/JPY": pd.Series(0.0, index=idx),     # no breakout
    })
    last_h, last_l, last_p = highs.iloc[-1], lows.iloc[-1], pct.iloc[-1]
    assert (last_h["EUR"], last_l["EUR"], last_p["EUR"]) == (1, 0, 100)
    assert (last_h["USD"], last_l["USD"], last_p["USD"]) == (1, 1, 50)
    assert (last_h["JPY"], last_l["JPY"], last_p["JPY"]) == (0, 1, 0)


def test_record_high_empty_when_no_breakouts():
    idx = pd.date_range("2026-01-05", periods=2, freq="10min", tz="UTC")
    _, _, pct = currency.record_high({"EUR/USD": pd.Series(0.0, index=idx)})
    assert pct.isna().all().all()

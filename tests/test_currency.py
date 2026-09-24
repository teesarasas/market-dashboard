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

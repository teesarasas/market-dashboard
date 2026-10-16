import numpy as np
import pandas as pd
import pytest

from indicators import daily, risk

PRICES = {"EUR/USD": 1.10, "GBP/USD": 1.25, "USD/JPY": 150.0, "USD/CHF": 0.80, "XAU/USD": 2400.0}


def test_conversion_to_account():
    assert risk.quote_to_account("EUR/USD", PRICES) == 1.0
    assert risk.quote_to_account("EUR/GBP", PRICES) == pytest.approx(1.25)
    assert risk.quote_to_account("USD/JPY", PRICES) == pytest.approx(1 / 150)
    assert risk.quote_to_account("EUR/CHF", PRICES) == pytest.approx(1 / 0.80)
    assert risk.quote_to_account("EUR/USD", PRICES, account="EUR") == pytest.approx(1 / 1.10)


# Hand-checked examples: $100,000 account, 0.25% risk = $250
@pytest.mark.parametrize("vendor, entry, stop, lots", [
    ("EUR/USD", 1.1000, 1.0975, 1.00),    # 25 pips x $10/pip = $250 per lot
    ("USD/JPY", 150.00, 149.50, 0.75),    # 50 pips x $6.667/pip = $333.33 per lot -> 0.75
    ("EUR/GBP", 0.8700, 0.8680, 1.00),    # 20 pips x GBP10 x 1.25 = $250 per lot
    ("XAU/USD", 2400.0, 2390.0, 0.25),    # $10 x 100 oz = $1,000 per lot
])
def test_lot_size_examples(vendor, entry, stop, lots):
    per_unit = risk.money_per_unit(vendor, PRICES)
    res = risk.size_position(250, entry, stop, per_unit)
    assert res["lots"] == pytest.approx(lots)
    assert res["risk"] <= 250 + 1e-9


def test_rounds_down_never_over_risk():
    res = risk.size_position(250, 1.1000, 1.0967, risk.money_per_unit("EUR/USD", PRICES))  # 33 pips
    assert res["raw_lots"] == pytest.approx(0.7576, abs=1e-4)
    assert res["lots"] == pytest.approx(0.75)
    assert res["risk"] == pytest.approx(247.5)


def test_short_trade_and_exact_step():
    res = risk.size_position(250, 1.0975, 1.1000, risk.money_per_unit("EUR/USD", PRICES))
    assert res["lots"] == pytest.approx(1.00)       # float noise must not round 1.00 down to 0.99


def test_below_min_lot_is_zero():
    res = risk.size_position(5, 2400.0, 2300.0, risk.money_per_unit("XAU/USD", PRICES))
    assert res["lots"] == 0.0 and res["risk"] == 0.0


def test_stop_side_and_targets():
    assert risk.stop_on_correct_side("Long", 1.10, 1.09)
    assert not risk.stop_on_correct_side("Long", 1.10, 1.11)
    assert risk.stop_on_correct_side("Short", 1.10, 1.11)
    t = risk.targets(1.1000, 1.0975, [1, 2])
    assert t[1] == pytest.approx(1.1025) and t[2] == pytest.approx(1.1050)
    t = risk.targets(1.0975, 1.1000, [1])
    assert t[1] == pytest.approx(1.0950)


def test_pips_and_decimals():
    assert risk.pip_size("EUR/USD") == 0.0001
    assert risk.pip_size("GBP/JPY") == 0.01
    assert risk.pip_size("XAU/USD") == 0.1
    assert risk.price_decimals("EUR/USD") == 5
    assert risk.price_decimals("USD/JPY") == 3
    assert risk.price_decimals("XAU/USD") == 2


def test_rma_seeded_with_simple_mean():
    s = pd.Series([2.0, 4.0, 6.0, 8.0])
    r = risk.rma(s, 3)
    assert np.isnan(r.iloc[1])
    assert r.iloc[2] == pytest.approx(4.0)                 # mean of 2, 4, 6
    assert r.iloc[3] == pytest.approx((4.0 * 2 + 8.0) / 3)


def _days_of_bars(n_days, open_today=100.0):
    """n_days FX trading days of 10m bars; every day high 101, low 99, close 100 (TR = 2)."""
    idx = pd.date_range("2026-03-01 22:00", periods=n_days * 7 // 5 * 144 + 400, freq="10min", tz="UTC")
    idx = idx[~daily.is_weekend(idx).to_numpy()]
    days = daily.trading_day(idx)
    keep = days.isin(days.unique()[:n_days]).to_numpy()
    idx = idx[keep]
    df = pd.DataFrame({"open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0}, index=idx)
    last_day = daily.trading_day(idx) == daily.trading_day(idx).iloc[-1]
    first_bar_today = last_day.to_numpy().argmax()
    df.iloc[first_bar_today, df.columns.get_loc("open")] = open_today
    return df


def test_distribution_levels():
    d = risk.distribution(_days_of_bars(20, open_today=100.5))
    assert d["atr"] == pytest.approx(2.0)
    assert d["open"] == pytest.approx(100.5)
    assert d["levels"][1] == pytest.approx(102.5)
    assert d["levels"][-2] == pytest.approx(96.5)
    assert sorted(d["levels"]) == [-3, -2, -1, 1, 2, 3]


def test_distribution_needs_enough_days():
    assert risk.distribution(_days_of_bars(10)) is None

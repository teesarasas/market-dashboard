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


def _days(rows, start="2026-03-02"):
    """rows: [(open, high, low, close)] -> daily frame indexed by consecutive dates."""
    idx = pd.date_range(start, periods=len(rows), freq="D")
    return pd.DataFrame(rows, index=idx, columns=["open", "high", "low", "close"])


def _steady(n, up=1.0, down=1.5, close=100.0):
    """Day 0 (dropped as possibly partial) + n days that each go `up` above and `down` below the prior close."""
    return [(close, close, close, close)] + [(close, close + up, close - down, close)] * n


def test_distribution_constant_volatility_equals_plain_percentiles():
    rows = _steady(60) + [(100.2, 100.5, 99.9, 100.3)]           # last row = today, still forming
    days = _days(rows)
    d = risk.distribution(days, today=days.index[-1], percentiles=[50, 90], scale_days=20, min_sample=20)
    assert d["atr"] == pytest.approx(2.5)                       # true range 1 + 1.5 every day
    assert d["anchor"] == pytest.approx(100)                    # yesterday's close, not today's price
    assert d["levels"]["Up P90"] == pytest.approx(101)          # 0.4 ATR x 2.5
    assert d["levels"]["Down P50"] == pytest.approx(98.5)       # 0.6 ATR x 2.5
    assert list(d["levels"]) == ["Up P90", "Up P50", "Anchor", "Down P50", "Down P90"]
    assert d["n"] == 60 - 20                                    # first 20 measured days have no ATR yet


def test_distribution_scales_to_current_volatility():
    # 60 calm days, then 20 days twice as wide: same shape in ATRs, so the bands double
    rows = _steady(60) + _steady(20, up=2.0, down=3.0)[1:]
    days = _days(rows)
    d = risk.distribution(days, today=days.index[-1] + pd.Timedelta(days=1), percentiles=[50], scale_days=20,
                          min_sample=20)
    assert d["atr"] == pytest.approx(5.0)
    assert d["up"][50] == pytest.approx(2.0)
    assert d["down"][50] == pytest.approx(3.0)


def test_distribution_matches_reference_loop():
    rng = np.random.default_rng(7)
    n = 160
    closes = 100 + rng.normal(0, 1, n).cumsum()
    rows = [(c, c + abs(a), c - abs(b), c) for c, a, b in zip(closes, rng.normal(0, 1, n), rng.normal(0, 1.3, n))]
    days = _days(rows)
    today = days.index[-1]
    d = risk.distribution(days, today=today, lookback=100, percentiles=[25, 90], scale_days=20)
    # independent reference: complete days 1..n-2, TR from day 1, ATR = mean TR of the 20 days before
    H, L, C = days["high"].to_numpy(), days["low"].to_numpy(), days["close"].to_numpy()
    m = n - 1                                                   # rows before today
    tr = [np.nan] + [max(H[k] - L[k], abs(H[k] - C[k - 1]), abs(L[k] - C[k - 1])) for k in range(1, m)]
    ups, dns = [], []
    for s in range(1, m):
        window = tr[s - 20:s]
        if s - 20 < 1:
            continue
        a = np.mean(window)
        ups.append((H[s] - C[s - 1]) / a)
        dns.append((C[s - 1] - L[s]) / a)
    ups, dns = ups[-100:], dns[-100:]
    atr_now = np.mean(tr[m - 20:m])
    assert d["n"] == 100
    assert d["atr"] == pytest.approx(atr_now)
    assert d["up"][25] == pytest.approx(np.percentile(ups, 25) * atr_now)
    assert d["down"][90] == pytest.approx(np.percentile(dns, 90) * atr_now)


def test_distribution_open_anchor_measures_from_each_days_open():
    rows = [(100, 100, 100, 100)] + [(100.5, 101, 98.5, 100)] * 40 + [(102.0, 102.1, 101.9, 102)]
    days = _days(rows)
    d = risk.distribution(days, today=days.index[-1], percentiles=[50], anchor="open", scale_days=20,
                          min_sample=20)
    assert d["anchor"] == pytest.approx(102.0)                  # today's open
    assert d["up"][50] == pytest.approx(0.5)                    # 101 - 100.5, from the day's own open
    assert d["down"][50] == pytest.approx(2.0)                  # 100.5 - 98.5


def test_distribution_weekend_and_min_sample():
    days = _days(_steady(45))
    saturday = days.index[-1] + pd.Timedelta(days=1)            # market closed: every row is complete
    d = risk.distribution(days, today=saturday, percentiles=[50], scale_days=20, min_sample=20)
    assert d["n"] == 45 - 20
    assert risk.distribution(days, today=saturday, scale_days=20, min_sample=30) is None


def test_daily_atr_complete_days_only():
    rows = [(100, 100, 100, 100)] + [(100, 101, 99, 100)] * 20 + [(100, 110, 90, 100)]  # today is wild
    days = _days(rows)
    assert risk.daily_atr(days, today=days.index[-1], length=14) == pytest.approx(2.0)


def test_current_trading_day_rolls_at_1700_new_york():
    before = pd.Timestamp("2026-07-15 16:59", tz="America/New_York").tz_convert("UTC")
    after = pd.Timestamp("2026-07-15 17:00", tz="America/New_York").tz_convert("UTC")
    assert risk.current_trading_day(after) - risk.current_trading_day(before) == pd.Timedelta(days=1)

import numpy as np
import pandas as pd
import pytest

import config
from indicators import daily

NY = config.DAY_ROLLOVER_TZ


def ny(ts: str) -> pd.Timestamp:
    return pd.Timestamp(ts, tz=NY).tz_convert("UTC")


def bars(rows):
    """rows: [(NY time string, open, high, low, close)] -> UTC-indexed OHLC frame."""
    idx = pd.DatetimeIndex([ny(r[0]) for r in rows])
    return pd.DataFrame([r[1:] for r in rows], index=idx, columns=["open", "high", "low", "close"])


@pytest.mark.parametrize("date", ["2026-07-15", "2026-01-14"])  # summer (EDT) and winter (EST)
def test_trading_day_rolls_over_at_1700_new_york(date):
    idx = pd.DatetimeIndex([ny(f"{date} 16:50"), ny(f"{date} 17:00")])
    days = daily.trading_day(idx)
    assert days.iloc[0] != days.iloc[1]
    assert days.iloc[1] - days.iloc[0] == pd.Timedelta(days=1)


def test_is_weekend_between_friday_and_sunday_rollovers():
    idx = pd.DatetimeIndex(
        [ny("2026-01-16 16:50"), ny("2026-01-16 17:00"), ny("2026-01-18 16:50"), ny("2026-01-18 17:00")]
    )
    assert daily.is_weekend(idx).tolist() == [False, True, True, False]


def _days_with_ranges(ranges):
    """One trading day per range (weekdays only), two bars each; day k spans 100..100+range."""
    dates = pd.bdate_range("2026-01-05", periods=len(ranges))
    rows = []
    for d, r in zip(dates, ranges):
        rows.append((f"{d:%Y-%m-%d} 03:00", 100, 100 + r, 100, 100 + r / 2))
        rows.append((f"{d:%Y-%m-%d} 10:00", 100, 100 + r / 2, 100, 100 + r / 2))
    return bars(rows)


def test_adr_excludes_today_and_partial_first_day(monkeypatch):
    monkeypatch.setattr(config, "ADR_DAYS", 3)
    # day 0 = partial first day, day 5 = today; both have huge ranges that must be ignored
    ranges = [50, 1, 2, 3, 4, 40]
    out = daily.compute(_days_with_ranges(ranges))
    adr_by_day = out.groupby(daily.trading_day(out.index))["adr"].last()

    assert np.isnan(adr_by_day.iloc[3])            # would need day 0, which is incomplete
    assert adr_by_day.iloc[4] == pytest.approx(np.mean([1, 2, 3]))
    assert adr_by_day.iloc[5] == pytest.approx(np.mean([2, 3, 4]))  # today excluded
    # ADR used = today's range so far / ADR
    assert out["adr_used"].iloc[-1] == pytest.approx(40 / 3 * 100)


@pytest.mark.parametrize(
    "close, zone, pos",
    [
        (110, daily.INSIDE, 100),     # at PDH
        (100, daily.INSIDE, 0),       # at PDL
        (105, daily.INSIDE, 50),
        (111, daily.ABOVE_PDH, 110),
        (99, daily.BELOW_PDL, -10),
    ],
)
def test_prev_day_zone(close, zone, pos):
    df = bars(
        [
            ("2026-01-06 03:00", 100, 110, 100, 105),   # previous day: PDH 110, PDL 100
            ("2026-01-07 03:00", close, close, close, close),
        ]
    )
    last = daily.compute(df).iloc[-1]
    assert last["pdh"] == 110 and last["pdl"] == 100
    assert last["prev_day_zone"] == zone
    assert last["prev_day_pos"] == pytest.approx(pos)

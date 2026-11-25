import numpy as np
import pandas as pd

from indicators import replay
from research import replay as runner

T0 = pd.Timestamp("2026-11-24 03:02", tz="UTC")          # Tuesday


def path(rows, start=T0.ceil("5min")):
    """rows: list of (open, high, low, close)."""
    idx = pd.date_range(start, periods=len(rows), freq="5min")
    return pd.DataFrame(rows, columns=["open", "high", "low", "close"], index=idx)


def test_target_stop_and_ambiguous_bar():
    p = path([(1.0, 1.004, 0.999, 1.003), (1.003, 1.012, 1.002, 1.011)])
    r = replay.simulate(p, True, 1.0, 0.995, 1.01)
    assert r.reason == "TP" and r.exit_price == 1.01 and r.exit_time == p.index[1]
    both = path([(1.0, 1.02, 0.99, 1.0)])
    r = replay.simulate(both, True, 1.0, 0.995, 1.01)
    assert r.reason == "SL" and r.ambiguous                         # pessimistic
    short = replay.simulate(path([(1.0, 1.006, 0.999, 1.005)]), False, 1.0, 1.005, 0.99)
    assert short.reason == "SL" and short.exit_price == 1.005


def test_gap_through_stop_fills_at_open():
    r = replay.simulate(path([(1.0, 1.001, 0.999, 1.0), (0.990, 0.991, 0.985, 0.986)]), True, 1.0, 0.995, 1.02)
    assert r.reason == "SL" and r.exit_price == 0.990


def test_breakeven_and_trailing():
    p = path([(1.0, 1.006, 0.999, 1.005), (1.005, 1.005, 0.998, 0.999)])     # +1.2R then back below entry
    be = replay.simulate(p, True, 1.0, 0.995, 1.02, breakeven_at=0.005)
    assert be.reason == "BE" and be.exit_price == 1.0
    tr = replay.simulate(path([(1.0, 1.01, 0.999, 1.009), (1.009, 1.010, 1.004, 1.005)]),
                         True, 1.0, 0.995, None, trail=0.004)
    assert tr.reason == "Trail" and np.isclose(tr.exit_price, 1.006)        # 1.010 best - 0.004


def test_time_exit_and_horizon_ends_friday():
    r = replay.simulate(path([(1.0, 1.001, 0.999, 1.0005)]), True, 1.0, 0.99, 1.02)
    assert r.reason == "Time" and r.exit_price == 1.0005
    end = replay.horizon_end(pd.Timestamp("2026-11-26 03:00", tz="UTC"))     # Thursday
    assert end.tz_convert("America/New_York").strftime("%a %H:%M") == "Fri 16:50"


def test_excursions_and_r():
    p = path([(1.0, 1.004, 0.997, 1.003), (1.003, 1.008, 1.001, 1.007)])
    mae, mfe = replay.excursions(p, True, 1.0, 0.005, until=p.index[0])
    assert np.isclose(mae, 0.6) and np.isclose(mfe, 0.8)
    res = replay.Result(1.01, "TP", False, p.index[1])
    assert np.isclose(replay.r_multiple(res, True, 1.0, 0.005), 2.0)


def test_variants_scale_r_by_their_own_stop():
    v = replay.variants({"long": True, "entry": 1.0, "sl": 0.995, "tp": 1.01, "atr_day": 0.02,
                         "bands": {"Up P50": 1.004, "Up P75": 1.008, "Up P90": 0.999}})
    stop, target, _, _, risk = v["Stop x2, same TP"]
    assert np.isclose(stop, 0.99) and np.isclose(risk, 0.01)
    assert "Target band P90" not in v                                          # band behind the entry
    assert np.isclose(v["No TP, trail 0.5 ATR"][3], 0.01)


def test_runner_end_to_end():
    snap = {"atr_day": 0.02, "bands": {"Up P75": 1.008}}
    trades = pd.DataFrame([
        {"pair": "EURUSD", "side": "Long", "entry": 1.0, "sl": 0.995, "tp": 1.01, "r_result": 2.0,
         "entry_time": T0, "exit_time": T0 + pd.Timedelta(minutes=13), "exit_reason": "TP hit", "snapshot": snap},
        {"pair": "EURUSD", "side": "Long", "entry": 1.0, "sl": 0.995, "tp": 1.01, "r_result": -1.0,
         "entry_time": T0, "exit_time": T0 + pd.Timedelta(minutes=8), "exit_reason": "SL hit", "snapshot": snap},
    ])
    bars = path([(1.0, 1.003, 0.998, 1.002), (1.002, 1.011, 1.001, 1.01)])
    per, long = runner.run(trades, {"EURUSD": bars})
    assert len(per) == 2 and set(long["rule"]) >= {"Actual SL/TP", "Target 2R", "Breakeven after +1R"}
    assert (per["Actual SL/TP | exit"] == "TP").all()          # both replays hit TP: second log disagrees
    table = replay.summarise(long)
    assert table.loc["Actual SL/TP", "win %"] == 100
    runner.report(per, long)                                   # prints without errors

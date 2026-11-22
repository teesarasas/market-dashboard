import numpy as np
import pandas as pd
import pytest

import config
from bot import run, store, telegram
from indicators import signals

NOW = pd.Timestamp("2026-11-24 07:21", tz="UTC")     # Tuesday, a minute after the 07:10 bar closed


def frame(passing, n=40):
    """Indicator-like frame of n 10m bars ending with the bar that closed just before NOW, plus one forming bar.
    passing: list of bools for the closed bars (aligned to the end)."""
    idx = pd.date_range(end=NOW.floor("10min"), periods=n + 1, freq="10min")   # last label = forming bar
    ok = np.zeros(n + 1, bool)
    ok[n - len(passing):n] = passing
    ok[-1] = True                                                               # forming bar always "passes"
    return pd.DataFrame({
        "close": 1.1, "ema_h1": 1.09, "state": np.where(ok, "Trend up", "Range"),
        "adx": np.where(ok, 32.0, 18.0), "di_spread": 40.0, "adr_used": 60.0, "prev_day_pos": 80.0,
        "score": 3.0, "natr": 0.05, "atr": 0.001, "adr": 0.008,
        "open": 1.1, "high": 1.101, "low": 1.099,
    }, index=idx)


ALL = config.SIGNAL_ALERT_CONDITIONS


def test_start_on_last_closed_bar_ignores_forming_bar():
    ind = frame([False] * 6 + [True])
    assert signals.starts(ind, NOW, ALL, 6, 2) == [ind.index[-2]]


def test_no_repeat_while_passing_and_cooldown():
    assert signals.starts(frame([False] * 6 + [True, True]), NOW, ALL, 6, 1) == []          # still passing
    blip = [False] * 6 + [True] + [False] * 3 + [True]                                     # failed only 3 bars
    assert signals.starts(frame(blip), NOW, ALL, 6, 1) == []
    gap = [False] * 6 + [True] + [False] * 6 + [True]                                      # failed 6 bars
    assert signals.starts(frame(gap), NOW, ALL, 6, 1) != []


def test_lookback_catches_a_missed_run_and_stale_data_is_ignored():
    ind = frame([False] * 6 + [True, True])
    assert signals.starts(ind, NOW, ALL, 6, 2) == [ind.index[-3]]
    assert signals.starts(ind, NOW + pd.Timedelta(hours=2), ALL, 6, 2) == []


def test_extra_conditions_block_alert_not_setup():
    ind = frame([False] * 6 + [True])
    ind["ema_h1"] = 1.2                                    # price below the H1 EMA in an uptrend
    assert signals.starts(ind, NOW, config.SIGNAL_RECORD_CONDITIONS, 6, 1) != []
    assert signals.starts(ind, NOW, ALL, 6, 1) == []


def test_message_shows_checks_and_open_trade_warning():
    ind = frame([False] * 6 + [True])
    info = signals.describe("EURUSD", "EUR/USD", ind, ind.index[-2], {"EUR": {"rank": 2}, "USD": {"rank": 7}})
    warn = signals.rule_warnings(info, {"open": [("GBPUSD", "Long"), ("USDJPY", "Long")], "trades_today": 4,
                                        "loss_today_pct": 1.05}, {"GBPUSD": "GBP/USD", "USDJPY": "USD/JPY"})
    text = signals.message(info, warn)
    assert text.startswith("🟢 LONG EURUSD")
    assert "closed 14:20 (Bangkok)" in text                       # 07:10 UTC bar closes 07:20 UTC = 14:20 BKK
    assert "✅ H1 above EMA120" in text and "✅ Score +3.0" in text and "EUR #2 vs USD #7" in text
    assert "⚠️ Open trades: 2 of 2" in text
    assert "Same bet as your open GBPUSD long: both short USD" in text      # EURUSD long also sells USD
    assert "USDJPY" not in text                                              # USDJPY long buys USD: opposite bet
    assert "Trades today: 4 of 4" in text and "daily stop is hit" in text


def test_rule_warnings_quiet_when_all_fine_and_unknown_log():
    info = {"symbol": "XAUUSD", "bought": "XAU", "sold": "USD"}
    assert signals.rule_warnings(info, {"open": [], "trades_today": 1, "loss_today_pct": 0.3}, {}) == [
        "Open trades: 0 of 2"]
    assert signals.rule_warnings(info, {"open": None}, {}) == ["Open trades: unknown (trade log unreachable)"]
    # gold long and an open EURUSD long are the same USD-short bet
    w = signals.rule_warnings(info, {"open": [("EURUSD", "Long")], "trades_today": 1, "loss_today_pct": 0},
                              {"EURUSD": "EUR/USD"})
    assert any("both short USD" in x for x in w)


def test_rollover_pause():
    ny = lambda s: pd.Timestamp(s, tz="America/New_York").tz_convert("UTC")
    assert signals.in_rollover_pause(ny("2026-11-24 16:40"))       # closes 16:50 NY
    assert signals.in_rollover_pause(ny("2026-11-24 17:40"))       # closes 17:50
    assert not signals.in_rollover_pause(ny("2026-11-24 17:50"))   # closes 18:00
    assert not signals.in_rollover_pause(ny("2026-11-24 16:30"))   # closes 16:40


def test_account_status_counts_today_only(monkeypatch, tmp_path):
    from data import tradelog
    log = tradelog.CsvLog(str(tmp_path / "t.csv"))
    base = {"pair": "EURUSD", "side": "Long", "entry": 1.1, "sl": 1.09, "balance": 100_000, "tags": [], "snapshot": {}}
    log.add({**base, "status": "closed", "entry_time": "2026-11-24T02:00:00+00:00", "pnl": -600.0})
    log.add({**base, "status": "closed", "entry_time": "2026-11-24T03:00:00+00:00", "pnl": -500.0})
    log.add({**base, "status": "open", "pair": "GBPUSD", "entry_time": "2026-11-24T06:00:00+00:00"})
    log.add({**base, "status": "closed", "entry_time": "2026-11-23T20:00:00+00:00", "pnl": -900.0})  # yesterday
    log.add({**base, "status": "skipped", "entry_time": "2026-11-24T05:00:00+00:00"})
    monkeypatch.setattr(tradelog, "get_log", lambda: (log, None))
    acc = run.account_status(NOW)
    assert acc["open"] == [("GBPUSD", "Long")] and acc["trades_today"] == 3
    assert abs(acc["loss_today_pct"] - 1.1) < 1e-9


class FakeTelegram:
    def __init__(self):
        self.sent = []

    def __call__(self, token, chat, text, http=None):
        self.sent.append(text)


def test_run_sends_once_and_records(monkeypatch, tmp_path):
    ind_bars = {"EURUSD": frame([False] * 6 + [True], n=200)}
    monkeypatch.setattr(config, "DATA_PROVIDER", "demo")
    monkeypatch.setattr(config, "SIGNAL_DEMO_FILE", str(tmp_path / "s.csv"))
    monkeypatch.setattr(run.fetch, "fetch_10m", lambda p, g: (ind_bars, {}, NOW))
    # skip indicator maths: the frame already has the indicator columns
    monkeypatch.setattr(run, "find_events", lambda bars, now: [
        {"kind": k, **signals.describe("EURUSD", "EUR/USD", bars["EURUSD"], bars["EURUSD"].index[-2], {})}
        for k in ("setup", "alert")])
    monkeypatch.setattr(run, "account_status", lambda now: {"open": [("USDJPY", "Short")], "trades_today": 1,
                                                             "loss_today_pct": 0.0})
    fake = FakeTelegram()
    monkeypatch.setattr(telegram, "send", fake)
    assert run.main([], now=NOW) == 0
    assert len(fake.sent) == 1 and "Open trades: 1 of 2" in fake.sent[0]
    saved = pd.read_csv(tmp_path / "s.csv")
    assert sorted(saved["kind"]) == ["alert", "setup"] and saved.loc[saved.kind == "alert", "sent"].item()
    assert run.main([], now=NOW) == 0                      # second run: already recorded, nothing sent
    assert len(fake.sent) == 1 and len(pd.read_csv(tmp_path / "s.csv")) == 2


def test_weekend_skips_fetch(monkeypatch):
    def boom(*a):
        raise AssertionError("should not fetch on the weekend")
    monkeypatch.setattr(run.fetch, "fetch_10m", boom)
    assert run.main([], now=pd.Timestamp("2026-11-28 12:00", tz="UTC")) == 0     # Saturday


def test_quiet_hours(monkeypatch):
    monkeypatch.setattr(config, "SIGNAL_QUIET_HOURS", (1, 7))
    assert run.quiet(pd.Timestamp("2026-11-24 20:30", tz="UTC"))       # 03:30 Bangkok
    assert not run.quiet(pd.Timestamp("2026-11-24 03:00", tz="UTC"))   # 10:00 Bangkok


def test_telegram_errors_hide_the_token():
    class Boom:
        def post(self, url, **kw):
            import requests
            raise requests.ConnectionError(f"cannot reach {url}")
    with pytest.raises(telegram.TelegramError) as e:
        telegram.send("123:SECRET", "42", "hi", http=Boom())
    assert "SECRET" not in str(e.value)


def test_supabase_known_and_add():
    calls = []

    class Resp:
        def __init__(self, data):
            self.status_code, self._d = 200, data
            self.text = "x" if data is not None else ""

        def json(self):
            return self._d

    class Http:
        def request(self, method, url, params=None, json=None, headers=None, timeout=None):
            calls.append((method, params, json, headers.get("Prefer")))
            return Resp([{"symbol": "EURUSD", "bar_time": "2026-11-24T07:10:00+00:00", "kind": "alert"}]
                        if method == "GET" else None)

    s = store.SupabaseSignals("https://x.supabase.co", "sb_secret_abc", http=Http())
    assert s.known(NOW) == {("EURUSD", pd.Timestamp("2026-11-24 07:10", tz="UTC"), "alert")}
    s.add([{"kind": "setup"}])
    assert calls[-1][0] == "POST" and calls[-1][3] == "return=minimal"

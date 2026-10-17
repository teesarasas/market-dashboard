import json

import numpy as np
import pandas as pd
import pytest

from data import tradelog
from indicators import journal


def utc(s):
    return pd.Timestamp(s, tz="UTC")


@pytest.mark.parametrize("ts, name", [
    ("2026-10-16 03:00", "Asia"), ("2026-10-16 08:00", "London"), ("2026-10-16 13:30", "London/NY overlap"),
    ("2026-10-16 18:00", "New York"), ("2026-10-16 22:00", "Late"),
])
def test_session_name(ts, name):
    assert journal.session_name(utc(ts)) == name


def test_band_position():
    lv = {"Down P50": 1.0950, "Anchor": 1.1000, "Up P25": 1.1020, "Up P90": 1.1080}
    assert journal.band_position(1.1010, lv) == "Anchor – Up P25"
    assert journal.band_position(1.0900, lv) == "below Down P50"
    assert journal.band_position(1.1100, lv) == "above Up P90"
    assert journal.band_position(1.1000, {}) is None


def test_trade_result_long_and_short():
    assert journal.trade_result("Long", 1.1000, 1.0975, 1.1050, 250) == pytest.approx((2.0, 500.0))
    assert journal.trade_result("Long", 1.1000, 1.0975, 1.0975, 250) == pytest.approx((-1.0, -250.0))
    assert journal.trade_result("Short", 150.00, 150.50, 149.25, 200) == pytest.approx((1.5, 300.0))


def test_clean_makes_json_safe():
    out = journal.clean({"a": np.float64(1.5), "b": np.nan, "c": np.int64(3), "d": np.bool_(True),
                         "e": utc("2026-10-16 03:00"), "f": [np.float32(2.0), None], "g": {"h": np.inf}})
    assert out == {"a": 1.5, "b": None, "c": 3, "d": True, "e": "2026-10-16T03:00:00+00:00",
                   "f": [2.0, None], "g": {"h": None}}
    json.dumps(out)


ROW = {"status": "open", "entry_time": "2026-10-16T03:00:00+00:00", "pair": "EURUSD", "side": "Long",
       "entry": 1.1, "sl": 1.0975, "tp": 1.105, "tp_choice": "2R", "lots": 1.0, "balance": 100000.0,
       "risk_pct": 0.25, "risk_money": 250.0, "stop_method": "distribution", "stop_band": "Down P50",
       "tags": ["Breakout", "Pullback"], "note": None, "snapshot": {"adx": 31.2, "state": "Trend up"}}


def test_csv_log_roundtrip(tmp_path):
    log = tradelog.CsvLog(str(tmp_path / "log.csv"))
    tid = log.add(ROW)
    log.add(dict(ROW, status="skipped", pair="GBPUSD"))
    open_ = log.open_trades()
    assert list(open_["id"]) == [tid]
    assert open_.iloc[0]["tags"] == ["Breakout", "Pullback"]
    assert open_.iloc[0]["snapshot"]["state"] == "Trend up"
    log.close(tid, {"status": "closed", "exit_price": 1.105, "r_result": 2.0, "exit_reason": "TP hit"})
    assert log.open_trades().empty
    recent = log.recent()
    assert set(recent["status"]) == {"closed", "skipped"}
    assert recent.set_index("id").loc[tid, "r_result"] == 2.0
    with pytest.raises(tradelog.TradeLogError):
        log.close("no-such-id", {"status": "closed"})


class FakeResponse:
    def __init__(self, status, payload):
        self.status_code, self._payload = status, payload
        self.text = json.dumps(payload)

    def json(self):
        return self._payload


class FakeSession:
    def __init__(self, responses):
        self.calls, self.responses = [], list(responses)

    def request(self, method, url, params=None, json=None, headers=None, timeout=None):
        self.calls.append(dict(method=method, url=url, params=params, json=json, headers=headers))
        return self.responses.pop(0)


def test_supabase_new_key_goes_only_in_apikey_header():
    s = FakeSession([FakeResponse(201, [{"id": "abc-123"}])])
    log = tradelog.SupabaseLog("https://proj.supabase.co/", "sb_secret_xyz", session=s)
    assert log.add(ROW) == "abc-123"
    call = s.calls[0]
    assert call["method"] == "POST"
    assert call["url"] == "https://proj.supabase.co/rest/v1/trades"
    assert call["headers"]["apikey"] == "sb_secret_xyz"
    assert "Authorization" not in call["headers"]
    assert call["headers"]["Prefer"] == "return=representation"
    assert call["json"]["tags"] == ["Breakout", "Pullback"]


def test_supabase_legacy_key_also_sends_bearer():
    s = FakeSession([FakeResponse(200, [])])
    log = tradelog.SupabaseLog("https://proj.supabase.co", "eyJhbGciOi.legacy", session=s)
    assert log.open_trades().empty
    call = s.calls[0]
    assert call["headers"]["Authorization"] == "Bearer eyJhbGciOi.legacy"
    assert call["params"] == {"status": "eq.open", "order": "entry_time.desc"}


def test_supabase_close_and_errors():
    s = FakeSession([FakeResponse(200, [{"id": "abc"}]), FakeResponse(200, []),
                     FakeResponse(401, {"message": "Invalid API key"})])
    log = tradelog.SupabaseLog("https://proj.supabase.co", "sb_secret_xyz", session=s)
    log.close("abc", {"status": "closed"})
    assert s.calls[0]["method"] == "PATCH" and s.calls[0]["params"] == {"id": "eq.abc"}
    with pytest.raises(tradelog.TradeLogError, match="updated 0"):
        log.close("missing", {"status": "closed"})
    with pytest.raises(tradelog.TradeLogError, match="401"):
        log.ping()


def test_get_log_demo_and_unconfigured(monkeypatch):
    import config
    monkeypatch.setattr(config, "DATA_PROVIDER", "demo")
    log, problem = tradelog.get_log()
    assert isinstance(log, tradelog.CsvLog) and problem is None
    monkeypatch.setattr(config, "DATA_PROVIDER", "twelvedata")
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_KEY", raising=False)
    log, problem = tradelog.get_log()
    assert log is None and "SUPABASE_URL" in problem
    monkeypatch.setenv("SUPABASE_URL", "https://proj.supabase.co")
    monkeypatch.setenv("SUPABASE_KEY", "sb_secret_xyz")
    log, problem = tradelog.get_log()
    assert isinstance(log, tradelog.SupabaseLog)

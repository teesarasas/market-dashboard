import config
from data import fetch


def test_load_all_uses_group_pages(monkeypatch):
    calls = {}

    def fake_fetch(symbols, api_key=None, interval="5min", outputsize=5000, batch_size=8, pages=1):
        calls[pages] = list(symbols)
        return {}, {}

    monkeypatch.setitem(fetch.PROVIDERS, "fake", type("P", (), {"fetch_bars": staticmethod(fake_fetch)}))
    fetch.load_all.clear()
    fetch.load_all("fake")

    crosses = set(config.SYMBOLS["Gold crosses"].values())
    assert set(calls[1]) == crosses
    assert not crosses & set(calls[config.SOURCE_PAGES])
    assert "XAU/USD" in calls[config.SOURCE_PAGES]


def test_silver_removed():
    vendors = {v for items in config.SYMBOLS.values() for v in items.values()}
    assert not any(v.startswith("XAG") for v in vendors)

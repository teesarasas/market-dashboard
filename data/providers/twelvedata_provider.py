"""Twelve Data adapter. Returns raw OHLC bars in UTC, oldest first."""
import time

import pandas as pd
import requests

BASE_URL = "https://api.twelvedata.com/time_series"


def _parse(payload: dict) -> pd.DataFrame:
    df = pd.DataFrame(payload["values"])
    df["datetime"] = pd.to_datetime(df["datetime"], utc=True)
    df = df.set_index("datetime").sort_index()
    cols = ["open", "high", "low", "close"]
    return df[cols].astype(float)


def _fetch_batch(batch, api_key, interval, outputsize, end_date=None):
    """One request for up to batch_size symbols. Returns (bars, errors)."""
    bars, errors = {}, {}
    params = {
        "symbol": ",".join(batch),
        "interval": interval,
        "outputsize": outputsize,
        "timezone": "UTC",
        "apikey": api_key,
    }
    if end_date is not None:
        params["end_date"] = end_date.strftime("%Y-%m-%d %H:%M:%S")

    for attempt in range(3):
        resp = requests.get(BASE_URL, params=params, timeout=30)
        data = resp.json()
        # Per-minute credit limit hit: wait and retry
        if isinstance(data, dict) and data.get("code") == 429:
            time.sleep(20 * (attempt + 1))
            continue
        break

    # A single-symbol request is not keyed by symbol; normalise it
    if len(batch) == 1:
        data = {batch[0]: data}

    # Whole-request error (bad key, etc.)
    if data.get("status") == "error" and "code" in data:
        for s in batch:
            errors[s] = data.get("message", "request failed")
        return bars, errors

    for s in batch:
        item = data.get(s)
        if not item or item.get("status") == "error" or "values" not in item:
            errors[s] = (item or {}).get("message", "no data returned")
            continue
        bars[s] = _parse(item)
    return bars, errors


def fetch_bars(symbols, api_key, interval, outputsize, batch_size=8, pages=1):
    """Returns (bars: {symbol: DataFrame}, errors: {symbol: message}).

    pages > 1 walks further back: each extra page is another request per symbol
    (one more credit each) ending where the previous page started.
    """
    bars, errors = {}, {}

    for i in range(0, len(symbols), batch_size):
        batch = symbols[i:i + batch_size]
        got, errs = _fetch_batch(batch, api_key, interval, outputsize)
        bars.update(got)
        errors.update(errs)

        for _ in range(pages - 1):
            live = [s for s in batch if s in bars]
            if not live:
                break
            # One end_date per request: use the latest start so no symbol gets a gap;
            # the overlap for the others is removed below
            end = max(bars[s].index[0] for s in live)
            older, _errs = _fetch_batch(live, api_key, interval, outputsize, end)
            # A failed extra page is not fatal: keep the recent page
            for s, df in older.items():
                both = pd.concat([df, bars[s]])
                bars[s] = both[~both.index.duplicated(keep="last")].sort_index()

    return bars, errors

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


def fetch_bars(symbols, api_key, interval, outputsize, batch_size=8):
    """Returns (bars: {symbol: DataFrame}, errors: {symbol: message})."""
    bars, errors = {}, {}

    for i in range(0, len(symbols), batch_size):
        batch = symbols[i:i + batch_size]
        params = {
            "symbol": ",".join(batch),
            "interval": interval,
            "outputsize": outputsize,
            "timezone": "UTC",
            "apikey": api_key,
        }

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
            continue

        for s in batch:
            item = data.get(s)
            if not item or item.get("status") == "error" or "values" not in item:
                errors[s] = (item or {}).get("message", "no data returned")
                continue
            bars[s] = _parse(item)

    return bars, errors

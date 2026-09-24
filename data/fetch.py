"""Single entry point for market data. Pages never talk to a vendor directly."""
import os

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

import config
from data.providers import demo_provider, twelvedata_provider
from indicators.daily import is_weekend

load_dotenv()

PROVIDERS = {
    "twelvedata": twelvedata_provider,
    "demo": demo_provider,
}


def get_api_key():
    key = os.getenv("TWELVEDATA_API_KEY")
    if key:
        return key
    try:
        return st.secrets["TWELVEDATA_API_KEY"]
    except Exception:
        return None


def resample(df: pd.DataFrame, rule: str) -> pd.DataFrame:
    out = df.resample(rule, label="left", closed="left").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last"}
    )
    return out.dropna()


def drop_weekend(df: pd.DataFrame) -> pd.DataFrame:
    """Removes the vendor's flat filler bars between the Friday and Sunday rollovers."""
    return df[~is_weekend(df.index).to_numpy()]


def symbol_map():
    """Display name -> (group, vendor symbol)."""
    return {
        name: (group, vendor)
        for group, items in config.SYMBOLS.items()
        for name, vendor in items.items()
    }


@st.cache_data(ttl=config.CACHE_TTL_SECONDS, show_spinner="Fetching market data…")
def load_all(provider_name: str):
    """Returns (bars: {display: 10m DataFrame}, errors: {display: msg}, fetched_at)."""
    provider = PROVIDERS[provider_name]
    api_key = get_api_key() if provider_name == "twelvedata" else None
    if provider_name == "twelvedata" and not api_key:
        raise RuntimeError(
            "No API key found. Add TWELVEDATA_API_KEY to your .env file."
        )

    smap = symbol_map()
    vendor_to_display = {v: name for name, (_, v) in smap.items()}

    raw, raw_errors = provider.fetch_bars(
        list(vendor_to_display),
        api_key,
        config.SOURCE_INTERVAL,
        config.OUTPUTSIZE,
        config.BATCH_SIZE,
        config.SOURCE_PAGES,
    )

    bars = {vendor_to_display[v]: resample(drop_weekend(df), config.TIMEFRAME) for v, df in raw.items()}
    errors = {vendor_to_display[v]: msg for v, msg in raw_errors.items()}
    return bars, errors, pd.Timestamp.now(tz="UTC")

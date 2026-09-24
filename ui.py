"""Shared by every page: loads data once, draws the sidebar."""
import streamlit as st

import config
from data.fetch import load_all, symbol_map
from indicators import snapshot, trend

AMBER = "#e59f2d"

STATE_COLORS = {
    trend.TREND_UP: "#1a9e77",
    trend.TREND_DOWN: "#d1495b",
    trend.CONFLICT: AMBER,
    trend.RANGE: "#6c8ebf",
    trend.NEUTRAL: "#a0a4ab",
}
STATE_ORDER = [trend.TREND_UP, trend.TREND_DOWN, trend.CONFLICT, trend.RANGE, trend.NEUTRAL]


def open_symbol(name: str):
    """Remembers the chosen symbol and offers a jump to its detail page."""
    st.session_state["symbol"] = name
    if st.button(f"Open {name} chart", type="primary"):
        st.switch_page("pages/symbol.py")


def load():
    """Returns history, snapshot, errors, fetched_at, and the selected groups."""
    with st.sidebar:
        st.caption(f"Source: {config.DATA_PROVIDER}, {config.TIMEFRAME} bars")
        if st.button("Refresh data", width="stretch"):
            load_all.clear()

    try:
        bars, errors, fetched_at = load_all(config.DATA_PROVIDER)
    except Exception as e:
        st.error(f"Could not load data: {e}")
        st.stop()

    history, snap = snapshot.build(bars, symbol_map(), fetched_at)

    with st.sidebar:
        groups = st.multiselect(
            "Asset classes", list(config.SYMBOLS), default=list(config.SYMBOLS)
        )
        st.caption(f"Fetched {fetched_at:%Y-%m-%d %H:%M} UTC")
        if errors:
            with st.expander(f"{len(errors)} symbol(s) failed"):
                for name, msg in errors.items():
                    st.write(f"**{name}**: {msg}")

    if not snap.empty:
        snap = snap[snap["Group"].isin(groups)]
    return history, snap, errors, fetched_at, groups

import streamlit as st

import config
import ui

history, snap, errors, fetched_at, groups = ui.load()

st.title("Market overview")
st.caption("Price vs EMA120 and ADX regime on 10-minute bars. Score = distance from EMA in ATRs.")

if snap.empty:
    st.info("No symbols to show. Pick at least one asset class in the sidebar, or check the failed symbols list.")
    st.stop()

# State counts
cols = st.columns(len(ui.STATE_ORDER))
for col, state in zip(cols, ui.STATE_ORDER):
    col.metric(state, int((snap["State"] == state).sum()))

c1, c2 = st.columns([1, 1])
sort_by = c1.radio(
    "Sort by", ["Strongest either way", "Score, high to low"], horizontal=True
)
split = c2.toggle("Split by asset class", value=False)

if sort_by == "Score, high to low":
    snap = snap.sort_values("Score", ascending=False)


def style(df):
    show = df.drop(columns=["Stale"]).copy()
    show["Symbol"] = [
        f"{s}  (stale)" if stale else s for s, stale in zip(df["Symbol"], df["Stale"])
    ]
    return (
        show.style
        .map(
            lambda v: f"background-color: {ui.STATE_COLORS.get(v, '')}; color: white; font-weight: 600",
            subset=["State"],
        )
        .map(
            lambda v: "color: #1a9e77" if v > 0 else "color: #d1495b",
            subset=["Score"],
        )
        .format(
            {
                "Price": "{:,.5g}",
                "ADX": "{:.1f}",
                "+DI": "{:.1f}",
                "-DI": "{:.1f}",
                "Score": "{:+.2f}",
                "Last bar (UTC)": lambda t: t.strftime("%a %H:%M"),
            }
        )
    )


if split:
    for g in groups:
        part = snap[snap["Group"] == g]
        if part.empty:
            continue
        st.subheader(g)
        st.dataframe(style(part.drop(columns=["Group"])), hide_index=True, width="stretch")
else:
    st.dataframe(style(snap), hide_index=True, width="stretch", height=38 * (len(snap) + 1))

st.caption(
    f"Trend: ADX above {config.ADX_TREND_ON} (stays until below {config.ADX_TREND_OFF}). "
    f"Range: ADX below {config.ADX_RANGE_ON} (stays until above {config.ADX_RANGE_OFF}). "
    "Conflict: ADX trending but EMA side and DI direction disagree. Stale: market closed or no recent bars."
)

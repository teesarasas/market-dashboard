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
    show["EMA lag"] = ["lag" if v else "" for v in df["EMA lag"]]
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
        .map(
            lambda v: f"color: {ui.AMBER}; font-weight: 600" if v >= config.ADR_USED_WARN else "",
            subset=["ADR used %"],
        )
        .format(
            {
                "Price": "{:,.5g}",
                "ADX": "{:.1f}",
                "+DI": "{:.1f}",
                "-DI": "{:.1f}",
                "Score": "{:+.2f}",
                "NATR": "{:.3f}%",
                "ADR used %": "{:.0f}%",
                "Prev-day pos %": "{:.0f}%",
                "Last bar (UTC)": lambda t: t.strftime("%a %H:%M"),
            },
            na_rep="–",
        )
    )


def table(df, key, **kwargs):
    """Row-selectable table; returns the selected symbol or None."""
    event = st.dataframe(
        style(df), hide_index=True, width="stretch", key=key,
        on_select="rerun", selection_mode="single-row", **kwargs,
    )
    rows = event.selection.rows
    return df["Symbol"].iloc[rows[0]] if rows else None


picked = []
if split:
    for g in groups:
        part = snap[snap["Group"] == g]
        if part.empty:
            continue
        st.subheader(g)
        picked.append(table(part.drop(columns=["Group"]), key=f"table_{g}"))
else:
    picked.append(table(snap, key="table_all", height=38 * (len(snap) + 1)))

selected = next((p for p in picked if p), None)
if selected:
    ui.open_symbol(selected)
else:
    st.caption("Select a row to open its chart.")

st.caption(
    f"Trend: ADX above {config.ADX_TREND_ON} (stays until below {config.ADX_TREND_OFF}). "
    f"Range: ADX below {config.ADX_RANGE_ON} (stays until above {config.ADX_RANGE_OFF}). "
    "Conflict: ADX trending but EMA side and DI direction disagree. Stale: market closed or no recent bars.  \n"
    f"NATR: ATR as % of price. ADR used: today's range vs the {config.ADR_DAYS}-day average "
    f"(amber at {config.ADR_USED_WARN}%+). Prev-day pos: 0% = previous day's low, 100% = its high. "
    f"EMA lag: price crossed EMA{config.EMA_LENGTH} but the EMA still slopes the other way."
)

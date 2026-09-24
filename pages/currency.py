import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

import config
import ui
from data.fetch import symbol_map
from indicators import currency

history, snap, errors, fetched_at, groups = ui.load()

st.title("Currencies")
st.caption(
    "Strength = mean score of every pair containing the currency (base +score, quote −score). "
    "Breadth = pairs in a trend that favours the currency. Uses all FX pairs, whatever the sidebar filter."
)

fx = {
    vendor: name
    for name, (group, vendor) in symbol_map().items()
    if group in config.CURRENCY_GROUPS and name in history
}
if not fx:
    st.info("No FX pairs loaded.")
    st.stop()

strength = currency.strength({vendor: history[name]["score"] for vendor, name in fx.items()})
states = {vendor: history[name]["state"].iloc[-1] for vendor, name in fx.items()}
table = currency.breadth(states)
now = strength.dropna(how="all").iloc[-1]
table["strength"] = now
table = table.sort_values("strength", ascending=False)

c1, c2 = st.columns([1, 2])

bars = now.sort_values(ascending=False)
fig = go.Figure(
    go.Bar(
        x=bars.index, y=bars.values,
        marker_color=[ui.STATE_COLORS["Trend up"] if v > 0 else ui.STATE_COLORS["Trend down"] for v in bars],
        hovertemplate="%{x}: %{y:+.2f}<extra></extra>",
    )
)
fig.update_layout(
    title="Strength now", height=420, margin=dict(l=10, r=10, t=40, b=10),
    yaxis_title="Mean score (ATRs)", plot_bgcolor="rgba(0,0,0,0)",
)
c1.plotly_chart(fig, width="stretch")

recent = strength.tail(config.CURRENCY_HISTORY_BARS)
fig = px.line(recent, labels={"value": "Mean score (ATRs)", "index": "", "variable": "Currency"})
fig.add_hline(y=0, line_width=1, line_color="#888")
fig.update_layout(
    title=f"Strength, last {config.CURRENCY_HISTORY_BARS} bars (UTC)", height=420,
    margin=dict(l=10, r=10, t=40, b=10), plot_bgcolor="rgba(0,0,0,0)",
)
c2.plotly_chart(fig, width="stretch")

table["breadth"] *= 100
show = table.rename_axis("Currency").reset_index()[
    ["Currency", "strength", "breadth", "in_favour", "against", "total"]
]
st.dataframe(
    show,
    hide_index=True,
    width="stretch",
    column_config={
        "strength": st.column_config.NumberColumn("Strength", format="%+.2f"),
        "breadth": st.column_config.NumberColumn("Breadth", format="%.0f%%"),
        "in_favour": st.column_config.NumberColumn("Pairs in favour"),
        "against": st.column_config.NumberColumn("Pairs against"),
        "total": st.column_config.NumberColumn("Total pairs"),
    },
)

thin = table[table["total"] < config.CURRENCY_MIN_COVERAGE]
if not thin.empty:
    st.warning(
        "Low coverage: "
        + ", ".join(f"{c} ({n} pair{'s' if n > 1 else ''})" for c, n in thin["total"].items())
        + f". With fewer than {config.CURRENCY_MIN_COVERAGE} pairs, strength is mostly one pair's score."
    )

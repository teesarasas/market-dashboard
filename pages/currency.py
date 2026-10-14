import pandas as pd
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
    "Breadth = pairs in a trend that favours the currency. "
    f"Record high % = of the currency's pairs that broke a {config.RECORD_LOOKBACK_BARS // 6}-hour high or low "
    f"in the last {config.RECORD_WINDOW_BARS * 10} minutes, the share that broke in its favour. "
    "Uses all FX pairs, whatever the sidebar filter. "
    "XAU is measured the same way on gold's 8 pairs (XAU/USD and the gold crosses), "
    "but gold is kept out of the currencies' own numbers."
)

def pairs_in(groups):
    return {
        vendor: name
        for name, (group, vendor) in symbol_map().items()
        if group in groups and name in history
    }


def measure(pairs):
    """Strength history, breadth table and record-high frames for a set of pairs."""
    strength = currency.strength({v: history[n]["score"] for v, n in pairs.items()})
    table = currency.breadth({v: history[n]["state"].iloc[-1] for v, n in pairs.items()})
    record = currency.record_high({
        v: currency.pair_breakouts(history[n], config.RECORD_LOOKBACK_BARS, config.RECORD_WINDOW_BARS)
        for v, n in pairs.items()
    })
    return strength, table, record


fx = pairs_in(config.CURRENCY_GROUPS)
if not fx:
    st.info("No FX pairs loaded.")
    st.stop()
metal = pairs_in(config.CURRENCY_METAL_GROUPS)
fx_codes = {c for v in fx for c in currency.parse_pair(v)}
metal_codes = sorted({c for v in metal for c in currency.parse_pair(v)} - fx_codes)

# FX currencies from FX pairs only; metals from their own pairs, keeping just the metal's column
strength, table, (highs, lows, record_pct) = measure(fx)
if metal and metal_codes:
    m_strength, m_table, (m_highs, m_lows, m_pct) = measure(metal)
    strength = pd.concat([strength, m_strength[metal_codes]], axis=1)
    table = pd.concat([table, m_table.loc[metal_codes]])
    if not m_pct.empty:
        highs = pd.concat([highs, m_highs[metal_codes]], axis=1)
        lows = pd.concat([lows, m_lows[metal_codes]], axis=1)
        record_pct = pd.concat([record_pct, m_pct[metal_codes]], axis=1)

# Latest value per currency (gold has a daily break, so take each column's last value)
now = strength.apply(lambda s: s.dropna().iloc[-1] if s.notna().any() else float("nan"))
table["strength"] = now
if not record_pct.empty:
    table["new_highs"] = highs.iloc[-1]
    table["new_lows"] = lows.iloc[-1]
    table["record_high"] = record_pct.iloc[-1]
else:
    table["new_highs"] = table["new_lows"] = table["record_high"] = float("nan")
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
table["record_high"] = table["record_high"].map(lambda v: "–" if pd.isna(v) else f"{v:.0f}%")
show = table.rename_axis("Currency").reset_index()[
    ["Currency", "strength", "record_high", "new_highs", "new_lows", "breadth", "in_favour", "against", "total"]
]
st.dataframe(
    show,
    hide_index=True,
    width="stretch",
    column_config={
        "strength": st.column_config.NumberColumn("Strength", format="%+.2f"),
        "record_high": st.column_config.TextColumn(
            "Record high %",
            help="Share of recent breakouts in the currency's favour. – = no breakouts.",
        ),
        "new_highs": st.column_config.NumberColumn("New highs", format="%d"),
        "new_lows": st.column_config.NumberColumn("New lows", format="%d"),
        "breadth": st.column_config.NumberColumn("Breadth", format="%.0f%%"),
        "in_favour": st.column_config.NumberColumn("Pairs in favour"),
        "against": st.column_config.NumberColumn("Pairs against"),
        "total": st.column_config.NumberColumn("Total pairs"),
    },
)

# --- Currency grid: every pair from the row currency's point of view ---
st.subheader("Currency grid")
st.caption("Row currency vs column currency, strongest first.")
order = list(now.dropna().sort_values(ascending=False).index)
grid_pairs = {**fx, **metal}
last = {vendor: history[name].iloc[-1] for vendor, name in grid_pairs.items()}
breakouts = {
    vendor: currency.pair_breakouts(history[name], config.RECORD_LOOKBACK_BARS, config.RECORD_WINDOW_BARS).iloc[-1]
    for vendor, name in grid_pairs.items()
}
score_m = currency.pair_matrix({v: r["score"] for v, r in last.items()}, order)
trend_m = currency.pair_matrix({v: currency.state_sign(r["state"]) for v, r in last.items()}, order)
brk_m = currency.pair_matrix({v: (0 if pd.isna(b) else b) for v, b in breakouts.items()}, order)
dis_m = currency.pair_matrix({v: r["di_spread"] for v, r in last.items()}, order)
names_m = currency.pair_names(grid_pairs, order)

clip = config.GRID_SCORE_CLIP
text, xs, ys, hover, cell_pairs = [], [], [], [], []
for row in order:
    text_row = []
    for col in order:
        pair = names_m.loc[row, col]
        if pd.isna(pair):
            text_row.append("")
            continue
        s, t, b = score_m.loc[row, col], trend_m.loc[row, col], brk_m.loc[row, col]
        marks = ("▲" if t > 0 else "▼" if t < 0 else "") + ("↑" if b > 0 else "↓" if b < 0 else "")
        text_row.append(f"{s:+.1f}" + (f"<br>{marks}" if marks else ""))
        r = last[pair]
        trend_txt = (f" (in {row}'s favour)" if t > 0 else f" (against {row})" if t < 0 else "")
        brk_txt = ("new 24h extreme in " + row + "'s favour" if b > 0
                   else "new 24h extreme against " + row if b < 0 else "none")
        xs.append(col)
        ys.append(row)
        cell_pairs.append(pair)
        hover.append(
            f"<b>{row} vs {col}</b> ({pair})<br>"
            f"Score for {row}: {s:+.2f}<br>"
            f"State: {r['state']}{trend_txt}<br>"
            f"DI spread for {row}: {dis_m.loc[row, col]:+.0f}<br>"
            f"Breakout, last hour: {brk_txt}"
        )
    text.append(text_row)

neutral = "#4a4f57"   # mid grey: white text stays readable on light and dark themes
fig = go.Figure(
    go.Heatmap(
        z=score_m.clip(-clip, clip).values, x=order, y=order, text=text, texttemplate="%{text}",
        zmin=-clip, zmax=clip, hoverinfo="skip", xgap=2, ygap=2, textfont=dict(color="white"),
        colorscale=[[0, ui.STATE_COLORS["Trend down"]], [0.5, neutral], [1, ui.STATE_COLORS["Trend up"]]],
        colorbar=dict(title="Score", ticksuffix=""),
    )
)
# Invisible markers on each cell carry the hover text and make cells clickable.
fig.add_trace(go.Scatter(
    x=xs, y=ys, mode="markers", marker=dict(size=40, color="rgba(0,0,0,0)"),
    hovertext=hover, hovertemplate="%{hovertext}<extra></extra>", showlegend=False,
))
fig.update_layout(
    height=540, margin=dict(l=10, r=10, t=30, b=10), plot_bgcolor="rgba(0,0,0,0)",
    xaxis=dict(side="top", title=None, showgrid=False, zeroline=False),
    yaxis=dict(autorange="reversed", title=None, showgrid=False, zeroline=False),
)
event = st.plotly_chart(fig, width="stretch", key="currency_grid", on_select="rerun", selection_mode="points")
clicked = [cell_pairs[p["point_index"]] for p in event.selection.points if p.get("curve_number") == 1]
if clicked:
    ui.open_symbol(grid_pairs[clicked[0]])
st.caption(
    "Each cell is the pair's Score seen from the row currency: green = the row currency is winning. "
    "▲/▼ = the pair is trending for/against the row currency. "
    "↑/↓ = a new 24-hour extreme for/against it in the last hour. "
    f"Colour is capped at ±{clip}, so full colour means stretched. "
    "Best-aligned pairs sit top-right (strongest vs weakest). Click a cell to open its chart."
)

thin = table[table["total"] < config.CURRENCY_MIN_COVERAGE]
if not thin.empty:
    st.warning(
        "Low coverage: "
        + ", ".join(f"{c} ({n} pair{'s' if n > 1 else ''})" for c, n in thin["total"].items())
        + f". With fewer than {config.CURRENCY_MIN_COVERAGE} pairs, strength is mostly one pair's score."
    )

if not record_pct.empty:
    recent_pct = record_pct.tail(config.CURRENCY_HISTORY_BARS)
    fig = px.line(recent_pct, labels={"value": "Record high %", "index": "", "variable": "Currency"},
                  line_shape="hv")
    fig.add_hline(y=50, line_width=1, line_color="#888")
    fig.update_layout(
        title=f"Record high %, last {config.CURRENCY_HISTORY_BARS} bars (UTC)", height=380,
        margin=dict(l=10, r=10, t=40, b=10), plot_bgcolor="rgba(0,0,0,0)",
        yaxis=dict(range=[-5, 105], ticksuffix="%"),
    )
    st.plotly_chart(fig, width="stretch")
    st.caption(
        "Gaps mean no breakouts either way. With 7 pairs per currency, one pair changes the value "
        "by about 14 points, so read it over the last hour rather than bar by bar."
    )

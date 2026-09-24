import plotly.graph_objects as go
import streamlit as st

import config
import ui

history, snap, errors, fetched_at, groups = ui.load()

st.title("Market map")
st.caption(
    f"Right = stronger trend (ADX). Up/down = distance from EMA{config.EMA_LENGTH} in ATRs. "
    f"Tails show the last {config.TRAIL_BARS} bars."
)

if snap.empty:
    st.info("No symbols to show. Pick at least one asset class in the sidebar.")
    st.stop()

c1, c2 = st.columns(2)
show_trails = c1.toggle("Show trails", value=True)
hide_neutral = c2.toggle("Hide neutral symbols", value=False)

fig = go.Figure()

# Regime zones
fig.add_vrect(x0=config.ADX_TREND_ON, x1=100, fillcolor="#1a9e77", opacity=0.06, line_width=0)
fig.add_vrect(x0=0, x1=config.ADX_RANGE_ON, fillcolor="#6c8ebf", opacity=0.06, line_width=0)
for x, dash in [(config.ADX_RANGE_ON, "solid"), (config.ADX_TREND_OFF, "dot"), (config.ADX_TREND_ON, "solid")]:
    fig.add_vline(x=x, line_width=1, line_dash=dash, line_color="#888")
fig.add_hline(y=0, line_width=1, line_color="#888")

legend_done = set()
marker_names = {}   # trace index -> symbol, for click selection
max_x, max_y = config.ADX_TREND_ON + 10, 1.0

for _, row in snap.iterrows():
    name, state = row["Symbol"], row["State"]
    if hide_neutral and state == "Neutral":
        continue
    color = ui.STATE_COLORS[state]
    trail = history[name].tail(config.TRAIL_BARS)[["adx", "score"]].dropna()
    if trail.empty:
        continue
    max_x = max(max_x, trail["adx"].max() + 5)
    max_y = max(max_y, trail["score"].abs().max() * 1.15)

    if show_trails and len(trail) > 1:
        fig.add_trace(
            go.Scatter(
                x=trail["adx"], y=trail["score"], mode="lines",
                line=dict(color=color, width=2), opacity=0.45,
                hoverinfo="skip", showlegend=False, legendgroup=state,
            )
        )

    marker_names[len(fig.data)] = name
    fig.add_trace(
        go.Scatter(
            x=[row["ADX"]], y=[row["Score"]], mode="markers+text",
            marker=dict(size=13, color=color, line=dict(color="white", width=1.5),
                        symbol="diamond" if row["Stale"] else "circle"),
            text=[name], textposition="top center",
            name=state, legendgroup=state, showlegend=state not in legend_done,
            customdata=[[row["Group"], row["Price"], row["Side"], "yes" if row["Stale"] else "no"]],
            hovertemplate=(
                f"<b>{name}</b><br>%{{customdata[0]}}<br>"
                "Price %{customdata[1]:,.5g} (%{customdata[2]} EMA)<br>"
                "ADX %{x:.1f}<br>Score %{y:+.2f}<br>Stale: %{customdata[3]}"
                f"<extra>{state}</extra>"
            ),
        )
    )
    legend_done.add(state)

fig.update_layout(
    height=680,
    margin=dict(l=10, r=10, t=10, b=10),
    xaxis=dict(title="ADX (trend strength)", range=[0, max_x], zeroline=False),
    yaxis=dict(title="Score (ATRs from EMA)", range=[-max_y, max_y], zeroline=False),
    legend=dict(orientation="h", yanchor="bottom", y=1.01, x=0),
    plot_bgcolor="rgba(0,0,0,0)",
)
event = st.plotly_chart(fig, width="stretch", key="market_map", on_select="rerun", selection_mode="points")

clicked = [marker_names[p["curve_number"]] for p in event.selection.points if p["curve_number"] in marker_names]
if clicked:
    ui.open_symbol(clicked[0])
else:
    st.caption("Click a dot to open its chart.")

st.caption("Diamond markers are stale (market closed or no recent bars).")

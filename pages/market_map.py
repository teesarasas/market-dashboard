import numpy as np
import plotly.graph_objects as go
import streamlit as st

import config
import ui
from indicators.metrics import METRICS

history, snap, errors, fetched_at, groups = ui.load()

STATE = "State"

st.title("Market map")

if snap.empty:
    st.info("No symbols to show. Pick at least one asset class in the sidebar.")
    st.stop()

names = list(METRICS)
c1, c2, c3 = st.columns(3)
x_name = c1.selectbox("X axis", names, index=names.index("ADX"))
y_name = c2.selectbox("Y axis", names, index=names.index("Score"))
colour_name = c3.selectbox("Colour", [STATE] + names, index=0)
xm, ym = METRICS[x_name], METRICS[y_name]
cm = METRICS.get(colour_name)

st.caption(f"Each dot is the latest bar. Tails show the last {config.TRAIL_BARS} bars.")

c1, c2 = st.columns(2)
show_trails = c1.toggle("Show trails", value=True)
hide_neutral = c2.toggle("Hide neutral symbols", value=False)

rows = snap if not hide_neutral else snap[snap["State"] != "Neutral"]
# The same metric may be on several channels; keep each column once
cols = list(dict.fromkeys([xm["column"], ym["column"]] + ([cm["column"]] if cm else [])))
latest = {name: history[name][cols].iloc[-1] for name in rows["Symbol"]}
trails = {
    name: history[name].tail(config.TRAIL_BARS)[cols].dropna(subset=[xm["column"], ym["column"]])
    for name in rows["Symbol"]
}

# Shared colour scale for numeric colouring
if cm:
    cvals = np.array([latest[n][cm["column"]] for n in latest], dtype=float)
    finite = cvals[np.isfinite(cvals)]
    if cm["signed"]:
        lim = float(np.abs(finite).max()) if finite.size else 1.0
        cmin, cmax, scale = -lim, lim, "RdYlGn"
    else:
        cmin, cmax = (float(finite.min()), float(finite.max())) if finite.size else (0.0, 1.0)
        scale = "Viridis"

fig = go.Figure()

# Regime zones only make sense on an ADX x-axis
if x_name == "ADX":
    fig.add_vrect(x0=config.ADX_TREND_ON, x1=100, fillcolor="#1a9e77", opacity=0.06, line_width=0)
    fig.add_vrect(x0=0, x1=config.ADX_RANGE_ON, fillcolor="#6c8ebf", opacity=0.06, line_width=0)
    for x, dash in [(config.ADX_RANGE_ON, "solid"), (config.ADX_TREND_OFF, "dot"), (config.ADX_TREND_ON, "solid")]:
        fig.add_vline(x=x, line_width=1, line_dash=dash, line_color="#888")
if ym["signed"]:
    fig.add_hline(y=0, line_width=1, line_color="#888")

legend_done = set()
marker_names = {}   # trace index -> symbol, for click selection
colourbar_done = False
xs, ys = [], []

for _, row in rows.iterrows():
    name, state = row["Symbol"], row["State"]
    trail = trails[name]
    point = latest[name]
    if trail.empty or point[[xm["column"], ym["column"]]].isna().any():
        continue
    xs.extend(trail[xm["column"]])
    ys.extend(trail[ym["column"]])
    state_colour = ui.STATE_COLORS[state]

    if show_trails and len(trail) > 1:
        fig.add_trace(
            go.Scatter(
                x=trail[xm["column"]], y=trail[ym["column"]], mode="lines",
                line=dict(color=state_colour if not cm else "#888", width=2), opacity=0.45,
                hoverinfo="skip", showlegend=False, legendgroup=state,
            )
        )

    marker = dict(size=13, line=dict(color="white", width=1.5),
                  symbol="diamond" if row["Stale"] else "circle")
    colour_line = ""
    if cm:
        cval = point[cm["column"]]
        marker.update(color=[cval], colorscale=scale, cmin=cmin, cmax=cmax,
                      showscale=not colourbar_done,
                      colorbar=dict(title=dict(text=colour_name), thickness=12))
        colourbar_done = True
        colour_line = f"<br>{colour_name} {cval:{cm['fmt']}}" if np.isfinite(cval) else ""
    else:
        marker.update(color=state_colour)

    marker_names[len(fig.data)] = name
    fig.add_trace(
        go.Scatter(
            x=[point[xm["column"]]], y=[point[ym["column"]]], mode="markers+text",
            marker=marker,
            text=[name], textposition="top center",
            name=state, legendgroup=state, showlegend=not cm and state not in legend_done,
            customdata=[[row["Group"], row["Price"], row["Side"], "yes" if row["Stale"] else "no"]],
            hovertemplate=(
                f"<b>{name}</b><br>%{{customdata[0]}}<br>"
                "Price %{customdata[1]:,.5g} (%{customdata[2]} EMA)<br>"
                f"{x_name} %{{x:{xm['fmt']}}}<br>{y_name} %{{y:{ym['fmt']}}}{colour_line}<br>"
                "Stale: %{customdata[3]}"
                f"<extra>{state}</extra>"
            ),
        )
    )
    legend_done.add(state)


def axis_range(metric_name, values):
    """ADX from zero; signed metrics symmetric around zero; others padded to fit."""
    v = np.asarray(values, dtype=float)
    v = v[np.isfinite(v)]
    if metric_name == "ADX":
        return [0, max(config.ADX_TREND_ON + 10, (v.max() + 5) if v.size else 0)]
    if METRICS[metric_name]["signed"]:
        lim = max(1.0, np.abs(v).max() * 1.15) if v.size else 1.0
        return [-lim, lim]
    if not v.size:
        return None
    pad = (v.max() - v.min()) * 0.08 or abs(v.max()) * 0.1 or 1.0
    return [v.min() - pad, v.max() + pad]


fig.update_layout(
    height=680,
    margin=dict(l=10, r=10, t=10, b=10),
    xaxis=dict(title=xm["label"], range=axis_range(x_name, xs), zeroline=False),
    yaxis=dict(title=ym["label"], range=axis_range(y_name, ys), zeroline=False),
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

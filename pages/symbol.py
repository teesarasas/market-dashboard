import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

import config
import ui

history, snap, errors, fetched_at, groups = ui.load()

st.title("Symbol detail")

names = list(history)
if not names:
    st.info("No data loaded. Check the failed symbols list in the sidebar.")
    st.stop()

# Session "symbol" survives page switches; the widget's own key would not
current = st.session_state.get("symbol")
name = st.selectbox(
    "Symbol", names, index=names.index(current) if current in names else 0, key="symbol_picker"
)
st.session_state["symbol"] = name

ind = history[name]
last = ind.iloc[-1]

cols = st.columns([1.4, 1, 1, 1, 1.4, 1])
cols[0].metric("State", last["state"])
cols[1].metric("Score", f"{last['score']:+.2f}")
cols[2].metric("ADX", f"{last['adx']:.1f}")
cols[3].metric("ADR used", "–" if pd.isna(last["adr_used"]) else f"{last['adr_used']:.0f}%")
cols[4].metric("Prev-day zone", last["prev_day_zone"] or "–")
cols[5].metric("EMA lag", "lag" if last["ema_lag"] else "no")

view = ind.tail(config.DETAIL_BARS)

fig = make_subplots(
    rows=2, cols=1, shared_xaxes=True, row_heights=[0.7, 0.3], vertical_spacing=0.03
)
fig.add_trace(
    go.Candlestick(
        x=view.index, open=view["open"], high=view["high"], low=view["low"], close=view["close"],
        name="Price", increasing_line_color=ui.STATE_COLORS["Trend up"],
        decreasing_line_color=ui.STATE_COLORS["Trend down"],
    ),
    row=1, col=1,
)
fig.add_trace(
    go.Scatter(x=view.index, y=view["ema"], name=f"EMA{config.EMA_LENGTH}",
               line=dict(color="#f2c14e", width=1.5)),
    row=1, col=1,
)
for level, label in [(last["pdh"], "PDH"), (last["pdl"], "PDL")]:
    if pd.notna(level):
        fig.add_hline(y=level, line_width=1, line_dash="dash", line_color="#aaa",
                      annotation_text=label, annotation_position="top left", row=1, col=1)

for col, label, color in [
    ("adx", "ADX", "#e8e8e8"),
    ("plus_di", "+DI", ui.STATE_COLORS["Trend up"]),
    ("minus_di", "−DI", ui.STATE_COLORS["Trend down"]),
]:
    fig.add_trace(
        go.Scatter(x=view.index, y=view[col], name=label, line=dict(color=color, width=1.5)),
        row=2, col=1,
    )
for level, dash in [(config.ADX_TREND_ON, "solid"), (config.ADX_TREND_OFF, "dot"), (config.ADX_RANGE_ON, "solid")]:
    fig.add_hline(y=level, line_width=1, line_dash=dash, line_color="#888", row=2, col=1)

# Hide weekend and other gaps: every missing 10m slot inside the window
step = pd.Timedelta(config.TIMEFRAME)
missing = pd.date_range(view.index[0], view.index[-1], freq=step).difference(view.index)
fig.update_xaxes(rangebreaks=[dict(values=missing, dvalue=step.total_seconds() * 1000)])

fig.update_layout(
    height=720,
    margin=dict(l=10, r=10, t=10, b=10),
    xaxis_rangeslider_visible=False,
    legend=dict(orientation="h", yanchor="bottom", y=1.01, x=0),
    plot_bgcolor="rgba(0,0,0,0)",
)
fig.update_yaxes(title_text="Price", row=1, col=1)
fig.update_yaxes(title_text="ADX / DI", row=2, col=1)
st.plotly_chart(fig, width="stretch")

st.caption(
    f"Last {config.DETAIL_BARS} {config.TIMEFRAME} bars, UTC. Dashed lines: previous trading day's "
    f"high and low. Lower panel lines: ADX {config.ADX_RANGE_ON} / {config.ADX_TREND_OFF} (dotted) / "
    f"{config.ADX_TREND_ON}."
)

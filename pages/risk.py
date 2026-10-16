import pandas as pd
import streamlit as st

import config
import ui
from data.fetch import load_daily, symbol_map
from indicators import risk

history, snap, errors, fetched_at, groups = ui.load()

st.title("Risk calculator")
st.caption(
    "Sizes a trade so that hitting the stop loses no more than your risk %. "
    "Spread and commission are not included. Prices come from Twelve Data (up to 10 minutes old); "
    "type your real entry from MT5."
)

MODES = {"distribution": "Distribution", "manual": "Manual stop", "atr": "ATR (experiment)"}
SIDES = ["Long", "Short"]

smap = symbol_map()
tradable = {n: v for n, (g, v) in smap.items() if g in config.RISK_GROUPS and n in history}
prices = {v: history[n]["close"].iloc[-1] for n, (g, v) in smap.items() if n in history}
if not tradable:
    st.info("No instruments loaded.")
    st.stop()

today = risk.current_trading_day(pd.Timestamp.now(tz="UTC"))
daily_bars, daily_errors = load_daily(config.DATA_PROVIDER, str(today.date()))


def qp_float(key, default):
    try:
        return float(st.query_params.get(key, default))
    except (TypeError, ValueError):
        return float(default)


qp_mode = st.query_params.get("stop", "distribution")
if qp_mode not in MODES:
    qp_mode = "distribution"
# Starting values come from the URL once; after that the widgets keep their own state
st.session_state.setdefault("risk_balance", qp_float("balance", config.RISK_DEFAULT_BALANCE))
st.session_state.setdefault("risk_pct", qp_float("risk", config.RISK_DEFAULT_PCT))
st.session_state.setdefault("risk_mode", MODES[qp_mode])

left, right = st.columns([1, 1.3], gap="large")

# ---------------- Inputs ----------------
with left:
    names = list(tradable)
    # Follow a symbol chosen on another page (e.g. "Size this trade"), otherwise keep this page's choice
    chosen_elsewhere = st.session_state.get("symbol")
    if chosen_elsewhere in names and chosen_elsewhere != st.session_state.get("_risk_synced"):
        st.session_state["risk_symbol"] = chosen_elsewhere
    if st.session_state.get("risk_symbol") not in names:
        st.session_state["risk_symbol"] = names[0]
    name = st.selectbox("Instrument", names, key="risk_symbol")
    st.session_state["symbol"] = st.session_state["_risk_synced"] = name
    vendor = tradable[name]
    pip = risk.pip_size(vendor)
    dec = risk.price_decimals(vendor)
    fmt = f"%.{dec}f"

    side = st.radio("Direction", SIDES, horizontal=True)
    c1, c2 = st.columns(2)
    balance = c1.number_input(
        f"Account balance ({config.ACCOUNT_CURRENCY})", min_value=0.0, step=1000.0, format="%.0f",
        key="risk_balance",
    )
    risk_pct = c2.number_input(
        "Risk per trade (%)", min_value=0.0, max_value=5.0, step=0.05, format="%.2f",
        key="risk_pct",
    )

    latest = float(prices[vendor])
    entry = st.number_input(
        "Entry price", value=round(latest, dec), step=pip, format=fmt, key=f"entry_{name}",
        help=f"Pre-filled with the latest Twelve Data price ({latest:.{dec}f}). Use your MT5 price.",
    )

    mode_label = st.radio("Stop loss", list(MODES.values()), horizontal=True, key="risk_mode")
    mode = next(k for k, v in MODES.items() if v == mode_label)

    days = daily_bars.get(name)
    dist = risk.distribution(days, today) if days is not None else None
    atr_day = risk.daily_atr(days, today) if days is not None else None
    atr_10m = float(history[name]["atr"].iloc[-1])
    sign = -1 if side == "Long" else 1   # which way the stop sits from entry
    stop = None

    if mode == "distribution":
        if dist is None:
            why = daily_errors.get(name, f"fewer than {config.DIST_MIN_SAMPLE} usable days of daily history")
            st.error(f"No distribution bands for {name}: {why}. Use a manual stop.")
        else:
            levels = dist["levels"]
            beyond = {lbl: p for lbl, p in levels.items() if (p < entry if side == "Long" else p > entry)}
            if not beyond:
                st.warning("Entry is beyond every band on the stop side. Use a manual stop.")
            else:
                # nearest band first
                options = sorted(beyond, key=lambda lbl: abs(entry - beyond[lbl]))
                pick = st.selectbox(
                    "Stop at band", options,
                    format_func=lambda l: f"{l}   {beyond[l]:.{dec}f}   ({abs(entry - beyond[l]) / pip:.1f} pips)",
                    key=f"band_{name}_{side}",
                )
                buffer_pips = st.number_input("Buffer beyond the band (pips)", min_value=0.0, value=0.0, step=0.5,
                                              key=f"buffer_{name}")
                stop = beyond[pick] + sign * buffer_pips * pip
            anchor_txt = "yesterday's close" if dist["anchor_type"] == "close" else "today's open"
            st.caption(
                f"Bands = {anchor_txt} {dist['anchor']:.{dec}f} ± percentiles of the last {dist['n']} days' moves, "
                f"measured in daily ATR({config.DIST_SCALE_DAYS}) and re-sized by today's ATR "
                f"{dist['atr']:.{dec}f}. Day starts 17:00 New York. "
                "The bands cover one day's move: a trade held 2–3 days needs more room."
            )
            with st.expander("All bands"):
                st.dataframe(
                    pd.DataFrame([{"Band": lbl, "Price": f"{p:.{dec}f}",
                                   "From entry (pips)": f"{(p - entry) / pip:+.1f}"} for lbl, p in levels.items()]),
                    hide_index=True, width="stretch",
                )
    elif mode == "manual":
        default = entry + sign * (0.5 * atr_day if atr_day else 3 * atr_10m)
        stop = st.number_input("Stop loss price", value=round(default, dec), step=pip, format=fmt,
                               key=f"stop_{name}_{side}")
    else:
        sources = list(config.ATR_STOP_DEFAULT_MULT)
        source = st.selectbox("ATR", sources, key="atr_source")
        atr_value = atr_day if source.startswith("Daily") else atr_10m
        mult = st.number_input("Multiplier", min_value=0.1, step=0.1, format="%.1f",
                               value=config.ATR_STOP_DEFAULT_MULT[source], key=f"mult_{source}")
        if atr_value is None:
            st.error("Not enough daily history for the daily ATR.")
        else:
            stop = entry + sign * mult * atr_value
            st.caption(f"{source} = {atr_value:.{dec}f}. Experiment: mark trades sized this way as ATR in your log.")

# Remember settings in the URL so a bookmark brings them back
st.query_params.update({"balance": f"{balance:.0f}", "risk": f"{risk_pct:g}", "stop": mode})

# ---------------- Results ----------------
with right:
    if stop is None:
        st.info("Choose a stop to see the position size.")
        st.stop()
    if not risk.stop_on_correct_side(side, entry, stop):
        st.error(f"For a {side.lower()} the stop must be {'below' if side == 'Long' else 'above'} the entry.")
        st.stop()
    if balance <= 0 or risk_pct <= 0:
        st.info("Enter a balance and a risk % above zero.")
        st.stop()

    try:
        per_unit = risk.money_per_unit(vendor, prices)
    except KeyError as e:
        st.error(f"Can't convert to {config.ACCOUNT_CURRENCY}: {e}.")
        st.stop()

    risk_money = balance * risk_pct / 100
    res = risk.size_position(risk_money, entry, stop, per_unit)
    distance = abs(entry - stop)
    cur = config.ACCOUNT_CURRENCY

    m1, m2 = st.columns(2)
    m1.metric("Lot size", f"{res['lots']:.2f}")
    m2.metric(f"Risk if stopped ({cur})", f"{res['risk']:,.2f}", f"{res['risk'] / balance * 100:.3f}% of balance",
              delta_color="off")

    st.dataframe(
        pd.DataFrame([{
            "Stop loss": f"{stop:.{dec}f}",
            "Distance (pips)": f"{distance / pip:.1f}",
            "× daily ATR": "–" if not atr_day else f"{distance / atr_day:.2f}",
            "× 10-min ATR": f"{distance / atr_10m:.1f}",
        }]),
        hide_index=True, width="stretch",
    )

    if res["lots"] == 0:
        st.error(
            f"Stop too wide for this risk: the minimum {config.MIN_LOT:.2f} lot would lose "
            f"{res['risk_per_lot'] * config.MIN_LOT:,.2f} {cur} "
            f"({res['risk_per_lot'] * config.MIN_LOT / balance * 100:.3f}%). Skip the trade or tighten the stop."
        )
    else:
        rows = []
        for r, price in risk.targets(entry, stop).items():
            rows.append({"Target": f"{r}R", "Price": f"{price:.{dec}f}",
                         "Distance (pips)": f"{r * distance / pip:.1f}",
                         f"Profit ({cur})": f"{r * res['risk']:,.2f}"})
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")

    st.caption(
        f"1 lot = {risk.contract_size(vendor):,.0f} units · {per_unit * pip:,.2f} {cur} per pip per lot · "
        f"{res['risk_per_lot']:,.2f} {cur} risk per lot at this stop · target risk {risk_money:,.2f} {cur} "
        f"(unrounded {res['raw_lots']:.3f} lots)."
    )

    # Warnings
    if risk_pct > config.RISK_MAX_PCT:
        st.warning(f"Risk {risk_pct:.2f}% is above your {config.RISK_MAX_PCT:.2f}% per-trade ceiling.")
    if distance < atr_10m:
        st.warning("Stop is inside one 10-minute ATR: normal noise can hit it.")
    if atr_day and abs(entry - latest) > 0.5 * atr_day:
        st.warning(f"Entry is far from the latest price ({latest:.{dec}f}). Check for a typo.")
    if mode == "atr":
        st.info("ATR stop is an experiment. Log the trade's stop method as ATR so it stays separate.")
    if not config.SPECS_CONFIRMED:
        st.caption(
            "⚠ Contract sizes are assumed (FX 100,000 units, XAUUSD 100 oz, lot step 0.01). "
            "Confirm them in MT5 (Specification) and set SPECS_CONFIRMED = True in config.py."
        )

import pandas as pd
import streamlit as st

import config
import ui
from data import tradelog
from data.fetch import symbol_map
from indicators import journal, risk

history, snap, errors, fetched_at, groups = ui.load()

st.title("Trade log")
log, problem = tradelog.get_log()
if log is None:
    st.info(problem)
    st.stop()

try:
    open_trades = log.open_trades()
    recent = log.recent(50)
except tradelog.TradeLogError as e:
    st.error(f"Can't reach the trade log: {e}")
    st.stop()

where = "Supabase" if isinstance(log, tradelog.SupabaseLog) else f"demo file {config.JOURNAL_DEMO_FILE}"
st.caption(f"Stored in {where}. Times in {config.DISPLAY_TZ}. Results exclude spread, commission and swap.")
msg = st.session_state.pop("_journal_msg", None)
if msg:
    st.success(msg)

smap = symbol_map()
tz = config.DISPLAY_TZ


def decimals(pair):
    return risk.price_decimals(smap[pair][1]) if pair in smap else 5


def local(ts):
    return pd.Timestamp(ts).tz_convert(tz)


# ---------------- Open trades ----------------
st.subheader(f"Open trades ({len(open_trades)})")
if open_trades.empty:
    st.info("No open trades. Log one from the Risk calculator.")

for _, t in open_trades.iterrows():
    dec = decimals(t["pair"])
    entry, sl, tp = float(t["entry"]), float(t["sl"]), float(t["tp"])
    opened = local(t["entry_time"])
    title = (f"{t['pair']} {t['side']} · {opened:%a %d %b %H:%M} · entry {entry:.{dec}f} · "
             f"SL {sl:.{dec}f} · TP {tp:.{dec}f} · {float(t['lots']):.2f} lots")
    with st.expander(title):
        if t["pair"] in history:
            last = float(history[t["pair"]]["close"].iloc[-1])
            r_now, _ = journal.trade_result(t["side"], entry, sl, last, float(t["risk_money"]))
            st.caption(f"Latest price {last:.{dec}f} (Twelve Data): about {r_now:+.2f}R.")
        now_local = pd.Timestamp.now(tz=tz)
        with st.form(f"close_{t['id']}"):
            reason = st.radio("Exit", ["TP hit", "SL hit", "Closed manually"], horizontal=True)
            price = st.number_input(
                "Exit price", value=None, format=f"%.{dec}f", step=risk.pip_size(smap[t['pair']][1])
                if t["pair"] in smap else 0.0001,
                help="Leave empty for TP hit / SL hit to use the TP / SL price. Required for a manual close.",
            )
            c1, c2 = st.columns(2)
            day = c1.date_input("Exit date", value=now_local.date())
            clock = c2.time_input("Exit time", value=now_local.time().replace(second=0, microsecond=0), step=60)
            submitted = st.form_submit_button("Close trade", type="primary")
        if submitted:
            if price is None:
                price = {"TP hit": tp, "SL hit": sl}.get(reason)
            exit_time = pd.Timestamp.combine(day, clock).tz_localize(tz).tz_convert("UTC")
            if price is None:
                st.error("Enter the exit price for a manual close.")
            elif exit_time < pd.Timestamp(t["entry_time"]).floor("min"):
                st.error("The exit time is before the entry time.")
            else:
                r, pnl = journal.trade_result(t["side"], entry, sl, float(price), float(t["risk_money"]))
                hold = max(0.0, (exit_time - pd.Timestamp(t["entry_time"])).total_seconds() / 60)
                try:
                    log.close(t["id"], journal.clean({
                        "status": "closed", "exit_time": exit_time.isoformat(), "exit_price": float(price),
                        "exit_reason": reason, "r_result": r, "pnl": pnl, "hold_minutes": hold,
                    }))
                except tradelog.TradeLogError as e:
                    st.error(f"Not saved: {e}")
                else:
                    st.session_state["_journal_msg"] = (
                        f"Closed {t['pair']} {t['side']}: {r:+.2f}R ({pnl:+,.2f} {config.ACCOUNT_CURRENCY}).")
                    st.rerun()

# ---------------- Closed and skipped ----------------
st.subheader("Closed and skipped")
if recent.empty:
    st.info("Nothing closed or skipped yet.")
else:
    rows = []
    for _, t in recent.iterrows():
        closed = t["status"] == "closed"
        tags = t.get("tags")
        rows.append({
            "Entry": local(t["entry_time"]).strftime("%d %b %H:%M"),
            "Pair": t["pair"], "Side": t["side"], "Status": t["status"],
            "Why": ", ".join(tags) if isinstance(tags, list) else "",
            "Exit": t.get("exit_reason") if closed else "",
            "R": float(t["r_result"]) if closed and pd.notna(t.get("r_result")) else None,
            f"P&L ({config.ACCOUNT_CURRENCY})": float(t["pnl"]) if closed and pd.notna(t.get("pnl")) else None,
            "Held (h)": float(t["hold_minutes"]) / 60 if closed and pd.notna(t.get("hold_minutes")) else None,
        })
    st.dataframe(
        pd.DataFrame(rows), hide_index=True, width="stretch",
        column_config={
            "R": st.column_config.NumberColumn(format="%+.2f"),
            f"P&L ({config.ACCOUNT_CURRENCY})": st.column_config.NumberColumn(format="%+.2f"),
            "Held (h)": st.column_config.NumberColumn(format="%.1f"),
        },
    )
    n_closed = int((recent["status"] == "closed").sum())
    st.caption(
        f"{n_closed} closed, {int((recent['status'] == 'skipped').sum())} skipped (latest 50 shown). "
        f"Win rate and pattern analysis unlock at {30} closed trades: fewer than that is mostly noise. "
        "To fix a mistake, edit the row in Supabase (Table Editor > trades)."
    )

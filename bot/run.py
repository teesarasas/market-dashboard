"""Signal bot: run every 10 minutes (cron). Checks the last closed 10m bars of every tradable instrument,
records new setups in Supabase and sends a Telegram alert when all alert conditions pass.

    python -m bot.run            normal run
    python -m bot.run --dry-run  print what it would send/record; sends and stores nothing
    python -m bot.run --test     send one test message to Telegram
    python -m bot.run --chat-id  print the chat ids that have messaged your bot
"""
import argparse
import os
import sys

import pandas as pd

import config
from bot import store, telegram
from data import fetch, tradelog
from indicators import daily, journal, signals, trend


def find_events(bars: dict, now: pd.Timestamp) -> list:
    smap = fetch.symbol_map()
    history = {n: daily.compute(trend.compute(df)) for n, df in bars.items() if len(df) > config.EMA_LENGTH}
    ccy = journal.currency_snapshot(history, smap) if history else {}
    events = []
    for name, ind in history.items():
        for kind, conds in (("setup", config.SIGNAL_RECORD_CONDITIONS), ("alert", config.SIGNAL_ALERT_CONDITIONS)):
            for t in signals.starts(ind, now, conds, config.SIGNAL_COOLDOWN_BARS, config.SIGNAL_LOOKBACK_BARS):
                events.append({"kind": kind, **signals.describe(name, smap[name][1], ind, t, ccy)})
    return events


def quiet(now: pd.Timestamp) -> bool:
    if not config.SIGNAL_QUIET_HOURS:
        return False
    start, end = config.SIGNAL_QUIET_HOURS
    h = now.tz_convert(config.DISPLAY_TZ).hour
    return start <= h < end if start < end else (h >= start or h < end)


def account_status(now: pd.Timestamp) -> dict:
    """Open trades, trades entered today and today's loss, from the trade log. Unknown -> None values.
    'Today' is the FTMO day: it starts at the 17:00 New York rollover (midnight FTMO server time)."""
    unknown = {"open": None, "trades_today": None, "loss_today_pct": None}
    try:
        log, _ = tradelog.get_log()
        if log is None:
            return unknown
        opened, recent = log.open_trades(), log.recent(50)
    except Exception:
        return unknown
    today = daily.trading_day(pd.DatetimeIndex([now])).iloc[0]
    rows = pd.concat([opened, recent], ignore_index=True)
    if rows.empty:
        return {"open": [], "trades_today": 0, "loss_today_pct": 0.0}
    entry = pd.to_datetime(rows["entry_time"], utc=True, format="mixed")
    rows = rows[(daily.trading_day(pd.DatetimeIndex(entry)).to_numpy() == today) & (rows["status"] != "skipped")]
    closed = rows[rows["status"] == "closed"]
    pnl = pd.to_numeric(closed.get("pnl"), errors="coerce").sum() if not closed.empty else 0.0
    balance = pd.to_numeric(rows.get("balance"), errors="coerce").dropna()
    loss_pct = max(0.0, -pnl / balance.iloc[0] * 100) if len(balance) else None
    return {"open": list(zip(opened.get("pair", []), opened.get("side", []))) if not opened.empty else [],
            "trades_today": len(rows), "loss_today_pct": loss_pct}


def to_row(e: dict, sent: bool) -> dict:
    snap = {k: v for k, v in e.items() if k not in ("kind", "symbol", "side", "bar_time", "price", "checks")}
    return journal.clean({"kind": e["kind"], "symbol": e["symbol"], "side": e["side"], "bar_time": e["bar_time"],
                          "price": e["price"], "checks": e["checks"], "snapshot": snap, "sent": sent})


def main(argv=None, now=None) -> int:
    p = argparse.ArgumentParser(description="Entry-signal bot")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--test", action="store_true")
    p.add_argument("--chat-id", action="store_true")
    args = p.parse_args(argv)
    token, chat = os.getenv("TELEGRAM_BOT_TOKEN"), os.getenv("TELEGRAM_CHAT_ID")

    if args.chat_id:
        for cid, who in telegram.chat_ids(token):
            print(f"{cid}  {who}")
        return 0
    if args.test:
        telegram.send(token, chat, "✅ Signal bot connected. Alerts will arrive here.")
        print("Test message sent.")
        return 0

    now = now or pd.Timestamp.now(tz="UTC")
    if daily.is_weekend(pd.DatetimeIndex([now])).iloc[0]:
        print(f"{now:%Y-%m-%d %H:%M} UTC: market closed, nothing to do")
        return 0

    bars, errors, fetched_at = fetch.fetch_10m(config.DATA_PROVIDER, config.SIGNAL_GROUPS)
    for name, msg in errors.items():
        print(f"fetch error {name}: {msg}", file=sys.stderr)
    events = find_events(bars, fetched_at)

    st = store.get_store(args.dry_run)
    try:
        known = st.known(fetched_at - pd.Timedelta(hours=3))
    except Exception as e:                       # can't de-duplicate: only look at the very last bar
        print(f"signals table unreachable ({e}); checking the last bar only", file=sys.stderr)
        known = set()
        last = max((e_["bar_time"] for e_ in events), default=None)
        events = [e_ for e_ in events if e_["bar_time"] == last]
    new = [e for e in events if store.key(e) not in known]

    rows, account = [], {}
    alerts = [e for e in new if e["kind"] == "alert"]
    if alerts:
        account = account_status(fetched_at)
    vendor_of = {n: v for n, (_, v) in fetch.symbol_map().items()}
    for e in new:
        sent = False
        if e["kind"] == "alert":
            text = signals.message(e, signals.rule_warnings(e, account, vendor_of))
            if args.dry_run:
                print(text, "\n")
            elif quiet(fetched_at) or signals.in_rollover_pause(e["bar_time"]):
                print(f"quiet hours / rollover: not sent {e['symbol']} {e['side']}")
            else:
                try:
                    telegram.send(token, chat, text)
                    sent = True
                except telegram.TelegramError as err:
                    print(err, file=sys.stderr)
        rows.append(to_row(e, sent))
    try:
        st.add(rows)
    except Exception as e:
        print(f"could not record signals: {e}", file=sys.stderr)

    print(f"{fetched_at:%Y-%m-%d %H:%M} UTC: {len(bars)} instruments, {len(new)} new "
          f"({len(alerts)} alert{'s' if len(alerts) != 1 else ''}), {len(errors)} fetch errors")
    return 0


if __name__ == "__main__":
    sys.exit(main())

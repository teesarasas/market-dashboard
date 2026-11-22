"""Entry signals on closed 10m bars, for the Telegram bot. Pure pandas — no Streamlit, no I/O.
Uses the same conditions as the Overview setup filter (indicators/screen.py), so the bot and the
dashboard can never disagree about what passes."""
import numpy as np
import pandas as pd

import config
from indicators import daily, screen, trend

BAR = pd.Timedelta(config.TIMEFRAME)


def bar_table(ind: pd.DataFrame) -> pd.DataFrame:
    """Indicator frame -> one row per bar with the Overview's column names, ready for screen.checks."""
    h1 = np.where(ind["ema_h1"].isna(), None, np.where(ind["close"] > ind["ema_h1"], "Above", "Below"))
    return pd.DataFrame({
        "State": ind["state"], "ADX": ind["adx"], "DI spread": ind["di_spread"],
        "ADR used %": ind["adr_used"], "Prev-day pos %": ind["prev_day_pos"], "H1 side": h1,
        "Score": ind["score"],
    }, index=ind.index)


def closed(ind: pd.DataFrame, now: pd.Timestamp) -> pd.DataFrame:
    """Only bars that have finished. A bar's label is its start time, so it closes at label + 10 minutes."""
    return ind[ind.index + BAR <= now]


def starts(ind: pd.DataFrame, now: pd.Timestamp, conditions, cooldown: int, lookback: int) -> list:
    """Closed bars (among the last `lookback`) where every condition passes and did not pass on any of the
    `cooldown` bars before. Empty when the data is stale."""
    c = closed(ind, now)
    if c.empty or now - (c.index[-1] + BAR) > pd.Timedelta(minutes=config.SIGNAL_MAX_BAR_AGE_MIN):
        return []
    ok = screen.checks(bar_table(c))[list(conditions)].all(axis=1)
    before = ok.shift(1, fill_value=False).astype(int).rolling(cooldown, min_periods=1).max().astype(bool)
    start = (ok & ~before).iloc[-lookback:]
    return list(start.index[start.to_numpy()])


def prev_day_close(ind: pd.DataFrame) -> pd.Series:
    day = daily.trading_day(ind.index)
    return day.map(daily.daily_ohlc(ind)["close"].shift(1))


def describe(name: str, vendor: str, ind: pd.DataFrame, t: pd.Timestamp, ccy: dict) -> dict:
    """Everything the alert shows and the signals table stores, for the bar starting at t."""
    from indicators import currency
    row = ind.loc[t]
    table = bar_table(ind.loc[[t]])
    d = int(screen.direction(table).iloc[0])
    passed = screen.checks(table).iloc[0].to_dict()
    pdc = prev_day_close(ind).loc[t]
    base, quote = currency.parse_pair(vendor)
    bought, sold = (base, quote) if d > 0 else (quote, base)
    return {
        "symbol": name, "side": "Long" if d > 0 else "Short", "bar_time": t,
        "price": row["close"], "state": row["state"], "adx": row["adx"], "di_spread": row["di_spread"],
        "adr_used": row["adr_used"], "prev_day_pos": row["prev_day_pos"], "score": row["score"],
        "natr": row["natr"], "atr_10m": row["atr"], "ema_h1": row["ema_h1"], "h1_side": table["H1 side"].iloc[0],
        "day_move_adr": d * (row["close"] - pdc) / row["adr"] if row["adr"] else np.nan,
        "checks": {k: bool(v) for k, v in passed.items()},
        "bought": bought, "bought_rank": ccy.get(bought, {}).get("rank"),
        "sold": sold, "sold_rank": ccy.get(sold, {}).get("rank"),
    }


def exposure(pair_vendor: str, side: str) -> tuple:
    """(currency bought, currency sold). XAU/USD long = buying gold, selling USD."""
    from indicators import currency
    base, quote = currency.parse_pair(pair_vendor)
    return (base, quote) if side == "Long" else (quote, base)


def rule_warnings(info: dict, account: dict, vendor_of: dict) -> list:
    """Your own limits, checked against the trade log. account: {"open": [(pair, side)], "trades_today": int,
    "loss_today_pct": float} (None values = unknown). Warns; never blocks."""
    out = []
    n_open = account.get("open")
    if n_open is None:
        return ["Open trades: unknown (trade log unreachable)"]
    if len(n_open) >= config.MAX_OPEN_TRADES:
        out.append(f"⚠️ Open trades: {len(n_open)} of {config.MAX_OPEN_TRADES}. Your limit is reached.")
    else:
        out.append(f"Open trades: {len(n_open)} of {config.MAX_OPEN_TRADES}")
    for pair, side in n_open:
        if pair == info["symbol"]:
            out.append(f"⚠️ You already have {pair} {side.lower()} open.")
            continue
        b, s = exposure(vendor_of.get(pair, pair), side)
        same = [c for c in ({b} & {info["bought"]}) | ({s} & {info["sold"]})]
        if same:
            verb = "long" if same[0] == info["bought"] else "short"
            out.append(f"⚠️ Same bet as your open {pair} {side.lower()}: both {verb} {same[0]}.")
    today = account.get("trades_today")
    if today is not None and today >= config.MAX_TRADES_PER_DAY:
        out.append(f"⚠️ Trades today: {today} of {config.MAX_TRADES_PER_DAY}. Daily limit reached.")
    loss = account.get("loss_today_pct")
    if loss is not None and loss >= config.DAILY_LOSS_STOP_PCT:
        out.append(f"⛔ Down {loss:.2f}% today: your {config.DAILY_LOSS_STOP_PCT:g}% daily stop is hit. No more trades.")
    return out


def in_rollover_pause(bar_time: pd.Timestamp) -> bool:
    start, end = config.SIGNAL_ROLLOVER_PAUSE_NY
    close = (bar_time + BAR).tz_convert(config.DAY_ROLLOVER_TZ).strftime("%H:%M")
    return start <= close < end


def _num(v, fmt):
    return "–" if v is None or (isinstance(v, float) and np.isnan(v)) else format(v, fmt)


def message(info: dict, warnings: list, tz: str = config.DISPLAY_TZ) -> str:
    """Plain-text Telegram message."""
    ok = lambda k: "✅" if info["checks"].get(k) else "❌"
    closes = (info["bar_time"] + BAR).tz_convert(tz)
    long = info["side"] == "Long"
    dec = 2 if info["price"] > 50 else 3 if info["price"] > 20 else 5
    lines = [
        f"{'🟢 LONG' if long else '🔴 SHORT'} {info['symbol']}",
        f"10m bar closed {closes:%H:%M} ({tz.split('/')[-1]}). Enter on the next bar.",
        f"Price {info['price']:.{dec}f}",
        f"{ok('adx')} ADX {_num(info['adx'], '.1f')} · {ok('di')} DI spread {_num(info['di_spread'], '+.0f')} · "
        f"{ok('trend')} {info['state']}",
        f"{ok('adr')} ADR used {_num(info['adr_used'], '.0f')}% · {ok('h1')} H1 {(info['h1_side'] or '–').lower()} "
        f"EMA{config.H1_EMA_LENGTH} · {ok('score')} Score {_num(info['score'], '+.1f')}",
        f"Moved today: {_num(info['day_move_adr'], '+.2f')} ADR from yesterday's close",
    ]
    if info.get("bought_rank") is not None and info.get("sold_rank") is not None:
        lines.append(f"Strength: {info['bought']} #{int(info['bought_rank'])} vs {info['sold']} #{int(info['sold_rank'])}")
    return "\n".join(lines + list(warnings))

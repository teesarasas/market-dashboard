"""Turns raw bars into indicator history + a one-row-per-symbol snapshot."""
import pandas as pd

import config
from indicators import daily, trend


def build(bars: dict, symbol_map: dict, now: pd.Timestamp):
    history, rows = {}, []

    for name, df in bars.items():
        if len(df) <= config.EMA_LENGTH:
            continue
        ind = daily.compute(trend.compute(df))
        history[name] = ind
        last = ind.iloc[-1]
        # The last 10m bar is still forming; its label is its start time
        age_min = (now - ind.index[-1]).total_seconds() / 60 - 10

        rows.append(
            {
                "Group": symbol_map[name][0],
                "Symbol": name,
                "Price": last["close"],
                "Side": "Above" if last["close"] > last["ema"] else "Below",
                "ADX": last["adx"],
                "+DI": last["plus_di"],
                "-DI": last["minus_di"],
                "State": last["state"],
                "Score": last["score"],
                "NATR": last["natr"],
                "ADR used %": last["adr_used"],
                "Prev-day zone": last["prev_day_zone"],
                "Prev-day pos %": last["prev_day_pos"],
                "EMA lag": bool(last["ema_lag"]),
                "Last bar (UTC)": ind.index[-1],
                "Stale": age_min > config.STALE_AFTER_MINUTES,
            }
        )

    snap = pd.DataFrame(rows)
    if not snap.empty:
        snap = snap.sort_values("Score", ascending=False, key=lambda s: s.abs())
    return history, snap.reset_index(drop=True)

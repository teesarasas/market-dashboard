"""Replay every closed trade in the trade log on 5m prices and compare exit rules (MAE/MFE study).
Run on the server, at a time that doesn't collide with the bot (e.g. :05 past the hour):

    .venv/bin/python -m research.replay              # prints the summary, saves replay_trades.csv
    .venv/bin/python -m research.replay --since 2026-11-02

Costs about 3-4 API credits per instrument traded (~100 for all 29), once.
"""
import argparse
import json
import math
import sys

import numpy as np
import pandas as pd

import config
from data import fetch, tradelog
from indicators import replay

pd.set_option("display.width", 160)


def load_trades(since=None) -> pd.DataFrame:
    log, problem = tradelog.get_log()
    if log is None:
        raise RuntimeError(f"Trade log unavailable: {problem}")
    if isinstance(log, tradelog.SupabaseLog):
        rows = log._send("GET", params={"status": "eq.closed", "order": "entry_time.asc", "limit": 5000})
        df = pd.DataFrame(rows)
    else:
        df = log._read()
        df = df[df["status"] == "closed"]
    if df.empty:
        return df
    df["entry_time"] = pd.to_datetime(df["entry_time"], utc=True, format="mixed")
    df["exit_time"] = pd.to_datetime(df["exit_time"], utc=True, format="mixed")
    df["snapshot"] = df["snapshot"].apply(lambda s: json.loads(s) if isinstance(s, str) else (s or {}))
    if since is not None:
        df = df[df["entry_time"] >= pd.Timestamp(since, tz="Asia/Bangkok")]
    return df.sort_values("entry_time").reset_index(drop=True)


def fetch_prices(pairs, first: pd.Timestamp):
    """5m bars for the traded pairs, far enough back to cover the first trade."""
    smap = fetch.symbol_map()
    vendors = {smap[p][1]: p for p in pairs if p in smap}
    days = (pd.Timestamp.now(tz="UTC") - first).days + 2
    pages = max(1, math.ceil(days / 17))                       # 5000 5m bars ≈ 17 calendar days
    provider = fetch.PROVIDERS[config.DATA_PROVIDER]
    key = fetch.get_api_key() if config.DATA_PROVIDER == "twelvedata" else None
    print(f"Fetching 5m prices: {len(vendors)} instruments x {pages} pages ≈ {len(vendors) * pages} credits…")
    raw, errors = provider.fetch_bars(list(vendors), key, "5min", config.OUTPUTSIZE, config.BATCH_SIZE, pages)
    for v, msg in errors.items():
        print(f"  price fetch failed for {vendors[v]}: {msg}", file=sys.stderr)
    return {vendors[v]: fetch.drop_weekend(df) for v, df in raw.items()}


def run(trades: pd.DataFrame, prices: dict):
    per_trade, long_rows = [], []
    for _, t in trades.iterrows():
        bars = prices.get(t["pair"])
        snap = t["snapshot"]
        if bars is None or pd.isna(t.get("sl")) or pd.isna(t.get("entry")):
            continue
        long = t["side"] == "Long"
        risk = abs(t["entry"] - t["sl"])
        if not risk:
            continue
        end = replay.horizon_end(t["entry_time"])
        path = replay.path_after(bars, t["entry_time"], end)
        if path.empty or path.index[0] - t["entry_time"] > pd.Timedelta(minutes=30):
            continue                                            # no price data right after entry
        mae, mfe = replay.excursions(path, long, t["entry"], risk, until=t["exit_time"])
        _, mfe_horizon = replay.excursions(path, long, t["entry"], risk)
        info = {"long": long, "entry": t["entry"], "sl": t["sl"], "tp": t["tp"],
                "atr_day": snap.get("atr_day"), "bands": snap.get("bands")}
        row = {"entry_time": t["entry_time"], "pair": t["pair"], "side": t["side"], "logged_exit": t["exit_reason"],
               "logged_R": t.get("r_result"), "MAE_R": mae, "MFE_R": mfe, "MFE_5d_R": mfe_horizon,
               "tp_R": abs(t["tp"] - t["entry"]) / risk if pd.notna(t.get("tp")) else np.nan,
               "stop_atr": risk / snap["atr_day"] if snap.get("atr_day") else np.nan}
        for name, (stop, target, be, trail, rk) in replay.variants(info).items():
            res = replay.simulate(path, long, t["entry"], stop, target, be, trail)
            r = replay.r_multiple(res, long, t["entry"], rk)
            long_rows.append({"rule": name, "R": r, "ambiguous": res.ambiguous})
            row[f"{name} | R"] = round(r, 2)
            row[f"{name} | exit"] = res.reason
        per_trade.append(row)
    return pd.DataFrame(per_trade), pd.DataFrame(long_rows)


def report(per: pd.DataFrame, long: pd.DataFrame):
    n = len(per)
    print(f"\nReplayed {n} trades on 5m mid prices (pessimistic when a bar hits both stop and target).\n")
    # sanity check: does the replay of your actual SL/TP agree with what really happened?
    hit = per[per["logged_exit"].isin(["TP hit", "SL hit"])]
    agree = (hit["logged_exit"].str[:2] == hit["Actual SL/TP | exit"]).mean() * 100 if len(hit) else np.nan
    print(f"Check: replayed SL/TP outcome matches your log on {agree:.0f}% of {len(hit)} TP/SL trades "
          f"(below ~85% means the vendor's prices differ too much from FTMO's to trust the rest).\n")
    print("EXIT RULES COMPARED (same entries):")
    print(replay.summarise(long).to_string(), "\n")
    win = per[per["logged_exit"] == "TP hit"]
    lose = per[per["logged_exit"] == "SL hit"]
    if len(win):
        q = win["MAE_R"].quantile([0.5, 0.75, 0.9]).round(2)
        print(f"WINNERS ({len(win)} TP hits): how far price went against you first (MAE, in R of your stop)")
        print(f"  half went no further than {q[0.5]}R · 75% no further than {q[0.75]}R · 90% no further than {q[0.9]}R")
        for lvl in (0.25, 0.5, 0.75):
            print(f"  a stop at {lvl}R would have killed {int((win['MAE_R'] >= lvl).sum())} of {len(win)} winners")
    if len(lose):
        print(f"\nLOSERS ({len(lose)} SL hits): how far they went in your favour before the stop (MFE, in R)")
        for lvl in (0.5, 1.0, 1.5):
            print(f"  reached +{lvl}R first: {int((lose['MFE_R'] >= lvl).sum())} of {len(lose)}")
        later = int((lose["MFE_5d_R"] >= lose["tp_R"]).sum())
        print(f"  stopped out, then price went on to reach your target (within the week): {later} of {len(lose)}")
    print("\nPer-trade detail saved to replay_trades.csv")


def main(argv=None):
    p = argparse.ArgumentParser(description="Replay trades under different exit rules")
    p.add_argument("--since", help="only trades entered on/after this date (Bangkok), e.g. 2026-11-02")
    args = p.parse_args(argv)
    trades = load_trades(args.since)
    if trades.empty:
        print("No closed trades found.")
        return 0
    prices = fetch_prices(sorted(trades["pair"].unique()), trades["entry_time"].min())
    per, long = run(trades, prices)
    if per.empty:
        print("No trade could be replayed (no price data around the entries).")
        return 1
    per.to_csv("replay_trades.csv", index=False)
    report(per, long)
    return 0


if __name__ == "__main__":
    sys.exit(main())

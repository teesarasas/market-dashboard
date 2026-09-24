"""Checks every symbol in config.py against your Twelve Data plan.

Run:  python check_symbols.py
"""
import os
import sys

import requests
from dotenv import load_dotenv

import config

load_dotenv()
KEY = os.getenv("TWELVEDATA_API_KEY")
if not KEY:
    sys.exit("TWELVEDATA_API_KEY not found. Create a .env file first (see .env.example).")

ok, failed = [], []
for group, items in config.SYMBOLS.items():
    for name, sym in items.items():
        r = requests.get(
            "https://api.twelvedata.com/time_series",
            params={"symbol": sym, "interval": "5min", "outputsize": 3,
                    "timezone": "UTC", "apikey": KEY},
            timeout=30,
        ).json()
        if r.get("status") == "ok":
            last = r["values"][0]
            ok.append((group, name, sym, last["datetime"], last["close"]))
            print(f"OK    {name:8} {sym:10} last {last['datetime']}  close {last['close']}")
        else:
            failed.append((group, name, sym, r.get("message", "")))
            print(f"FAIL  {name:8} {sym:10} {r.get('message', '')[:90]}")

print(f"\n{len(ok)} ok, {len(failed)} failed")
if failed:
    print("\nFor failed symbols, search the right name with:")
    print("  https://api.twelvedata.com/symbol_search?symbol=DAX")
    print("then update config.py.")

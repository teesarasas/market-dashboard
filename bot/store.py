"""Where signals are recorded: Supabase in production, a CSV file in demo mode, nowhere in a dry run."""
import os

import pandas as pd

import config
from data import tradelog


def key(row) -> tuple:
    return row["symbol"], pd.Timestamp(row["bar_time"]), row["kind"]


class SupabaseSignals(tradelog.SupabaseLog):
    def __init__(self, url, key_, http=None):
        super().__init__(url, key_, table=config.SIGNAL_TABLE, session=http)

    def known(self, since: pd.Timestamp) -> set:
        rows = self._send("GET", params={"select": "symbol,bar_time,kind", "bar_time": f"gte.{since.isoformat()}"})
        return {key(r) for r in rows}

    def add(self, rows: list):
        if rows:
            self._send("POST", body=rows, prefer="return=minimal")


class CsvSignals:
    def __init__(self, path):
        self.path = path

    def _read(self):
        return pd.read_csv(self.path) if os.path.exists(self.path) else pd.DataFrame()

    def known(self, since):
        df = self._read()
        return set() if df.empty else {key(r) for r in df.to_dict("records")
                                       if pd.Timestamp(r["bar_time"]) >= since}

    def add(self, rows):
        if rows:
            new = pd.DataFrame([{k: (str(v) if isinstance(v, (dict, list)) else v) for k, v in r.items()}
                                for r in rows])
            pd.concat([self._read(), new], ignore_index=True).to_csv(self.path, index=False)


class DryRun:
    def known(self, since):
        return set()

    def add(self, rows):
        print(f"[dry run] would record {len(rows)} signal(s)")


def get_store(dry_run: bool):
    if dry_run:
        return DryRun()
    if config.DATA_PROVIDER == "demo":
        return CsvSignals(config.SIGNAL_DEMO_FILE)
    url, k = os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY")
    if not url or not k:
        raise RuntimeError("SUPABASE_URL and SUPABASE_KEY must be set (in .env on the server)")
    return SupabaseSignals(url, k)

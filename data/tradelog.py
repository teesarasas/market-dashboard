"""Trade log storage. Supabase in production (REST API via requests), a CSV file in demo mode.
Pages call get_log(); they never talk to Supabase directly."""
import json
import os
import uuid

import pandas as pd
import requests
import streamlit as st

import config


class TradeLogError(RuntimeError):
    pass


class SupabaseLog:
    """Talks to Supabase's REST API. New-style keys (sb_secret_...) go only in the apikey header, as Supabase
    requires; legacy JWT keys (eyJ...) also go in Authorization, as before."""

    def __init__(self, url: str, key: str, table: str = config.JOURNAL_TABLE, session=None):
        self.base = f"{url.rstrip('/')}/rest/v1/{table}"
        self.headers = {"apikey": key, "Content-Type": "application/json"}
        if key.startswith("eyJ"):
            self.headers["Authorization"] = f"Bearer {key}"
        self.http = session or requests.Session()

    def _send(self, method, params=None, body=None, prefer=None):
        headers = dict(self.headers)
        if prefer:
            headers["Prefer"] = prefer
        r = self.http.request(method, self.base, params=params, json=body, headers=headers, timeout=15)
        if r.status_code >= 300:
            raise TradeLogError(f"Supabase {r.status_code}: {r.text[:300]}")
        return r.json() if r.text else []

    def ping(self):
        self._send("GET", params={"select": "id", "limit": 1})
        return True

    def add(self, row: dict) -> str:
        data = self._send("POST", body=row, prefer="return=representation")
        return data[0]["id"]

    def open_trades(self) -> pd.DataFrame:
        return pd.DataFrame(self._send("GET", params={"status": "eq.open", "order": "entry_time.desc"}))

    def recent(self, limit: int = 50) -> pd.DataFrame:
        return pd.DataFrame(self._send("GET", params={"status": "neq.open", "order": "entry_time.desc",
                                                      "limit": limit}))

    def close(self, trade_id: str, fields: dict):
        data = self._send("PATCH", params={"id": f"eq.{trade_id}"}, body=fields, prefer="return=representation")
        if len(data) != 1:
            raise TradeLogError(f"Expected to update 1 trade, updated {len(data)}")


class CsvLog:
    """Same interface, one CSV file. Demo mode only: on Streamlit Cloud the file would not survive a restart."""

    def __init__(self, path: str):
        self.path = path

    def _read(self) -> pd.DataFrame:
        if not os.path.exists(self.path):
            return pd.DataFrame()
        df = pd.read_csv(self.path, dtype={"id": str})
        for col in ("tags", "snapshot"):
            if col in df:
                df[col] = df[col].apply(lambda s: json.loads(s) if isinstance(s, str) else s)
        return df

    def _write(self, df: pd.DataFrame):
        out = df.copy()
        for col in ("tags", "snapshot"):
            if col in out:
                out[col] = out[col].apply(json.dumps)
        out.to_csv(self.path, index=False)

    def ping(self):
        return True

    def add(self, row: dict) -> str:
        row = dict(row, id=str(uuid.uuid4()), created_at=pd.Timestamp.now(tz="UTC").isoformat())
        df = self._read()
        self._write(pd.concat([df, pd.DataFrame([row])], ignore_index=True))
        return row["id"]

    def open_trades(self) -> pd.DataFrame:
        df = self._read()
        return df[df["status"] == "open"].sort_values("entry_time", ascending=False) if not df.empty else df

    def recent(self, limit: int = 50) -> pd.DataFrame:
        df = self._read()
        if df.empty:
            return df
        return df[df["status"] != "open"].sort_values("entry_time", ascending=False).head(limit)

    def close(self, trade_id: str, fields: dict):
        df = self._read()
        hit = df["id"] == trade_id
        if hit.sum() != 1:
            raise TradeLogError(f"Expected to update 1 trade, found {hit.sum()}")
        for k, v in fields.items():
            if k not in df:
                df[k] = None
            df[k] = df[k].astype(object)
            df.loc[hit, k] = v
        self._write(df)


def _secret(env_name: str, section: str, key: str):
    value = os.getenv(env_name)
    if value:
        return value
    try:
        return st.secrets[section][key]
    except Exception:
        return None


def get_log():
    """(log, problem). Demo mode -> CSV file. Real data -> Supabase, or (None, reason) if not configured."""
    if config.DATA_PROVIDER == "demo":
        return CsvLog(config.JOURNAL_DEMO_FILE), None
    url = _secret("SUPABASE_URL", "supabase", "url")
    key = _secret("SUPABASE_KEY", "supabase", "key")
    if not url or not key:
        return None, ("Trade log not set up: add SUPABASE_URL and SUPABASE_KEY to .env (local) "
                      "or a [supabase] section to Streamlit Secrets.")
    return SupabaseLog(url, key), None

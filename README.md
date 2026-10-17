# Market dashboard

Trend filter across FX majors, crosses, and gold on 10-minute bars:
price vs EMA120, ADX regime with hysteresis, and a strength score (ATRs from EMA).

## Run locally

1. Create a virtual environment and install packages

   macOS / Linux:
   ```
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```
   Windows:
   ```
   python -m venv .venv
   .venv\Scripts\activate
   pip install -r requirements.txt
   ```

2. Add your API key: copy `.env.example` to `.env` and paste your Twelve Data key.

3. Check symbol coverage on your plan:
   ```
   python check_symbols.py
   ```
   Fix any failed symbols in `config.py` (use the symbol_search link it prints).

4. Start the dashboard:
   ```
   streamlit run app.py
   ```
   It opens at http://localhost:8501

To test the UI without spending API credits, set `DATA_PROVIDER = "demo"` in `config.py`.

## Project layout

- `config.py` — symbols, thresholds, all settings
- `data/providers/` — one file per data vendor
- `data/fetch.py` — fetches, drops weekend filler bars, resamples 5m to 10m, caches for 10 minutes
- `indicators/trend.py` — EMA, ADX/DI, ATR, NATR, regime, state, EMA lag (no Streamlit, reusable for backtests)
- `indicators/daily.py` — FX trading day (17:00 New York rollover), ADR, previous-day range
- `indicators/currency.py` — currency strength and breadth from FX pair scores
- `indicators/risk.py` — position sizing, ATR-scaled distribution bands, R targets (reusable by the robot)
- `indicators/metrics.py` — metrics available on the Market map axes
- `indicators/snapshot.py` — latest values per symbol
- `indicators/journal.py` — trade-log snapshot and results (pure)
- `data/tradelog.py` — trade-log storage: Supabase (REST) or a demo CSV file
- `sql/trades.sql` — the Supabase table
- `pages/` — Overview, Market map, Symbol, Currencies, Risk calculator, Trade log
- `tests/` — run with `python -m pytest` (install `requirements-dev.txt` first)

## API usage

Each refresh costs `SOURCE_PAGES` credits per symbol (2 pages of 5m bars give ~26 FX trading
days for the daily metrics). Groups in `GROUP_PAGES` use fewer: the 7 gold crosses take 1 each,
since only the Currencies page uses them. Default: 29 x 2 + 7 x 1 = 65 credits per refresh.
The Risk calculator also fetches 1h bars once per trading day for the distribution bands
(29 credits a day). Data is cached for 10 minutes,
so reloading the page doesn't spend credits. "Refresh data" forces a new fetch.

## Trade log (Supabase)

"Log trade" on the Risk calculator saves the trade plus every dashboard value at that moment;
the Trade log page closes it. In demo mode it writes to `trade_log_demo.csv` instead.

1. Create a free project at supabase.com.
2. SQL Editor > New query: paste `sql/trades.sql` and Run.
3. Settings > API Keys: copy the Project URL and create a **Secret key** (`sb_secret_...`).
   Never put the secret key in the repo.
4. Streamlit Cloud: app > Settings > Secrets, add
   ```
   [supabase]
   url = "https://YOUR-PROJECT.supabase.co"
   key = "sb_secret_..."
   ```
5. Running locally: add `SUPABASE_URL=...` and `SUPABASE_KEY=...` lines to `.env`.
6. Open the Trade log page: it should say "Stored in Supabase".


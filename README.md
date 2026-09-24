# Market dashboard

Trend filter across FX majors, crosses, and metals on 10-minute bars:
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
- `indicators/metrics.py` — metrics available on the Market map axes
- `indicators/snapshot.py` — latest values per symbol
- `pages/` — Overview, Market map, Symbol, Currencies
- `tests/` — run with `python -m pytest` (install `requirements-dev.txt` first)

## API usage

Each refresh costs `SOURCE_PAGES` credits per symbol (2 x 15 = 30 by default; two pages of
5m bars give ~26 FX trading days for the daily metrics). Data is cached for 10 minutes,
so reloading the page doesn't spend credits. "Refresh data" forces a new fetch.

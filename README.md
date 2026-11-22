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
- `sql/trades.sql` — the Supabase trade table; `sql/signals.sql` — the signal bot's table
- `indicators/signals.py` — entry signals on closed 10m bars (same conditions as the Overview filter)
- `bot/` — the Telegram signal bot (`bot/run.py`), its Telegram client and storage
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

## Telegram signal bot

Every 10 minutes the bot checks the last closed 10m bar of the 29 tradable instruments (58 credits per run).

- **Alert** (Telegram): a bar closes with every condition in `SIGNAL_ALERT_CONDITIONS` passing (ADX > 25,
  DI spread ≥ 20 with the trend, State Trend up/down, ADR used ≥ 50%, H1 price on the trend side of EMA120,
  Score ≥ 3 with the trend) after they had failed for the previous hour. Enter on the next bar.
  The Overview's setup filter ticks the same conditions by default.
- **Setup** (recorded silently in Supabase): ADX, DI spread and Trend pass. Each row stores whether ADR, H1 and
  Score passed too, so we can later measure whether those conditions earn their place.
- The alert checks your own limits against the trade log and warns (never blocks): open trades vs
  `MAX_OPEN_TRADES`, the same pair already open, an open trade that is the same currency bet,
  trades today vs `MAX_TRADES_PER_DAY`, and today's loss vs `DAILY_LOSS_STOP_PCT` (FTMO day, 17:00 New York).
- No alerts for bars closing 16:50-18:00 New York (`SIGNAL_ROLLOVER_PAUSE_NY`): spreads blow out at the rollover.
- Nothing runs while the FX market is closed (Friday 17:00 to Sunday 17:00 New York).

### One-time setup

1. Supabase: run `sql/signals.sql` (SQL Editor > New query > Run).
2. Telegram: create a new bot with @BotFather and copy its token. Send your new bot any message.
3. Server: any small Linux server (Ubuntu 24.04, smallest plan, Singapore region is fine).
   ```
   sudo apt update && sudo apt install -y python3-venv git
   ssh-keygen -t ed25519 -f ~/.ssh/id_ed25519 -N ""      # then add ~/.ssh/id_ed25519.pub to the GitHub repo:
                                                          # Settings > Deploy keys > Add (read-only)
   git clone git@github.com:teesarasas/market-dashboard.git
   cd market-dashboard
   python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
   nano .env        # TWELVEDATA_API_KEY=...  SUPABASE_URL=...  SUPABASE_KEY=...  TELEGRAM_BOT_TOKEN=...
   chmod 600 .env
   .venv/bin/python -m bot.run --chat-id     # prints your chat id; add TELEGRAM_CHAT_ID=... to .env
   .venv/bin/python -m bot.run --test        # a test message should arrive in Telegram
   .venv/bin/python -m bot.run --dry-run     # prints what it would send; sends and stores nothing
   ```
4. Schedule it (server clock is UTC; runs at :01, :11, :21 ... one minute after each 10m bar closes):
   ```
   crontab -e
   1-59/10 * * * * cd ~/market-dashboard && .venv/bin/python -m bot.run >> ~/signals.log 2>&1
   ```
5. After you push changes: `cd ~/market-dashboard && git pull`.

The `.env` on the server is separate from your PC's and is never committed.

# Market dashboard — v2 implementation plan

Instructions for Claude Code. Read the whole file before starting. Work task by task,
in order, and commit after each task passes its acceptance criteria.

## Context

A Streamlit dashboard used as a trend filter for intraday FX trading (FTMO challenge).
It ranks 15 instruments (FX majors, FX crosses, XAU/USD, XAG/USD) on 10-minute bars
using price vs EMA120, ADX(14) with hysteresis, +DI/−DI, and an ATR-normalised score.

### Current structure (v1)

```
app.py                        # st.navigation entry point
config.py                     # symbols, thresholds, all settings
ui.py                         # shared load() + sidebar, state colours
data/fetch.py                 # provider routing, 5m -> 10m resample, st.cache_data
data/providers/               # twelvedata_provider.py, demo_provider.py
indicators/trend.py           # EMA, Wilder ADX/DI, ATR, regime, state (pure pandas)
indicators/snapshot.py        # per-symbol history + latest snapshot table
pages/overview.py             # ranking table
pages/market_map.py           # ADX vs Score scatter with trails
check_symbols.py              # validates symbols against Twelve Data
```

### Rules

- `indicators/` stays pure pandas/numpy. No Streamlit imports there. It will be reused for backtests.
- Pages never call a data vendor directly. All data goes through `data/fetch.py`.
- Every threshold, window, and length goes in `config.py`. No magic numbers in pages or indicators.
- Never read, print, modify, or commit `.env`.
- Use `width="stretch"`, not the deprecated `use_container_width`.
- Test the UI with `DATA_PROVIDER = "demo"` to avoid spending API credits. Restore `"twelvedata"` when done.
- Environment is Windows. The Python launcher is `py`; inside the activated `.venv`, `python` works.
- Indices were removed from `config.SYMBOLS` because Twelve Data has no usable index data. Do not re-add them in v2.

## Task 1 — Data history for daily metrics

ADR needs ~15 complete trading days. Current `OUTPUTSIZE = 1200` 5m bars is ~4 days.

- Set `OUTPUTSIZE = 5000` in `config.py` (Twelve Data's maximum; ~17 days of 5m bars).
- Check in the Twelve Data docs that credits are charged per symbol, not per bar. If larger
  outputsize costs more credits, stop and report before continuing.
- Make sure the demo provider generates enough bars for this too.

**Acceptance:** each symbol's 10m history covers at least 15 FX trading days. Page load time stays reasonable (report it).

## Task 2 — New per-symbol metrics

Create `indicators/daily.py` and extend `indicators/snapshot.py`.

### 2a. FX trading day
The FX day rolls over at **17:00 America/New_York** (handles DST). Implement
`trading_day(index) -> Series of dates`: convert to New York time, shift by −17h, take the date.
Aggregate 10m bars into daily OHLC with this key. Drop weekend days with no bars.

### 2b. NATR
`natr = atr / close * 100` (ATR as already computed in `trend.compute`).

### 2c. ADR used
- `ADR` = mean of (high − low) over the last `ADR_DAYS = 14` **complete** trading days (exclude today).
- `ADR used %` = today's (high − low) so far / ADR × 100. Can exceed 100.

### 2d. Position vs previous day's range
- `PDH`, `PDL` = previous complete trading day's high and low.
- `Prev-day pos %` = (close − PDL) / (PDH − PDL) × 100. Below 0 = under PDL, above 100 = over PDH.
- `Prev-day zone` label: `"Above PDH"`, `"Below PDL"`, or `"Inside"`.

### 2e. EMA lag flag
Flags when price has crossed the EMA but the EMA itself still slopes the other way
(an early turn or a pullback against the slower trend).
- `ema_slope_atr = (ema − ema.shift(SLOPE_BARS)) / atr`, `SLOPE_BARS = 10`.
- Flag is true when sign(close − ema) != sign(ema_slope_atr) and `abs(ema_slope_atr) > SLOPE_MIN_ATR` (`0.1`).
- Snapshot column: `EMA lag` (bool). Show as a short marker in the table, not a colour fill.

Add all new settings (`ADR_DAYS`, `DAY_ROLLOVER_TZ`, `DAY_ROLLOVER_HOUR`, `SLOPE_BARS`, `SLOPE_MIN_ATR`) to `config.py`.

Add to Overview table: `NATR`, `ADR used %`, `Prev-day zone`, `Prev-day pos %`, `EMA lag`.
Format percentages with no decimals. Colour `ADR used %` ≥ 90 in amber (little room left).

**Acceptance:** unit tests (Task 6) pass; Overview shows the new columns with sensible values on demo and real data.

## Task 3 — Symbol detail page

New page `pages/symbol.py`, registered in `app.py` as "Symbol".

- Symbol selector (selectbox). Selected symbol stored in `st.session_state["symbol"]`.
- Plotly figure with shared x-axis, two rows:
  - Row 1: 10m candlesticks + EMA120 line + horizontal lines for PDH and PDL.
  - Row 2: ADX, +DI, −DI, with horizontal lines at `ADX_TREND_ON`, `ADX_TREND_OFF`, `ADX_RANGE_ON`.
- Show the last `DETAIL_BARS = 300` bars by default. Hide weekend gaps (Plotly rangebreaks).
- Above the chart: current state, Score, ADX, ADR used %, Prev-day zone, EMA lag.
- Navigation into this page:
  - Overview: make the table row-selectable (`st.dataframe(..., on_select="rerun", selection_mode="single-row")`); selecting a row sets the session symbol and offers a button to open the Symbol page (`st.switch_page`).
  - Market Map: `st.plotly_chart(..., on_select="rerun")`; clicking a dot does the same.
  - Note: the Overview table uses a pandas Styler. If selection doesn't work with Styler, switch that table to `column_config` formatting instead.

**Acceptance:** selecting a symbol from Overview or Market Map opens its detail chart; the chart matches the table values for the latest bar.

## Task 4 — Currency strength and breadth

New module `indicators/currency.py` (pure pandas) and page `pages/currency.py` ("Currencies").

### Strength
- Use FX pairs only (exclude metals). Parse base and quote from the vendor symbol (`EUR/USD`).
- For each pair and each bar: base gets `+score`, quote gets `−score`.
- Currency strength per bar = mean of its contributions across all pairs containing it.
- Align pairs on the common 10m index (outer join, forward-fill at most 1 bar, drop rows with too few pairs).

### Breadth
- For currency C, a pair counts in C's favour if its state is `Trend up` and C is the base,
  or `Trend down` and C is the quote.
- Breadth = count in favour / number of pairs containing C. Also report counts against C.

### Page
- Bar chart: current strength per currency, sorted.
- Line chart: strength per currency over the last `CURRENCY_HISTORY_BARS = 144` bars (24h).
- Table: currency, strength, pairs in favour, pairs against, total pairs.
- Show a visible note when a currency is covered by fewer than 3 pairs. With the current symbol list,
  CAD, CHF, and NZD appear in only one pair each, so their strength is just one pair's score.
  Do not add symbols to fix this; just show the coverage.

**Acceptance:** unit test with synthetic scores confirms the decomposition signs; page renders on demo data.

## Task 5 — Configurable Market Map

Refactor `pages/market_map.py`.

- A metric registry (dict in one place, e.g. `indicators/metrics.py` or top of the page) mapping display
  name → history column: ADX, Score, NATR, ADR used %, Prev-day pos %, EMA slope (ATR).
  Metrics used as axes need a per-bar history column so trails work.
- Selectors for X axis, Y axis, and Colour. Defaults: X = ADX, Y = Score, Colour = State (categorical).
  Numeric colour metrics use a continuous colour scale with a colour bar.
- Draw ADX regime lines and zones only when X is ADX. Draw the zero line only when Y is Score or EMA slope.
- Keep trails, hover details, the asset-class filter, and the hide-neutral toggle.

**Acceptance:** every axis combination renders without errors; default view matches v1.

## Task 6 — Tests

Add `tests/` with pytest (add `pytest` to a `requirements-dev.txt`, not `requirements.txt`).

- `trading_day`: bars at 16:50 and 17:00 New York time fall on different trading days, in both summer and winter time.
- ADR excludes today and uses only complete days.
- Prev-day zone labels at, above, and below the range.
- EMA lag flag on a constructed series.
- Currency decomposition: EUR/USD score +2 and USD/JPY score +1 → EUR +2, JPY −1, USD mean of (−2, +1).
- Existing `adx_regime` hysteresis: crossing 30 enters trend; staying above 25 keeps it; dropping below 25 exits.

**Acceptance:** `python -m pytest` passes.

## Out of scope for v2

Backtesting, indices via yfinance, currency RRG, session ranges, scanner recipes, alert bot, COT data,
deployment. These are planned for later versions. Do not start them.

## When finished

Report: what changed per task, test results, page load time with real data, and any deviations from this plan with reasons.

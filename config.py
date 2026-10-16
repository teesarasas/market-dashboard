"""All settings live here. Edit this file, not the code."""

# "twelvedata" = real data (needs TWELVEDATA_API_KEY)
# "demo"       = synthetic data, no key needed (for testing the UI)
DATA_PROVIDER = "twelvedata"

# Display name -> Twelve Data symbol, grouped by asset class.
# Run `python check_symbols.py` to confirm every symbol works on your plan.
# If an index fails, try the alternatives noted beside it.
SYMBOLS = {
    "FX majors": {
        "EURUSD": "EUR/USD",
        "GBPUSD": "GBP/USD",
        "USDJPY": "USD/JPY",
        "AUDUSD": "AUD/USD",
        "USDCAD": "USD/CAD",
        "USDCHF": "USD/CHF",
        "NZDUSD": "NZD/USD",
    },
    "FX crosses": {
        # EUR
        "EURGBP": "EUR/GBP",
        "EURJPY": "EUR/JPY",
        "EURAUD": "EUR/AUD",
        "EURNZD": "EUR/NZD",
        "EURCAD": "EUR/CAD",
        "EURCHF": "EUR/CHF",
        # GBP
        "GBPJPY": "GBP/JPY",
        "GBPAUD": "GBP/AUD",
        "GBPNZD": "GBP/NZD",
        "GBPCAD": "GBP/CAD",
        "GBPCHF": "GBP/CHF",
        # AUD
        "AUDJPY": "AUD/JPY",
        "AUDNZD": "AUD/NZD",
        "AUDCAD": "AUD/CAD",
        "AUDCHF": "AUD/CHF",
        # NZD
        "NZDJPY": "NZD/JPY",
        "NZDCAD": "NZD/CAD",
        "NZDCHF": "NZD/CHF",
        # CAD and CHF
        "CADJPY": "CAD/JPY",
        "CADCHF": "CAD/CHF",
        "CHFJPY": "CHF/JPY",
    },
    "Metals": {
        "XAUUSD": "XAU/USD",
    },
    # Gold priced in each currency, so XAU gets 8 pairs on the Currencies page.
    # Not traded; hidden from Overview and Market map by default (HIDDEN_GROUPS).
    "Gold crosses": {
        "XAUEUR": "XAU/EUR",
        "XAUGBP": "XAU/GBP",
        "XAUJPY": "XAU/JPY",
        "XAUCHF": "XAU/CHF",
        "XAUAUD": "XAU/AUD",
        "XAUNZD": "XAU/NZD",
        "XAUCAD": "XAU/CAD",
    },
}
HIDDEN_GROUPS = ["Gold crosses"]   # not ticked in the sidebar filter by default

# --- Data ---
SOURCE_INTERVAL = "5min"     # Twelve Data has no 10min; we resample
TIMEFRAME = "10min"          # the timeframe all indicators run on
OUTPUTSIZE = 5000            # 5m bars per request (Twelve Data max)
SOURCE_PAGES = 2             # requests per symbol, walking back in time (~26 FX days)
                             # Twelve Data fills weekends with flat bars; those are dropped
GROUP_PAGES = {"Gold crosses": 1}  # groups that need less history (no daily metrics): 1 credit each
CACHE_TTL_SECONDS = 600      # refetch at most every 10 minutes
BATCH_SIZE = 8               # symbols per API request (1 credit each, per page)
STALE_AFTER_MINUTES = 30     # flag a symbol if its last bar is older than this

# FX trading day rolls over at 17:00 New York time (DST handled by the tz)
DAY_ROLLOVER_TZ = "America/New_York"
DAY_ROLLOVER_HOUR = 17

# --- Indicators ---
EMA_LENGTH = 120
ADX_LENGTH = 14
ATR_LENGTH = 14

# ADX regime with hysteresis (stops flickering around the thresholds)
ADX_TREND_ON = 30    # enter trend state above this
ADX_TREND_OFF = 25   # leave trend state below this
ADX_RANGE_ON = 20    # enter range state below this
ADX_RANGE_OFF = 23   # leave range state above this

# Direction needs clear DI dominance, not just +DI above -DI.
# DI spread = 100 x (+DI - -DI) / (+DI + -DI), from -100 to +100.
# Trend up needs spread >= this; Trend down needs spread <= minus this. 0 = the old +DI vs -DI rule.
DI_SPREAD_MIN = 20

# EMA lag flag: price crossed the EMA but the EMA still slopes the other way
SLOPE_BARS = 10        # EMA slope measured over this many bars
SLOPE_MIN_ATR = 0.1    # ignore slopes flatter than this (in ATRs)

# --- Daily metrics ---
ADR_DAYS = 14          # average daily range over this many complete trading days
ADR_USED_WARN = 90     # ADR used % at or above this is highlighted (little room left)

# --- Symbol page ---
DETAIL_BARS = 300    # bars shown on the detail chart

# --- Currencies ---
CURRENCY_GROUPS = ["FX majors", "FX crosses"]   # groups used for strength (no metals)
CURRENCY_METAL_GROUPS = ["Metals", "Gold crosses"]  # shown beside the currencies, kept out of their strength
CURRENCY_MIN_PAIR_SHARE = 0.8   # drop bars where fewer than this share of pairs have a score
CURRENCY_HISTORY_BARS = 144     # 144 x 10m = 24h on the strength chart
CURRENCY_MIN_COVERAGE = 3       # warn when a currency appears in fewer pairs than this
# Record high %: share of a currency's pair breakouts that go its way
RECORD_LOOKBACK_BARS = 144      # a "new high" breaks the highest high of the previous 144 bars (24h)
RECORD_WINDOW_BARS = 6          # count a pair's most recent breakout within the last 6 bars (1h)
GRID_SCORE_CLIP = 4             # currency grid: scores beyond +/-4 ATR show at full colour

# --- Market Map ---
TRAIL_BARS = 12      # 12 x 10m = last 2 hours

# --- Risk calculator ---
ACCOUNT_CURRENCY = "USD"
RISK_DEFAULT_BALANCE = 100_000   # used when the URL has no ?balance=
RISK_DEFAULT_PCT = 0.25          # used when the URL has no ?risk=
RISK_MAX_PCT = 0.33              # warn above this (plan: 0.25-0.33% per trade)
RISK_GROUPS = ["FX majors", "FX crosses", "Metals"]   # instruments you can size
RISK_TARGETS_R = [1, 2, 3]       # take-profit levels shown, in multiples of the stop distance
# Contract specs: ASSUMED until checked in FTMO MT5 (right-click symbol > Specification)
SPECS_CONFIRMED = False
FX_CONTRACT_SIZE = 100_000       # units of the base currency per lot
CONTRACT_SIZES = {"XAU/USD": 100}   # ounces per lot
PIP_SIZES = {"XAU/USD": 0.1}     # FX: 0.0001, JPY quote: 0.01 (automatic)
LOT_STEP = 0.01
MIN_LOT = 0.01
# Distribution stop (same method as the updated TradingView "Prev-Day Range -> Next-Day Distribution"
# indicator): percentiles of how far each past day went above / below the previous close,
# measured in daily ATRs and re-sized by today's ATR.
DIST_INTERVAL = "1h"          # daily bars are built from 1h bars (17:00 New York days)
DIST_OUTPUTSIZE = 5000        # ~145 trading days of 1h bars; 1 credit per symbol, fetched once per trading day
DIST_LOOKBACK = 100           # days in the sample
DIST_MIN_SAMPLE = 20          # no bands with fewer days than this
DIST_PERCENTILES = [25, 50, 75, 90]
DIST_ANCHOR = "close"         # "close" = previous day's close (indicator default), "open" = today's open
DIST_SCALE_DAYS = 20          # ATR used for scaling: simple mean of the last 20 daily true ranges
DIST_ATR_DAYS = 14            # daily ATR shown beside the stop, and used by the ATR stop
# ATR stop (experiment): source -> default multiplier
ATR_STOP_DEFAULT_MULT = {"Daily ATR(14)": 0.5, "10-min ATR(14)": 3.0}

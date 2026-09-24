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
        "EURJPY": "EUR/JPY",
        "GBPJPY": "GBP/JPY",
        "EURGBP": "EUR/GBP",
        "AUDJPY": "AUD/JPY",
        "EURAUD": "EUR/AUD",
        "GBPAUD": "GBP/AUD",
    },
    "Metals": {
        "XAUUSD": "XAU/USD",
        "XAGUSD": "XAG/USD",
    },
}

# --- Data ---
SOURCE_INTERVAL = "5min"     # Twelve Data has no 10min; we resample
TIMEFRAME = "10min"          # the timeframe all indicators run on
OUTPUTSIZE = 5000            # 5m bars per request (Twelve Data max)
SOURCE_PAGES = 2             # requests per symbol, walking back in time (~26 FX days)
                             # Twelve Data fills weekends with flat bars; those are dropped
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

# --- Market Map ---
TRAIL_BARS = 12      # 12 x 10m = last 2 hours

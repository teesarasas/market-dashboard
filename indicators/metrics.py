"""Metrics that can be plotted per bar. Display name -> history column and how to show it.

signed: centred on zero (symmetric axis, diverging colours, zero line on Y).
"""
METRICS = {
    "ADX": {"column": "adx", "label": "ADX (trend strength)", "fmt": ".1f", "signed": False},
    "Score": {"column": "score", "label": "Score (ATRs from EMA)", "fmt": "+.2f", "signed": True},
    "NATR": {"column": "natr", "label": "NATR (ATR % of price)", "fmt": ".3f", "signed": False},
    "ADR used %": {"column": "adr_used", "label": "ADR used %", "fmt": ".0f", "signed": False},
    "Prev-day pos %": {"column": "prev_day_pos", "label": "Position in previous day's range %", "fmt": ".0f", "signed": False},
    "EMA slope (ATR)": {"column": "ema_slope_atr", "label": "EMA slope (ATRs per slope window)", "fmt": "+.2f", "signed": True},
}

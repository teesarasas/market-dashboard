"""Overview setup filter: which instruments pass the chosen conditions. Pure pandas — no Streamlit."""
import numpy as np
import pandas as pd

import config
from indicators import trend

# key -> label shown above the Overview table
CONDITIONS = {
    "adx": f"ADX > {config.SETUP_ADX_MIN}",
    "di": f"DI spread ≥ {config.SETUP_DI_MIN} with the trend",
    "trend": "State is Trend up / down",
    "adr": f"ADR used ≥ {config.SETUP_ADR_MIN}%",
    "pdhl": "Beyond yesterday's high / low with the trend",
    "h1": f"H1 price on the trend side of EMA{config.H1_EMA_LENGTH}",
    "score": f"Score ≥ {config.SETUP_SCORE_MIN} with the trend",
}


def direction(snap: pd.DataFrame) -> pd.Series:
    """+1 for Trend up, -1 for Trend down; otherwise the sign of the DI spread."""
    from_state = snap["State"].map({trend.TREND_UP: 1, trend.TREND_DOWN: -1})
    return from_state.fillna(np.sign(snap["DI spread"])).fillna(0)


def checks(snap: pd.DataFrame) -> pd.DataFrame:
    """One True/False column per condition (missing values fail)."""
    d = direction(snap)
    pos = snap["Prev-day pos %"]
    return pd.DataFrame({
        "adx": snap["ADX"] > config.SETUP_ADX_MIN,
        "di": d * snap["DI spread"] >= config.SETUP_DI_MIN,
        "trend": snap["State"].isin([trend.TREND_UP, trend.TREND_DOWN]),
        "adr": snap["ADR used %"] >= config.SETUP_ADR_MIN,
        "pdhl": ((d > 0) & (pos > 100)) | ((d < 0) & (pos < 0)),
        "h1": ((d > 0) & (snap["H1 side"] == "Above")) | ((d < 0) & (snap["H1 side"] == "Below")),
        "score": d * snap["Score"] >= config.SETUP_SCORE_MIN,
    }, index=snap.index).fillna(False).astype(bool)


def setup_mask(snap: pd.DataFrame, selected) -> pd.Series:
    """True where every selected condition passes. No conditions selected = everything passes."""
    selected = list(selected)
    if not selected:
        return pd.Series(True, index=snap.index)
    return checks(snap)[selected].all(axis=1)

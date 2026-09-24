"""Currency strength and breadth from FX pair scores/states. Pure pandas — no Streamlit."""
import pandas as pd

import config
from indicators import trend


def parse_pair(vendor: str) -> tuple[str, str]:
    """'EUR/USD' -> ('EUR', 'USD')."""
    base, quote = vendor.split("/")
    return base, quote


def strength(scores: dict) -> pd.DataFrame:
    """Per-bar currency strength.

    scores: {'EUR/USD': Series of score, ...} (FX pairs only).
    Each pair adds +score to its base and -score to its quote; a currency's strength
    is the mean of its contributions. Returns a frame indexed by time, one column per currency.
    """
    if not scores:
        return pd.DataFrame()
    pairs = pd.concat(scores, axis=1).sort_index().ffill(limit=1)
    enough = pairs.notna().sum(axis=1) >= config.CURRENCY_MIN_PAIR_SHARE * pairs.shape[1]
    pairs = pairs[enough]

    contributions = {}
    for pair in pairs.columns:
        base, quote = parse_pair(pair)
        contributions.setdefault(base, []).append(pairs[pair])
        contributions.setdefault(quote, []).append(-pairs[pair])
    return pd.DataFrame(
        {c: pd.concat(parts, axis=1).mean(axis=1) for c, parts in sorted(contributions.items())}
    )


def breadth(states: dict) -> pd.DataFrame:
    """How many pairs trend in each currency's favour.

    states: {'EUR/USD': 'Trend up', ...} (latest state per FX pair).
    Returns one row per currency: in_favour, against, total, breadth (in_favour / total).
    """
    rows = {}
    for pair, state in states.items():
        base, quote = parse_pair(pair)
        for ccy, sign in ((base, 1), (quote, -1)):
            r = rows.setdefault(ccy, {"in_favour": 0, "against": 0, "total": 0})
            r["total"] += 1
            if state == (trend.TREND_UP if sign > 0 else trend.TREND_DOWN):
                r["in_favour"] += 1
            elif state == (trend.TREND_DOWN if sign > 0 else trend.TREND_UP):
                r["against"] += 1
    out = pd.DataFrame.from_dict(rows, orient="index").sort_index()
    if not out.empty:
        out["breadth"] = out["in_favour"] / out["total"]
    return out

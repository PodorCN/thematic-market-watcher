"""Daily-return primitives shared by every analysis script in returns/.

fetch_data.py produces raw-data JSONs; this module turns them into
closes / return series. Anything downstream (covariance, future
volatility/beta/... scripts) must build on these helpers instead of
re-parsing the JSON itself.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd


def load_closes(path: Path) -> pd.DataFrame:
    """Read a raw-data JSON into a wide DataFrame of closes (index=date str)."""
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)
    cols = {
        symbol: pd.Series({h["date"]: h["close"] for h in t["history"]})
        for symbol, t in raw["tickers"].items()
        if t.get("history")
    }
    if not cols:
        raise ValueError(f"no ticker history found in {path}")
    return pd.DataFrame(cols).dropna()


def daily_returns(closes: pd.DataFrame) -> pd.DataFrame:
    """Simple daily percent returns, first row dropped."""
    return closes.pct_change().dropna()

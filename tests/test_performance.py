"""Unit tests for analysis/performance.py.

Pure pandas -- no network, no yfinance.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from analysis.performance import biggest_moves, daily_moves, window_returns  # noqa: E402


def _series(values):
    idx = pd.bdate_range("2026-07-01", periods=len(values))
    return pd.Series(values, index=idx)


def test_window_returns_computes_each_window():
    # 30 trading days: last=110, -1d=105, -5d=90, -21d=80
    s = _series([80.0] * 9 + [90.0] * 16 + [100.0] + [105.0] * 3 + [110.0])
    r = window_returns(s)
    assert r["1d"] == round((110 / 105 - 1) * 100, 2)
    assert r["1w"] == round((110 / 90 - 1) * 100, 2)
    assert r["1m"] == round((110 / 80 - 1) * 100, 2)
    assert r["6m"] is None  # not enough history


def test_daily_moves_has_pct_change():
    s = _series([100.0, 101.0, 99.0])
    df = daily_moves(s)
    assert list(df.columns) == ["close", "chg_pct"]
    assert df["chg_pct"].iloc[0] != df["chg_pct"].iloc[0]  # first row NaN
    assert df["chg_pct"].iloc[1] == pytest.approx(1.0)
    assert df["chg_pct"].iloc[2] == pytest.approx((99.0 / 101.0 - 1) * 100, abs=0.01)


def test_biggest_moves_ranks_by_abs_change():
    s = _series([100.0, 100.5, 95.0, 95.2, 99.0])
    top = biggest_moves(daily_moves(s), n=2)
    assert abs(top["chg_pct"].iloc[0]) >= abs(top["chg_pct"].iloc[1].item())
    # the -5.5% style day (100.5 -> 95) must be first
    assert top["chg_pct"].iloc[0] < 0

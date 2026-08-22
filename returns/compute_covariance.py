#!/usr/bin/env python3
"""EWMA covariance matrix from a raw-data JSON produced by fetch_data.py.

Computes exponentially-weighted daily-return covariance, where recent
returns count more: weights decay with half-life `--halflife` trading
days. Also derives the implied correlation matrix and an annualized
version (x `--periods`).

Usage:
    python returns/compute_covariance.py --input <raw_data.json>
        [--halflife 63] [--periods 252] [--output out.csv]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from returns.daily_returns import daily_returns, load_closes  # noqa: E402


def ewma_covariance(returns: pd.DataFrame, halflife: float) -> pd.DataFrame:
    full = returns.ewm(halflife=halflife).cov()
    return full.loc[returns.index[-1]]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, help="path to raw_data JSON")
    parser.add_argument("--halflife", type=float, default=63.0)
    parser.add_argument("--periods", type=int, default=252)
    parser.add_argument("--output", default=None)
    args = parser.parse_args()

    in_path = Path(args.input)
    if not in_path.is_absolute():
        in_path = REPO_ROOT / in_path

    closes = load_closes(in_path)
    returns = daily_returns(closes)

    cov_daily = ewma_covariance(returns, args.halflife)
    d = np.sqrt(np.diag(cov_daily.to_numpy()))
    corr = pd.DataFrame(
        cov_daily.to_numpy() / np.outer(d, d),
        index=cov_daily.index,
        columns=cov_daily.columns,
    )
    cov_annual = cov_daily * args.periods

    print(f"{len(returns)} daily returns | {returns.index[0]} -> {returns.index[-1]}")
    print(f"EWMA half-life: {args.halflife} days\n")
    print("=== Covariance (daily, EWMA) ===")
    print(cov_daily.to_string(float_format=lambda x: f"{x:.3e}"))
    print("\n=== Covariance (annualized) ===")
    print(cov_annual.to_string(float_format=lambda x: f"{x:.4f}"))
    print("\n=== Correlation (implied) ===")
    print(corr.round(4).to_string())

    out_path = (
        Path(args.output)
        if args.output
        else in_path.with_name(f"{in_path.stem}_cov_hl{args.halflife:g}.csv")
    )
    keys = ["cov_daily", "cov_annual", "corr"]
    pd.concat(dict(zip(keys, [cov_daily, cov_annual, corr]))).to_csv(out_path)
    print(f"\nwrote {out_path}")


if __name__ == "__main__":
    main()

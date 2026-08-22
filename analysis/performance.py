#!/usr/bin/env python3
"""Ad-hoc market analysis tools (pure code, no LLM).

Reusable primitives distilled from real research sessions ("why did X
drop this week?"):

  1. perf   -- windowed performance table (1d/1w/1m/3m/...) for a list
               of tickers, optionally relative to a benchmark.
  2. daily  -- day-by-day close + % change breakdown for ONE ticker,
               with the biggest absolute moves highlighted. This is how
               you localize *which days* a selloff happened before you
               go looking for news on those exact dates.

Library functions are importable:

    from analysis.performance import (
        fetch_closes, performance_table, daily_moves, biggest_moves,
    )

CLI examples:

    python analysis/performance.py perf
    python analysis/performance.py perf --tickers ZEB.TO,RY.TO,XIU.TO --benchmark XIU.TO
    python analysis/performance.py daily ZEB.TO --period 1mo
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

TICKERS_PATH = REPO_ROOT / "config" / "tickers.json"

# Trading-day lookback windows used by `perf`. Roughly calendar-based:
# 1 day, 1 week (5), 1 month (21), 3 months (63), 6 months (126).
WINDOWS = {
    "1d": 1,
    "1w": 5,
    "1m": 21,
    "3m": 63,
    "6m": 126,
}


def load_default_tickers() -> list[str]:
    return json.loads(TICKERS_PATH.read_text(encoding="utf-8"))["tickers"]


def fetch_closes(tickers: list[str], period: str = "6mo") -> pd.DataFrame:
    """Wide DataFrame of closes (columns=tickers) via yfinance.

    Uses auto_adjust=True (dividends/splits reinvested), so every return
    computed from this frame is a TOTAL RETURN, not just price change.
    For high-dividend names (e.g. ZEB.TO ~2.3% yield) the difference is
    material: price-only vs total can diverge by double digits over 2y.
    """
    import yfinance as yf

    closes = pd.DataFrame()
    for ticker in tickers:
        try:
            hist = yf.Ticker(ticker).history(period=period, auto_adjust=True)
            if not hist.empty:
                closes[ticker] = hist["Close"]
        except Exception as exc:  # noqa: BLE001 -- one bad ticker must not kill the run
            print(f"  ! {ticker}: {exc}", file=sys.stderr)
    return closes.dropna(how="all")


def window_returns(closes: pd.Series) -> dict[str, float | None]:
    """Total-return % over each of WINDOWS, from most recent close.

    "Total" because the input closes are dividend-adjusted (see
    fetch_closes). Windows longer than the available history yield None
    rather than a misleading number computed off too little data.
    """
    out: dict[str, float | None] = {}
    n = len(closes)
    for label, back in WINDOWS.items():
        if n > back:
            out[label] = round((closes.iloc[-1] / closes.iloc[-1 - back] - 1) * 100, 2)
        else:
            out[label] = None
    return out


def performance_table(
    tickers: list[str], period: str = "6mo", benchmark: str | None = None
) -> pd.DataFrame:
    """One row per ticker, columns = window returns (in %).

    With --benchmark, each cell becomes the *excess* return versus the
    benchmark's same-window return -- instantly shows which names moved
    independently of the broad market.
    """
    table = pd.DataFrame({t: window_returns(closes) for t, closes in fetch_closes(tickers, period).items()}).T

    if benchmark:
        bench = fetch_closes([benchmark], period)
        if bench.empty:
            print(f"  ! benchmark {benchmark}: no data", file=sys.stderr)
        else:
            bench_row = window_returns(bench.iloc[:, 0])
            table = (table - pd.Series(bench_row)).round(2)

    return table


def daily_moves(closes: pd.Series) -> pd.DataFrame:
    """DataFrame(date, close, chg_pct) -- the day-by-day breakdown."""
    df = closes.rename("close").to_frame()
    df.index = df.index.date
    df["chg_pct"] = (df["close"].pct_change() * 100).round(2)
    return df


def biggest_moves(moves: pd.DataFrame, n: int = 5) -> pd.DataFrame:
    """The n rows of a daily_moves frame with the largest |chg_pct|."""
    ranked = moves.dropna(subset=["chg_pct"]).reindex(
        moves["chg_pct"].abs().sort_values(ascending=False).index
    )
    return ranked.head(n)


def _print_frame(df: pd.DataFrame) -> None:
    print(df.to_string())


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_perf = sub.add_parser("perf", help="windowed performance table")
    p_perf.add_argument("--tickers", help="comma-separated; default = config/tickers.json")
    p_perf.add_argument("--period", default="9mo", help="yfinance period fetched (default 9mo)")
    p_perf.add_argument("--benchmark", help="subtract this ticker's returns, e.g. XIU.TO")

    p_daily = sub.add_parser("daily", help="day-by-day moves for one ticker")
    p_daily.add_argument("ticker")
    p_daily.add_argument("--period", default="1mo")
    p_daily.add_argument("--top", type=int, default=0, help="also show N biggest move days")

    args = parser.parse_args()

    if args.cmd == "perf":
        tickers = (
            [t.strip() for t in args.tickers.split(",")]
            if args.tickers
            else load_default_tickers()
        )
        table = performance_table(tickers, args.period, args.benchmark)
        suffix = f" (excess vs {args.benchmark})" if args.benchmark else ""
        print(f"== windowed returns % ({args.period} fetched){suffix} ==")
        _print_frame(table)

    elif args.cmd == "daily":
        closes = fetch_closes([args.ticker], args.period)
        if closes.empty:
            sys.exit(f"no data for {args.ticker}")
        moves = daily_moves(closes.iloc[:, 0])
        print(f"== {args.ticker} daily moves ({args.period}) ==")
        _print_frame(moves)
        if args.top:
            print(f"\n-- {args.top} biggest move days --")
            _print_frame(biggest_moves(moves, args.top))


if __name__ == "__main__":
    main()

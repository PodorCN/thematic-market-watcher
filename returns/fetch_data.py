"""Stage 1 -- fetch_data.py (returns/ package)

Pure code, no LLM. Downloads daily market data for a configurable list
of ETFs/indexes and writes archive/<date>/<output>.json. Runnable and
testable in complete isolation from every other stage.

Usage:
    python returns/fetch_data.py [--date YYYY-MM-DD] [--tickers A,B,C]
        [--history-days 30] [--output raw_data.json]
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from returns.market_data_provider import get_provider  # noqa: E402

STAGE_DIR = Path(__file__).resolve().parent
TICKERS_FILE = REPO_ROOT / "config" / "tickers.json"


def load_tickers() -> list[str]:
    with open(TICKERS_FILE, encoding="utf-8") as f:
        return json.load(f)["tickers"]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=date.today().isoformat())
    parser.add_argument("--provider", default="yfinance")
    parser.add_argument(
        "--tickers",
        default=None,
        help="comma-separated symbols; overrides data/tickers.json",
    )
    parser.add_argument("--history-days", type=int, default=30)
    parser.add_argument(
        "--output", default="raw_data.json", help="file name inside archive/<date>/"
    )
    args = parser.parse_args()

    out_dir = REPO_ROOT / "archive" / args.date
    out_dir.mkdir(parents=True, exist_ok=True)

    tickers = (
        [t.strip().upper() for t in args.tickers.split(",") if t.strip()]
        if args.tickers
        else load_tickers()
    )
    provider = get_provider(args.provider)
    raw_data = provider.fetch(tickers, history_days=args.history_days)
    raw_data["date"] = args.date
    raw_data["fetched_at"] = datetime.now(timezone.utc).isoformat()

    out_path = out_dir / args.output
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(raw_data, f, ensure_ascii=False, indent=2)

    print(f"wrote {out_path}")


if __name__ == "__main__":
    main()

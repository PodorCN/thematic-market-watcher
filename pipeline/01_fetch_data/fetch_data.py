#!/usr/bin/env python3
"""Stage 1 -- fetch_data.py

Pure code, no LLM. Downloads today's water-theme market data and writes
data/<date>/raw_data.json. Runnable and testable in complete isolation
from every other stage.

Usage:
    python pipeline/01_fetch_data/fetch_data.py [--date YYYY-MM-DD]
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

from lib.market_data_provider import get_provider  # noqa: E402

STAGE_DIR = Path(__file__).resolve().parent
TICKERS_FILE = STAGE_DIR / "tickers.json"


def load_tickers() -> list[str]:
    with open(TICKERS_FILE, encoding="utf-8") as f:
        return json.load(f)["tickers"]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=date.today().isoformat())
    parser.add_argument("--provider", default="yfinance")
    args = parser.parse_args()

    out_dir = REPO_ROOT / "data" / args.date
    out_dir.mkdir(parents=True, exist_ok=True)

    tickers = load_tickers()
    provider = get_provider(args.provider)
    raw_data = provider.fetch(tickers)
    raw_data["date"] = args.date
    raw_data["fetched_at"] = datetime.now(timezone.utc).isoformat()

    out_path = out_dir / "raw_data.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(raw_data, f, ensure_ascii=False, indent=2)

    print(f"wrote {out_path}")


if __name__ == "__main__":
    main()

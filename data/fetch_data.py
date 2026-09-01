#!/usr/bin/env python3
"""Stage 1 -- fetch_data.py (data/ package)

Pure code, no LLM. Downloads today's theme-specific market data and writes
archive/<date>/raw_data.json. Runnable and testable in complete isolation
from every other stage.

Usage:
    python data/fetch_data.py [--date YYYY-MM-DD]
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from data.market_data_provider import get_provider  # noqa: E402

STAGE_DIR = Path(__file__).resolve().parent
DEFAULT_TICKERS_FILE = STAGE_DIR / "tickers.json"


def _tickers_path(theme: str | None) -> Path:
    if theme:
        p = REPO_ROOT / "config" / "themes" / theme / "tickers.json"
        if p.exists():
            return p
    return DEFAULT_TICKERS_FILE


def load_tickers(theme: str | None = None) -> list[str]:
    path = _tickers_path(theme)
    with open(path, encoding="utf-8") as f:
        return json.load(f)["tickers"]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=date.today().isoformat())
    parser.add_argument("--provider", default="yfinance")
    parser.add_argument("--theme", default=None, help="Theme name (e.g. canadian_banks, us_smallcap, us_rates, tariff_war)")
    args = parser.parse_args()

    if args.theme:
        out_dir = REPO_ROOT / "archive" / args.theme / args.date
    else:
        out_dir = REPO_ROOT / "archive" / args.date
    out_dir.mkdir(parents=True, exist_ok=True)

    tickers = load_tickers(args.theme)
    provider = get_provider(args.provider)
    raw_data = provider.fetch(tickers, history_days=90)
    raw_data["date"] = args.date
    if args.theme:
        raw_data["theme"] = args.theme
    raw_data["fetched_at"] = datetime.now(timezone.utc).isoformat()

    out_path = out_dir / "raw_data.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(raw_data, f, ensure_ascii=False, indent=2)

    print(f"wrote {out_path}")


if __name__ == "__main__":
    main()

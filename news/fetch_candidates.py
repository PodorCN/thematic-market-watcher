#!/usr/bin/env python3
"""Stage 2a -- fetch_candidates.py (news/ package)

LLM call *with a hosted web-search tool*. This is the one deliberate,
narrow exception in this repo to "LLM only does a single prompt+schema
completion over data we already prepared" -- see readme/AGENTS.md section
4a for why, and utils/llm_client.call_llm_with_web_search for how it
stays a single, provider-abstracted call rather than an ad hoc agent loop.

judge.py (stage 2b), by contrast, is a plain call_llm() with no tools --
it only reasons over the candidates.json this script produces.

Usage:
    python news/fetch_candidates.py [--date YYYY-MM-DD]
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from utils.llm_client import call_llm_with_web_search  # noqa: E402
from utils.theme import load_theme  # noqa: E402

STAGE_DIR = Path(__file__).resolve().parent
PROMPT_PATH = STAGE_DIR / "prompt_candidates.md"
SCHEMA_PATH = STAGE_DIR / "schema_candidates.json"
TICKERS_PATH = REPO_ROOT / "config" / "tickers.json"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=date.today().isoformat())
    args = parser.parse_args()

    out_dir = REPO_ROOT / "archive" / args.date
    out_dir.mkdir(parents=True, exist_ok=True)

    config = json.loads(TICKERS_PATH.read_text(encoding="utf-8"))
    tickers = config["tickers"]
    theme = load_theme()
    prompt_template = PROMPT_PATH.read_text(encoding="utf-8")
    prompt = (
        prompt_template
        .replace("{{theme_description}}", theme["description"])
        .replace("{{tickers}}", ", ".join(tickers))
    )
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))

    result = call_llm_with_web_search(prompt, schema, stage="market_headline_search")
    result["date"] = args.date

    out_path = out_dir / "candidates.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"wrote {out_path} ({len(result.get('candidates', []))} candidates)")


if __name__ == "__main__":
    main()

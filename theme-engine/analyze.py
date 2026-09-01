#!/usr/bin/env python3
"""Stage 3 -- analyze.py (theme-engine/ package)

Plain call_llm(): one prompt+schema completion over raw_data.json +
headlines.json. Writes archive/<date>/analysis.json, which is the only
input the render/ package reads.

Usage:
    python theme-engine/analyze.py [--date YYYY-MM-DD]
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from utils.llm_client import call_llm  # noqa: E402

STAGE_DIR = Path(__file__).resolve().parent
DEFAULT_PROMPT_PATH = STAGE_DIR / "prompt.md"
SCHEMA_PATH = STAGE_DIR / "schema.json"


def _prompt_path(theme: str | None) -> Path:
    if theme:
        p = REPO_ROOT / "config" / "themes" / theme / "prompt.md"
        if p.exists():
            return p
    return DEFAULT_PROMPT_PATH


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=date.today().isoformat())
    parser.add_argument("--theme", default=None, help="Theme name")
    args = parser.parse_args()

    if args.theme:
        data_dir = REPO_ROOT / "archive" / args.theme / args.date
    else:
        data_dir = REPO_ROOT / "archive" / args.date
    raw_data = json.loads((data_dir / "raw_data.json").read_text(encoding="utf-8"))
    headlines = json.loads((data_dir / "headlines.json").read_text(encoding="utf-8"))

    prompt_path = _prompt_path(args.theme)
    prompt_template = prompt_path.read_text(encoding="utf-8")
    prompt = (
        prompt_template
        .replace("{{raw_data_json}}", json.dumps(raw_data, ensure_ascii=False, indent=2))
        .replace("{{headlines_json}}", json.dumps(headlines["headlines"], ensure_ascii=False, indent=2))
    )
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))

    result = call_llm(prompt, schema, stage="analysis")
    result["date"] = args.date
    if args.theme:
        result["theme"] = args.theme

    out_path = data_dir / "analysis.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"wrote {out_path}")


if __name__ == "__main__":
    main()

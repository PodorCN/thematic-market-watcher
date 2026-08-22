#!/usr/bin/env python3
"""Stage 2b -- judge.py (news/ package)

Plain call_llm(): one prompt+schema completion, no tools, no network
access on the model's side. Reads candidates.json (produced by
fetch_candidates.py) and writes the curated archive/<date>/headlines.json.

Usage:
    python news/judge.py [--date YYYY-MM-DD]
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
from utils.theme import load_theme  # noqa: E402

STAGE_DIR = Path(__file__).resolve().parent
PROMPT_PATH = STAGE_DIR / "prompt_judge.md"
SCHEMA_PATH = STAGE_DIR / "schema_judge.json"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=date.today().isoformat())
    args = parser.parse_args()

    data_dir = REPO_ROOT / "archive" / args.date
    candidates = json.loads((data_dir / "candidates.json").read_text(encoding="utf-8"))

    theme = load_theme()
    prompt_template = PROMPT_PATH.read_text(encoding="utf-8")
    prompt = (
        prompt_template
        .replace("{{theme_description}}", theme["description"])
        .replace("{{theme}}", theme["name"])
        .replace(
            "{{candidates_json}}", json.dumps(candidates["candidates"], ensure_ascii=False, indent=2)
        )
    )
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))

    result = call_llm(prompt, schema, stage="headline_judge")
    result["date"] = args.date
    result["headlines"].sort(key=lambda h: h["importance"], reverse=True)

    out_path = data_dir / "headlines.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"wrote {out_path} ({len(result['headlines'])} headlines kept)")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Stage 3 -- analyze.py (theme-engine/ package)

Plain call_llm(): one prompt+schema completion over raw_data.json +
headlines.json. Writes archive/<date>/analysis.json, which is the only
input the render/ package reads.

ANALYSIS POLICY: output is driver-level (trade policy, rates path,
climate, regulation, earnings transmission). A single name appears only
if it is systemically significant for the theme. Input-quality problems
(news too thin/too concentrated, returns too shallow) must be written
to readme/analysis-feedback.md so upstream pullers see them.

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
from utils.theme import load_theme  # noqa: E402

STAGE_DIR = Path(__file__).resolve().parent
PROMPT_PATH = STAGE_DIR / "prompt.md"
SCHEMA_PATH = STAGE_DIR / "schema.json"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=date.today().isoformat())
    args = parser.parse_args()

    data_dir = REPO_ROOT / "archive" / args.date
    raw_data = json.loads((data_dir / "raw_data.json").read_text(encoding="utf-8"))
    headlines = json.loads((data_dir / "headlines.json").read_text(encoding="utf-8"))

    theme = load_theme()
    prompt_template = PROMPT_PATH.read_text(encoding="utf-8")
    prompt = (
        prompt_template
        .replace("{{theme_description}}", theme["description"])
        .replace("{{theme}}", theme["name"])
        .replace("{{raw_data_json}}", json.dumps(raw_data, ensure_ascii=False, indent=2))
        .replace("{{headlines_json}}", json.dumps(headlines["headlines"], ensure_ascii=False, indent=2))
    )
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))

    result = call_llm(prompt, schema, stage="analysis")
    result["date"] = args.date

    out_path = data_dir / "analysis.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"wrote {out_path}")


if __name__ == "__main__":
    main()

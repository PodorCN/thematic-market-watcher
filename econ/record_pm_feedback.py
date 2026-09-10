#!/usr/bin/env python3
"""Persist a rejected PM review as durable feedback for future collection runs."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path

try:
    from econ.validate_pm_review import validate_review
except ModuleNotFoundError:  # Direct execution
    from validate_pm_review import validate_review

REPO_ROOT = Path(__file__).resolve().parent.parent


def _atomic_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temp, path)


def record_feedback(candidate_path: Path, review_path: Path, feedback_root: Path) -> tuple[Path, Path]:
    result = validate_review(candidate_path, review_path, require_approved=False)
    review = json.loads(review_path.read_text(encoding="utf-8"))
    if result["verdict"] != "revise":
        raise ValueError("only a revise verdict becomes mandatory collection feedback")

    review_sha = hashlib.sha256(review_path.read_bytes()).hexdigest()
    reviewed_at = review["reviewed_at"]
    date = reviewed_at[:10]
    payload = {
        "schema_version": "1.0",
        "status": "open",
        "reviewed_at": reviewed_at,
        "candidate_sha256": result["candidate_sha256"],
        "review_sha256": review_sha,
        "source_review": review_path.as_posix(),
        "executive_summary": review["executive_summary"],
        "failed_checks": sorted(k for k, value in review["checks"].items() if value == "fail"),
        "findings": review["findings"],
        "required_recollection": [
            finding["instruction"] for finding in review["findings"]
            if finding["severity"] in {"critical", "major"}
        ],
        "operator_instructions": review["operator_instructions"],
        "next_run_contract": [
            "Read this feedback before collecting or editing the next candidate.",
            "Re-trigger collection for every affected source and claim.",
            "Rebuild the whole internally consistent candidate; do not patch prose only.",
            "Submit the rebuilt candidate to a fresh independent PM review.",
            "Do not publish until an exact-byte-bound approved review passes the gate.",
        ],
    }
    history = feedback_root / "history" / f"{date}-{review_sha[:12]}.json"
    latest = feedback_root / "latest.json"
    _atomic_json(history, payload)
    _atomic_json(latest, payload)
    return history, latest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--review", type=Path, required=True)
    parser.add_argument("--feedback-root", type=Path, default=REPO_ROOT / "review" / "fed-boc" / "feedback")
    args = parser.parse_args()
    try:
        history, latest = record_feedback(args.candidate, args.review, args.feedback_root)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        raise SystemExit(f"PM FEEDBACK RECORD FAILED: {exc}") from exc
    print(f"wrote {history}")
    print(f"wrote {latest}")


if __name__ == "__main__":
    main()

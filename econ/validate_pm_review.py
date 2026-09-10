#!/usr/bin/env python3
"""Validate an independent PM review and bind it to exact candidate bytes."""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime
from pathlib import Path

CHECK_KEYS = {
    "official_policy",
    "pricing",
    "drivers",
    "market_validation",
    "freshness",
    "decision_usefulness",
}
REQUIRED = {
    "schema_version",
    "reviewer_role",
    "reviewed_at",
    "candidate_sha256",
    "verdict",
    "executive_summary",
    "checks",
    "findings",
    "pnl_risks",
    "operator_instructions",
}
FINDING_KEYS = {"severity", "field", "issue", "evidence", "pnl_impact", "instruction"}


def candidate_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_review(candidate_path: Path, review_path: Path, require_approved: bool = False) -> dict:
    candidate = json.loads(candidate_path.read_text(encoding="utf-8"))
    review = json.loads(review_path.read_text(encoding="utf-8"))
    errors: list[str] = []

    if set(review) != REQUIRED:
        errors.append(f"review keys must be exactly {sorted(REQUIRED)}")
    if review.get("schema_version") != "1.0":
        errors.append("schema_version must be 1.0")
    if review.get("reviewer_role") != "independent_portfolio_manager":
        errors.append("reviewer_role must be independent_portfolio_manager")
    try:
        reviewed_at = datetime.fromisoformat(str(review.get("reviewed_at", "")).replace("Z", "+00:00"))
        if reviewed_at.tzinfo is None:
            errors.append("reviewed_at must include a UTC offset")
    except ValueError:
        errors.append("reviewed_at must be ISO 8601")

    digest = candidate_digest(candidate_path)
    if review.get("candidate_sha256") != digest:
        errors.append("candidate_sha256 does not match candidate bytes")
    verdict = review.get("verdict")
    if verdict not in {"approved", "revise"}:
        errors.append("verdict must be approved or revise")
    if len(str(review.get("executive_summary", "")).strip()) < 20:
        errors.append("executive_summary is too short")

    checks = review.get("checks")
    if not isinstance(checks, dict) or set(checks) != CHECK_KEYS:
        errors.append(f"checks keys must be exactly {sorted(CHECK_KEYS)}")
    elif any(value not in {"pass", "fail"} for value in checks.values()):
        errors.append("every check must be pass or fail")

    findings = review.get("findings")
    if not isinstance(findings, list):
        errors.append("findings must be an array")
        findings = []
    for index, finding in enumerate(findings):
        if not isinstance(finding, dict) or set(finding) != FINDING_KEYS:
            errors.append(f"finding[{index}] has invalid keys")
            continue
        if finding.get("severity") not in {"critical", "major", "minor"}:
            errors.append(f"finding[{index}] has invalid severity")
        for key in FINDING_KEYS - {"severity"}:
            if len(str(finding.get(key, "")).strip()) < (1 if key == "field" else 10):
                errors.append(f"finding[{index}].{key} is too short")

    pnl_risks = review.get("pnl_risks")
    if not isinstance(pnl_risks, list) or not pnl_risks or any(len(str(x).strip()) < 10 for x in pnl_risks):
        errors.append("pnl_risks must contain at least one substantive risk")
    instructions = review.get("operator_instructions")
    if not isinstance(instructions, list) or any(len(str(x).strip()) < 10 for x in instructions):
        errors.append("operator_instructions must be an array of substantive instructions")

    material = [f for f in findings if isinstance(f, dict) and f.get("severity") in {"critical", "major"}]
    failed_checks = [key for key, value in checks.items() if value == "fail"] if isinstance(checks, dict) else []
    if verdict == "approved" and (material or failed_checks or instructions):
        errors.append("approved review cannot contain material findings, failed checks, or operator instructions")
    if verdict == "revise" and not (material or failed_checks or instructions):
        errors.append("revise review must contain an actionable material problem")
    if require_approved and verdict != "approved":
        errors.append("publication blocked: PM verdict is not approved")

    candidate_as_of = candidate.get("as_of")
    if not candidate_as_of:
        errors.append("candidate payload is missing as_of")
    if errors:
        raise ValueError("; ".join(errors))
    return {"verdict": verdict, "candidate_sha256": digest, "candidate_as_of": candidate_as_of}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--review", type=Path, required=True)
    parser.add_argument("--require-approved", action="store_true")
    args = parser.parse_args()
    try:
        result = validate_review(args.candidate, args.review, args.require_approved)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        raise SystemExit(f"PM REVIEW GATE FAILED: {exc}") from exc
    print(
        "PM REVIEW GATE PASS: "
        f"verdict={result['verdict']} candidate_as_of={result['candidate_as_of']} "
        f"sha256={result['candidate_sha256']}"
    )


if __name__ == "__main__":
    main()

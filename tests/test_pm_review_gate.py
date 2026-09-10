from __future__ import annotations

import hashlib
import json

import pytest

from econ.validate_pm_review import validate_review


def _candidate(tmp_path):
    path = tmp_path / "candidate.json"
    path.write_text(
        json.dumps({"as_of": "2026-09-09T12:40:00-04:00", "meetings": {}, "drivers": {}}),
        encoding="utf-8",
    )
    return path


def _review(candidate, verdict="approved"):
    approved = verdict == "approved"
    return {
        "schema_version": "1.0",
        "reviewer_role": "independent_portfolio_manager",
        "reviewed_at": "2026-09-09T21:00:00-04:00",
        "candidate_sha256": hashlib.sha256(candidate.read_bytes()).hexdigest(),
        "verdict": verdict,
        "executive_summary": "The candidate is internally consistent and suitable for a trading decision.",
        "checks": {
            "official_policy": "pass",
            "pricing": "pass" if approved else "fail",
            "drivers": "pass",
            "market_validation": "pass",
            "freshness": "pass",
            "decision_usefulness": "pass",
        },
        "findings": [] if approved else [{
            "severity": "major",
            "field": "meetings.fed.pricing",
            "issue": "The contract is not a clean single-meeting probability.",
            "evidence": "The cited quarterly future spans more than one meeting.",
            "pnl_impact": "False precision can produce an oversized front-end rates position.",
            "instruction": "Recollect a meeting-specific source or label the value as a proxy.",
        }],
        "pnl_risks": ["A surprise inflation print can rapidly reprice the front-end curve."],
        "operator_instructions": [] if approved else [
            "Recollect and rebuild the pricing section before requesting a new review."
        ],
    }


def _write_review(tmp_path, data):
    path = tmp_path / "pm-review.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_approved_review_passes_exact_candidate_gate(tmp_path):
    candidate = _candidate(tmp_path)
    result = validate_review(candidate, _write_review(tmp_path, _review(candidate)), True)
    assert result["verdict"] == "approved"


def test_revision_verdict_blocks_publication(tmp_path):
    candidate = _candidate(tmp_path)
    with pytest.raises(ValueError, match="publication blocked"):
        validate_review(candidate, _write_review(tmp_path, _review(candidate, "revise")), True)


def test_approval_is_invalid_after_candidate_changes(tmp_path):
    candidate = _candidate(tmp_path)
    review_path = _write_review(tmp_path, _review(candidate))
    candidate.write_text('{"as_of":"2026-09-10T08:00:00-04:00"}', encoding="utf-8")
    with pytest.raises(ValueError, match="candidate_sha256"):
        validate_review(candidate, review_path, True)


def test_operator_cannot_hide_material_finding_under_approval(tmp_path):
    candidate = _candidate(tmp_path)
    review = _review(candidate, "revise")
    review["verdict"] = "approved"
    with pytest.raises(ValueError, match="approved review cannot contain"):
        validate_review(candidate, _write_review(tmp_path, review), True)

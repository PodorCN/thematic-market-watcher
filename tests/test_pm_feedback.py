from __future__ import annotations

import hashlib
import json

import pytest

from econ.record_pm_feedback import record_feedback


def _review(candidate, verdict):
    revise = verdict == "revise"
    return {
        "schema_version": "1.0",
        "reviewer_role": "independent_portfolio_manager",
        "reviewed_at": "2026-09-10T00:33:16-04:00",
        "candidate_sha256": hashlib.sha256(candidate.read_bytes()).hexdigest(),
        "verdict": verdict,
        "executive_summary": "Independent portfolio review found a material pricing issue requiring recollection.",
        "checks": {
            "official_policy": "pass", "pricing": "fail" if revise else "pass",
            "drivers": "pass", "market_validation": "pass", "freshness": "pass",
            "decision_usefulness": "fail" if revise else "pass",
        },
        "findings": [{
            "severity": "critical", "field": "meetings.boc.pricing",
            "issue": "The proxy spans more than one policy meeting.",
            "evidence": "The quarterly contract covers two decision dates.",
            "pnl_impact": "False precision can mis-size a Canada rates position.",
            "instruction": "Recollect meeting-specific pricing or remove probabilities.",
        }] if revise else [],
        "pnl_risks": ["Inflation can rapidly reprice the front-end curve."],
        "operator_instructions": ["Re-trigger pricing collection and rebuild the whole candidate."] if revise else [],
    }


def test_revise_review_becomes_latest_and_historical_feedback(tmp_path):
    candidate = tmp_path / "candidate.json"
    candidate.write_text('{"as_of":"2026-09-10T00:11:00-04:00"}', encoding="utf-8")
    review = tmp_path / "pm-review.json"
    review.write_text(json.dumps(_review(candidate, "revise")), encoding="utf-8")

    history, latest = record_feedback(candidate, review, tmp_path / "feedback")

    assert history.exists() and latest.exists()
    payload = json.loads(latest.read_text(encoding="utf-8"))
    assert payload["status"] == "open"
    assert payload["failed_checks"] == ["decision_usefulness", "pricing"]
    assert payload["required_recollection"] == [
        "Recollect meeting-specific pricing or remove probabilities."
    ]
    assert payload["review_sha256"] == hashlib.sha256(review.read_bytes()).hexdigest()
    assert payload["next_run_contract"][1].startswith("Re-trigger collection")


def test_approved_review_is_not_recorded_as_open_feedback(tmp_path):
    candidate = tmp_path / "candidate.json"
    candidate.write_text('{"as_of":"2026-09-10T00:11:00-04:00"}', encoding="utf-8")
    review = tmp_path / "pm-review.json"
    review.write_text(json.dumps(_review(candidate, "approved")), encoding="utf-8")

    with pytest.raises(ValueError, match="only a revise verdict"):
        record_feedback(candidate, review, tmp_path / "feedback")

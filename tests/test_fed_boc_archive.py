from __future__ import annotations

import hashlib
import json

from econ.archive_fed_boc import archive_dashboard


def _approved_review(candidate, tmp_path):
    review = tmp_path / "pm-review.json"
    review.write_text(json.dumps({
        "schema_version": "1.0",
        "reviewer_role": "independent_portfolio_manager",
        "reviewed_at": "2026-08-24T12:00:00-04:00",
        "candidate_sha256": hashlib.sha256(candidate.read_bytes()).hexdigest(),
        "verdict": "approved",
        "executive_summary": "All material policy, pricing, driver, and freshness checks passed.",
        "checks": {
            "official_policy": "pass", "pricing": "pass", "drivers": "pass",
            "market_validation": "pass", "freshness": "pass",
            "decision_usefulness": "pass",
        },
        "findings": [],
        "pnl_risks": ["Unexpected inflation can rapidly reprice the front end of the curve."],
        "operator_instructions": [],
    }), encoding="utf-8")
    return review


def test_archive_dashboard_writes_snapshot_and_sorted_manifest(tmp_path):
    source = tmp_path / "dashboard.json"
    docs = tmp_path / "docs"
    payload = {
        "as_of": "2026-08-24T08:00:00-04:00",
        "version": "2026-08-24-001",
        "meetings": {"fed": {}, "boc": {}},
        "drivers": {"fed": {}, "boc": {}},
    }
    source.write_text(json.dumps(payload), encoding="utf-8")
    review = _approved_review(source, tmp_path)

    snapshot, dates_path = archive_dashboard(
        source,
        docs,
        source,
        review,
        snapshot_date="2026-08-24",
        archived_at="2026-08-24T13:10:00Z",
    )

    assert snapshot == docs / "data" / "fed-boc" / "archive" / "2026-08-24.json"
    archived = json.loads(snapshot.read_text(encoding="utf-8"))
    assert {key: archived[key] for key in payload} == payload
    assert archived["snapshot_date"] == "2026-08-24"
    assert archived["archived_at"] == "2026-08-24T13:10:00Z"
    assert archived["stale"] is False
    assert json.loads((docs / "data" / "fed-boc" / "latest.json").read_text(encoding="utf-8")) == archived
    manifest = json.loads(dates_path.read_text(encoding="utf-8"))
    assert manifest["latest"] == "2026-08-24"
    assert manifest["dates"] == ["2026-08-24"]

    stale_snapshot, dates_path = archive_dashboard(
        source,
        docs,
        source,
        review,
        snapshot_date="2026-08-25",
        archived_at="2026-08-25T13:10:00Z",
    )
    assert json.loads(stale_snapshot.read_text(encoding="utf-8"))["stale"] is True
    manifest = json.loads(dates_path.read_text(encoding="utf-8"))
    assert manifest["latest"] == "2026-08-25"
    assert manifest["dates"] == ["2026-08-25", "2026-08-24"]

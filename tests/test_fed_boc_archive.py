from __future__ import annotations

import json

from econ.archive_fed_boc import archive_dashboard


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

    snapshot, dates_path = archive_dashboard(
        source,
        docs,
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
        snapshot_date="2026-08-25",
        archived_at="2026-08-25T13:10:00Z",
    )
    assert json.loads(stale_snapshot.read_text(encoding="utf-8"))["stale"] is True
    manifest = json.loads(dates_path.read_text(encoding="utf-8"))
    assert manifest["latest"] == "2026-08-25"
    assert manifest["dates"] == ["2026-08-25", "2026-08-24"]


def _payload(driver: dict) -> dict:
    return {
        "as_of": "2026-09-09T12:40:00-04:00",
        "meetings": {"fed": {}, "boc": {}},
        "drivers": {"fed": {"dovish": [driver], "hawkish": []}, "boc": {}},
    }


def test_observation_stamp_may_follow_publication(tmp_path):
    """A driver refreshed with a newer reading is the normal case, not a defect."""
    from econ.driver_quality import check_payload

    assert check_payload(_payload({
        "id": "fed_dove_oil",
        "published_at_toronto": "2026-08-27T16:00:00-04:00",
        "observed_at_toronto": "2026-09-09T12:31:00-04:00",
    })) == []


def test_reading_cannot_predate_or_outrun_the_snapshot():
    from econ.driver_quality import check_payload

    backwards = check_payload(_payload({
        "id": "fed_dove_oil",
        "published_at_toronto": "2026-09-09T12:00:00-04:00",
        "observed_at_toronto": "2026-08-27T16:00:00-04:00",
    }))
    assert len(backwards) == 1 and "precedes published_at_toronto" in backwards[0]

    future = check_payload(_payload({
        "id": "fed_dove_oil",
        "published_at_toronto": "2026-08-27T16:00:00-04:00",
        "observed_at_toronto": "2026-09-10T09:00:00-04:00",
    }))
    assert len(future) == 1 and "after the payload as_of" in future[0]


def test_naive_timestamp_is_rejected():
    from econ.driver_quality import check_payload

    problems = check_payload(_payload({
        "id": "fed_dove_oil",
        "published_at_toronto": "2026-08-27T16:00:00",
    }))
    assert len(problems) == 1 and "UTC offset" in problems[0]


def test_archive_refuses_an_incoherent_payload(tmp_path):
    """A bad driver must not overwrite the last good latest.json."""
    import pytest

    source = tmp_path / "dashboard.json"
    docs = tmp_path / "docs"
    source.write_text(json.dumps(_payload({
        "id": "fed_dove_oil",
        "published_at_toronto": "2026-09-09T12:00:00-04:00",
        "observed_at_toronto": "2026-08-27T16:00:00-04:00",
    })), encoding="utf-8")

    with pytest.raises(ValueError, match="refusing to archive"):
        archive_dashboard(source, docs, snapshot_date="2026-09-09")
    assert not (docs / "data" / "fed-boc" / "latest.json").exists()

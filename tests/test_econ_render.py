from __future__ import annotations

import json

import econ.render_calendar as render_calendar
from econ.render_calendar import _chart_category, build_context


def _event(name: str, event_id: str, datetime_utc: str, **values) -> dict:
    return {
        "id": f"release-{event_id}",
        "eventId": event_id,
        "datetime_utc": datetime_utc,
        "date": datetime_utc[:10],
        "time": datetime_utc[11:16],
        "country": "US",
        "currency": "USD",
        "event": name,
        "impact": "HIGH",
        "unit": "%",
        "actual": values.get("actual"),
        "forecast": values.get("forecast"),
        "previous": values.get("previous"),
    }


def test_context_uses_toronto_time_and_merges_mom_yoy_rows():
    data = {
        "events": [
            _event("Consumer Price Index (MoM)", "mom", "2026-01-15T01:30:00", forecast="0.2", previous="0.1"),
            _event("Consumer Price Index (YoY)", "yoy", "2026-01-15T01:30:00", forecast="2.8", previous="2.7"),
        ]
    }

    context = build_context(data)

    assert context["start"] == "2026-01-14"
    assert context["end"] == "2026-01-14"
    assert list(context["grouped"]) == ["2026-01-14"]
    release = context["grouped"]["2026-01-14"][0]
    assert release["display_time"] == "8:30 PM"
    assert release["event"] == "Consumer Price Index"
    assert [row["period"] for row in release["period_rows"]] == ["MoM", "YoY"]
    assert [row["forecast"] for row in release["period_rows"]] == [0.2, 2.8]


def test_context_groups_clear_chart_data_and_formats_frequency_labels():
    event = _event(
        "Core Personal Consumption Expenditures - Price Index (YoY)",
        "core-pce",
        "2026-08-26T12:30:00",
        forecast="3.3",
        previous="3.2",
    )
    data = {
        "events": [event],
        "history": {
            "core-pce": [
                {"periodDateUtc": "2026-04-30T00:00:00Z", "actual": 3.0, "consensus": 2.9},
                {"periodDateUtc": "2026-05-31T00:00:00Z", "actual": 3.1, "consensus": 3.0},
                {"periodDateUtc": "2026-06-30T00:00:00Z", "actual": 3.2, "consensus": 3.1},
            ]
        },
        "history_meta": {
            "core-pce": {
                "event": "Core Personal Consumption Expenditures - Price Index (YoY)",
                "currency": "USD",
                "unit": "%",
            }
        },
    }

    context = build_context(data)

    assert [group["name"] for group in context["chart_groups"]] == ["Inflation"]
    chart = context["chart_groups"][0]["charts"][0]
    assert chart["event"] == "Core PCE Price Index"
    assert chart["period_label"] == "Annual change"
    assert chart["upcoming_label"] == "Aug 26 at 8:30 AM"
    assert chart["labels"] == ["Apr '26", "May '26", "Jun '26"]
    assert "consensuses" not in context["chart_data"][0]


def test_housing_price_is_grouped_as_housing_not_inflation():
    assert _chart_category("Housing Price Index (MoM)") == "Housing"


def test_publish_calendar_snapshot_writes_public_history(tmp_path, monkeypatch):
    monkeypatch.setattr(render_calendar, "REPO_ROOT", tmp_path)
    source_dir = tmp_path / "archive" / "2026-08-24"
    source_dir.mkdir(parents=True)
    source_json = source_dir / "economic_calendar.json"
    source_html = source_dir / "economic_calendar.html"
    source_json.write_text('{"count": 1, "events": [{"id": "event-1"}]}', encoding="utf-8")
    source_html.write_text("<html>snapshot</html>", encoding="utf-8")

    latest_json, latest_html = render_calendar.publish_calendar_snapshot(
        "2026-08-24", source_json, source_html
    )

    assert latest_json.read_text(encoding="utf-8") == source_json.read_text(encoding="utf-8")
    assert latest_html.read_text(encoding="utf-8") == "<html>snapshot</html>"
    dates = json.loads(
        (tmp_path / "docs" / "data" / "economic-calendar" / "dates.json").read_text(encoding="utf-8")
    )
    assert dates == {"latest": "2026-08-24", "dates": ["2026-08-24"]}

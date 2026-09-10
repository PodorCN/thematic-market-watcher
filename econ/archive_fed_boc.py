#!/usr/bin/env python3
"""Archive the current Fed/BOC dashboard payload and update its manifest.

Usage:
    python econ/archive_fed_boc.py
    python econ/archive_fed_boc.py --input docs/data/fed-boc-dashboard.json
"""
from __future__ import annotations

import argparse
import json
import math
import os
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

try:  # imported as econ.archive_fed_boc
    from econ.driver_quality import check_payload
    from econ.validate_pm_review import validate_review
except ModuleNotFoundError:  # run directly: python econ/archive_fed_boc.py
    from driver_quality import check_payload
    from validate_pm_review import validate_review

REPO_ROOT = Path(__file__).resolve().parent.parent
TORONTO = ZoneInfo("America/Toronto")


def _validate_finite(value: object, path: str = "root") -> None:
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError(f"{path} contains a non-finite number")
    if isinstance(value, dict):
        for key, child in value.items():
            _validate_finite(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _validate_finite(child, f"{path}[{index}]")


def _atomic_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def _snapshot_date(payload: dict) -> str:
    raw = payload.get("as_of")
    if not raw:
        raise ValueError("dashboard payload is missing as_of")
    parsed = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("as_of must include a UTC offset")
    return parsed.astimezone(TORONTO).date().isoformat()


def archive_dashboard(
    input_path: Path,
    docs_root: Path,
    candidate_path: Path,
    review_path: Path,
    snapshot_date: str | None = None,
    archived_at: str | None = None,
) -> tuple[Path, Path]:
    if input_path.read_bytes() != candidate_path.read_bytes():
        raise ValueError("publication input does not match the PM-reviewed candidate bytes")
    validate_review(candidate_path, review_path, require_approved=True)
    payload = json.loads(input_path.read_text(encoding="utf-8"))
    _validate_finite(payload)
    if not payload.get("meetings") or not payload.get("drivers"):
        raise ValueError("dashboard payload is missing meetings or drivers")
    problems = check_payload(payload)
    if problems:
        # Refuse rather than publish: latest.json keeps the last coherent snapshot
        # and the page's own `stale` flag tells readers the data has not advanced.
        raise ValueError(
            "driver timestamps are incoherent; refusing to archive:\n  "
            + "\n  ".join(problems)
        )

    data_date = _snapshot_date(payload)
    date = snapshot_date or datetime.now(TORONTO).date().isoformat()
    datetime.strptime(date, "%Y-%m-%d")
    captured_at = archived_at or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    published = dict(payload)
    published["snapshot_date"] = date
    published["archived_at"] = captured_at
    published["stale"] = data_date < date
    data_root = docs_root / "data" / "fed-boc"
    snapshot_path = data_root / "archive" / f"{date}.json"
    dates_path = data_root / "dates.json"
    _atomic_json(snapshot_path, published)

    dates = sorted((path.stem for path in snapshot_path.parent.glob("*.json")), reverse=True)
    latest_date = dates[0]
    latest_payload = json.loads(
        (snapshot_path.parent / f"{latest_date}.json").read_text(encoding="utf-8")
    )
    _atomic_json(data_root / "latest.json", latest_payload)
    _atomic_json(
        dates_path,
        {
            "latest": latest_date,
            "updated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "dates": dates,
        },
    )
    return snapshot_path, dates_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Archive the Fed/BOC dashboard JSON")
    parser.add_argument(
        "--input",
        type=Path,
        default=REPO_ROOT / "docs" / "data" / "fed-boc-dashboard.json",
        help="current dashboard JSON",
    )
    parser.add_argument(
        "--docs-root",
        type=Path,
        default=REPO_ROOT / "docs",
        help="GitHub Pages document root",
    )
    parser.add_argument(
        "--candidate",
        type=Path,
        required=True,
        help="frozen candidate JSON reviewed by the independent PM",
    )
    parser.add_argument(
        "--pm-review",
        type=Path,
        required=True,
        help="approved PM review JSON bound to the candidate digest",
    )
    parser.add_argument(
        "--date",
        default=None,
        help="Toronto snapshot date YYYY-MM-DD (defaults to today in Toronto)",
    )
    args = parser.parse_args()
    snapshot, dates = archive_dashboard(
        args.input,
        args.docs_root,
        args.candidate,
        args.pm_review,
        args.date,
    )
    print(f"wrote {snapshot}")
    print(f"wrote {dates}")


if __name__ == "__main__":
    main()

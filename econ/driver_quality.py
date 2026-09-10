#!/usr/bin/env python3
"""Consistency checks for Fed/BOC driver records.

A driver carries two different moments and the dashboard used to conflate them:

* ``published_at_toronto`` -- when the driver first entered the board.
* ``observed_at_toronto``  -- when the reading now sitting in ``data`` was taken.

The refresh process keeps a stable ``id`` and rewrites ``summary`` / ``reason`` /
``data`` in place, so a record can hold a reading from today while still carrying
the timestamp of the day it was created.  The front end decays a driver's weight
by its age, so a stale timestamp silently discounts fresh evidence.

These checks are mechanical -- they never parse prose -- so they cannot fire on a
driver that merely *mentions* a date (a forward-looking "next test is Sep 3" is
not a defect).  They only assert that the timestamps a record declares are
internally coherent.
"""
from __future__ import annotations

from datetime import datetime


def _parse(value: object, label: str, problems: list[str]) -> datetime | None:
    if value is None:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        problems.append(f"{label} is not an ISO-8601 timestamp: {value!r}")
        return None
    if parsed.tzinfo is None:
        problems.append(f"{label} must include a UTC offset: {value!r}")
        return None
    return parsed


def check_driver(driver: dict, as_of: datetime, where: str) -> list[str]:
    """Return the coherence problems in one driver record."""
    problems: list[str] = []
    published = _parse(driver.get("published_at_toronto"), f"{where}.published_at_toronto", problems)
    observed = _parse(driver.get("observed_at_toronto"), f"{where}.observed_at_toronto", problems)

    if published is not None and published > as_of:
        problems.append(f"{where}.published_at_toronto is after the payload as_of")
    if observed is not None:
        if observed > as_of:
            problems.append(f"{where}.observed_at_toronto is after the payload as_of")
        if published is not None and observed < published:
            problems.append(
                f"{where}.observed_at_toronto precedes published_at_toronto -- a reading "
                "cannot predate the driver that reports it"
            )
    return problems


def check_payload(payload: dict) -> list[str]:
    """Return every driver coherence problem in a dashboard payload."""
    problems: list[str] = []
    as_of = _parse(payload.get("as_of"), "as_of", problems)
    if as_of is None:
        return problems
    drivers = payload.get("drivers") or {}
    for bank in sorted(drivers):
        sides = drivers[bank] or {}
        if not isinstance(sides, dict):
            continue
        for side in sorted(sides):
            entries = sides[side] or []
            if not isinstance(entries, list):
                continue
            for index, driver in enumerate(entries):
                if not isinstance(driver, dict):
                    continue
                label = driver.get("id") or f"{bank}.{side}[{index}]"
                problems.extend(check_driver(driver, as_of, f"drivers.{bank}.{side}[{label}]"))
    return problems

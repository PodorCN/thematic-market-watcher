# Public Macro Pages: Backend and Daily Archive Contract

This document is the canonical backend contract for these public pages:

| Page | Public HTML | Latest data |
|---|---|---|
| Global Economic Calendar | `docs/economic_calendar.html` | `docs/data/economic-calendar/latest.json` |
| Fed/BOC Watcher | `docs/feds-boc-watcher.html` | `docs/data/fed-boc/latest.json` |

The frontend is static. The backend publishes JSON once per day, preserves an immutable dated copy, and updates a small date manifest. All public times are rendered in `America/Toronto`; source timestamps must retain an explicit UTC offset.

## 1. Required Publication Layout

```text
docs/
  economic_calendar.html
  economic-calendar/archive/YYYY-MM-DD.html
  feds-boc-watcher.html
  data/
    economic-calendar/
      latest.json
      dates.json
      archive/YYYY-MM-DD.json
    fed-boc/
      latest.json
      dates.json
      archive/YYYY-MM-DD.json
```

Rules:

1. `archive/YYYY-MM-DD.json` is immutable after a successful publication, except to repair invalid data.
2. `latest.json` is an atomic copy of the newest successful archive.
3. `dates.json` lists only snapshots that exist and passed validation.
4. A failed collection must not replace `latest.json`. Continue serving the last successful snapshot.
5. Keep archives indefinitely unless a retention policy is explicitly introduced later.

`dates.json` has the same shape for both pages:

```json
{
  "latest": "2026-08-24",
  "dates": ["2026-08-24", "2026-08-23"]
}
```

Dates are Toronto calendar dates in descending order.

## 2. Daily Publication Sequence

Run after the backend has collected and validated both payloads:

1. Resolve the publication date in `America/Toronto`.
2. Write a temporary JSON file and validate its schema and numeric values.
3. Atomically rename it to `archive/YYYY-MM-DD.json`.
4. Atomically update `latest.json` from the newest archive.
5. Rebuild `dates.json` from successful archive files.
6. For Economic Calendar, render and archive `economic-calendar/archive/YYYY-MM-DD.html`.
7. Commit or upload all new archive files together.

Repository commands:

```bash
python econ/fetch_calendar.py --date YYYY-MM-DD --days 7 --countries US,CA,EMU,DE,FR,IT,ES,UK,CH --impacts HIGH,MEDIUM --with-history --history-events 15 --history-limit 12
python econ/render_calendar.py --date YYYY-MM-DD
python econ/archive_fed_boc.py --input docs/data/fed-boc-dashboard.json
```

The calendar renderer publishes its JSON, HTML snapshot, `latest` files, and date manifest. `econ/archive_fed_boc.py` uses `as_of` to determine the Toronto snapshot date.

## 3. Economic Calendar Payload

Top-level required fields:

| Field | Type | Requirement |
|---|---|---|
| `start`, `end` | `YYYY-MM-DD` | Inclusive collection window |
| `fetched_at` | ISO 8601 | Must include `Z` or a numeric UTC offset |
| `source` | string | Data provider identifier |
| `count` | integer | Must equal `events.length` |
| `events` | array | Upcoming releases |
| `history` | object | Historical chart points keyed by `eventId` |
| `history_meta` | object | Display metadata keyed by `eventId` |

Required `events[]` fields:

```json
{
  "id": "release-id",
  "eventId": "indicator-id",
  "datetime_utc": "2026-08-26T12:30:00Z",
  "country": "US",
  "currency": "USD",
  "event": "Core PCE Price Index (MoM)",
  "impact": "HIGH",
  "actual": null,
  "forecast": 0.2,
  "previous": 0.1,
  "unit": "%"
}
```

Constraints:

- `datetime_utc` is the source of truth. The frontend converts it to `America/Toronto`, including EST/EDT transitions.
- `impact` is one of `HIGH`, `MEDIUM`, `LOW`, `NONE`.
- `actual`, `forecast`, and `previous` are numbers or `null`; `NaN` and `Infinity` are forbidden.
- Matching MoM and YoY releases are merged for display only when base event, currency, country, and release timestamp all match.
- `history[eventId]` is oldest to newest and contains at least `periodDateUtc` and `actual`. Twelve points are preferred.
- Store the raw MoM, YoY, and QoQ series separately. They must not share one chart axis.

The detailed source schema remains in `BACKEND_API_SPEC.md`.

## 4. Fed/BOC Watcher Payload

Top-level required fields:

| Field | Type | Requirement |
|---|---|---|
| `as_of` | ISO 8601 | Explicit offset, interpreted in Toronto |
| `version` | string | Stable publication version |
| `timezone` | string | Must be `America/Toronto` |
| `meetings` | object | Required `fed` and `boc` objects |
| `drivers` | object | Dovish/hawkish arrays for both banks |
| `market` | object | Market validation strip |
| `calendar` | array | Upcoming policy-relevant releases |
| `history` | array | Optional historical analogs |

Minimum shape:

```json
{
  "as_of": "2026-08-24T08:00:00-04:00",
  "version": "2026-08-24-001",
  "timezone": "America/Toronto",
  "meetings": {
    "fed": { "label": "Fed meeting", "pricing": { "cut_25bp": 0.64, "hold": 0.34, "hike_25bp": 0.02 } },
    "boc": { "label": "BOC meeting", "pricing": { "cut_25bp": 0.41, "hold": 0.54, "hike_25bp": 0.05 } }
  },
  "drivers": {
    "fed": { "dovish": [], "hawkish": [] },
    "boc": { "dovish": [], "hawkish": [] }
  },
  "market": { "tickers": [] },
  "calendar": [],
  "history": []
}
```

Constraints:

- Meeting probabilities must be numbers from `0` to `1` and total approximately `1`.
- Driver `weight` must be from `0` to `3`; `published_at_toronto` requires an explicit offset.
- Each driver requires stable `id`, `title`, `importance`, `weight`, `data`, and `reason` fields.
- Calendar items require `datetime_toronto`, `datetime_utc`, `currency`, `event`, and `impact`.
- A historical selection uses the payload's `as_of` as the countdown reference so the page reproduces what a visitor saw on that date.

The detailed dashboard schema remains in `BACKEND_DATA_SPEC.md`.

## 5. HTTP Alternative

A backend service may expose the same files as endpoints:

```text
GET /api/calendar/latest
GET /api/calendar/dates
GET /api/calendar/archive/{date}
GET /api/fed-boc/latest
GET /api/fed-boc/dates
GET /api/fed-boc/archive/{date}
```

Responses must use `Content-Type: application/json; charset=utf-8`. Recommended caching:

- `latest` and `dates`: `Cache-Control: public, max-age=300`
- dated archives: `Cache-Control: public, max-age=31536000, immutable`

Return `404` for a date not listed in `dates.json`. Do not silently substitute the latest snapshot.

## 6. Validation Checklist

- [ ] Toronto publication date matches `fetched_at` or `as_of`.
- [ ] Archive JSON parses with strict JSON and contains no `NaN`/`Infinity`.
- [ ] `latest` points to the maximum available date.
- [ ] Every entry in `dates.json` has a corresponding archive file.
- [ ] Calendar `count` equals the event count and chart history is chronological.
- [ ] Fed/BOC probabilities are bounded and required driver arrays exist.
- [ ] Failed updates preserve the previous latest snapshot.
- [ ] Historical date selection works from both desktop and mobile pages.

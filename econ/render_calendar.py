#!/usr/bin/env python3
"""Render economic_calendar.json -> HTML (pure code, no LLM).

Usage:
    python econ/render_calendar.py --date 2026-08-24
    python econ/render_calendar.py --input archive/2026-08-24/economic_calendar.json --output docs/economic_calendar.html

Also supports --watch to auto-regenerate on file change.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import shutil
from collections import defaultdict, OrderedDict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from statistics import median
from zoneinfo import ZoneInfo

from jinja2 import Environment, FileSystemLoader

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

STAGE_DIR = Path(__file__).resolve().parent

# Currency -> flag emoji (fallback) + image code for reliable rendering
FLAG = {
    "USD": "🇺🇸", "EUR": "🇪🇺", "GBP": "🇬🇧", "JPY": "🇯🇵",
    "CNY": "🇨🇳", "AUD": "🇦🇺", "CAD": "🇨🇦", "CHF": "🇨🇭",
    "NZD": "🇳🇿", "HKD": "🇭🇰", "SGD": "🇸🇬", "UAH": "🇺🇦",
}
# Currency -> ISO 3166-1 alpha-2 for flagcdn.com (reliable image, works on Windows)
FLAG_CODE = {
    "USD": "us", "EUR": "eu", "GBP": "gb", "JPY": "jp",
    "CNY": "cn", "AUD": "au", "CAD": "ca", "CHF": "ch",
    "NZD": "nz", "HKD": "hk", "SGD": "sg", "UAH": "ua",
    "SEK": "se", "NOK": "no", "MXN": "mx", "ZAR": "za",
    "BRL": "br", "INR": "in", "KRW": "kr", "TRY": "tr",
}
WEEKDAY = ["Mon","Tue","Wed","Thu","Fri","Sat","Sun"]
TORONTO = ZoneInfo("America/Toronto")
PERIOD_RE = re.compile(r"\s*\((MoM|YoY|QoQ)\)\s*$", re.IGNORECASE)
PERIOD_LABELS = {
    "MoM": "Monthly change",
    "YoY": "Annual change",
    "QoQ": "Quarterly change",
}
CATEGORY_RULES = (
    ("Labor market", ("jobless", "nonfarm", "payroll", "employment", "unemployment", "jolts", "adp")),
    ("Housing", ("housing", "home sales", "house price", "mortgage", "building permit", "construction")),
    ("Inflation", ("inflation", "consumer price", "price index", "pce price", "personal consumption expenditures", "producer price", "hicp")),
    ("Growth & demand", ("gross domestic product", "gdp", "durable goods", "personal income", "personal spending", "retail sales", "industrial production", "trade balance")),
    ("Business & confidence", ("pmi", "ifo", "zew", "confidence", "sentiment", "business climate")),
)
CATEGORY_ORDER = ["Labor market", "Inflation", "Growth & demand", "Housing", "Business & confidence", "Other"]


def load_calendar(path: Path) -> dict:
    # Be tolerant of NaN literal (old files) -> replace with null before json load
    text = path.read_text(encoding="utf-8")
    # fix invalid JSON NaN (pandas wrote NaN without quotes)
    text = text.replace(": NaN", ": null").replace(": nan", ": null")
    return json.loads(text)


def _atomic_copy(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.tmp")
    shutil.copyfile(source, temporary)
    temporary.replace(destination)


def _atomic_json(destination: Path, payload: dict) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(destination)


def publish_calendar_snapshot(archive_date: str, data_path: Path, html_path: Path) -> tuple[Path, Path]:
    data_root = REPO_ROOT / "docs" / "data" / "economic-calendar"
    data_archive = data_root / "archive"
    html_archive = REPO_ROOT / "docs" / "economic-calendar" / "archive"

    _atomic_copy(data_path, data_archive / f"{archive_date}.json")
    _atomic_copy(html_path, html_archive / f"{archive_date}.html")

    dates = sorted(path.stem for path in data_archive.glob("*.json"))
    latest_date = dates[-1]
    _atomic_json(data_root / "dates.json", {"latest": latest_date, "dates": list(reversed(dates))})

    latest_data = data_root / "latest.json"
    latest_html = REPO_ROOT / "docs" / "economic_calendar.html"
    _atomic_copy(data_archive / f"{latest_date}.json", latest_data)
    _atomic_copy(html_archive / f"{latest_date}.html", latest_html)
    return latest_data, latest_html


def _toronto_datetime(value: str | None, fallback_date: str = "", fallback_time: str = "") -> datetime | None:
    raw = value or (f"{fallback_date}T{fallback_time}" if fallback_date else "")
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(TORONTO)
    except (TypeError, ValueError):
        return None


def _display_time(value: datetime) -> str:
    return value.strftime("%I:%M %p").lstrip("0")


def _split_period(name: str) -> tuple[str, str | None]:
    match = PERIOD_RE.search(name or "")
    if not match:
        return name, None
    period = {"mom": "MoM", "yoy": "YoY", "qoq": "QoQ"}[match.group(1).casefold()]
    return PERIOD_RE.sub("", name).strip(), period


def _display_event_name(name: str) -> str:
    return (
        name.replace("Core Personal Consumption Expenditures - Price Index", "Core PCE Price Index")
        .replace("Personal Consumption Expenditures - Price Index", "PCE Price Index")
        .replace("Personal Consumption Expenditures Prices", "PCE Prices")
    )


def _merge_period_events(events: list[dict]) -> list[dict]:
    buckets: dict[tuple, dict[str, dict]] = defaultdict(dict)
    event_keys: dict[int, tuple] = {}
    for event in events:
        base, period = _split_period(event.get("event") or "")
        if period not in ("MoM", "YoY"):
            continue
        key = (
            event.get("date"),
            event.get("time"),
            event.get("country"),
            event.get("currency"),
            base.casefold(),
        )
        buckets[key][period] = event
        event_keys[id(event)] = key

    pair_keys = {key for key, variants in buckets.items() if {"MoM", "YoY"} <= variants.keys()}
    emitted = set()
    merged = []
    impact_rank = {"HIGH": 0, "MEDIUM": 1, "LOW": 2, "NONE": 3}
    for event in events:
        key = event_keys.get(id(event))
        if key not in pair_keys:
            event["event"] = _display_event_name(event.get("event") or "")
            event["period_rows"] = []
            event["search_text"] = " ".join(str(event.get(k) or "") for k in ("event", "currency", "country")).lower()
            merged.append(event)
            continue
        if key in emitted:
            continue

        variants = buckets[key]
        first = variants["MoM"]
        combined = dict(first)
        combined["event"] = _display_event_name(_split_period(first.get("event") or "")[0])
        combined["title"] = combined["event"]
        combined["impact"] = min(
            (variants[period].get("impact") or "NONE" for period in ("MoM", "YoY")),
            key=lambda impact: impact_rank.get(impact, 3),
        )
        combined["period_rows"] = [
            {
                "period": period,
                "actual": variants[period].get("actual"),
                "forecast": variants[period].get("forecast"),
                "previous": variants[period].get("previous"),
                "unit": variants[period].get("unit") or "",
            }
            for period in ("MoM", "YoY")
        ]
        combined["search_text"] = f"{combined['event']} MoM YoY {combined.get('currency', '')} {combined.get('country', '')}".lower()
        merged.append(combined)
        emitted.add(key)
    return merged


def _chart_category(name: str) -> str:
    lowered = name.casefold()
    for category, keywords in CATEGORY_RULES:
        if any(keyword in lowered for keyword in keywords):
            return category
    return "Other"


def _history_labels(series: list[dict]) -> list[str]:
    parsed_dates = []
    raw_dates = []
    for point in series:
        raw = (point.get("periodDateUtc") or point.get("dateUtc") or point.get("date") or "")[:10]
        raw_dates.append(raw)
        try:
            parsed_dates.append(datetime.strptime(raw, "%Y-%m-%d"))
        except ValueError:
            parsed_dates.append(None)

    valid_dates = [value for value in parsed_dates if value is not None]
    gaps = [(right - left).days for left, right in zip(valid_dates, valid_dates[1:])]
    frequent = bool(gaps) and median(gaps) <= 14
    date_format = "%b %d" if frequent else "%b '%y"
    return [value.strftime(date_format) if value else raw for value, raw in zip(parsed_dates, raw_dates)]


def build_context(data: dict, snapshot_date: str | None = None) -> dict:
    events = [dict(event) for event in data.get("events", [])]
    # Normalize nulls and enrich
    for e in events:
        for k in ("actual","forecast","previous","url","unit","eventId"):
            if e.get(k) is None or (isinstance(e.get(k), float) and str(e[k])=="nan"):
                e[k]=None
        # flag - emoji + image code for reliable rendering (Windows emoji often broken)
        cur = e.get("currency") or ""
        e["flag"] = FLAG.get(cur, "🏳️")
        code = FLAG_CODE.get(cur)
        e["flag_code"] = code
        e["flag_url"] = f"https://flagcdn.com/w20/{code}.png" if code else None
        e["flag_url_2x"] = f"https://flagcdn.com/w40/{code}.png" if code else None
        local_dt = _toronto_datetime(e.get("datetime_utc"), e.get("date") or "", e.get("time") or "")
        if local_dt:
            e["date"] = local_dt.strftime("%Y-%m-%d")
            e["time"] = local_dt.strftime("%H:%M")
            e["display_time"] = _display_time(local_dt)
            e["weekday"] = WEEKDAY[local_dt.weekday()]
            e["timezone"] = local_dt.tzname()
        else:
            e["display_time"] = e.get("time") or ""
            try:
                e["weekday"] = WEEKDAY[datetime.strptime(e["date"], "%Y-%m-%d").weekday()]
            except (KeyError, TypeError, ValueError):
                e["weekday"] = ""
        # ensure impact upper
        e["impact"] = (e.get("impact") or "NONE").upper()
        if e["impact"] not in ("HIGH","MEDIUM","LOW","NONE"):
            e["impact"]="NONE"
        # Format forecast/previous for display, keep numeric for chart
        for k in ("forecast","previous","actual"):
            v = e.get(k)
            if v is not None:
                try:
                    # Keep as float for now, template will format
                    e[k] = float(v) if isinstance(v, (int,float)) or (isinstance(v, str) and v.replace('.','',1).replace('-','',1).isdigit()) else v
                except Exception:
                    pass

    # Sort by datetime_utc then currency
    def sort_key(x):
        return (x.get("datetime_utc") or x.get("date") or "", x.get("currency") or "")
    events.sort(key=sort_key)

    display_events = _merge_period_events(events)

    # Group by Toronto date
    grouped = OrderedDict()
    for e in display_events:
        grouped.setdefault(e["date"], []).append(e)

    previous_day = None
    if snapshot_date:
        try:
            previous_day = (date.fromisoformat(snapshot_date) - timedelta(days=1)).isoformat()
        except ValueError:
            pass
    timeline_days = [
        {
            "date": day,
            "weekday": day_events[0].get("weekday", ""),
            "is_previous_day": day == previous_day,
            "us_events": [event for event in day_events if event.get("country") == "US"],
            "other_events": [event for event in day_events if event.get("country") != "US"],
        }
        for day, day_events in grouped.items()
    ]

    currencies = sorted({e["currency"] for e in events if e.get("currency")})
    dates = sorted(grouped.keys())
    high = sum(1 for e in events if e["impact"]=="HIGH")
    medium = sum(1 for e in events if e["impact"]=="MEDIUM")
    low = sum(1 for e in events if e["impact"]=="LOW")

    # History for charts
    history = data.get("history", {}) or {}
    history_meta = data.get("history_meta", {}) or {}
    # Focus: US primary, Canada secondary, Europe tertiary — exclude AUD/JPY/NZD etc.
    ALLOWED_CURRENCIES = ("USD", "CAD", "EUR", "GBP", "CHF", "EMU", "DE", "FR", "IT", "ES", "UK")
    charts = []
    for event_id, series in history.items():
        meta = history_meta.get(event_id, {})
        event_name = meta.get("event") or "Unknown"
        currency = meta.get("currency") or ""
        unit = meta.get("unit") or ""
        has_numeric = any(pt.get("actual") is not None for pt in series)
        if not has_numeric:
            continue
        if currency not in ALLOWED_CURRENCIES:
            continue
        # Find upcoming event for this series to get forecast
        upcoming = next((ev for ev in events if ev.get("eventId")==event_id), None)
        forecast_val = upcoming.get("forecast") if upcoming else None
        actuals = []
        for pt in series:
            actuals.append(pt.get("actual"))
        display_event, period = _split_period(event_name)
        display_event = _display_event_name(display_event)
        latest_actual = next((value for value in reversed(actuals) if value is not None), None)
        upcoming_label = None
        if upcoming:
            try:
                upcoming_label = f"{datetime.strptime(upcoming['date'], '%Y-%m-%d').strftime('%b %d')} at {upcoming['display_time']}"
            except (KeyError, TypeError, ValueError):
                upcoming_label = upcoming.get("date")
        code = FLAG_CODE.get(currency)
        chart_obj = {
            "event": display_event,
            "currency": currency,
            "flag": FLAG.get(currency, "🏳️"),
            "flag_url": f"https://flagcdn.com/w20/{code}.png" if code else None,
            "flag_url_2x": f"https://flagcdn.com/w40/{code}.png" if code else None,
            "unit": unit,
            "period": period,
            "period_label": PERIOD_LABELS.get(period),
            "category": _chart_category(event_name),
            "labels": _history_labels(series),
            "actuals": actuals,
            "latest_actual": latest_actual,
            "forecast": forecast_val,
            "upcoming_label": upcoming_label,
        }
        charts.append(chart_obj)

    period_rank = {"MoM": 0, "YoY": 1, "QoQ": 2, None: 3}
    charts.sort(key=lambda chart: (
        CATEGORY_ORDER.index(chart["category"]),
        chart["event"].casefold(),
        period_rank.get(chart["period"], 4),
    ))
    for index, chart in enumerate(charts, 1):
        chart["chart_id"] = f"chart-{index}"

    chart_groups = [
        {"name": category, "charts": [chart for chart in charts if chart["category"] == category]}
        for category in CATEGORY_ORDER
        if any(chart["category"] == category for chart in charts)
    ]
    chart_data = [
        {
            "id": chart["chart_id"],
            "labels": chart["labels"],
            "actuals": chart["actuals"],
            "latest_actual": chart["latest_actual"],
            "forecast": chart["forecast"],
            "unit": chart["unit"],
        }
        for chart in charts
    ]

    display_start = snapshot_date or (dates[0] if dates else data.get("start"))
    return {
        "start": display_start,
        "end": dates[-1] if dates else data.get("end"),
        "fetched_at": data.get("fetched_at"),
        "source": data.get("source"),
        "count": data.get("count", len(events)),
        "high_count": high,
        "medium_count": medium,
        "low_count": low,
        "currencies": currencies,
        "dates": dates,
        "grouped": grouped,
        "timeline_days": timeline_days,
        "charts": charts,
        "chart_groups": chart_groups,
        "chart_data": chart_data,
        "has_history": len(charts) > 0,
    }


def main() -> None:
    p = argparse.ArgumentParser(description="Render economic calendar HTML")
    p.add_argument("--date", default=date.today().isoformat(), help="archive date YYYY-MM-DD")
    p.add_argument("--input", default=None, help="input json path (overrides --date)")
    p.add_argument("--output", default=None, help="output html path (default archive/<date>/economic_calendar.html)")
    p.add_argument("--docs", action="store_true", help="also copy to docs/economic_calendar.html for GitHub Pages")
    args = p.parse_args()

    if args.input:
        in_path = Path(args.input)
        out_date = args.date
    else:
        in_path = REPO_ROOT / "archive" / args.date / "economic_calendar.json"
        out_date = args.date

    if not in_path.exists():
        print(f"not found: {in_path}", file=sys.stderr)
        print(f"hint: python econ/fetch_calendar.py --date {out_date} --days 7", file=sys.stderr)
        sys.exit(1)

    data = load_calendar(in_path)
    ctx = build_context(data, out_date)
    ctx["archive_date"] = out_date

    env = Environment(loader=FileSystemLoader(str(STAGE_DIR)), autoescape=True)
    tmpl = env.get_template("template_calendar.html.j2")
    html = tmpl.render(**ctx)
    html = "\n".join(line.rstrip() for line in html.splitlines()) + "\n"

    if args.output:
        out_path = Path(args.output)
    else:
        out_path = REPO_ROOT / "archive" / out_date / "economic_calendar.html"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding="utf-8")
    print(f"wrote {out_path} ({ctx['count']} events)")

    latest_data, latest_html = publish_calendar_snapshot(out_date, in_path, out_path)
    print(f"published calendar snapshot {out_date}")
    print(f"latest data: {latest_data}")
    print(f"latest page: {latest_html}")

if __name__ == "__main__":
    main()

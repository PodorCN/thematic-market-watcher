#!/usr/bin/env python3
"""Stage-like fetcher for global economic calendar.

Writes archive/<date>/economic_calendar.json — same file-per-stage pattern
as returns/fetch_data.py and news/fetch_headlines.py.

Example:
    python econ/fetch_calendar.py --date 2026-08-24 --days 7
    python econ/fetch_calendar.py --date 2026-08-24 --currencies USD,EUR,JPY --impacts HIGH
    python econ/fetch_calendar.py --from 2026-08-24 --to 2026-08-31 --watch
"""
from __future__ import annotations

import argparse
import sys
from datetime import date, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from econ.core import EconomicCalendar  # noqa: E402


def _resolve_window(
    snapshot_date: str,
    date_from: str | None,
    date_to: str | None,
    days: int,
) -> tuple[str, str]:
    snapshot = date.fromisoformat(snapshot_date)
    start = date.fromisoformat(date_from) if date_from else snapshot - timedelta(days=1)
    if date_to:
        end = date.fromisoformat(date_to)
    elif date_from:
        end = start + timedelta(days=days - 1)
    else:
        end = snapshot + timedelta(days=days - 1)
    return start.isoformat(), end.isoformat()


def main() -> None:
    p = argparse.ArgumentParser(description="Fetch global economic calendar (fxstreet primary, ForexFactory fallback)")
    p.add_argument("--date", default=date.today().isoformat(), help="Toronto snapshot/archive date YYYY-MM-DD")
    p.add_argument("--from", dest="date_from", default=None, help="start date YYYY-MM-DD")
    p.add_argument("--to", dest="date_to", default=None, help="end date YYYY-MM-DD")
    p.add_argument("--days", type=int, default=7, help="days from the snapshot date if --from/--to are omitted (default 7, plus the previous day)")
    p.add_argument("--countries", default=None, help="comma-separated fxstreet country codes: US,UK,EMU,JP,CN,... (default global)")
    p.add_argument("--currencies", default=None, help="filter by currency: USD,EUR,GBP,JPY,CNY,...")
    p.add_argument("--impacts", default=None, help="filter by impact: HIGH,MEDIUM,LOW (comma-separated)")
    p.add_argument("--with-details", action="store_true", help="fetch per-event details (forecast/previous, threaded)")
    p.add_argument("--with-history", action="store_true", help="fetch historical series for key indicators (adds ~6*12 requests, enables charts)")
    p.add_argument("--history-limit", type=int, default=12, help="historical points per indicator (default 12)")
    p.add_argument("--history-events", type=int, default=6, help="number of indicators to fetch history for (default 6)")
    p.add_argument("--threads", type=int, default=5, help="thread count for details")
    p.add_argument("--output", default="economic_calendar.json", help="filename inside archive/<date>/")
    p.add_argument("--csv", action="store_true", help="also write CSV alongside JSON")
    args = p.parse_args()

    if args.days < 1:
        p.error("--days must be at least 1")
    start, end = _resolve_window(args.date, args.date_from, args.date_to, args.days)

    countries = [c.strip().upper() for c in args.countries.split(",") if c.strip()] if args.countries else None
    currencies = [c.strip().upper() for c in args.currencies.split(",") if c.strip()] if args.currencies else None
    impacts = [c.strip().upper() for c in args.impacts.split(",") if c.strip()] if args.impacts else None

    print(f"-- economic calendar: {start} -> {end} (archive date {args.date})")
    if countries:
        print(f"   countries: {countries}")
    if currencies:
        print(f"   currencies: {currencies}")
    if impacts:
        print(f"   impacts: {impacts}")

    # HTML needs forecast/previous + history for charts, so enable details+history by default
    # Keep flags for explicit control, but default to True for better UX
    want_details = True if not args.with_details and not args.with_history else (args.with_details or args.with_history)
    # If no history flag given, still fetch history for HTML (user wants charts)
    want_history = args.with_history or (not args.with_details and not args.with_history)
    # Override: if user explicitly set --with-details without history, respect it
    if args.with_details and not args.with_history:
        want_history = False
    cal = EconomicCalendar(
        start=start,
        end=end,
        countries=countries,
        currencies=currencies,
        impacts=impacts,
        with_details=want_details,
        nb_threads=args.threads,
    )
    df = cal.fetch(with_history=want_history, history_limit=args.history_limit, history_max_events=args.history_events)
    print(f"   fetched {len(df)} events via {cal.source_used}")

    # Summary by impact/currency like market-calendar-tool's stats
    if not df.empty:
        print("   by impact:", df["impact"].value_counts().to_dict())
        print("   by currency:", df["currency"].value_counts().head(10).to_dict())
        # Show top high-impact upcoming
        high = df[df["impact"] == "HIGH"].head(10)
        if not high.empty:
            print("\n   next HIGH impact:")
            for _, r in high.iterrows():
                print(f"     {r['date']} {r['time']:>8} {r['currency']:>4}  {r['event'][:70]}")

    out_dir = REPO_ROOT / "archive" / args.date
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = cal.save_json(out_dir / args.output)
    if args.csv:
        cal.save_csv(out_dir / args.output.replace(".json", ".csv"))

    # Also print path for pipeline chaining
    print(f"\nwrote {json_path}")


if __name__ == "__main__":
    main()

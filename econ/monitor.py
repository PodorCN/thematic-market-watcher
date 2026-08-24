#!/usr/bin/env python3
"""Global data-release MONITOR — watches upcoming events and alerts.

Mimics:
 - ecocal's worldwide filtering + saveCalendar
 - market-calendar-tool's clean + DataFrame
 - spoluan's weekly scrape + impact coloring
 - bockuden/macro-event-telegram-alerts idea of "pre-event alerts"

Features:
 - One-shot table view (default) or --watch live loop
 - Highlights HIGH impact, shows countdown (hh:mm until release)
 - Filters: --currencies, --impacts, --hours (next N hours), --days
 - Supports both local JSON (archive/<date>/economic_calendar.json) and live fetch
 - Colorized output with emoji (🇺🇸🇪🇺🇬🇧🇯🇵) like investiny UX

Examples:
    # one-shot: next 48h high-impact global releases
    python econ/monitor.py --hours 48 --impacts HIGH

    # watch mode: refresh every 5min, alert 60min before HIGH events
    python econ/monitor.py --watch --interval 5 --alert-minutes 60 --impacts HIGH

    # monitor specific currencies only (US+EU+China)
    python econ/monitor.py --currencies USD,EUR,CNY --days 3

    # use cached file instead of live fetch
    python econ/monitor.py --from-file archive/2026-08-24/economic_calendar.json
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

# Ensure UTF-8 output on Windows (cp1252 would choke on emoji)
try:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from econ.core import EconomicCalendar  # noqa: E402
from econ.constants import CURRENCY_EMOJI, IMPACT_COLOR  # noqa: E402


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Monitor global economic data releases")
    p.add_argument("--date", default=None, help="archive date for --from-file default (today)")
    p.add_argument("--from", dest="date_from", default=None)
    p.add_argument("--to", dest="date_to", default=None)
    p.add_argument("--days", type=int, default=3, help="days to look ahead (default 3)")
    p.add_argument("--hours", type=int, default=None, help="hours ahead (overrides --days)")
    p.add_argument("--currencies", default=None, help="filter currencies comma-separated")
    p.add_argument("--countries", default=None, help="filter fxstreet countries")
    p.add_argument("--impacts", default="HIGH,MEDIUM", help="filter impacts (default HIGH,MEDIUM)")
    p.add_argument("--from-file", dest="from_file", default=None, help="use cached JSON instead of live fetch")
    p.add_argument("--watch", action="store_true", help="live watch loop")
    p.add_argument("--interval", type=int, default=5, help="watch refresh minutes (default 5)")
    p.add_argument("--alert-minutes", type=int, default=60, help="alert if event within N minutes (default 60)")
    p.add_argument("--json", action="store_true", help="output JSON instead of table")
    return p.parse_args()


def load_or_fetch(args: argparse.Namespace):
    if args.from_file:
        path = Path(args.from_file)
        data = json.loads(path.read_text(encoding="utf-8"))
        import pandas as pd
        df = pd.DataFrame(data.get("events", []))
        source = data.get("source", "file")
        return df, source
    # compute window
    if args.hours is not None:
        start = datetime.now(timezone.utc).date().isoformat()
        end = (datetime.now(timezone.utc) + timedelta(hours=args.hours)).date().isoformat()
    else:
        if args.date_from:
            start = args.date_from
        elif args.date:
            start = args.date
        else:
            start = datetime.now(timezone.utc).date().isoformat()
        if args.date_to:
            end = args.date_to
        else:
            days = args.days
            end = (datetime.fromisoformat(start).date() + timedelta(days=days - 1)).isoformat()

    countries = [c.strip().upper() for c in args.countries.split(",") if c.strip()] if args.countries else None
    currencies = [c.strip().upper() for c in args.currencies.split(",") if c.strip()] if args.currencies else None
    impacts = [c.strip().upper() for c in args.impacts.split(",") if c.strip()] if args.impacts else None

    cal = EconomicCalendar(start=start, end=end, countries=countries, currencies=currencies, impacts=impacts)
    df = cal.fetch()
    return df, cal.source_used


def countdown_str(event_dt_str: str | None) -> str:
    if not event_dt_str:
        return "  —  "
    try:
        # Parse ISO; assume naive is UTC
        dt = datetime.fromisoformat(event_dt_str.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        delta = dt - now
        secs = int(delta.total_seconds())
        if secs < 0:
            return f"done {-secs//60}m ago" if secs > -3600 else "past"
        h, rem = divmod(secs, 3600)
        m = rem // 60
        if h > 48:
            return f"{h//24}d {h%24}h"
        return f"{h:02d}:{m:02d}"
    except Exception:
        return "  —  "


def print_table(df, source: str, alert_minutes: int = 60) -> None:
    import pandas as pd

    if df.empty:
        print(f"no events (source={source})")
        return

    # Ensure datetime_utc parsed for sorting/filtering by countdown
    # Keep original string for display, but sort by parsed
    def _parse(s):
        try:
            return datetime.fromisoformat(str(s).replace("Z", "+00:00")).replace(tzinfo=timezone.utc) if pd.notna(s) else datetime.max.replace(tzinfo=timezone.utc)
        except Exception:
            return datetime.max.replace(tzinfo=timezone.utc)

    df["_sort"] = df["datetime_utc"].apply(_parse)
    df = df.sort_values("_sort").reset_index(drop=True)

    # Filter to future window if --hours implied (otherwise show all)
    # Already filtered by fetch range; just highlight alert window
    now = datetime.now(timezone.utc)
    alert_cutoff = now + timedelta(minutes=alert_minutes)

    # Header
    print(f"\nGlobal Data Release Monitor  |  source={source}  |  now={now.strftime('%Y-%m-%d %H:%M UTC')}  |  alert<{alert_minutes}m = ⚠️")
    print("─" * 120)
    print(f"{'When(UTC)':<18} {'In':<10} {'Cur':<6} {'Imp':<8} {'Event':<58} {'Fcst':<10} {'Prev':<10}")
    print("─" * 120)

    for _, r in df.iterrows():
        dt_str = str(r.get("datetime_utc") or f"{r.get('date')} {r.get('time')}")
        # Truncate dt display
        disp_dt = dt_str[:16].replace("T", " ")
        cd = countdown_str(str(r.get("datetime_utc")))
        cur = str(r.get("currency") or "—")
        emoji = CURRENCY_EMOJI.get(cur, "🏳️")
        imp = str(r.get("impact") or "NONE")
        col = IMPACT_COLOR.get(imp, "⚪")
        event = str(r.get("event") or r.get("title") or "")[:56]
        # Handle pandas NaN -> "—"
        def _fmt(v):
            import pandas as pd
            if v is None or (isinstance(v, float) and pd.isna(v)) or str(v).lower() == "nan":
                return "—"
            return str(v)[:9]
        fcst = _fmt(r.get("forecast"))
        prev = _fmt(r.get("previous"))

        # Alert highlight: within alert_minutes and HIGH
        try:
            evt_dt = _parse(r.get("datetime_utc"))
            is_alert = (evt_dt >= now) and (evt_dt <= alert_cutoff) and imp == "HIGH"
        except Exception:
            is_alert = False
        alert_mark = "⚠️ " if is_alert else "  "

        # Dim past events
        is_past = False
        try:
            is_past = _parse(r.get("datetime_utc")) < now
        except Exception:
            pass
        dim = "\033[2m" if is_past else ""
        reset = "\033[0m" if is_past else ""

        print(f"{dim}{alert_mark}{disp_dt:<16} {cd:<8} {emoji}{cur:<4} {col}{imp:<6} {event:<58} {fcst:<10} {prev:<10}{reset}")

    print("─" * 120)
    # Summary
    print(f"total {len(df)}  |  HIGH={len(df[df['impact']=='HIGH'])}  MEDIUM={len(df[df['impact']=='MEDIUM'])}  LOW={len(df[df['impact']=='LOW'])}")
    # Next HIGH countdown
    high_future = df[(df["impact"] == "HIGH") & (df["_sort"] >= now)]
    if not high_future.empty:
        nxt = high_future.iloc[0]
        print(f"next HIGH: {nxt['date']} {nxt['time']} {nxt['currency']} {nxt['event']}  (in {countdown_str(str(nxt['datetime_utc']))})")
    print()


def main() -> None:
    args = parse_args()

    def one_shot():
        df, source = load_or_fetch(args)
        if args.json:
            # JSON output for piping
            out = {
                "fetched_at": datetime.now(timezone.utc).isoformat(),
                "source": source,
                "count": len(df),
                "events": df.to_dict(orient="records") if not df.empty else [],
            }
            print(json.dumps(out, ensure_ascii=False, indent=2))
        else:
            print_table(df, source, alert_minutes=args.alert_minutes)

    if not args.watch:
        one_shot()
        return

    # Watch loop
    print(f"watch mode: refresh every {args.interval} min (Ctrl+C to stop)")
    try:
        while True:
            print("\n" + "=" * 120)
            print(f"refresh @ {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
            one_shot()
            # countdown to next refresh
            for remaining in range(args.interval * 60, 0, -1):
                mins, secs = divmod(remaining, 60)
                print(f"\rnext refresh in {mins:02d}:{secs:02d}  (Ctrl+C to exit)  ", end="", flush=True)
                time.sleep(1)
            print("\r" + " " * 60 + "\r", end="")
    except KeyboardInterrupt:
        print("\nmonitor stopped.")


if __name__ == "__main__":
    main()

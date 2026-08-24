"""Investing.com Economic Calendar fetcher — direct implementation.

Tries to fetch timeline data directly from investing.com's
Service/getCalendarFilteredData endpoint (same data the website's
timeline uses). Falls back to FxStreet if Cloudflare blocks.

Usage mirrors econ/core.py: fetch_investing(start, end) -> DataFrame

Note: investing.com is heavily Cloudflare-protected (Just a moment...).
cloudscraper can bypass in many cases, but residential IP may still be
required. This module is ready — when it gets 403, the caller should
fallback to FxStreet (same underlying data provider).
"""

from __future__ import annotations

import time
from datetime import datetime, date, timedelta
from typing import Any

import pandas as pd

try:
    import cloudscraper
    HAS_CLOUDSCRAPER = True
except ImportError:
    HAS_CLOUDSCRAPER = False

try:
    from bs4 import BeautifulSoup
    HAS_BS4 = True
except ImportError:
    HAS_BS4 = False

INVESTING_URL = "https://www.investing.com/economic-calendar/Service/getCalendarFilteredData"
INVESTING_REFERER = "https://www.investing.com/economic-calendar/"

# investing.com country IDs for timeline (common majors)
INVESTING_COUNTRY_IDS = {
    "US": "5", "EU": "72", "EMU": "72", "DE": "17", "FR": "22",
    "IT": "10", "ES": "26", "UK": "4", "JP": "35", "CN": "37",
    "AU": "25", "CA": "6", "CH": "12", "NZ": "43",
}

# category mapping investing.com uses
CATEGORY_IDS = ["_employment","_economicActivity","_inflation","_credit","_centralBanks","_confidenceIndex","_balance","_Bonds"]

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36",
    "Referer": INVESTING_REFERER,
    "X-Requested-With": "XMLHttpRequest",
    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
    "Accept": "*/*",
    "Origin": "https://www.investing.com",
}


def fetch_investing_timeline(
    start: str | date | datetime,
    end: str | date | datetime,
    importance: list[str] | None = None,
    countries: list[str] | None = None,
    timeout: int = 15,
) -> pd.DataFrame:
    """Fetch Investing.com calendar and return DataFrame in same schema as econ/core.py.
    Returns columns: id, datetime_utc, date, time, country, currency, event, impact, actual, forecast, previous, source
    Raises on Cloudflare block (403) so caller can fallback.
    """
    if not HAS_CLOUDSCRAPER or not HAS_BS4:
        raise RuntimeError("need cloudscraper + bs4 for investing.com")

    scraper = cloudscraper.create_scraper(
        browser={"browser": "chrome", "platform": "windows", "mobile": False}
    )

    # Normalize dates
    def norm(d):
        if isinstance(d, str):
            return datetime.strptime(d[:10], "%Y-%m-%d").date()
        if isinstance(d, datetime):
            return d.date()
        return d
    sd = norm(start)
    ed = norm(end)

    # investing.com expects timeFilter and limit_from paging; we fetch in chunks
    # First warm up cookies by GETting main page
    try:
        scraper.get(INVESTING_REFERER, headers={"User-Agent": DEFAULT_HEADERS["User-Agent"]}, timeout=timeout)
    except Exception:
        pass

    country_ids = [INVESTING_COUNTRY_IDS.get(c.upper(), c) for c in (countries or list(INVESTING_COUNTRY_IDS.keys()))]
    imp = importance or ["1","2","3"]  # 1=low,2=medium,3=high
    # Map our HIGH/MEDIUM/LOW to investing 3/2/1 if needed
    imp_map = {"HIGH":"3","MEDIUM":"2","LOW":"1"}
    imp = [imp_map.get(x.upper(), x) for x in imp]

    all_rows: list[dict[str, Any]] = []
    limit_from = 0
    # Investing.com paginates ~ ~100 rows per request; loop until no data
    for _ in range(5):  # cap 5 pages (~500 events) to avoid hammering
        data = {
            "country[]": country_ids,
            "category[]": CATEGORY_IDS,
            "importance[]": imp,
            "timeZone": "55",  # UTC
            "timeFilter": "timeRemain",
            "currentTab": "custom",
            "limit_from": str(limit_from),
        }
        # Need to encode date range: investing.com uses server-side filter, but we can post-filter
        # The endpoint returns HTML snippet with <tr> rows; we filter by date after parse
        r = scraper.post(INVESTING_URL, headers=DEFAULT_HEADERS, data=data, timeout=timeout)
        if r.status_code == 403:
            raise RuntimeError(f"investing.com blocked by Cloudflare (403) — fallback to FxStreet. Body: {r.text[:200]}")
        if r.status_code != 200:
            raise RuntimeError(f"investing.com HTTP {r.status_code}")

        html = r.json().get("data", "") if r.headers.get("Content-Type","").startswith("application/json") else r.text
        if not html or "No results" in html:
            break

        soup = BeautifulSoup(html, "html.parser")
        rows = soup.select("tr.js-event-item")
        if not rows:
            # Alternative selector for investing.com layout
            rows = soup.find_all("tr", attrs={"data-event-datetime": True})
        if not rows:
            break

        for tr in rows:
            try:
                # investing.com row has data-event-datetime like "2026/08/24 07:00:00"
                dt_str = tr.get("data-event-datetime") or tr.find("td", class_="theDay").get_text(strip=True) if tr.find("td", class_="theDay") else ""
                # Currency
                cur_el = tr.find("td", class_="flagCur")
                currency = cur_el.get_text(strip=True).replace("\n","").strip() if cur_el else ""
                # Importance: count of grayFull vs grayEmpty
                imp_el = tr.find("td", class_="sentiment")
                imp_text = imp_el.get_text(strip=True) if imp_el else ""
                # Count bull icons: investing uses <i class="grayFullBullishIcon"> vs grayEmpty
                bulls = len(tr.select("i.grayFullBullishIcon")) or len(tr.select("span.ceFlags"))
                if bulls >= 3:
                    impact = "HIGH"
                elif bulls == 2:
                    impact = "MEDIUM"
                elif bulls == 1:
                    impact = "LOW"
                else:
                    # fallback by title attribute
                    impact = "MEDIUM"

                event_el = tr.find("td", class_="event")
                event = event_el.get_text(strip=True) if event_el else ""
                actual_el = tr.find("td", class_="act")
                forecast_el = tr.find("td", class_="fore")
                prev_el = tr.find("td", class_="prev")
                actual = actual_el.get_text(strip=True) if actual_el else None
                forecast = forecast_el.get_text(strip=True) if forecast_el else None
                previous = prev_el.get_text(strip=True) if prev_el else None
                # Clean placeholders like empty or &nbsp;
                for v in (actual, forecast, previous):
                    if v in ("", "&nbsp;", "—"):
                        v = None

                # Parse datetime
                dt = None
                date_str = ""
                time_str = ""
                if dt_str:
                    try:
                        # try "2026/08/24 07:00:00"
                        dt = datetime.strptime(dt_str.strip(), "%Y/%m/%d %H:%M:%S")
                        date_str = dt.strftime("%Y-%m-%d")
                        time_str = dt.strftime("%H:%M")
                    except Exception:
                        pass
                if not date_str:
                    continue
                # Filter by requested range
                d = datetime.strptime(date_str, "%Y-%m-%d").date()
                if d < sd or d > ed:
                    continue

                all_rows.append({
                    "id": tr.get("id") or tr.get("data-event-id") or f"inv_{date_str}_{currency}_{event[:20]}",
                    "datetime_utc": dt.isoformat() if dt else f"{date_str}T{time_str}",
                    "date": date_str,
                    "time": time_str,
                    "country": currency,  # investing puts currency as country flag
                    "currency": currency,
                    "event": event,
                    "title": event,
                    "impact": impact,
                    "volatility": impact,
                    "actual": actual,
                    "forecast": forecast,
                    "previous": previous,
                    "source": "investing.com",
                    "url": "https://www.investing.com/economic-calendar/",
                    "eventId": tr.get("data-event-id"),
                    "unit": None,
                })
            except Exception:
                continue

        if len(rows) < 50:  # last page
            break
        limit_from += len(rows)
        time.sleep(0.5)

    if not all_rows:
        raise RuntimeError("investing.com returned no parsable rows (likely Cloudflare or layout change)")

    df = pd.DataFrame(all_rows)
    return df


if __name__ == "__main__":
    # quick test
    df = fetch_investing_timeline("2026-08-24", "2026-08-30")
    print(df.head().to_string())
    print(f"fetched {len(df)} investing.com rows")

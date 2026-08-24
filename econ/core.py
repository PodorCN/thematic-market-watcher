"""Core calendar fetcher — mimics ecocal + market-calendar-tool + forex-factory-scraper.

Primary: fxstreet CSV API (ecocal's API_SOURCE_URL) — worldwide, no key, no Cloudflare.
Fallback: ForexFactory weekly HTML scraping (spoluan's approach) if fxstreet fails.

Design mirrors market-calendar-tool's ScrapeResult + clean step, but with
ecocal's global country/volatility filtering semantics.

Usage:
    from econ.calendar import EconomicCalendar
    cal = EconomicCalendar(start="2026-08-24", end="2026-08-31")
    df = cal.fetch()          # pandas DataFrame
    events = cal.to_events()  # list[dict] for JSON
    cal.save_json("archive/2026-08-24/economic_calendar.json")
"""

from __future__ import annotations

import io
import json
import re
import time
from dataclasses import dataclass, asdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import requests
import pandas as pd

from .constants import (
    COUNTRY_MAP,
    DEFAULT_COUNTRIES,
    DEFAULT_USER_AGENT,
    FXSTREET_API_URL,
    FXSTREET_BASE_URL,
    FXSTREET_CATEGORIES,
    IMPACT_LEVELS,
    VOLATILITIES,
)

# Optional dependencies — degrade gracefully
try:
    from bs4 import BeautifulSoup  # type: ignore
    HAS_BS4 = True
except ImportError:
    HAS_BS4 = False

try:
    import cloudscraper  # type: ignore
    HAS_CLOUDSCRAPER = True
except ImportError:
    HAS_CLOUDSCRAPER = False


@dataclass
class EconomicEvent:
    """Normalized event — superset of fxstreet + ForexFactory fields."""
    id: str | None
    datetime_utc: str | None  # ISO8601
    date: str  # YYYY-MM-DD
    time: str  # HH:MM (local or UTC depending on source)
    country: str | None
    currency: str | None
    event: str
    title: str
    impact: str  # HIGH / MEDIUM / LOW / NONE
    volatility: str
    actual: str | None
    forecast: str | None
    previous: str | None
    source: str  # fxstreet | forexfactory
    url: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class EconomicCalendar:
    """Worldwide economic calendar fetcher.

    Args:
        start: YYYY-MM-DD or datetime/date. Default today UTC.
        end: YYYY-MM-DD or datetime/date. Default start+7d.
        countries: list of fxstreet country codes (US, UK, EMU, CN, JP ...). Default global.
        impacts: list of impact levels to keep (HIGH/MEDIUM/LOW). None = all.
        currencies: filter by currency after fetch (USD/EUR/GBP...). None = all.
        with_details: if True, fetch per-event details via threaded JSON (ecocal's withDetails).
        nb_threads: concurrency for details fetching (ecocal's nbThreads).

    Mimics:
        ecocal.Calendar(startHorizon, endHorizon, withDetails, nbThreads, preBuildCalendar)
        market-calendar-tool.scrape_calendar(date_from, date_to, extended, options)
    """

    def __init__(
        self,
        start: str | date | datetime | None = None,
        end: str | date | datetime | None = None,
        countries: list[str] | None = None,
        impacts: list[str] | None = None,
        currencies: list[str] | None = None,
        with_details: bool = False,
        nb_threads: int = 5,
        timeout: int = 15,
    ) -> None:
        self.start_str = self._norm_date(start) if start else date.today().isoformat()
        self.end_str = self._norm_date(end) if end else (date.today() + timedelta(days=7)).isoformat()
        self.countries = countries or DEFAULT_COUNTRIES
        self.impacts_filter = [i.upper() for i in impacts] if impacts else None
        self.currencies_filter = [c.upper() for c in currencies] if currencies else None
        self.with_details = with_details
        self.nb_threads = max(1, nb_threads)
        self.timeout = timeout

        self._df: pd.DataFrame | None = None
        self._events: list[EconomicEvent] | None = None
        self.source_used: str | None = None
        self._history: dict[str, list[dict]] = {}
        self._history_meta: dict[str, dict] = {}

    # ------------------------------------------------------------------ public
    def fetch(self, with_history: bool = False, history_limit: int = 12, history_max_events: int = 6) -> pd.DataFrame:
        """Fetch and return cleaned DataFrame. Tries fxstreet, falls back to ForexFactory.
        If with_history True, also fetches details (for forecast/previous) and historical series for key indicators.
        """
        try:
            df = self._fetch_fxstreet()
            self.source_used = "fxstreet"
        except Exception as exc:
            print(f"  ! fxstreet failed ({exc}), falling back to ForexFactory...")
            if not HAS_BS4:
                raise RuntimeError("bs4 not installed and fxstreet fallback failed") from exc
            df = self._fetch_forexfactory()
            self.source_used = "forexfactory"

        # Normalize + clean (market-calendar-tool's clean step)
        df = self._clean(df)

        # Post-filter by impact/currency (ecocal semantics: filter after fetch for flexibility)
        if self.impacts_filter:
            df = df[df["impact"].isin(self.impacts_filter)]
        if self.currencies_filter:
            df = df[df["currency"].isin(self.currencies_filter)]

        df = df.sort_values(by=["datetime_utc", "currency"]).reset_index(drop=True)

        # If with_history, ensure details are fetched (even if with_details False) to get eventId/unit/forecast
        if with_history and self.source_used == "fxstreet" and "eventId" not in df.columns:
            # Force details fetch
            df = self._merge_details_threaded(df)
        elif with_history and self.source_used == "fxstreet" and df.get("eventId") is not None and df["eventId"].isna().all():
            df = self._merge_details_threaded(df)

        # Fetch historical series for key events
        if with_history and self.source_used == "fxstreet":
            try:
                hist = self.enrich_with_history(df, max_events=history_max_events, limit=history_limit)
                self._history = hist
            except Exception as e:
                print(f"  ! history fetch failed: {e}")
                self._history = {}

        self._df = df
        self._events = None  # invalidate
        return df

    def to_events(self) -> list[dict[str, Any]]:
        if self._df is None:
            self.fetch()
        assert self._df is not None
        # lazy build events
        if self._events is None:
            self._events = [EconomicEvent(**row).to_dict() for row in self._df.to_dict(orient="records")]
            # also store as objects for caller that wants attributes
        return [e for e in self._df.to_dict(orient="records")]

    def to_dataframe(self) -> pd.DataFrame:
        if self._df is None:
            self.fetch()
        assert self._df is not None
        return self._df.copy()

    def save_json(self, path: str | Path) -> Path:
        """Save to archive/<date>/economic_calendar.json (stage-file pattern)."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        df = self.to_dataframe()
        # Replace NaN/NaT with None for valid JSON — must cast to object first otherwise float NaN stays
        df_clean = df.astype(object).where(pd.notna(df), None)
        records = df_clean.to_dict(orient="records")
        # Extra safety: any remaining float NaN / inf
        import math
        for rec in records:
            for k, v in list(rec.items()):
                if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
                    rec[k] = None
                # Also catch string "nan" / "None"
                if isinstance(v, str) and v.lower() in ("nan", "none", "nat"):
                    rec[k] = None
        # Include history if available — sanitize too
        history_payload = {}
        history_meta = {}
        if hasattr(self, "_history") and self._history:
            history_payload = self._history
            history_meta = getattr(self, "_history_meta", {})
            # Sanitize history NaNs as well
            for eid, series in history_payload.items():
                for pt in series:
                    for kk, vv in list(pt.items()):
                        if isinstance(vv, float) and (math.isnan(vv) or math.isinf(vv)):
                            pt[kk] = None
        payload = {
            "start": self.start_str,
            "end": self.end_str,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "source": self.source_used,
            "countries": self.countries,
            "impacts_filter": self.impacts_filter,
            "currencies_filter": self.currencies_filter,
            "count": len(df),
            "events": records,
            "history": history_payload,
            "history_meta": history_meta,
        }
        # Use allow_nan=True then sanitize string to avoid ValueError on edge cases
        json_text = json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=True)
        # Sanitize any remaining NaN/Infinity literals to null for strict JSON
        json_text = json_text.replace(": NaN", ": null").replace(": nan", ": null").replace(" NaN", " null")
        json_text = json_text.replace("Infinity", "null").replace("-Infinity", "null")
        path.write_text(json_text, encoding="utf-8")
        print(f"wrote {path} ({len(df)} events, source={self.source_used}, history={len(history_payload)} series)")
        return path

    def save_csv(self, path: str | Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.to_dataframe().to_csv(path, index=False, encoding="utf-8")
        print(f"wrote {path}")
        return path

    # ---------------------------------------------------------------- fxstreet
    def _fetch_fxstreet(self) -> pd.DataFrame:
        """Fetch CSV from fxstreet API (ecocal's _buildCalendar)."""
        # Build URL exactly like ecocal: /eventDates/START/END?volatilities=...&countries=...&categories=...
        # Need ISO with T time
        start_iso = f"{self.start_str}T00:00:00Z"
        end_iso = f"{self.end_str}T23:59:59Z"
        vol_params = "&".join(f"volatilities={v}" for v in VOLATILITIES)
        country_params = "&".join(f"countries={c}" for c in self.countries)
        cat_params = "&".join(f"categories={cat}" for cat in FXSTREET_CATEGORIES)
        url = f"{FXSTREET_API_URL}/{start_iso}/{end_iso}?&{vol_params}&{country_params}&{cat_params}"

        headers = {
            "Accept": "text/csv",
            "Content-Type": "text/csv",
            "Referer": FXSTREET_BASE_URL,
            "Connection": "keep-alive",
            "User-Agent": DEFAULT_USER_AGENT,
        }
        resp = requests.get(url, headers=headers, timeout=self.timeout)
        if resp.status_code != 200:
            raise RuntimeError(f"fxstreet HTTP {resp.status_code}: {resp.text[:500]}")
        # Parse CSV (ecocal uses pd.read_csv on io.StringIO(r.content.decode))
        text = resp.content.decode("utf-8", errors="ignore")
        if not text.strip() or text.strip().startswith("<"):
            raise RuntimeError("fxstreet returned non-CSV (likely blocked)")
        df = pd.read_csv(io.StringIO(text))
        if df.empty:
            # No events in range — return empty with expected columns
            return self._empty_df()

        # Handle new fxstreet CSV format (2024+): Id,Start,Name,Impact,Currency
        # where Start = "08/24/2026 07:00:00"
        if "Start" in df.columns:
            # Normalize new format
            df.rename(columns={"Id": "id", "Name": "event", "Impact": "volatility", "Currency": "currency"}, inplace=True)
            # Parse Start into date/time/datetime_utc
            def _parse_start(s):
                try:
                    dt = datetime.strptime(str(s).strip(), "%m/%d/%Y %H:%M:%S")
                    return dt.strftime("%Y-%m-%d"), dt.strftime("%H:%M"), dt.isoformat()
                except Exception:
                    try:
                        dt = datetime.strptime(str(s).strip(), "%m/%d/%Y %H:%M")
                        return dt.strftime("%Y-%m-%d"), dt.strftime("%H:%M"), dt.isoformat()
                    except Exception:
                        return None, None, str(s)
            parsed = df["Start"].apply(_parse_start)
            df["date"] = [p[0] for p in parsed]
            df["time"] = [p[1] for p in parsed]
            df["datetime_utc"] = [p[2] for p in parsed]
            df["title"] = df["event"]
            df["impact"] = df["volatility"].apply(self._normalize_impact)
            # Infer country from currency
            rev_map = {v: k for k, v in COUNTRY_MAP.items()}
            # Keep first country for EUR (could be EMU) — use EMU for EUR
            rev_map["EUR"] = "EMU"
            df["country"] = df["currency"].map(rev_map)
            for col in ["actual", "forecast", "previous", "eventId", "unit", "hasHistorical"]:
                if col not in df.columns:
                    df[col] = None
            df["source"] = "fxstreet"
            df["url"] = None
        else:
            # Legacy format: Id, Date, Time, Country, Currency, Title, Volatility, Actual...
            col_map = {
                "Id": "id",
                "Date": "date",
                "Time": "time",
                "Country": "country",
                "Currency": "currency",
                "Title": "title",
                "Event": "event",
                "Name": "event",
                "Volatility": "volatility",
                "Impact": "volatility",
                "Actual": "actual",
                "Forecast": "forecast",
                "Previous": "previous",
            }
            for old, new in col_map.items():
                if old in df.columns:
                    df.rename(columns={old: new}, inplace=True)
            for col in ["id", "date", "time", "country", "currency", "title", "volatility", "actual", "forecast", "previous"]:
                if col not in df.columns:
                    df[col] = None
            if "event" not in df.columns or df["event"].isna().all():
                df["event"] = df["title"]
            else:
                df["event"] = df["event"].fillna(df["title"])
            df["title"] = df["title"].fillna(df["event"])
            df["volatility"] = df["volatility"].astype(str).str.upper().str.strip()
            df["impact"] = df["volatility"].apply(self._normalize_impact)
            df["currency"] = df.apply(lambda r: r["currency"] if pd.notna(r["currency"]) and str(r["currency"]).strip() else COUNTRY_MAP.get(str(r["country"]).upper(), None), axis=1)
            df["datetime_utc"] = df.apply(lambda r: self._combine_datetime(r.get("date"), r.get("time")), axis=1)
            df["source"] = "fxstreet"
            df["url"] = None

        # Keep normalized columns in fixed order (like market-calendar-tool's base)
        keep = ["id", "datetime_utc", "date", "time", "country", "currency", "event", "title", "impact", "volatility", "actual", "forecast", "previous", "source", "url", "eventId", "unit", "hasHistorical"]
        df = df[[c for c in keep if c in df.columns]]

        # Optionally fetch details per event (ecocal's threaded _getDetails)
        if self.with_details:
            df = self._merge_details_threaded(df)
            # Ensure keep order after merge (details may add columns)
            df = df[[c for c in keep if c in df.columns]]

        return df

    def _merge_details_threaded(self, df: pd.DataFrame) -> pd.DataFrame:
        """Fetch per-event JSON details via threaded requests (mirrors ecocal._getDetails).
        Correctly maps fxstreet detail fields: consensus->forecast, previous, actual, eventId, unit.
        """
        from concurrent.futures import ThreadPoolExecutor, as_completed

        if df.empty or "id" not in df.columns:
            return df

        ids = df["id"].dropna().astype(str).tolist()
        if not ids:
            return df

        def _fetch_one(eid: str) -> dict | None:
            url = f"{FXSTREET_API_URL}/{eid}"
            headers = {
                "Accept": "application/json",
                "Content-Type": "application/json",
                "Referer": FXSTREET_BASE_URL,
                "User-Agent": DEFAULT_USER_AGENT,
            }
            try:
                r = requests.get(url, headers=headers, timeout=self.timeout)
                if r.status_code // 100 == 2:
                    return r.json()
            except Exception:
                pass
            return None

        details: dict[str, dict] = {}
        with ThreadPoolExecutor(max_workers=self.nb_threads) as ex:
            futs = {ex.submit(_fetch_one, eid): eid for eid in ids[:200]}  # cap 200 for monitor
            for fut in as_completed(futs):
                eid = futs[fut]
                data = fut.result()
                if data:
                    details[eid] = data

        if not details:
            return df

        # Map detail fields onto df columns
        # Ensure columns exist
        for col in ["eventId", "unit", "forecast", "previous", "actual"]:
            if col not in df.columns:
                df[col] = None
        for eid, j in details.items():
            mask = df["id"] == eid
            if not mask.any():
                continue
            # consensus is forecast
            consensus = j.get("consensus")
            prev = j.get("previous")
            actual = j.get("actual")
            event_id = j.get("eventId")
            unit = j.get("unit")
            # Only overwrite if not None (future events have actual null)
            df.loc[mask, "eventId"] = event_id
            df.loc[mask, "unit"] = unit
            # consensus -> forecast (even if None, keep)
            df.loc[mask, "forecast"] = consensus
            df.loc[mask, "previous"] = prev
            # For past events, actual is populated; for future, keep None
            if actual is not None:
                df.loc[mask, "actual"] = actual
            # Also store hasHistorical for chart eligibility
            df.loc[mask, "hasHistorical"] = j.get("hasHistorical")
        return df

    def fetch_historical(self, event_id: str, limit: int = 12) -> list[dict]:
        """Fetch historical series for a given fxstreet eventId via /events/{eventId}/historical.
        Returns list of {dateUtc, actual, consensus, previous} sorted newest first.
        """
        url = f"https://calendar-api.fxstreet.com/en/api/v1/events/{event_id}/historical"
        headers = {
            "Accept": "application/json",
            "Referer": FXSTREET_BASE_URL,
            "User-Agent": DEFAULT_USER_AGENT,
        }
        try:
            r = requests.get(url, headers=headers, timeout=self.timeout)
            if r.status_code // 100 != 2:
                return []
            data = r.json()
            if not isinstance(data, list):
                return []
            # Sort by dateUtc descending (newest first), take limit
            data_sorted = sorted(data, key=lambda x: x.get("dateUtc") or "", reverse=True)
            out = []
            for item in data_sorted[:limit]:
                out.append({
                    "dateUtc": item.get("dateUtc"),
                    "periodDateUtc": item.get("periodDateUtc"),
                    "actual": item.get("actual"),
                    "consensus": item.get("consensus"),
                    "previous": item.get("previous"),
                    "date": (item.get("dateUtc") or "")[:10],
                })
            # Return chronological order for chart (oldest -> newest)
            out.reverse()
            return out
        except Exception:
            return []

    # Predefined job eventIds for US & Canada — always show even if not in upcoming week
    JOB_EVENT_IDS = {
        "9c689bbf-af2a-4f65-81a8-c5f5e2b78d70": {"event": "Initial Jobless Claims", "currency": "USD", "unit": None, "impact": "MEDIUM"},
        "f9277929-3091-4219-aa73-715d3adadb57": {"event": "Continuing Jobless Claims", "currency": "USD", "unit": None, "impact": "LOW"},
        "9cdf56fd-99e4-4026-aa99-2b6c0ca92811": {"event": "Nonfarm Payrolls", "currency": "USD", "unit": "K", "impact": "HIGH"},
        "932c21fa-f664-40e1-a921-dbeb452f0081": {"event": "Unemployment Rate", "currency": "USD", "unit": "%", "impact": "MEDIUM"},
        "4f50e4f8-cd33-428b-b721-5fb620b7f097": {"event": "ADP Employment Change", "currency": "USD", "unit": "K", "impact": "HIGH"},
        "9ba65d91-c2d2-4e4b-b6f3-dfe3677dc980": {"event": "JOLTS Job Openings", "currency": "USD", "unit": "M", "impact": "MEDIUM"},
        "b2c3c097-b609-4385-bf44-f70089df1074": {"event": "Net Change in Employment", "currency": "CAD", "unit": "K", "impact": "HIGH"},
        "e620bb5a-1940-4e56-9a96-ca279a85e57f": {"event": "Employment Cost Index", "currency": "USD", "unit": "%", "impact": "MEDIUM"},
    }

    def enrich_with_history(self, df: pd.DataFrame, max_events: int = 6, limit: int = 12) -> dict[str, list[dict]]:
        """For HIGH/medium events with eventId, fetch historical series.
        Focus: US > Canada > Europe, job data always included.
        Returns dict keyed by eventId with history list.
        """
        from concurrent.futures import ThreadPoolExecutor, as_completed
        if df.empty or "eventId" not in df.columns:
            # still try to fetch job history even if df empty
            candidates = pd.DataFrame()
        else:
            candidates = df[df["eventId"].notna() & df["eventId"].astype(str).str.len().gt(0)].copy()
        # Priority: US > Canada > Europe, job data boosted within tier
        EUROPE_CURRENCIES = ("EUR", "GBP", "CHF", "EMU", "DE", "FR", "IT", "ES", "UK")
        JOB_KEYWORDS = ["Jobless Claims", "Nonfarm", "Payrolls", "Employment", "Unemployment", "JOLTS", "ADP", "Job Cuts"]
        def _priority(row):
            cur = str(row["currency"])
            imp = str(row["impact"])
            name = str(row["event"])
            is_job = any(kw.lower() in name.lower() for kw in JOB_KEYWORDS)
            job_boost = -0.5 if is_job else 0
            if cur == "USD" and imp == "HIGH":
                base = 0
            elif cur == "CAD" and imp == "HIGH":
                base = 1
            elif cur in EUROPE_CURRENCIES and imp == "HIGH":
                base = 2
            elif cur == "USD" and imp == "MEDIUM":
                base = 3
            elif cur == "CAD" and imp == "MEDIUM":
                base = 4
            elif cur in EUROPE_CURRENCIES and imp == "MEDIUM":
                base = 5
            else:
                base = 9
            imp_order = {"HIGH":0,"MEDIUM":1,"LOW":2,"NONE":3}.get(imp, 3)
            return base * 10 + imp_order + job_boost
        if not candidates.empty:
            candidates["_prio"] = candidates.apply(_priority, axis=1)
            candidates = candidates.sort_values(by=["_prio", "impact"])
        # Deduplicate by eventId (only need one per indicator)
        seen = set()
        uniq_ids = []
        uniq_map = {}  # eventId -> event name for title
        for _, row in candidates.iterrows():
            eid = str(row["eventId"])
            if eid in seen:
                continue
            seen.add(eid)
            uniq_ids.append(eid)
            uniq_map[eid] = {"event": row["event"], "currency": row["currency"], "unit": row.get("unit"), "impact": row["impact"]}
            if len(uniq_ids) >= max_events:
                break
        # Always ensure US & CA job data are included even if not in upcoming week
        for jid, meta in self.JOB_EVENT_IDS.items():
            if jid in seen:
                continue
            if len(uniq_ids) >= max_events:
                break
            # Only add if within allowed currencies (US/CAD) — already is
            seen.add(jid)
            uniq_ids.append(jid)
            uniq_map[jid] = meta
        if not uniq_ids:
            return {}

        history: dict[str, list[dict]] = {}
        with ThreadPoolExecutor(max_workers=min(4, len(uniq_ids))) as ex:
            futs = {ex.submit(self.fetch_historical, eid, limit): eid for eid in uniq_ids}
            for fut in as_completed(futs):
                eid = futs[fut]
                try:
                    hist = fut.result()
                    if hist:
                        history[eid] = hist
                except Exception:
                    pass
        # Also store mapping for rendering
        self._history_meta = uniq_map
        return history

    # --------------------------------------------------------------- forexfactory fallback
    def _fetch_forexfactory(self) -> pd.DataFrame:
        """Scrape ForexFactory weekly HTML (spoluan's scrape_forexfactory)."""
        # Generate week urls covering [start, end]
        urls = self._generate_week_urls(self.start_str, self.end_str)
        all_rows: list[dict] = []
        session = cloudscraper.create_scraper() if HAS_CLOUDSCRAPER else requests.Session()
        session.headers.update({"User-Agent": DEFAULT_USER_AGENT})

        for url in urls:
            try:
                resp = session.get(url, timeout=self.timeout)
                resp.raise_for_status()
                rows = self._parse_forexfactory_html(resp.text, url)
                all_rows.extend(rows)
                time.sleep(0.6)  # be polite
            except Exception as exc:
                print(f"  ! forexfactory {url}: {exc}")
                continue

        if not all_rows:
            return self._empty_df()

        df = pd.DataFrame(all_rows)
        # Normalize to our schema (spoluan already uses similar columns)
        # Expected keys: date, time, currency, event, impact, actual, forecast, previous, datetime_utc
        df["country"] = df["currency"].apply(lambda c: {v: k for k, v in COUNTRY_MAP.items()}.get(c, c))
        df["title"] = df["event"]
        df["volatility"] = df["impact"]
        df["impact"] = df["impact"].apply(self._normalize_impact)
        df["source"] = "forexfactory"
        df["id"] = None
        df["url"] = urls[0] if urls else None
        # Ensure date/time formats
        df["datetime_utc"] = df["datetime_utc"].astype(str)
        keep = ["id", "datetime_utc", "date", "time", "country", "currency", "event", "title", "impact", "volatility", "actual", "forecast", "previous", "source", "url"]
        for c in keep:
            if c not in df.columns:
                df[c] = None
        df = df[keep]
        # Filter to requested date range (since weekly urls overshoot)
        df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.strftime("%Y-%m-%d")
        mask = (df["date"] >= self.start_str) & (df["date"] <= self.end_str)
        df = df[mask]
        return df

    def _generate_week_urls(self, start: str, end: str) -> list[str]:
        sd = datetime.strptime(start, "%Y-%m-%d").date()
        ed = datetime.strptime(end, "%Y-%m-%d").date()
        # Align to Monday per ForexFactory week param (like jul21.2024)
        cur = sd - timedelta(days=sd.weekday())  # Monday
        urls = []
        while cur <= ed:
            week_str = cur.strftime("%b%d.%Y").lower()  # e.g. aug24.2026
            urls.append(f"https://www.forexfactory.com/calendar?week={week_str}")
            cur += timedelta(days=7)
        return urls

    def _parse_forexfactory_html(self, html: str, url: str) -> list[dict]:
        if not HAS_BS4:
            return []
        soup = BeautifulSoup(html, "html.parser")
        table = soup.find("table", {"class": "calendar__table"})
        if not table:
            return []
        rows = table.find_all("tr", {"class": "calendar__row"})
        out: list[dict] = []
        last_time = ""
        # ForexFactory embeds date in day-breaker rows; need to track
        # Simplified: extract date from week param fallback, else from breaker
        # We'll try to find breaker text near each row
        for row in rows:
            # Date: look backwards for breaker
            date_cell = row.find_previous("tr", {"class": "calendar__row--day-breaker"})
            date_text = date_cell.get_text(strip=True) if date_cell else ""
            # date_text like "Mon Aug 25" — parse
            parsed_date = self._parse_forexfactory_date(date_text) or self._extract_date_from_url(url)

            time_el = row.find("td", {"class": "calendar__time"})
            t = time_el.get_text(strip=True) if time_el else ""
            if t and t.lower() not in ("", "all day", "tentative", "n/a"):
                last_time = t
            else:
                t = last_time or "00:00"

            curr_el = row.find("td", {"class": "calendar__currency"})
            currency = curr_el.get_text(strip=True) if curr_el else ""

            event_el = row.find("td", {"class": "calendar__event"})
            # Event text may have truncation; get div if exists
            event = event_el.get_text(strip=True) if event_el else ""
            if not event:
                continue

            impact_el = row.find("td", {"class": "calendar__impact"})
            impact = "NONE"
            if impact_el and impact_el.find("span"):
                classes = impact_el.find("span").get("class", [])
                impact = self._impact_from_class(classes)

            actual_el = row.find("td", {"class": "calendar__actual"})
            actual = actual_el.get_text(strip=True) if actual_el else None
            forecast_el = row.find("td", {"class": "calendar__forecast"})
            forecast = forecast_el.get_text(strip=True) if forecast_el else None
            prev_el = row.find("td", {"class": "calendar__previous"})
            previous = prev_el.get_text(strip=True) if prev_el else None

            # Build datetime_utc naive; ForexFactory times are ET — we keep as local string for display,
            # but also try to normalize to UTC: ET = UTC-4/5, for monitor we just keep date+time as ISO
            dt_str = self._combine_datetime(parsed_date, t) or f"{parsed_date}T{t}"
            if currency and event:
                out.append({
                    "date": parsed_date,
                    "time": t,
                    "currency": currency,
                    "event": event,
                    "impact": impact,
                    "actual": actual or None,
                    "forecast": forecast or None,
                    "previous": previous or None,
                    "datetime_utc": dt_str,
                })
        return out

    # ---------------------------------------------------------------- helpers
    @staticmethod
    def _norm_date(d: str | date | datetime) -> str:
        if isinstance(d, str):
            return d[:10]
        if isinstance(d, datetime):
            return d.date().isoformat()
        return d.isoformat()

    @staticmethod
    def _normalize_impact(v: str | None) -> str:
        if not v:
            return "NONE"
        v = str(v).upper().strip()
        if "HIGH" in v or "RED" in v or "3" in v:
            return "HIGH"
        if "MEDIUM" in v or "ORA" in v or "2" in v:
            return "MEDIUM"
        if "LOW" in v or "YEL" in v or "1" in v:
            return "LOW"
        return "NONE"

    @staticmethod
    def _impact_from_class(classes: list[str]) -> str:
        joined = " ".join(classes).lower()
        if "impact-red" in joined:
            return "HIGH"
        if "impact-ora" in joined:
            return "MEDIUM"
        if "impact-yel" in joined:
            return "LOW"
        if "impact-gra" in joined or "impact-whi" in joined:
            return "NONE"
        return "NONE"

    @staticmethod
    def _combine_datetime(d: str | None, t: str | None) -> str | None:
        if not d:
            return None
        d = str(d).strip()
        t = str(t).strip() if t else "00:00"
        # Normalize date: expect YYYY-MM-DD; if not, try parse
        try:
            # d may be like "2026-08-24"
            dt_date = datetime.strptime(d[:10], "%Y-%m-%d")
        except Exception:
            # Try "Aug 25" style
            try:
                cur_year = datetime.now().year
                dt_date = datetime.strptime(f"{d} {cur_year}", "%a %b %d %Y")
            except Exception:
                return f"{d}T{t}"
        # Parse time: "2:30pm", "14:30", "00:00"
        t_clean = t.lower().replace(" ", "")
        for fmt in ("%I:%M%p", "%I%p", "%H:%M", "%H"):
            try:
                dt_time = datetime.strptime(t_clean, fmt)
                return datetime(dt_date.year, dt_date.month, dt_date.day, dt_time.hour, dt_time.minute).isoformat()
            except Exception:
                continue
        return dt_date.strftime("%Y-%m-%d") + f"T{t}"

    @staticmethod
    def _parse_forexfactory_date(text: str) -> str | None:
        # text like "Mon Aug 25" or "Tue • Aug 26"
        text = re.sub(r"[^A-Za-z0-9 ]", " ", text).strip()
        # Extract Mon Aug 25 pattern
        m = re.search(r"(Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s+([A-Za-z]{3})\s+(\d{1,2})", text)
        if not m:
            return None
        try:
            cur_year = datetime.now().year
            dt = datetime.strptime(f"{m.group(2)} {m.group(3)} {cur_year}", "%b %d %Y")
            return dt.strftime("%Y-%m-%d")
        except Exception:
            return None

    @staticmethod
    def _extract_date_from_url(url: str) -> str:
        # week=aug24.2026
        m = re.search(r"week=([a-z]{3})(\d{1,2})\.(\d{4})", url.lower())
        if m:
            try:
                dt = datetime.strptime(f"{m.group(1)} {m.group(2)} {m.group(3)}", "%b %d %Y")
                return dt.strftime("%Y-%m-%d")
            except Exception:
                pass
        return date.today().isoformat()

    @staticmethod
    def _empty_df() -> pd.DataFrame:
        return pd.DataFrame(columns=["id","datetime_utc","date","time","country","currency","event","title","impact","volatility","actual","forecast","previous","source","url","eventId","unit","hasHistorical"])

    @staticmethod
    def _clean(df: pd.DataFrame) -> pd.DataFrame:
        # Drop empty event rows, strip strings, dedupe
        if df.empty:
            return df
        # Strip whitespace for string cols
        for col in df.select_dtypes(include="object").columns:
            df[col] = df[col].astype(str).str.strip().replace({"nan": None, "None": None, "": None})
            # revert "None" string back to None where needed
            df[col] = df[col].where(df[col].notna() & (df[col] != "None"), None)
        # Drop rows with no event title
        df = df[df["event"].notna() & (df["event"].astype(str).str.strip() != "")]
        # Dedupe on id or (date+time+currency+event)
        if "id" in df.columns and df["id"].notna().any():
            df = df.drop_duplicates(subset=["id"], keep="first")
        else:
            df = df.drop_duplicates(subset=["date", "time", "currency", "event"], keep="first")
        return df

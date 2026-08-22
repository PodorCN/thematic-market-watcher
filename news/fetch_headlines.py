#!/usr/bin/env python3
"""Stage 2-pre -- fetch_headlines.py (news/ package)

Deterministic headline fetcher, no LLM involved. Complements
fetch_candidates.py (LLM + web search) with raw headlines pulled
directly from reputable free sources:

  1. yfinance  -- per-ticker news via ``yf.Ticker(t).news`` for every
                  ticker listed in data/tickers.json.
  2. Investing.com RSS -- market-wide headlines from Investing.com's
                  public RSS feeds. (investpy/investiny are dead since
                  Cloudflare blocking in 2022; the official RSS is the
                  reliable path.)

Output: archive/<date>/headlines_raw.json with the same core fields as
schema_candidates.json (headline / source / url / published_at) plus a
``ticker`` key (null for feed items) so downstream stages can consume
either file interchangeably. Each item also carries a short ``summary``
(RSS description / Yahoo summary) and, with --full-text, the extracted
article body in ``content`` (via trafilatura).

Usage:
    python news/fetch_headlines.py [--date YYYY-MM-DD]
        [--limit-per-ticker N] [--no-yfinance] [--no-rss]
        [--full-text] [--max-full-text N]
"""

from __future__ import annotations

import argparse
import json
import sys
import xml.etree.ElementTree as ET
from datetime import date, datetime, timezone
from pathlib import Path

import requests

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

TICKERS_PATH = REPO_ROOT / "config" / "tickers.json"

# Official Investing.com RSS feeds (public, no API key needed).
RSS_FEEDS = {
    "investing.com": [
        "https://www.investing.com/rss/news.rss",       # all news
        "https://www.investing.com/rss/news_25.rss",    # economic indicators
        "https://www.investing.com/rss/news_95.rss",    # commodities
    ]
}

REQUEST_HEADERS = {
    # investing.com rejects the default requests User-Agent sometimes.
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
    ),
}

TIMEOUT_SECONDS = 15


def _norm(headline: dict) -> dict:
    return {
        "headline": headline["headline"].strip(),
        "source": headline["source"],
        "url": headline["url"],
        "published_at": headline.get("published_at"),
        "ticker": headline.get("ticker"),
        "summary": (headline.get("summary") or "").strip() or None,
    }


def fetch_yfinance_headlines(tickers: list[str], limit_per_ticker: int) -> list[dict]:
    """Per-ticker headlines straight from Yahoo Finance."""
    import yfinance as yf

    out: list[dict] = []
    for ticker in tickers:
        try:
            items = yf.Ticker(ticker).news or []
        except Exception as exc:  # noqa: BLE001 -- one bad ticker must not kill the run
            print(f"  ! yfinance {ticker}: {exc}", file=sys.stderr)
            continue
        for item in items[:limit_per_ticker]:
            content = item.get("content") or {}
            title = content.get("title")
            if not title:
                continue
            url_obj = content.get("canonicalUrl") or content.get("clickThroughUrl") or {}
            out.append(
                _norm(
                    {
                        "headline": title,
                        "source": (content.get("provider") or {}).get("displayName", "Yahoo Finance"),
                        "url": url_obj.get("url", ""),
                        "published_at": content.get("pubDate"),
                        "ticker": ticker,
                        "summary": content.get("summary") or content.get("description"),
                    }
                )
            )
    return out


def parse_rss(xml_text: str, source_label: str) -> list[dict]:
    """Parse an RSS 2.0 feed into headline dicts."""
    root = ET.fromstring(xml_text)
    out: list[dict] = []
    for item in root.iter("item"):
        def _text(tag: str) -> str:
            el = item.find(tag)
            return (el.text or "").strip() if el is not None else ""

        link = _text("link")
        title = _text("title")
        if not title or not link:
            continue
        published = _text("pubDate") or None
        if published:
            for fmt, assume_utc in (
                ("%a, %d %b %Y %H:%M:%S %z", False),
                ("%Y-%m-%d %H:%M:%S", True),
            ):
                try:
                    parsed = datetime.strptime(published, fmt)
                    if assume_utc:
                        parsed = parsed.replace(tzinfo=timezone.utc)
                    published = parsed.astimezone(timezone.utc).isoformat()
                    break
                except ValueError:
                    pass  # keep the raw string rather than dropping the item
        out.append(
            _norm(
                {
                    "headline": title,
                    "source": source_label,
                    "url": link,
                    "published_at": published,
                    "ticker": None,
                    "summary": _text("description"),
                }
            )
        )
    return out


def fetch_rss_headlines(feeds: dict[str, list[str]]) -> list[dict]:
    out: list[dict] = []
    for source_label, urls in feeds.items():
        for url in urls:
            try:
                resp = requests.get(url, headers=REQUEST_HEADERS, timeout=TIMEOUT_SECONDS)
                resp.raise_for_status()
                out.extend(parse_rss(resp.text, source_label))
            except Exception as exc:  # noqa: BLE001
                print(f"  ! rss {url}: {exc}", file=sys.stderr)
    return out


def dedupe(headlines: list[dict]) -> list[dict]:
    seen: set[str] = set()
    out: list[dict] = []
    for h in headlines:
        key = h["url"] or h["headline"].lower()
        if key not in seen:
            seen.add(key)
            out.append(h)
    return out


def fetch_full_text(url: str) -> str | None:
    """Download an article page and extract the main body text.

    Uses trafilatura (best-in-class open source article extractor).
    Returns None on any failure -- a missing body must not break the run.
    """
    try:
        import trafilatura

        downloaded = trafilatura.fetch_url(url)
        if not downloaded:
            return None
        text = trafilatura.extract(downloaded, include_comments=False, include_tables=False)
        return text.strip() if text else None
    except Exception as exc:  # noqa: BLE001
        print(f"  ! full-text {url}: {exc}", file=sys.stderr)
        return None


def enrich_with_full_text(headlines: list[dict], max_articles: int) -> None:
    done = 0
    for h in headlines:
        if done >= max_articles:
            break
        if not h["url"]:
            continue
        text = fetch_full_text(h["url"])
        if text:
            h["content"] = text
        done += 1


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=date.today().isoformat())
    parser.add_argument("--limit-per-ticker", type=int, default=8)
    parser.add_argument("--no-yfinance", action="store_true")
    parser.add_argument("--no-rss", action="store_true")
    parser.add_argument(
        "--full-text",
        action="store_true",
        help="also download pages and extract article body text (slow)",
    )
    parser.add_argument("--max-full-text", type=int, default=20)
    args = parser.parse_args()

    out_dir = REPO_ROOT / "archive" / args.date
    out_dir.mkdir(parents=True, exist_ok=True)

    headlines: list[dict] = []

    if not args.no_yfinance:
        tickers = json.loads(TICKERS_PATH.read_text(encoding="utf-8"))["tickers"]
        print(f"-- yfinance: {len(tickers)} tickers")
        headlines.extend(fetch_yfinance_headlines(tickers, args.limit_per_ticker))

    if not args.no_rss:
        print(f"-- rss: {sum(len(v) for v in RSS_FEEDS.values())} feeds")
        headlines.extend(fetch_rss_headlines(RSS_FEEDS))

    headlines = dedupe(headlines)

    if args.full_text:
        print(f"-- full-text: up to {args.max_full_text} articles")
        enrich_with_full_text(headlines, args.max_full_text)
        got = sum(1 for h in headlines if h.get("content"))
        print(f"   extracted body text for {got} articles")

    result = {
        "date": args.date,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "headlines": headlines,
    }
    out_path = out_dir / "headlines_raw.json"
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"wrote {out_path} ({len(headlines)} unique headlines)")


if __name__ == "__main__":
    main()

"""Unit tests for news/fetch_headlines.py.

No network calls -- RSS parsing and dedupe are tested with inline
fixture XML; yfinance fetching is only smoke-tested for its dict
normalization via a fake item payload.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from news.fetch_headlines import dedupe, fetch_yfinance_headlines, parse_rss  # noqa: E402

RSS_FIXTURE = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
  <item>
    <title>Water utilities rally on new EPA rules</title>
    <link>https://www.investing.com/news/a-1</link>
    <description>Shares of water utilities jumped after the announcement.</description>
    <pubDate>Fri, 21 Aug 2026 12:00:00 +0000</pubDate>
  </item>
  <item>
    <title>No date here</title>
    <link>https://www.investing.com/news/a-2</link>
  </item>
  <item>
    <title></title>
    <link>https://www.investing.com/news/a-3</link>
  </item>
</channel></rss>
"""


def test_parse_rss_extracts_items():
    items = parse_rss(RSS_FIXTURE, "investing.com")
    assert len(items) == 2  # empty title dropped
    first = items[0]
    assert first["headline"] == "Water utilities rally on new EPA rules"
    assert first["source"] == "investing.com"
    assert first["url"] == "https://www.investing.com/news/a-1"
    assert first["published_at"] == "2026-08-21T12:00:00+00:00"
    assert first["ticker"] is None
    assert first["summary"] == "Shares of water utilities jumped after the announcement."


def test_parse_rss_keeps_unparseable_date_as_raw_string():
    xml = RSS_FIXTURE.replace("Fri, 21 Aug 2026 12:00:00 +0000", "garbage date")
    items = parse_rss(xml, "investing.com")
    assert items[0]["published_at"] == "garbage date"


def test_dedupe_by_url_and_headline():
    a = {"headline": "A", "source": "s", "url": "u1", "published_at": None, "ticker": None, "summary": None}
    b = {**a, "source": "other"}  # same url -> dup
    c = {"headline": "C", "source": "s", "url": "", "published_at": None, "ticker": None, "summary": None}
    d = {**c}  # same (empty) url -> falls back to headline -> dup
    out = dedupe([a, b, c, d])
    assert [h["headline"] for h in out] == ["A", "C"]


def test_yfinance_normalization_with_fake_payload(monkeypatch):
    class FakeTicker:
        def __init__(self, symbol):
            pass

        @property
        def news(self):
            return [
                {
                    "content": {
                        "title": "  XYL wins contract  ",
                        "provider": {"displayName": "Reuters"},
                        "canonicalUrl": {"url": "https://example.com/xyl"},
                        "pubDate": "2026-08-21T10:00:00Z",
                        "summary": "Xylem signed a $200M deal.",
                    }
                },
                {"content": {}},  # no title -> skipped
            ]

    import types

    fake_mod = types.ModuleType("yfinance")
    fake_mod.Ticker = FakeTicker
    monkeypatch.setitem(sys.modules, "yfinance", fake_mod)

    out = fetch_yfinance_headlines(["XYL"], limit_per_ticker=5)
    assert out == [
        {
            "headline": "XYL wins contract",
            "source": "Reuters",
            "url": "https://example.com/xyl",
            "published_at": "2026-08-21T10:00:00Z",
            "ticker": "XYL",
            "summary": "Xylem signed a $200M deal.",
        }
    ]

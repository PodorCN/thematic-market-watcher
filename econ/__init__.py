"""econ package — global economic calendar monitor.

Mimics the core ideas from:
  - lcsrodriguez/ecocal      -> worldwide fxstreet CSV API, country/volatility filtering, threaded details
  - pavelkrusek/market-calendar-tool -> ScrapeResult + clean + DataFrame + async concurrency
  - spoluan/forex-factory-scraper    -> weekly ForexFactory scraping as fallback (cloudscraper + bs4)

Primary source is fxstreet API (no key, no Cloudflare), fallback is ForexFactory HTML.
"""

from .core import EconomicCalendar, EconomicEvent  # noqa: F401

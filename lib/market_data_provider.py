"""Pluggable structured-data providers for pipeline/01_fetch_data.

fetch_data.py never imports yfinance (or any other vendor) directly -- it
only calls get_provider(name).fetch(tickers). Swapping data vendors later
means adding one class here and changing config/data_source.yaml; no
pipeline code changes.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any


class MarketDataProvider(ABC):
    @abstractmethod
    def fetch(self, tickers: list[str], history_days: int = 30) -> dict[str, Any]:
        """Return {"as_of": iso datetime, "tickers": {symbol: {...}}}.

        Per-symbol fields (see fetch_data.py's raw_data.json contract):
            name, currency, last_close, prev_close, change_pct,
            history: [{"date": "YYYY-MM-DD", "close": float}, ...]
        """


class YFinanceProvider(MarketDataProvider):
    """Default provider. Free, no API key, uses the `yfinance` package."""

    def fetch(self, tickers: list[str], history_days: int = 30) -> dict[str, Any]:
        import yfinance as yf

        result: dict[str, Any] = {
            "as_of": datetime.now(timezone.utc).isoformat(),
            "provider": "yfinance",
            "tickers": {},
        }

        for symbol in tickers:
            ticker = yf.Ticker(symbol)
            hist = ticker.history(period=f"{history_days}d")
            if hist.empty:
                result["tickers"][symbol] = {"error": "no data returned"}
                continue

            closes = hist["Close"].dropna()
            last_close = float(closes.iloc[-1])
            prev_close = float(closes.iloc[-2]) if len(closes) > 1 else last_close
            change_pct = (
                ((last_close - prev_close) / prev_close * 100) if prev_close else 0.0
            )

            info = {}
            try:
                info = ticker.get_info() or {}
            except Exception:
                pass  # info is a nice-to-have; never fail the whole fetch for it

            result["tickers"][symbol] = {
                "name": info.get("shortName") or info.get("longName") or symbol,
                "currency": info.get("currency", "USD"),
                "last_close": round(last_close, 4),
                "prev_close": round(prev_close, 4),
                "change_pct": round(change_pct, 3),
                "history": [
                    {"date": idx.strftime("%Y-%m-%d"), "close": round(float(val), 4)}
                    for idx, val in closes.items()
                ],
            }

        return result


_PROVIDERS: dict[str, type[MarketDataProvider]] = {
    "yfinance": YFinanceProvider,
}


def get_provider(name: str = "yfinance") -> MarketDataProvider:
    try:
        return _PROVIDERS[name]()
    except KeyError:
        raise ValueError(
            f"unknown market data provider '{name}', have: {list(_PROVIDERS)}"
        ) from None

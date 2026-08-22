# Configuring Which Tickers Are Tracked

The list of ETFs/indexes fetched every day lives in **`config/tickers.json`**.
It is configuration, not code — edit freely.

```json
{
  "_comment": "Water-theme tickers tracked for the daily digest.",
  "tickers": [
    "CGW",
    "PHO",
    "FIW",
    "TBLU",
    "AWK",
    "XYL",
    "WTRG",
    "VIE.PA"
  ]
}
```

## Adding / removing tickers

- Add or remove symbols in the `"tickers"` array. The next run of
  `python returns/fetch_data.py` picks up the change automatically — nothing
  else to update.
- Use Yahoo Finance symbol conventions:
  - US ETFs/stocks: plain ticker (`BANK`, `SOXL`)
  - Non-US exchanges: exchange suffix (`VIE.PA` = Veolia on Euronext Paris,
    `7203.T` = Toyota on the Tokyo Stock Exchange)
- If a symbol is wrong or delisted, yfinance logs a warning and the entry
  comes back as `{"error": "no data returned"}` in `raw_data.json`; the
  rest of the run is unaffected.

## Notes

- There is currently one flat global list shared by the whole pipeline.
  If you want per-theme groups (e.g. `water`, `banks`, `leveraged`),
  extend `config/tickers.json` with named sections and have
  `load_tickers()` in `returns/fetch_data.py` merge them.
- History depth defaults to ~30 days (`history_days` in
  `YFinanceProvider.fetch`). Increase it there if you want longer series.

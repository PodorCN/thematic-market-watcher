# Configuring the Theme and Tracked Tickers

The theme (name + description fed to every LLM prompt) and the list of
ETFs/indexes fetched every day live in **`config/tickers.json`**.
They are configuration, not code — edit freely.

```json
{
  "_comment": "Tickers tracked for the daily digest, plus the theme the prompts describe.",
  "theme": {
    "name": "broad market",
    "description": "global equities and macro drivers: broad equity beta, sector rotation (financials, energy, utilities, industrials), rates and duration, real assets, trade policy"
  },
  "tickers": [
    "SPY",
    "QQQ",
    "XLF",
    "XLE",
    "XLU",
    "XLI",
    "TLT",
    "GLD"
  ]
}
```

- `theme.name` — short label used in prompts and the report title
  ("Broad Market Market Watcher" style; keep it title-friendly).
- `theme.description` — one or two sentences telling the analysis stage
  what to look for. This is the single most important knob for steering
  driver-level analysis.
- `tickers` — the data universe. It defines which drivers are visible:
  a sector-only basket can only ever surface sector-internal drivers,
  so include beta/sector/rates/real-asset legs if cross-sector drivers
  matter.

## Adding / removing tickers

- Add or remove symbols in the `"tickers"` array. The next run of
  `python returns/fetch_data.py` picks up the change automatically — nothing
  else to update. If you change the universe mid-stream, re-run all
  downstream stages for that date so every artifact matches.
- Use Yahoo Finance symbol conventions:
  - US ETFs/stocks: plain ticker (`SPY`, `TLT`)
  - Non-US exchanges: exchange suffix (`VIE.PA` = Euronext Paris,
    `7203.T` = Tokyo)
- If a symbol is wrong or delisted, yfinance logs a warning and the entry
  comes back as `{"error": "no data returned"}` in `raw_data.json`; the
  rest of the run is unaffected.

## Notes

- There is currently one flat global list shared by the whole pipeline.
  If you want named groups (e.g. `beta`, `sectors`, `rates`),
  extend `config/tickers.json` with named sections and have
  `load_tickers()` in `returns/fetch_data.py` merge them.
- History depth defaults to ~30 days (`history_days` in
  `YFinanceProvider.fetch`). Increase it there if you want longer series
  -- the analyzer benefits from more context (see
  [analysis-feedback.md](./analysis-feedback.md)).

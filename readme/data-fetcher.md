# Data Fetcher — Usage Guide

`returns/fetch_data.py` is Stage 1 of the pipeline: pure code (no LLM) that
downloads daily market data for a configurable list of ETFs/indexes and
writes it into the date-partitioned archive.

## Quickstart

From the repo root:

```bash
pip install -r requirements.txt

# today (UTC), default ticker list from config/tickers.json, 30d history
python returns/fetch_data.py

# a specific date (used for the archive folder name)
python returns/fetch_data.py --date 2026-08-21
```

### All CLI options

| Flag | Default | Meaning |
|---|---|---|
| `--date` | today (UTC) | Archive folder name (`archive/<date>/`) |
| `--provider` | `yfinance` | Data vendor, see provider abstraction below |
| `--tickers` | *(from `config/tickers.json`)* | Comma-separated symbols; overrides the config file |
| `--history-days` | 30 | Calendar days of daily closes to fetch |
| `--output` | `raw_data.json` | File name written inside `archive/<date>/` |

Examples:

```bash
# ad-hoc list, one year of history, custom output name
python returns/fetch_data.py \
    --tickers ZSP.TO,ZXLC.TO,ZXLK.TO \
    --history-days 365 \
    --output zsp_bmo_sectors_1y.json
```

Output goes to `archive/<YYYY-MM-DD>/raw_data.json`.

On Windows there is no system Python configured; use the repo venv:

```powershell
.\.venv\Scripts\python.exe returns/fetch_data.py
```

## What you get

For each ticker in `config/tickers.json`, `raw_data.json` contains:

| Field | Meaning |
|---|---|
| `name` | Instrument name from Yahoo Finance |
| `currency` | Quote currency |
| `last_close` | Most recent close |
| `prev_close` | Previous trading day's close |
| `change_pct` | Daily return in percent (`(last-prev)/prev*100`) |
| `history` | ~30 daily closes: `[{"date": "YYYY-MM-DD", "close": 123.45}, ...]` |

Plus top-level metadata: `as_of` (fetch timestamp), `provider`,
`fetched_at`, and `date`.

A ticker that returns no data gets `{"error": "no data returned"}` and
never fails the whole run — but do check the console output for
warnings (e.g. delisted symbols).

## Fetching an ad-hoc list of tickers

Use `--tickers` (comma-separated) — no config edit needed:

```bash
python returns/fetch_data.py --tickers HFIN.TO,BANK.TO,SOXL --history-days 365
```

To pull a list you'll reuse across runs, put it in `config/tickers.json`
instead (see [configuring-tickers.md](./configuring-tickers.md)).

## Provider abstraction

`fetch_data.py` never imports `yfinance` itself — it calls
`get_provider(name).fetch(tickers)` from `returns/market_data_provider.py`.
To add another data vendor (Alpha Vantage, Tiingo, ...), subclass
`MarketDataProvider` there and register it in `_PROVIDERS`; then run
with `--provider <name>`. No other file changes.

## Covariance / correlation analysis

`returns/compute_covariance.py` reads any raw-data JSON written by
`fetch_data.py` and computes an exponentially-weighted (decayed)
covariance matrix of daily returns — recent returns count more, weight
controlled by `--halflife` in trading days:

```bash
python returns/compute_covariance.py --input archive/2026-08-22/zsp_bmo_sectors_1y.json \
    [--halflife 63] [--periods 252] [--output out.csv]
```

Prints daily EWMA covariance, annualized covariance, and the implied
correlation matrix; writes all three to CSV next to the input file
(`*_cov_hl<halflife>.csv` by default).

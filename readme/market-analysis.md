# Market Analysis — Usage Guide

`analysis/performance.py` is **not a pipeline stage** — it is the
ad-hoc research toolbox used to answer questions like *"why did this
ETF drop this week?"*. It packages the two moves that every such
investigation starts with:

1. `perf` — windowed performance table across tickers (optionally
   relative to a benchmark), to confirm *what* moved and *how much*.
2. `daily` — day-by-day close + % change breakdown for one ticker,
   with biggest-move days highlighted, to localize *which days*
   happened before you search news for those exact dates.

Pure code, no LLM, no API key. Data comes from yfinance with
`auto_adjust=True`, so **all returns shown are total returns**
(dividends reinvested), not just price change — this matters for
high-dividend names like Canadian bank ETFs.

## Quickstart

From the repo root (on Windows use the repo venv):

```bash
pip install -r requirements.txt

# windowed returns for the default config/tickers.json list
python analysis/performance.py perf

# ad-hoc list, benchmark-relative
python analysis/performance.py perf --tickers ZEB.TO,RY.TO,XIU.TO --benchmark XIU.TO

# day-by-day breakdown for one ticker, last month, top 3 move days
python analysis/performance.py daily ZEB.TO --period 1mo --top 3
```

Windows / no system Python:

```powershell
.\.venv\Scripts\python.exe analysis/performance.py perf
```

### All CLI options

| Command | Flag | Default | Meaning |
|---|---|---|---|
| `perf` | `--tickers` | `config/tickers.json` | Comma-separated symbols |
| `perf` | `--period` | `9mo` | History fetched from yfinance (`1mo`, `6mo`, `1y`, ...) |
| `perf` | `--benchmark` | *(none)* | Subtract this ticker's same-window return; shows *excess* performance |
| `daily` | `ticker` (positional) | required | One symbol |
| `daily` | `--period` | `1mo` | History length |
| `daily` | `--top N` | `0` (off) | Also print the N days with the largest \|chg\| |

## What you get

### `perf`

One row per ticker, columns are % returns over trading-day windows:

```
== windowed returns % (excess vs XIU.TO) ==
          1d    1w    1m    3m     6m
ZEB.TO -0.25 -5.29 -6.91 -0.88   9.98
RY.TO  -1.04 -5.26 -7.56  1.38  10.31
XIU.TO  0.00  0.00  0.00  0.00   0.00   <- benchmark is all zeros by definition
```

Reading it: `ZEB.TO -5.29` on `1w` means "the bank ETF lost 5.3 points
more than the broad market this week" — i.e. a sector-specific selloff,
not market beta. A `None` cell means not enough history for that window.

### `daily`

```
                close  chg_pct
2026-08-18  77.000000    -1.50
2026-08-19  74.459999    -3.30   <- localize THIS date in the news
2026-08-20  73.160004    -1.75
```

The `--top N` section ranks days by absolute move so the exact dates
worth investigating surface immediately.

## Library usage (from other scripts)

Everything above is importable; stages that want these numbers should
call the functions rather than parsing CLI output:

```python
import sys; sys.path.insert(0, str(REPO_ROOT))

from analysis.performance import (
    fetch_closes,          # tickers, period -> wide DataFrame of closes
    performance_table,     # tickers, period, benchmark -> DataFrame (%)
    daily_moves,           # closes Series -> DataFrame(date, close, chg_pct)
    biggest_moves,         # moves DataFrame, n -> largest |chg| rows
)
```

## The research recipe this encodes

When something looks wrong in the market:

1. `perf --benchmark <broad ETF>` → is the drop sector-specific or market-wide?
2. `daily <worst ticker> --top 5` → pin down the exact dates.
3. Search news for those dates only (e.g. FOMC minutes, earnings,
   tariff deadlines) → attribute causes.
4. Optional: `news/fetch_headlines.py` pulls current headlines into
   `archive/<date>/headlines_raw.json` for the pipeline's own view.

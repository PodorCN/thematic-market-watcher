# Macro Pages Data Operations and LLM Handoff

This runbook covers the two public macro pages:

| Page | Staging or raw input | Published data |
|---|---|---|
| Global Economic Calendar | `archive/<date>/economic_calendar.json` | `docs/data/economic-calendar/` |
| Fed/BOC Watcher | `docs/data/fed-boc-dashboard.json` | `docs/data/fed-boc/` |

The canonical publication contract is
[`docs/PUBLIC_PAGES_BACKEND_SPEC.md`](../docs/PUBLIC_PAGES_BACKEND_SPEC.md).
The detailed schemas are
[`docs/BACKEND_API_SPEC.md`](../docs/BACKEND_API_SPEC.md) and
[`docs/BACKEND_DATA_SPEC.md`](../docs/BACKEND_DATA_SPEC.md).

## Current Automation Boundary

- `econ/fetch_calendar.py` collects the Economic Calendar from FxStreet,
  with ForexFactory as its fallback.
- `econ/render_calendar.py` validates and publishes the calendar JSON, date
  manifest, latest page, and dated HTML page.
- `econ/archive_fed_boc.py` validates and publishes an existing Fed/BOC
  staging payload.
- There is currently no Fed/BOC collector. An operator or web-enabled LLM
  must research and update `docs/data/fed-boc-dashboard.json` before it is
  archived.
- `.github/workflows/public-pages-daily.yml` runs daily at `13:10 UTC`. It
  fetches fresh calendar data, but only republishes the Fed/BOC staging file
  already present in the repository. It does not invoke an LLM.
- The public-site repository syncs these artifacts approximately 30 minutes
  later through its `sync-macro-pages.yml` workflow.

## Manual Daily Run

Run from the repository root. On Windows, use the repository virtual
environment explicitly:

```powershell
$date = "YYYY-MM-DD" # Toronto calendar date
.\.venv\Scripts\python.exe econ/fetch_calendar.py --date $date --days 7 --countries US,CA,EMU,DE,FR,IT,ES,UK,CH --impacts HIGH,MEDIUM --with-history --history-events 15 --history-limit 12
.\.venv\Scripts\python.exe econ/render_calendar.py --date $date
```

With no explicit `--from`, the fetcher includes the Toronto calendar day
before `$date` and keeps the full seven-day window beginning on `$date`.

Then research and update `docs/data/fed-boc-dashboard.json`. Do not use the
example payload as current data. After the payload is verified:

```powershell
.\.venv\Scripts\python.exe econ/archive_fed_boc.py --date $date
.\.venv\Scripts\python.exe -m pytest tests/test_econ_render.py tests/test_fed_boc_archive.py -q
```

Review only the relevant output paths before publishing:

```text
archive/<date>/economic_calendar.json
docs/economic_calendar.html
docs/economic-calendar/archive/<date>.html
docs/data/economic-calendar/
docs/data/fed-boc-dashboard.json
docs/data/fed-boc/
```

## Publish to PodorCN.github.io

`thematic-market-watcher` is the source-data repository. The public website is
served from the sibling `PodorCN.github.io` repository, where the final files
live under `macro/`. For an immediate end-to-end publication, first commit and
push only the intended source snapshots to `thematic-market-watcher/dev`, then
run from the source repository root:

```powershell
.\.venv\Scripts\python.exe ..\PodorCN.github.io\sync_macro_pages.py --source docs
git -C ..\PodorCN.github.io status --short
git -C ..\PodorCN.github.io diff -- macro
```

After reviewing the public diff, commit only `macro/` in the website repository
and push `PodorCN.github.io/main`. The website workflow
`.github/workflows/sync-macro-pages.yml` also performs this sync daily, but an
LLM assigned an immediate publication should not wait for the schedule.

## Fed/BOC Collection Rules

1. Read the current payload before editing it and preserve its schema and
   stable driver IDs where the underlying event has not changed.
2. Use authoritative or direct sources where possible: Federal Reserve and
   Bank of Canada for meetings and decisions; BLS, BEA, and Statistics Canada
   for releases; CME FedWatch and an identified OIS source for market pricing;
   structured market data such as yfinance for the validation strip.
3. Every driver must have a verifiable source and `source_url`, plus a one-line
   plain-English `summary` (for example "Job market is cracking: payrolls went
   negative, far below forecast."). Keep Actual, Forecast, and Previous
   distinct. Do not infer or invent missing values.
4. Reuse the freshly collected `archive/<date>/economic_calendar.json` for
   upcoming releases when possible instead of transcribing the same events
   from search results.
5. Change `as_of` only after the payload has actually been refreshed and
   verified. If collection is incomplete, retain the prior timestamp so the
   archiver publishes the new daily snapshot with `stale: true`.
6. Meeting probabilities must be in `[0, 1]` and total approximately `1` for
   each bank. Driver weights must be in `0.5` increments from `0` to `3`, with
   most values in the `1.0` to `2.0` range. Do not use `2.5+` without unusually
   strong evidence.
7. Do not alter page design, archived dates other than the requested date, or
   unrelated working-tree files. Commit and push only when the assignment
   explicitly includes publication, as the prompt below does.

## Copy-Paste LLM Assignment

Use this prompt with a model that has web access and repository tools:

```text
Work as the daily data operator for the two public macro pages in this
repository. Do not redesign the pages.

Before changing anything, read:
- readme/AGENTS.md
- readme/macro-data-operations.md
- docs/PUBLIC_PAGES_BACKEND_SPEC.md
- docs/BACKEND_API_SPEC.md
- docs/BACKEND_DATA_SPEC.md
- the current docs/data/fed-boc-dashboard.json

Target Toronto snapshot date: YYYY-MM-DD.

Tasks:
1. Run the documented econ/fetch_calendar.py command for the target date and
   then econ/render_calendar.py. Confirm the event count matches events.length,
   timestamps are valid UTC ISO 8601 values, history is chronological, and the
   JSON contains no NaN or Infinity.
2. Research current Fed and Bank of Canada meeting dates, policy pricing,
   macro drivers, market validation prices/returns, and upcoming relevant
   releases using authoritative live sources. Update only
   docs/data/fed-boc-dashboard.json. Include source URLs, preserve Actual vs
   Forecast vs Previous, and do not fabricate unavailable data.
3. Apply the weight, probability, timezone, and freshness rules in
   docs/BACKEND_DATA_SPEC.md. Prefer the freshly fetched economic-calendar
   archive for the watcher calendar. Update as_of only when the payload has
   been genuinely refreshed and verified.
4. Run econ/archive_fed_boc.py --date YYYY-MM-DD and the two focused tests in
   readme/macro-data-operations.md.
5. Inspect the diff. Do not modify unrelated existing changes, old archive
   dates, or frontend design.
6. This assignment includes publication: commit and push only the intended
   source snapshot files to thematic-market-watcher/dev. Run the documented
   sync_macro_pages.py command, review the website diff, then commit macro/
   only and push PodorCN.github.io/main.

Report the changed files, exact source URLs and observation times, validation
results, and any values that could not be independently verified. If a
required source is unavailable, preserve the previous confirmed data and
report the snapshot as stale rather than guessing.
```

Replace `YYYY-MM-DD` before assigning the task. The LLM should return its
sources and unresolved gaps in addition to modifying the files; a successful
script exit alone does not prove the researched values are correct.

# Thematic Market Watcher — Project Guide

This is the project-level guide and PM document for any coding agent/CLI
(Claude Code, Codex, Cursor, aider, opencode, ...) and any engineer
working in this repo. `CLAUDE.md` (in this same `readme/` folder) points
here — do not fork its content into it.

Note: because these docs live under `readme/` rather than the repo root,
tools that auto-load a root-level `AGENTS.md`/`CLAUDE.md` by convention
won't find them automatically. Point such a tool at `readme/AGENTS.md`
explicitly if it doesn't pick this up on its own.

## 1. What this is

A daily pipeline: download market data for a configurable list of
ETFs/indexes -> compute daily returns / covariance analytics -> collect
and judge news headlines -> LLM analysis -> render a static HTML report.
Runs once a day via GitHub Actions; each run's output is archived by date
and the latest report is published to GitHub Pages via `docs/`.

The tracked universe and its theme are configuration, not code:
`config/tickers.json` (broad-market macro universe today; add/remove
symbols freely, and the theme name/description feeds every prompt).

## 2. Hard constraints

1. **Stages talk only through files.** Each stage is an independently
   runnable script living in its own top-level package (`returns/`,
   `news/`, `theme-engine/`, `render/`). It reads its input file(s) from
   `archive/<date>/`, writes its output file(s) there, and never imports
   another stage's code. Any stage can be rerun, tested, or replaced in
   isolation.
2. **Date-partitioned archive.** Every day's artifacts live under
   `archive/<YYYY-MM-DD>/`. That directory is the full history. (Not
   called `data/` — that folder was renamed to `returns/`; see §3.)
3. **Deterministic code and LLM reasoning are separated**, with one
   deliberate, narrow exception (4a below):
   - Stage 1 (`returns/fetch_data.py`): pure code, no LLM.
   - Stage 1b (`returns/compute_covariance.py`): pure code, no LLM.
   - Stage 2a (`news/fetch_candidates.py`): LLM call, **with a hosted
     web-search tool** — see 4a.
   - Stage 2b (`news/judge.py`): LLM call, pure prompt+schema, no tools.
   - Stage 3 (`theme-engine/analyze.py`): LLM call, pure prompt+schema,
     no tools.
   - Stage 4 (`render/render.py`): pure code, no LLM.
4. **LLM-provider-independence is a hard requirement:**
   - Pipeline scripts never import a vendor SDK. They only call
     `utils/llm_client.call_llm(...)` or
     `utils/llm_client.call_llm_with_web_search(...)`.
   - Provider/model per stage lives in `config/llm.yaml`. Changing vendor
     or model is a config edit, not a code change.
   - Each provider gets its own small adapter function inside
     `utils/llm_client.py` (`_call_anthropic`, `_call_openai`, ...) because
     structured-output enforcement differs per vendor. Do not assume an
     "OpenAI-compatible" endpoint is a universal shortcut across vendors.

   **4a. The one documented exception:** the original design for stage 2
   split it into "pure-code candidate retrieval" + "LLM judgment", with
   retrieval hitting a specific news/search API directly. The project
   owner explicitly overrode that for `news/fetch_candidates.py`: the LLM
   itself holds a web-search tool and searches freely, rather than us
   picking one news API vendor and writing a scraper against it. This is
   implemented via each provider's own **hosted/server-side** search tool
   (e.g. Anthropic's `web_search_20250305`), exposed through
   `call_llm_with_web_search()` — still a single call into the
   provider-abstracted adapter layer, not a dependency on a coding
   agent's own tool ecosystem (no Claude Code `WebSearch`/`Bash`, no
   general agent loop we hand-roll). `news/judge.py` immediately
   downstream of it is a plain, tool-free `call_llm()` call, same as
   `theme-engine/analyze.py` — so the "LLM only reasons over prepared
   data" property still holds everywhere except this one retrieval step.
   Only the Anthropic backend implements `call_llm_with_web_search`
   today; the OpenAI backend stub raises `NotImplementedError` with a
   pointer to where to wire up its Responses API hosted search tool.

## 3. Repo layout

Each top-level folder is a self-contained package for exactly one
concern/process — scripts within a folder may import each other, but no
folder imports another pipeline-stage folder's code.

```
readme/                  # docs package
  README.md               # human quickstart
  AGENTS.md                # this file, source of truth
  CLAUDE.md                # pointer to AGENTS.md
  data-fetcher.md           # how to run the ETF fetcher & covariance tool
  configuring-tickers.md    # how to control which tickers are tracked
config/
  llm.yaml                 # per-stage LLM provider/model
  tickers.json              # tracked ticker universe (edit freely)
utils/                    # SHARED cross-cutting helpers ONLY
  llm_client.py             # the only place vendor SDKs are imported
returns/                  # stage 1: market data + return analytics (pure code)
  fetch_data.py             # downloads daily prices -> archive/<date>/*.json
  market_data_provider.py    # pluggable structured-data source (yfinance today)
  daily_returns.py           # shared primitives: load_closes(), daily_returns()
  compute_covariance.py       # EWMA covariance/correlation matrix
news/                     # stage 2: headline collection + judging
  fetch_candidates.py       # LLM + hosted web-search tool (see 4a)
  prompt_candidates.md
  schema_candidates.json
  judge.py                  # pure LLM, no tools
  prompt_judge.md
  schema_judge.json
theme-engine/             # stage 3: LLM synthesis (pure prompt+schema)
  analyze.py
  prompt.md
  schema.json
render/                   # stage 4: pure-code HTML rendering
  render.py
  template.html.j2
archive/<YYYY-MM-DD>/     # daily output archive (the pipeline's shared "database")
  raw_data.json
  candidates.json
  headlines.json
  analysis.json
  report.html
docs/index.html           # copy of the latest report.html, for GitHub Pages
tests/
run_all.sh                 # runs all stages for one date, locally
.github/workflows/daily-pipeline.yml
```

### Where new code goes

| Kind of code | Home |
|---|---|
| Generic helper usable by ≥2 packages (parsing, dates, IO wrappers) | `utils/` |
| Vendor SDK calls (LLM, future market-data vendors behind providers) | adapter inside the relevant package's provider module (`utils/llm_client.py`, `returns/market_data_provider.py`) |
| Return-series math (returns, volatility, beta, ...) | `returns/daily_returns.py` + thin scripts beside it |
| One pipeline stage | its own top-level package |

## 4. Running locally

```
cp .env.example .env   # fill in ANTHROPIC_API_KEY at minimum
pip install -r requirements.txt
./run_all.sh                # today
./run_all.sh 2026-08-21     # a specific date
```

On Windows there is no system Python; use the repo venv:
`.\.venv\Scripts\python.exe`.

Each stage also runs standalone with `--date YYYY-MM-DD`, reading/writing
only `archive/<date>/`, e.g.:

```
python theme-engine/analyze.py --date 2026-08-21
python returns/fetch_data.py --tickers ZSP.TO,ZXLK.TO --history-days 365
python returns/compute_covariance.py --input archive/<date>/raw_data.json
```

Run tests (no API key needed — SDKs are mocked):

```
pytest
```

## 5. Open TODOs (project owner has not finalized these yet)

- **Schedule/timezone**: `.github/workflows/daily-pipeline.yml` has
  `schedule:` commented out pending a decision on run time/timezone.
  `workflow_dispatch` works today for manual/testing runs.
- **Repo visibility**: not yet decided public vs. private. If it stays
  public and unattended, remember GitHub disables a scheduled workflow
  after 60 days with no repo activity — needs either periodic activity or
  a private repo (which has no such limit).
- **LLM provider**: currently defaults to Anthropic everywhere
  (`config/llm.yaml`). The project owner mentioned a separate "opencode"
  API they may want to route through instead — the adapter layer has an
  `openai`-compatible backend stubbed (reads `OPENAI_BASE_URL` so it can
  point at any OpenAI-compatible gateway) ready to receive those details
  and become the new default once specified.
- **Legacy ad-hoc artifacts**: `archive/custom_tickers*.json`,
  `archive/zsp_bmo_sectors_1y.json` etc. predate the `--output` flag;
  they are historical scratch data and safe to delete.

## 6. Conventions for future changes

**Feedback loop (mandatory).** The analysis stage writes its input-quality
complaints to [`analysis-feedback.md`](./analysis-feedback.md). Any
sub-agent or engineer touching `returns/` (data pulling) or `news/`
(headline pulling / judging) MUST read that file before making changes
and fix or explicitly acknowledge each item. When you change anything
upstream — universe, sources, recency windows, tagging — leave a one-line
note so the analyzer knows the input regime changed.

**Reuse first.** Before writing anything new:

1. Search for an existing function that does the job (start in
   `returns/daily_returns.py` and `utils/`) and call it.
2. If an existing function almost fits, extend its signature — do not
   fork a near-copy next to it.
3. If an existing function has grown too complex to use safely
   (many responsibilities, tangled flags, hard-to-test), **rewrite it
   clean** and migrate callers; do not pile another wrapper on top.
4. Never write a one-off inline script for something the pipeline tools
   already do — extend the tool's CLI instead (see how `fetch_data.py`
   grew `--tickers/--history-days/--output`).

Other standing conventions:

- Add a new market-data source by adding a `MarketDataProvider` subclass
  in `returns/market_data_provider.py` and registering it in `_PROVIDERS` —
  don't touch `fetch_data.py`.
- Add a new LLM provider by adding `_call_<provider>` (and optionally
  `_call_<provider>_with_web_search`) in `utils/llm_client.py` and
  registering it in the two dispatch dicts at the bottom of that file.
- Downstream analytics must consume closes via
  `returns.daily_returns.load_closes()` / `daily_returns()` — never
  re-parse raw-data JSONs ad hoc.
- Prompts are plain markdown files living next to the script that uses
  them (`news/`, `theme-engine/`), not embedded in any SKILL.md or
  agent-specific wrapper. If this pipeline is ever wrapped as a Claude
  Code skill, the SKILL.md must reference these files rather than
  duplicating prompt text.
- The tracked sector is pure config (`config/tickers.json` → `theme`
  object) injected into prompts as `{{theme}}` / `{{theme_description}}`
  via `utils/theme.py`. Never hardcode a sector name in prompts or
  templates -- re-pointing the pipeline at a new theme must be a config
  edit only.

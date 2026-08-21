# Thematic Market Water — Daily Digest Pipeline

This is the project-level guide for any coding agent/CLI (Claude Code,
Codex, Cursor, aider, ...) working in this repo. `CLAUDE.md` (in this same
`readme/` folder) is a symlink to this file — do not fork content into it.

Note: because these docs live under `readme/` rather than the repo root,
tools that auto-load a root-level `AGENTS.md`/`CLAUDE.md` by convention
won't find them automatically. Point such a tool at `readme/AGENTS.md`
explicitly if it doesn't pick this up on its own.

## 1. What this is

A daily pipeline: download water-sector market data -> collect and judge
water-sector news headlines -> LLM analysis -> render a static HTML
report. Runs once a day via GitHub Actions; each run's output is archived
by date and the latest report is published to GitHub Pages via `docs/`.

## 2. Hard constraints

1. **Stages talk only through files.** Each stage is an independently
   runnable script living in its own top-level package (`data/`, `news/`,
   `theme-engine/`, `render/`). It reads its input file(s) from
   `archive/<date>/`, writes its output file(s) there, and never imports
   another stage's code. Any stage can be rerun, tested, or replaced in
   isolation.
2. **Date-partitioned archive.** Every day's artifacts live under
   `archive/<YYYY-MM-DD>/`. That directory is the full history. (Not
   called `data/` — that name is the stage-1 market-data *code* package;
   see §3.)
3. **Deterministic code and LLM reasoning are separated**, with one
   deliberate, narrow exception (4a below):
   - Stage 1 (`data/fetch_data.py`): pure code, no LLM.
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

Each top-level folder is a self-contained package for one concern —
scripts within a folder may import each other, but no folder imports
another pipeline-stage folder's code. `utils/` is the one shared
cross-cutting package everything else is allowed to import.

```
readme/                  # docs package
  README.md               # human quickstart
  AGENTS.md                # this file, source of truth
  CLAUDE.md -> AGENTS.md   # symlink
config/
  llm.yaml                 # per-stage provider/model
utils/
  llm_client.py             # the only place vendor SDKs are imported
data/                     # stage 1: market data (pure code, no LLM)
  fetch_data.py
  market_data_provider.py   # pluggable structured-data source (yfinance today)
  tickers.json               # water-theme tickers tracked (edit freely)
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
  test_llm_client.py
run_all.sh                 # runs all stages for one date, locally
.github/workflows/daily-pipeline.yml
```

## 4. Running locally

```
cp .env.example .env   # fill in ANTHROPIC_API_KEY at minimum
pip install -r requirements.txt
./run_all.sh                # today
./run_all.sh 2026-08-21     # a specific date
```

Each stage also runs standalone with `--date YYYY-MM-DD`, reading/writing
only `archive/<date>/`, e.g.:

```
python theme-engine/analyze.py --date 2026-08-21
```

Run tests (no API key needed — the Anthropic SDK is mocked):

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

## 6. Conventions for future changes

- Add a new market-data source by adding a `MarketDataProvider` subclass
  in `data/market_data_provider.py` and registering it in `_PROVIDERS` —
  don't touch `fetch_data.py`.
- Add a new LLM provider by adding `_call_<provider>` (and optionally
  `_call_<provider>_with_web_search`) in `utils/llm_client.py` and
  registering it in the two dispatch dicts at the bottom of that file.
- Prompts are plain markdown files living next to the script that uses
  them (`news/`, `theme-engine/`), not embedded in any SKILL.md or
  agent-specific wrapper. If this pipeline is ever wrapped as a Claude
  Code skill, the SKILL.md must reference these files rather than
  duplicating prompt text.

# Thematic Market Water — Daily Digest

A daily pipeline that turns water-sector market data + news into a static
HTML report: fetch market data → collect & judge news headlines → LLM
analysis → render HTML. Runs on a schedule via GitHub Actions; the latest
report is published via GitHub Pages from `docs/`.

See [`AGENTS.md`](./AGENTS.md) (in this same `readme/` folder) for the
full design, hard constraints, and open TODOs (`CLAUDE.md` is a symlink
to it).

## Quickstart

Run these from the repo root (not from inside `readme/`):

```bash
cp .env.example .env    # set ANTHROPIC_API_KEY at minimum
pip install -r requirements.txt
./run_all.sh             # runs the full pipeline for today (UTC)
open archive/$(date -u +%F)/report.html
```

Run a specific date, or rerun a single stage:

```bash
./run_all.sh 2026-08-21
python theme-engine/analyze.py --date 2026-08-21
```

Run the test suite (mocked LLM calls, no API key or network needed):

```bash
pytest
```

## Repo layout

Each top-level folder is a self-contained package for one concern:

| Folder | What it is |
|---|---|
| `utils/` | Provider-independent LLM adapter (`llm_client.py`) — the only place any vendor SDK is imported |
| `data/` | Stage 1: market data fetching (pure code, no LLM) |
| `news/` | Stage 2: headline collection (LLM + hosted web search) and judging (pure LLM) |
| `theme-engine/` | Stage 3: LLM synthesis of market data + headlines into structured analysis |
| `render/` | Stage 4: pure-code HTML rendering (Jinja2) |
| `config/` | Per-stage provider/model config (`llm.yaml`) |
| `tests/` | Unit tests (mocked SDK, no network) |
| `readme/` | This file, plus `AGENTS.md`/`CLAUDE.md` |
| `archive/<date>/` | The daily output archive — every stage's input/output JSON + the rendered report |

## Pipeline stages

| Stage | Script | LLM? | Reads | Writes |
|---|---|---|---|---|
| 1 | `data/fetch_data.py` | no | `data/tickers.json` | `archive/<date>/raw_data.json` |
| 2a | `news/fetch_candidates.py` | yes, with hosted web search | — | `archive/<date>/candidates.json` |
| 2b | `news/judge.py` | yes, no tools | `candidates.json` | `archive/<date>/headlines.json` |
| 3 | `theme-engine/analyze.py` | yes, no tools | `raw_data.json`, `headlines.json` | `archive/<date>/analysis.json` |
| 4 | `render/render.py` | no | `analysis.json`, `raw_data.json`, `headlines.json` | `archive/<date>/report.html`, `docs/index.html` |

All LLM calls go through `utils/llm_client.py`. Provider/model per stage
is set in `config/llm.yaml`.

## GitHub Actions

`.github/workflows/daily-pipeline.yml` runs all four stages and commits
`archive/` + `docs/` back to the repo. It currently only has
`workflow_dispatch` (manual trigger) enabled — the `schedule:` cron is
commented out pending a decision on run time/timezone (see AGENTS.md §5).

Required repo secrets: `ANTHROPIC_API_KEY` (and `OPENAI_API_KEY` if any
stage in `config/llm.yaml` is switched to an OpenAI-compatible provider).

To trigger a run manually: repo → Actions → "Daily Digest" → Run workflow.

## GitHub Pages

Enable Pages under Settings → Pages → Deploy from branch → `main` /
`/docs`. After the workflow runs once, the latest report is at the Pages
URL (`docs/index.html` is overwritten by every run).

## Open decisions

See AGENTS.md §5 — schedule/timezone, repo visibility (public repos
disable an idle scheduled workflow after 60 days), and whether to route
some stages through a different LLM provider are all still pending input
from the project owner.

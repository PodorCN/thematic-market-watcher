# Thematic Market Water — Daily Digest

A daily pipeline that turns water-sector market data + news into a static
HTML report: fetch market data → collect & judge news headlines → LLM
analysis → render HTML. Runs on a schedule via GitHub Actions; the latest
report is published via GitHub Pages from `docs/`.

See [`AGENTS.md`](./AGENTS.md) for the full design, hard constraints, and
open TODOs (`CLAUDE.md` is a symlink to it).

## Quickstart

```bash
cp .env.example .env    # set ANTHROPIC_API_KEY at minimum
pip install -r requirements.txt
./run_all.sh             # runs the full pipeline for today (UTC)
open data/$(date -u +%F)/report.html
```

Run a specific date, or rerun a single stage:

```bash
./run_all.sh 2026-08-21
python pipeline/03_analyze/analyze.py --date 2026-08-21
```

Run the test suite (mocked LLM calls, no API key or network needed):

```bash
pytest
```

## Pipeline stages

| Stage | Script | LLM? | Reads | Writes |
|---|---|---|---|---|
| 1 | `pipeline/01_fetch_data/fetch_data.py` | no | `pipeline/01_fetch_data/tickers.json` | `data/<date>/raw_data.json` |
| 2a | `pipeline/02_collect_headlines/fetch_candidates.py` | yes, with hosted web search | — | `data/<date>/candidates.json` |
| 2b | `pipeline/02_collect_headlines/judge.py` | yes, no tools | `candidates.json` | `data/<date>/headlines.json` |
| 3 | `pipeline/03_analyze/analyze.py` | yes, no tools | `raw_data.json`, `headlines.json` | `data/<date>/analysis.json` |
| 4 | `pipeline/04_render_html/render.py` | no | `analysis.json`, `raw_data.json`, `headlines.json` | `data/<date>/report.html`, `docs/index.html` |

All LLM calls go through `lib/llm_client.py`, which is the only place any
vendor SDK is imported. Provider/model per stage is set in
`config/llm.yaml`.

## GitHub Actions

`.github/workflows/daily-pipeline.yml` runs all four stages and commits
`data/` + `docs/` back to the repo. It currently only has
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

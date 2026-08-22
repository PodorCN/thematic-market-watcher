# Theme-Engine Implementation Walkthrough — 2026-08-22

Goal: implement/execute the theme-engine stage end-to-end for 2026-08-22 —
turn recent market data (`returns`) + curated news (`news`) into a structured
market-theme analysis, then verify it renders downstream. Every step is logged
here so it's easy to review and re-run.

**Scope note:** the project was clarified mid-task to be a *generic* thematic
market watcher; "water" naming in prompts/templates is legacy from the current
ticker config. The analysis below treats the basket as one theme (water
infrastructure/utilities/tech) but the method is theme-agnostic.

---

## Step 0 — Recon: what existed vs. what was missing

Read first: `theme-engine/analyze.py`, `theme-engine/prompt.md`,
`theme-engine/schema.json`, `utils/llm_client.py`, `render/render.py`,
`render/template.html.j2`, all files under `readme/`.

State of `archive/2026-08-22/` at start:

| File | Status |
|---|---|
| `raw_data.json` | present (8 tickers, yfinance, as_of 18:27 UTC) |
| `headlines_raw.json` | present (64 raw headlines via `fetch_headlines.py`) |
| `candidates.json` | **missing** (stage-2a output; judge reads this) |
| `headlines.json` | **missing** (stage-2b output; theme-engine + render read this) |
| `analysis.json` | **missing** (this task's deliverable) |

Also: no `.env` in the repo → the real Anthropic API path can't run locally.
Since I *am* an LLM, I executed stages 2b and 3 myself, following each stage's
prompt + schema exactly. No code changes were needed anywhere.

## Step 1 — Built `candidates.json` from `headlines_raw.json`

Stage 2b (`news/judge.py`) consumes `candidates.json`
(`schema_candidates.json`: exactly `headline/source/url/published_at`),
while `fetch_headlines.py` emits richer records (adds `ticker`, `summary`).
Converted with a small inline script:

```python
cands = [{'headline': h['headline'], 'source': h['source'],
          'url': h['url'], 'published_at': h.get('published_at')}
         for h in raw['headlines']]
json.dump({'date': d, 'candidates': cands}, ...)
```

Result: `archive/2026-08-22/candidates.json`, 64 items.

*Observation:* `fetch_headlines.py`'s docstring still says data lives in
`data/tickers.json` — stale path, actual file is `config/tickers.json`.
Noted for cleanup later.

## Step 2 — Played stage 2b (`judge`): curated 64 → 14 headlines

Followed `news/prompt_judge.md` rules (drop off-topic/clickbait/listicles;
dedupe same-story coverage; assign category + importance 1–5). Wrote
`archive/2026-08-22/headlines.json` per `schema_judge.json`.

Kept (14): XYL new CFO/board pick; XYL "23% below fair value"; XYL analyst
ratings overview; AWK bullish/bearish survey; AWK wastewater-discharge risk
narrative; WTRG Q2 results; AWR Q2 results; CWCO Q2 results; Veolia fresh
attention; Badger Meter AMI/BlueEdge growth story; El Nino climate piece;
US services PMI acceleration; US manufacturing PMI miss; Canada matching US
tariffs.

Dropped (~50), by rule:
- ~30 ETF listicles / "Should you invest in X?" promo pieces (clickbait rule)
- 6 duplicate Q2-earnings retellings across wires (dedupe rule)
- 8 items older than ~3 weeks (e.g. May/June Veolia-vs-WM comparisons)
- Off-theme macro noise: Iran sanctions, Ukraine strikes, Apple CFO chatter,
  CTA positioning, metals breakout, etc.
- GE HealthCare CFO change — non-water company despite appearing under the
  XYL tag

## Step 3 — Played stage 3 (`theme-engine`): wrote `analysis.json`

Inputs actually used (no invented numbers):

- Computed per-ticker stats from `raw_data.json` history: last close,
  daily %chg, 1-week %chg, 30-day high/low, plus day-by-day moves for XYL
  and AWK (the two outliers).
- Cross-referenced those dates against kept headlines (XYL selloff window
  Aug 17–20 overlaps the CFO/board story Aug 19 and ratings piece Aug 18).

Key numbers driving the narrative:
- **XYL −5.2% on the week**, closed 113.42 = 30-day low (−3.0% Aug 18,
  −2.4% Aug 20); worst week of the month.
- **AWK** faded late week (−1.1% Thu, −1.3% Fri) from a period high 138.71
  (Aug 19), close 135.39.
- ETF sleeve flat-to-up: PHO +0.75%, FIW +0.63%, TBLU +0.46%, CGW +0.37%;
  VIE.PA +0.62%; WTRG −0.57%.

Output follows `schema.json` strictly:
`market_summary` (data-driven tape read) / `top_story` (XYL momentum-vs-value
tension) / 4 `themes` (equipment derating · steady utility Q2s · El Nino
climate re-pricing · macro crosscurrents incl. tariffs) / `outlook`.
Plain text only (no markdown) so the fixed template renders predictably.

First write attempt failed lint (trailing comma, stray extra field violating
`additionalProperties:false`, a space inside one URL) — caught by the editor's
JSON check, fixed, rewrote clean.

## Step 4 — Verification

1. Schema field check on both outputs: PASS (manual required-field check;
   `jsonschema` not installed in repo venv).
2. `python render/render.py --date 2026-08-22` → wrote
   `archive/2026-08-22/report.html` and copied to `docs/index.html`
   (21,738 bytes each). Spot-checked rendered HTML contains the four themes
   and top story.
3. `pytest -q` → **13 passed** (mocked LLM suite untouched).

Full pipeline state now: every stage-2/3/4 artifact for 2026-08-22 exists and
is mutually consistent. Stage 2a proper (LLM web-search candidates) remains
unexercised locally — my `candidates.json` came from `fetch_headlines.py`
output instead, which judge consumed interchangeably by design.

## Step 5 (addendum) — Data refresh & ZEB.TO discovery

Re-ran stage 1 after the initial write-up (`returns/fetch_data.py` +
`compute_covariance.py`, as_of 20:37 UTC):

- US names unchanged (Friday close; Saturday run) — all prior claims held.
- New: `config/tickers.json` had gained **ZEB.TO** (Canadian banks ETF)
  after the first 18:27 fetch, now picked up: Fri +0.45% but **-6.1% on
  the week** — the basket's worst weekly move, deeper than XYL.
- This invalidated the earlier "no macro shock in the tape" read:
  ZEB.TO is the price confirmation of the Canada-US tariff-escalation
  headline. Updated `market_summary` + macro theme synthesis in
  `analysis.json`, re-rendered report/docs, pytest still 13 passed,
  ad-hoc claim-vs-data verification re-run: ALL CHECKS PASSED
  (17 assertions incl. ZEB.TO week/bounce/worst-in-basket).
- EWMA correlation notes from the refreshed covariance matrix:
  PHO/FIW ~0.96, AWK/WTRG ~0.97 (utility bloc moves together);
  XYL correlates more with the industrial ETF sleeve (~0.88/0.90) than
  with utilities (~0.48); ZEB.TO near-zero/negative vs everything —
  its drawdown was idiosyncratic macro exposure, not sector beta.

## Deliverables

- `archive/2026-08-22/candidates.json` (64 items, stage-2a shape)
- `archive/2026-08-22/headlines.json` (14 curated, stage-2b shape)
- `archive/2026-08-22/analysis.json` (**the theme analysis**)
- `archive/2026-08-22/report.html` + `docs/index.html` (downstream proof)

## Known gaps / suggestions for next iteration

- The real stage-2a (`call_llm_with_web_search`) hasn't been wired to a key
  locally; when `.env` exists, rerun `run_all.sh` to compare machine output
  against this hand-run baseline.
- `fetch_headlines.py` docstring references stale `data/tickers.json` path.
- Judge prompt has no recency rule — several >3-week-old items were dropped
  by judgment; consider making a max-age explicit in `prompt_judge.md`.
- `config/tickers.json` currently mixes one theme; when adding more themes,
  the AGENTS.md suggestion of named sections + `load_tickers()` merge becomes
  relevant, and `prompt.md` should stop hardcoding "water sector".

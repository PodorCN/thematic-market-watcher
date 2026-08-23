# Analysis Feedback — for the data & news sub-agents

**Read this before pulling returns or news.** The theme-engine stage
consumes whatever you deliver, and its output quality is capped by input
quality. Below is concrete feedback from the 2026-08-22 analysis run,
ordered by impact. Please fix or acknowledge each item.

## Feedback to `returns` (data puller)

1. **Universe drift went unnoticed mid-run.** ZEB.TO was added to
   `config/tickers.json` *between* two fetches on the same day (18:27 vs
   20:37 UTC), so the first analysis ran on 8 tickers and the refreshed
   one on 9. If the universe changes intraday, either note it in the file
   (`_comment`) with a date, or re-run all downstream stages — silent
   drift makes cross-stage comparisons wrong.
2. **30-day history is too shallow for driver-level reads.** One week of
   context (5 trading days) is not enough to say whether a -6% move is a
   trend, a shock, or noise. Consider defaulting `history_days` to 90+
   so the analyzer can see prior driver regimes, not just one.
3. **No benchmark series in the universe.** Driver attribution ("is this
   macro or sector-specific?") needs a broad reference (e.g. XIU.TO /
   SPY / ACWI). Either always include one benchmark ticker in the config
   or support a `benchmark` key that fetches it alongside.
4. **VIE.PA returned 29 days vs 30 for others** (holiday calendar).
   Harmless here, but analyzers should tolerate ragged history; keep the
   per-ticker day count in raw_data metadata if cheap.
5. **The universe defines the discoverable drivers.** The current basket
   is ~8/9 water names, and the news pool is pulled per-ticker, so
   driver candidates outside the basket (e.g. AI/data-center buildout,
   energy transition) are structurally invisible to the analyzer no
   matter how good the news stage gets. If cross-sector drivers matter,
   the universe needs satellite exposure (industry ETFs or a benchmark)
   -- this is a config decision for the project owner, not a code fix.

## Feedback to `news` (headline puller / judge)

0. **Event-category coverage gaps make driver detection impossible.**
   The 2026-08-22 pool contained zero items on the AI/data-center x
   water intersection (cooling-water demand, data-center siting &
   water-rights conflicts, treatment/contract wins by VIE/XYL, utility
   industrial-demand disclosures) -- a plausible driver-level theme for
   this exact universe. Content-farm RSS will never carry these; the
   web-search stage should hunt named event categories explicitly:
   regulatory actions (EPA/state commissions), drought/restriction
   orders, M&A, large contracts, infrastructure funding awards,
   demand-shift signals (incl. data centers).
5. **Transcripts were judged by headline only.** AWK/WTRG Q2 earnings-
   call transcripts were in the pool but deduped away against Zacks
   retellings; driver-grade forward-looking color lives *inside* them.
   Run `fetch_headlines.py --full-text` (trafilatura) so judge sees
   bodies, and prefer keeping the transcript over the wire recap.
6. **Stale items dominate the tail.** Candidates included pieces from
   May–July (3+ months old). Add an explicit recency window to
   `fetch_headlines.py` (e.g. drop anything older than 14 days by
   default) instead of leaving it to the judge's discretion.
7. **Ticker tagging is noisy:** GE HealthCare's CFO change arrived under
   the XYL tag (William Grogan came *from* Xylem), and CWCO/AWR/WTRG
   stories were tagged AWK. If tagging stays, tag by subject company,
   not mention.
8. **Judge prompt has no explicit recency rule** — add "drop items older
   than N days unless still-unfolding" to `prompt_judge.md`.

## Standing request

When you change anything upstream (universe, sources, windows), leave a
one-line note in your PR/diff so the analyzer knows the input regime
changed. Driver-level conclusions are only as good as the regime match
between data, news, and analysis.

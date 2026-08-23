# Demo: driver-level analysis on a macro universe (NOT the water config)

**What this is:** a demonstration that the same theme-engine method
produces genuinely different, driver-level output when given a broad
universe. Uses `fetch_data.py --tickers ... --output demo_macro_drivers.json`
-- the repo config (`config/tickers.json`, currently theme=water) was NOT
touched. Data as of 2026-08-22 close, 90d history.

Universe: SPY QQQ (equity beta) / XLF XLE XLU XLI (sector drivers) /
TLT (rates) / GLD (real assets & fear).

## What the tape says (driver-level)

1. **Rates & duration stress is THE cross-asset driver.**
   XLU -7.6% over a month (-3.5% week, -2.3% Friday alone) while TLT is
   flat-ish (-1.0% month). Utilities are being hit as a *rates* story,
   not a bond-market rout -- long-duration equities de-rating on
   higher-for-longer while bonds hold. This single spread (XLU vs TLT)
   is the cleanest signal in the whole table.
2. **Energy + gold = real-asset bid, i.e. inflation/hedge demand.**
   XLE +6.7% m and GLD +13.8% m (+5.5% w, +1.95% Friday) with SPY only
   +3.6% m. Money is paying up for inflation/geo hedges; gold's weekly
   acceleration alongside oil strength points at risk-premium building,
   consistent with the tariff/geopolitics headlines in this week's pool.
3. **Equity beta soft but not broken.**
   SPY -1.4% w, QQQ -2.4% w after a strong month; XLI -3.4% w shows the
   industrials/cyclicals leg carrying the tariff exposure. Rotation out
   of cyclicals into hedges, not liquidation.
4. **Financials are the outlier: XLF +11.5% 3m, +2.1% m.**
   Banks keep making new ground even as rate-sensitives sell off --
   either steepening-curve optimism or pre-tariff domestic positioning;
   worth watching whether it survives an escalation headline.

## Contrast with the water-config run

Same day, same method, different universe -> different drivers:
the water run surfaced tariffs-via-ZEB.TO, PMI split, El Nino,
utility pass-through; the macro run surfaces rates-vs-real-assets
rotation, cyclical de-risking, and financials' divergence. The universe
is the lens; there is no universe-independent "market theme".

## If you want this to be the real config

Say the word and I'll set `config/tickers.json` accordingly (theme
name/description + tickers incl. one benchmark), then re-run the full
pipeline for the next session. Suggested starter set:
SPY QQQ XLF XLE XLU XLI TLT GLD (+ XIU.TO if Canadian exposure matters).

*Demo artifacts:* `archive/2026-08-22/demo_macro_drivers.json` (delete
freely; not referenced by any pipeline stage).

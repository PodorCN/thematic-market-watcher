#!/usr/bin/env bash
# Run the full pipeline for one date, end to end, locally.
#
# Usage:
#   ./run_all.sh                # today (UTC)
#   ./run_all.sh 2026-08-21     # a specific date (also lets you re-run
#                                 a single past day's data)
#
# Each stage is just a normal python invocation -- run any one of them
# individually (with the same --date) to rerun/debug just that stage.

set -euo pipefail
cd "$(dirname "$0")"

if [ -f .env ]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

DATE="${1:-$(date -u +%F)}"
THEME="${2:-all}"
THEMES=("canadian_banks" "us_smallcap" "us_rates" "tariff_war")

run_theme() {
  local theme="$1"
  echo "===== Theme: $theme — $DATE ====="
  echo "-- 1. fetch_data ($theme)"
  python data/fetch_data.py --date "$DATE" --theme "$theme"

  echo "-- 2a. fetch_candidates ($theme)"
  python news/fetch_candidates.py --date "$DATE" --theme "$theme"

  echo "-- 2b. judge ($theme)"
  python news/judge.py --date "$DATE" --theme "$theme"

  echo "-- 3. analyze ($theme)"
  python theme-engine/analyze.py --date "$DATE" --theme "$theme"

  echo "-- 4. render ($theme)"
  python render/render.py --date "$DATE" --theme "$theme"

  echo "== done: archive/$theme/$DATE/report.html =="
}

if [ "$THEME" = "all" ]; then
  echo "== Daily Digest pipeline for $DATE — all themes =="
  for t in "${THEMES[@]}"; do
    run_theme "$t"
  done
  echo "== all themes done =="
else
  echo "== Daily Digest pipeline for $DATE — theme: $THEME =="
  run_theme "$THEME"
fi

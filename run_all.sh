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
echo "== Daily Digest pipeline for $DATE =="

echo "-- 1. fetch_data"
python data/fetch_data.py --date "$DATE"

echo "-- 2a. fetch_candidates"
python news/fetch_candidates.py --date "$DATE"

echo "-- 2b. judge"
python news/judge.py --date "$DATE"

echo "-- 3. analyze"
python theme-engine/analyze.py --date "$DATE"

echo "-- 4. render"
python render/render.py --date "$DATE"

echo "== done: archive/$DATE/report.html =="

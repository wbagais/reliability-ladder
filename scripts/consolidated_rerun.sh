#!/bin/bash
# THE CONSOLIDATED RE-RUN — plan item 0b, 2026-09-03.
#
# One base run per draw per corpus produces every descriptive dev-side number
# in the article; the arms replay on the SAME cache so their model calls are
# hits and only the arm's own calls are paid. Three cold draws each.
#
#   scripts/consolidated_rerun.sh <corpus> <draw>     corpus: cadec | finer
#
# A DRAW is a run against a COLD cache: LADDER_LLM_CACHE names a directory
# that must not exist yet, and run.py stamps it into <run>.aggregates.json so
# the run file says which cache the draw used. The arms run second on that
# cache, so their p95 latencies include cache hits and are NOT comparable with
# the base's — they are not compared.
#
# DEV SPLIT ONLY. The held-out split was spent once (Phase F, 2026-08-26) and
# is never re-run; this script refuses any other split by construction.
set -euo pipefail
corpus="${1:?corpus: cadec | finer}"
d="${2:?draw index: 0 | 1 | 2}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
PY="${LADDER_PYTHON:-/Users/wejdanbagais/Documents/repo/reliability-ladder/.venv/bin/python}"
case "$corpus" in
  cadec) base=manifest.json;       arms="judgemenu judgeshuffle lexarm";
         man_for() { case "$1" in judgemenu) echo manifest.judgemenu.json;; judgeshuffle) echo manifest.judgeshuffle.json;; lexarm) echo manifest.lexarm.json;; esac; } ;;
  finer) base=manifest.finer.json; arms="judgemenu judgeshuffle";
         man_for() { case "$1" in judgemenu) echo manifest.finer.judgemenu.json;; judgeshuffle) echo manifest.finer.judgeshuffle.json;; esac; } ;;
  *) echo "unknown corpus $corpus" >&2; exit 2 ;;
esac
export LADDER_LLM_CACHE="$ROOT/.llm_cache.rerun-$corpus-d$d"
if [ -e "$LADDER_LLM_CACHE" ]; then
  echo "REFUSING: $LADDER_LLM_CACHE exists — a draw is a run against a COLD cache" >&2
  exit 3
fi
run() {  # run <manifest> <run-id>
  echo "=== $(date '+%F %T') $2 ($1) cache=$LADDER_LLM_CACHE ==="
  "$PY" -u -m ladder.run --manifest "$1" ladder --split dev --rungs 0-6 --plain --run-id "$2" 2>&1 | grep -v '^\s*$'
}
run "$base" "rerun-$corpus-d$d"
for arm in $arms; do
  run "$(man_for "$arm")" "rerun-$corpus-d$d-$arm"
done
echo "=== $(date '+%F %T') DRAW $d $corpus DONE ==="

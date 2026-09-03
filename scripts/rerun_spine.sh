#!/bin/bash
# The SPINE replay for a finished draw: rungs 5 and 6 alone over the rung 1
# snapshot — i.e. the ladder with self-correction, voting and the judge
# removed — on the SAME rung 0 output. Zero model calls, so it is exact, and
# it is what the article's "deleting the three paid layers changed N answers"
# claim must be re-derived from.
#
#   scripts/rerun_spine.sh <corpus> <draw>
set -euo pipefail
corpus="${1:?cadec | finer}"; d="${2:?draw}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$ROOT"
PY="${LADDER_PYTHON:-/Users/wejdanbagais/Documents/repo/reliability-ladder/.venv/bin/python}"
case "$corpus" in
  cadec) man=manifest.json; dir=out ;;
  finer) man=manifest.finer.json; dir=out/finer ;;
  *) echo "unknown corpus $corpus" >&2; exit 2 ;;
esac
base="$dir/rerun-$corpus-d$d"
[ -f "$base.r1.records.jsonl" ] || { echo "no rung 1 snapshot at $base" >&2; exit 3; }
export LADDER_LLM_CACHE="$ROOT/.llm_cache.rerun-$corpus-d$d"
"$PY" -u -m ladder.run --manifest "$man" ladder --split dev --rungs 5,6 \
  --predictions "$base.r1.records.jsonl" --plain --run-id "rerun-$corpus-d$d-spine" 2>&1 | grep -v '^\s*$'

#!/bin/bash
# S0 and S1 on CADEC dev, rung 0 only, three cold draws each, current frozen config with --rung0-step.
# Waits for the type-check replays to release the GPU.
cd "$(dirname "$0")/.."
PY=/Users/wejdanbagais/Documents/repo/reliability-ladder/.venv/bin/python
until grep -q "TYPECHECK DONE" out/rerun-typecheck.log; do sleep 30; done
for step in S0 S1; do for d in 0 1 2; do
  lc=$(echo "$step" | tr 'A-Z' 'a-z')
  export LADDER_LLM_CACHE="$PWD/.llm_cache.rerun-cadec-$lc-d$d"
  [ -e "$LADDER_LLM_CACHE" ] && { echo "REFUSING $LADDER_LLM_CACHE exists"; exit 3; }
  echo "=== $(date '+%F %T') rerun-cadec-$lc-d$d ==="
  $PY -u -m ladder.run ladder --split dev --rungs 0 --rung0-step $step --plain --run-id "rerun-cadec-$lc-d$d" 2>&1 | grep "rung 0 (\|wrote\|Error\|Traceback"
done; done
echo "=== $(date '+%F %T') STEPS DONE ==="

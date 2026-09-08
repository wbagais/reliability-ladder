#!/bin/bash
# The FiNER type-check arm (rung 7, then rung 2 on its rejections) replayed over each base draw's rung 1
# snapshot on the same cache. Waits for the S0/S1 draws to release the GPU.
cd "$(dirname "$0")/.."
PY=/Users/wejdanbagais/Documents/repo/reliability-ladder/.venv/bin/python
until grep -q "STEPS DONE" out/rerun-steps.log; do sleep 30; done
for d in 0 1 2; do
  export LADDER_LLM_CACHE="$PWD/.llm_cache.rerun-finer-d$d"
  echo "=== $(date '+%F %T') rerun-finer-d$d-typecheck ==="
  $PY -u -m ladder.run --manifest manifest.finer.typecheck.json ladder --split dev --rungs 7,2,3,4,5,6 \
     --predictions out/finer/rerun-finer-d$d.r1.records.jsonl --plain --run-id "rerun-finer-d$d-typecheck" 2>&1 | grep "rung [0-9] (\|wrote\|Error\|Traceback"
done
echo "=== $(date '+%F %T') TYPECHECK DONE ==="

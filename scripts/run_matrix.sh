#!/usr/bin/env bash
# run_matrix.sh — every model on every corpus, in one pass, resumably.
#
# WHAT IT DOES
#
# For each (corpus, model, draw) it derives a manifest from the corpus's own
# base by changing ONE key — model.extractor — runs the ladder, and writes to
# out/matrix/<corpus>-<model>-d<draw>. Nothing else varies. No rung is modified:
# a model sweep is manifest work, which is what manifest.model exists for.
#
# RESUMABLE, because it will be interrupted
#
# A cell whose output directory already holds a results.csv is skipped. That
# makes the script safe to re-run after a dropped SSH session, a full disk or a
# destroyed droplet — and it means the cost of stopping is one cell, not the
# whole matrix.
#
# RUNGS 0-1 BY DEFAULT, and this is the important flag
#
# Every question this matrix answers is about the free check: how much of the
# gold it reaches (occupancy) and how much of what it endorses is right
# (correctness). Rung 3 alone is roughly three quarters of the runtime and
# answers neither. Pass RUNGS=0-6 for the full ladder if a cell needs it.
#
# WHAT IS NOT UNIFORM, and must travel with any table built from this
#
# CADEC and PsyTAR retrieve DENSELY; the other four retrieve LEXICALLY, because
# no embedding index exists over a gazetteer, a taxonomy, a tag set or MeSH. On
# CADEC that substitution cost ~21 points of recall@20. The matrix is uniform in
# MODELS and not in RETRIEVAL.
#
#   ./scripts/run_matrix.sh                 # rungs 0-1, three draws
#   RUNGS=0-6 DRAWS=1 ./scripts/run_matrix.sh
#   CORPORA="psytar finer" ./scripts/run_matrix.sh
set -uo pipefail

RUNGS="${RUNGS:-0-1}"
DRAWS="${DRAWS:-3}"
SPLIT="${SPLIT:-dev}"
OUT="${OUT:-out/matrix}"

# corpus:manifest — CADEC is deliberately absent. Its runs live on the other
# owner's machine and a second set from different hardware could not be compared
# with them; floating-point differs between a CPU-split model and a GPU one, so
# two CADEC columns would be two experiments wearing one name.
ALL_CORPORA="finer:manifest.finer.json \
geo:manifest.geo.json \
psytar:manifest.psytar.json \
lgl:manifest.lgl.json \
trnews:manifest.trnews.json \
linnaeus:manifest.linnaeus.json \
bc5cdr:manifest.bc5cdr.json"

MODELS="${MODELS:-ollama/gpt-oss:20b ollama/llama3.1:8b ollama/mistral:7b-instruct ollama/ibm/granite4:micro-h ollama/qwen3:4b}"

mkdir -p "$OUT"
started=$(date +%s)
done_n=0; skip_n=0; fail_n=0

for pair in $ALL_CORPORA; do
  corpus="${pair%%:*}"; manifest="${pair##*:}"

  if [ -n "${CORPORA:-}" ]; then
    case " $CORPORA " in *" $corpus "*) ;; *) continue ;; esac
  fi
  if [ ! -f "$manifest" ]; then
    echo "  SKIP $corpus — $manifest not found (run prep_all_arms.py)"
    continue
  fi

  # THE GATE. One second per arm, checked once rather than once per cell.
  #
  # On 2026-09-06 twelve cells ran with another corpus's task description —
  # asking for adverse drug reactions in documents about places, species and
  # diseases — and every one produced a complete, well-formed results table.
  # At LGL's 45 seconds a document that was hours of card time spent on numbers
  # that had to be thrown away. crosscheck reads every declared fact back from
  # an independent source and would have caught it before the first document.
  #
  # A FAILING ARM IS SKIPPED, NOT FATAL: one broken manifest should not stop
  # five good ones, and the skip is recorded the same way a failed cell is.
  # SKIP_CROSSCHECK=1 for the case where you know a check fires and want the
  # run anyway — a model absent from this machine, say.
  if [ -z "${SKIP_CROSSCHECK:-}" ]; then
    if ! PYTHONPATH=. python3 scripts/crosscheck.py --quiet \
         --manifest "$manifest" >/tmp/xcheck.$$ 2>&1; then
      echo "  SKIP $corpus — crosscheck failed:"
      grep -E "FAIL|declared|found" /tmp/xcheck.$$ | head -6 | sed 's/^/    /'
      echo "$corpus: crosscheck" >> "$OUT/failures.txt"
      rm -f /tmp/xcheck.$$
      fail_n=$((fail_n+1))
      continue
    fi
    rm -f /tmp/xcheck.$$
  fi

  for model in $MODELS; do
    short=$(echo "$model" | sed 's|.*/||; s|:|_|g')
    for d in $(seq 0 $((DRAWS-1))); do
      cell="$OUT/${corpus}-${short}-d${d}"
      if compgen -G "$cell/*.results.csv" >/dev/null 2>&1; then
        skip_n=$((skip_n+1)); continue
      fi

      python3 - "$manifest" "$model" "$d" "$cell" <<'PY'
import json, pathlib, sys
manifest, model, draw, cell = sys.argv[1:5]
m = json.loads(pathlib.Path(manifest).read_text())
# ONE key. Everything else is the corpus's own base manifest, unmodified.
m.setdefault("model", {})["extractor"] = model
m.setdefault("rungs", {}).setdefault("0", {})["sample_index"] = int(draw)
m["output"] = {"dir": cell}
m["_cell"] = (f"matrix cell: {manifest} with model.extractor={model}, "
              f"draw {draw}. One key differs from the base.")
pathlib.Path("manifest.cell.json").write_text(json.dumps(m, indent=2) + "\n")
PY

      echo ""
      echo "=== $corpus · $short · draw $d · rungs $RUNGS ==="
      if PYTHONPATH=. python3 -m ladder.run --manifest manifest.cell.json \
           ladder --split "$SPLIT" --rungs "$RUNGS" --plain; then
        done_n=$((done_n+1))
        cp manifest.cell.json "$cell/cell.manifest.json" 2>/dev/null || true
      else
        fail_n=$((fail_n+1))
        echo "!! FAILED $corpus/$short/d$d — continuing"
        echo "$corpus $short $d" >> "$OUT/failures.txt"
      fi
    done
  done
done

elapsed=$(( ($(date +%s) - started) / 60 ))
echo ""
echo "  matrix: $done_n run · $skip_n already present · $fail_n failed · ${elapsed} min"
[ "$fail_n" -gt 0 ] && echo "  failures listed in $OUT/failures.txt"
echo "  A failed cell is a cell, not the matrix. Re-run this script to fill it."

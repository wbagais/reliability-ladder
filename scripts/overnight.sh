#!/usr/bin/env bash
# overnight.sh — run every planned phase unattended, and be honest at breakfast.
#
# WHAT UNATTENDED CHANGES
#
# Nothing here is new science. What changes is that nobody is watching, so every
# failure mode that a person caught today has to be caught by the script:
#
#   a dropped SSH session          -> runs under nohup, survives the terminal
#   a cell that hangs forever      -> per-cell timeout, then quarantine
#   ollama dying mid-phase         -> health check before each phase, restarted
#   a model that was never pulled  -> pulled up front, phase skipped if it fails
#   two runners colliding          -> a lockfile; the second refuses to start
#   a cell running the wrong model -> verified after EVERY phase, not at the end
#   a phase failing                -> logged, and the next phase still runs
#
# WHAT IS NOT COMPROMISED FOR RESILIENCE
#
#   · one variable per cell — every cell still derives from its corpus manifest
#     and changes only model.extractor
#   · a cell whose saved manifest disagrees with its directory name is
#     QUARANTINED, never scored. 23% of yesterday's matrix was corrupt this way
#     and it was invisible until checked.
#   · a retry is a retry of a CELL, never of a phase, and never more than once.
#     A cell that fails twice is a fact about that cell.
#   · nothing is pooled across configurations. Each phase writes its own OUT.
#
# THE MORNING
#
#   out/overnight/SUMMARY.md   read this first — what ran, what failed, what
#                              was quarantined, and the scored tables
#   out/overnight/LOG.txt      the full transcript
#   out/overnight/quarantine/  cells that ran the wrong thing, kept not deleted
#
#   nohup ./scripts/overnight.sh > /dev/null 2>&1 &
#   tail -f out/overnight/LOG.txt
set -uo pipefail
cd "$(dirname "$0")/.."

OUT=out/overnight
LOG="$OUT/LOG.txt"
SUM="$OUT/SUMMARY.md"
LOCK="$OUT/.running"
CELL_TIMEOUT="${CELL_TIMEOUT:-10800}"    # 3 h. The full ladder is ~5x rungs 0-1
                                         # because rung 3 samples three times per
                                         # record; LGL's slowest 0-1 cell was 45 m.
PHASES="${PHASES:-4 1 3 2}"   # 2 LAST: it patches r0.py, and every
                              # phase after would inherit the change.

mkdir -p "$OUT/quarantine"

# ── one runner only ──────────────────────────────────────────────────
# Two runners sharing a scratch manifest swapped each other's configuration
# yesterday and five cells ran the wrong model. Cheaper to refuse.
if [ -e "$LOCK" ] && kill -0 "$(cat "$LOCK" 2>/dev/null)" 2>/dev/null; then
  echo "already running as PID $(cat "$LOCK")" ; exit 1
fi
echo $$ > "$LOCK"
trap 'rm -f "$LOCK"' EXIT

log() { echo "[$(date -u +%H:%M:%S)] $*" | tee -a "$LOG"; }
hdr() { { echo; echo "==================== $* ===================="; } | tee -a "$LOG"; }

: > "$LOG"
log "start · phases: $PHASES · cell timeout ${CELL_TIMEOUT}s"

# ── preflight: fail loudly now rather than at 3am ────────────────────
hdr "PREFLIGHT"
FATAL=0
for f in ladder/cache/snomed.sqlite ladder/cache/geonames.sqlite \
         ladder/cache/mesh.sqlite ladder/cache/taxonomy.sqlite \
         ladder/cache/keywords.vectors.npy; do
  [ -f "$f" ] && log "  ok    $f" || { log "  MISSING $f"; FATAL=1; }
done
free_gb=$(df -BG --output=avail . | tail -1 | tr -dc '0-9')
log "  disk  ${free_gb}G free"
[ "$free_gb" -lt 20 ] && { log "  FATAL under 20G"; FATAL=1; }
python3 -c "import numpy, httpx, openpyxl" 2>/dev/null \
  && log "  ok    python deps" || { log "  MISSING python deps"; FATAL=1; }
[ "$FATAL" = 1 ] && { log "preflight failed — nothing run"; exit 1; }

ollama_alive() { curl -sf http://localhost:11434/api/tags >/dev/null 2>&1; }
ensure_ollama() {
  ollama_alive && return 0
  log "  ollama not responding — restarting"
  (nohup ollama serve >/dev/null 2>&1 &) ; sleep 15
  ollama_alive && { log "  ollama back"; return 0; }
  log "  ollama WILL NOT START"; return 1
}

# ── pull every model up front ────────────────────────────────────────
# A phase that dies on a missing model at 2am wastes the night. qwen3:8b and
# NOT 4b: the 4b has no models.yaml entry, falls back to 2,000 tokens, spends
# them thinking and returns empty content — diagnosed 2026-09-06.
hdr "MODELS"
ensure_ollama || exit 1
for m in gpt-oss:20b llama3.1:8b mistral:7b-instruct ibm/granite4:micro-h \
         qwen3:8b granite-embedding:30m; do
  if ollama list 2>/dev/null | grep -q "^${m%%:*}"; then
    log "  present $m"
  else
    log "  pulling $m"
    timeout 900 ollama pull "$m" >>"$LOG" 2>&1 \
      && log "  pulled  $m" || log "  FAILED  $m — phases needing it will be skipped"
  fi
done

# ── run one cell, with a timeout and exactly one retry ───────────────
cell() {                       # cell <label> <env-assignments...>
  local label="$1"; shift
  local attempt
  for attempt in 1 2; do
    ensure_ollama || { log "    $label: ollama down, skipped"; return 1; }
    # rc captured DIRECTLY, not after an `if`: the if statement consumes $?
    # and the morning report showed rc=0 for a cell that exited 3.
    timeout "$CELL_TIMEOUT" env "$@" ./scripts/run_matrix.sh >>"$LOG" 2>&1
    local rc=$?
    if [ "$rc" = 0 ]; then
      log "    $label: ok"
      return 0
    fi
    if [ "$rc" = 124 ]; then
      log "    $label: TIMED OUT after ${CELL_TIMEOUT}s (attempt $attempt)"
    else
      log "    $label: failed rc=$rc (attempt $attempt)"
    fi
    [ "$attempt" = 1 ] && log "    $label: retrying once"
  done
  echo "$label" >> "$OUT/failed.txt"
  return 1
}

# ── verify a directory of cells, quarantine any that lied ────────────
# Run after EVERY phase, not at the end: a corrupt cell found at 3am is one
# cell, and found at 8am is a table nobody can trust.
verify() {                     # verify <dir>
  local dir="$1" bad=0
  [ -d "$dir" ] || return 0
  for d in "$dir"/*/; do
    [ -d "$d" ] || continue
    local name declared
    name=$(basename "$d")
    declared=$(python3 -c "
import json,sys
try:
    m=json.load(open('$d/cell.manifest.json'))['model']['extractor']
    print(m.split('/')[-1].replace(':','_'))
except Exception: print('NOMANIFEST')" 2>/dev/null)
    case "$name" in
      *"$declared"*) ;;
      *) log "    QUARANTINE $name ran '$declared'"
         mv "$d" "$OUT/quarantine/" 2>/dev/null; bad=$((bad+1));;
    esac
  done
  [ "$bad" -gt 0 ] && log "    $bad cell(s) quarantined from $dir"
  return 0
}

# ── the phases ───────────────────────────────────────────────────────
for phase in $PHASES; do
case "$phase" in

4) hdr "PHASE 4 · rungs 0-6 on PsyTAR, gpt-oss, 3 draws"
   log "  the only phase that measures something no corpus but CADEC has:"
   log "  whether the PAID layers pay. Rung 2 fires only on REJECT, and rung 1"
   log "  wrongly rejects on PsyTAR because its semantic check encodes CADEC's"
   log "  annotation guide — so this is the one corpus where self-correction"
   log "  has real work to do, and nobody has run it."
   # DRAWS=3 in ONE directory. Three DRAWS=1 runs would each set
   # sample_index=0 and, determinism being proven, produce the same run three
   # times. The runner varies sample_index across draws; that is the point.
   cell "psytar-full" MODELS=ollama/gpt-oss:20b CORPORA=psytar \
        DRAWS=3 RUNGS=0-6 OUT="$OUT/full-psytar"
   verify "$OUT/full-psytar"
   ;;

1) hdr "PHASE 1 · qwen3:8b across six corpora, rungs 0-1"
   if ollama list 2>/dev/null | grep -q qwen3; then
     # One corpus per cell() call: the timeout is per invocation, so a
     # six-corpus sweep under one cap dies partway and retries all six.
     for c in finer bc5cdr psytar geo trnews lgl; do
       cell "qwen3-$c" MODELS=ollama/qwen3:8b CORPORA="$c" \
            DRAWS=1 RUNGS=0-1 OUT="$OUT/matrix"
     done
     verify "$OUT/matrix"
   else
     log "  qwen3:8b absent — phase skipped, not failed"
   fi
   ;;

2) hdr "PHASE 2 · LINNAEUS, third fix: cap the few-shot passage"
   log "  RUNS LAST ON PURPOSE: this patches ladder/rungs/r0.py, and any"
   log "  phase after it would inherit a truncated few-shot block — making"
   log "  its numbers incomparable with every cell run before."
   log "  Two fixes failed. Untried: LINNAEUS's few-shot example is a WHOLE"
   log "  RESEARCH PAPER where CADEC's is a two-line forum post. Capping it at"
   log "  600 characters is the change. prep_corpus predicts a 4.8% ceiling"
   log "  here, so even a perfect extractor gives a thin lane."
   python3 - <<'PY' 2>&1 | tee -a "$LOG"
import pathlib
p = pathlib.Path("ladder/rungs/r0.py"); s = p.read_text()
if "TRUNCATED" in s:
    print("  already capped"); raise SystemExit
old = '        body = "\\n   ".join(text.strip().splitlines())'
new = '''        # TRUNCATED. CADEC's few-shot examples are two-line forum posts;
        # LINNAEUS's are whole research papers, and one plus the rules appears
        # to exceed what a 4-8B model holds usefully — granite4 emitted
        # sentence fragments, mistral emitted diseases, llama3.1 emitted
        # nothing. The mentions shown are unchanged; only the passage is cut.
        _t = text.strip()
        if len(_t) > 600:
            _t = _t[:600].rsplit(" ", 1)[0] + " ..."
        body = "\\n   ".join(_t.splitlines())'''
if old in s:
    p.write_text(s.replace(old, new, 1)); print("  few-shot passage capped at 600 chars")
else:
    print("  ! anchor not found — LINNAEUS phase will run unchanged")
PY
   rm -rf "$OUT/linnaeus"
   for m in ollama/llama3.1:8b ollama/mistral:7b-instruct ollama/ibm/granite4:micro-h ollama/gpt-oss:20b; do
     cell "linnaeus-${m##*/}" MODELS="$m" CORPORA=linnaeus DRAWS=1 RUNGS=0-1 \
          OUT="$OUT/linnaeus"
   done
   verify "$OUT/linnaeus"
   ;;

3) hdr "PHASE 3 · LGL + TR-News test splits, four models"
   log "  Last and largest: LGL runs at 45 s/document and its test split is 60,"
   log "  so one cell is 45 minutes. Bigger denominators under a finding that"
   log "  is not in doubt. TR-News first, because it is the faster of the two."
   # TR-News before LGL, and one model per call. LGL is 45 s/document on a
   # 60-document test split — 45 minutes a cell — so eight cells under one
   # timeout would not finish.
   for c in trnews lgl; do
     for m in ollama/gpt-oss:20b ollama/llama3.1:8b ollama/mistral:7b-instruct ollama/ibm/granite4:micro-h; do
       cell "test-$c-${m##*/}" MODELS="$m" CORPORA="$c" DRAWS=1 RUNGS=0-1 \
            SPLIT=test OUT="$OUT/matrix-test"
     done
   done
   verify "$OUT/matrix-test"
   ;;
esac
done

# ── the morning report ───────────────────────────────────────────────
hdr "SCORING"
{
  echo "# Overnight $(date -u '+%Y-%m-%d %H:%M') UTC"
  echo
  echo "## What ran"
  echo
  for d in "$OUT"/*/; do
    [ -d "$d" ] || continue
    case "$d" in *quarantine*) continue;; esac
    n=$(ls "$d"/*/*.results.csv 2>/dev/null | wc -l)
    echo "- \`$(basename "$d")\` — $n cell(s) complete"
  done
  echo
  if [ -s "$OUT/failed.txt" ]; then
    echo "## Failed after two attempts"; echo
    sed 's/^/- /' "$OUT/failed.txt"; echo
  else
    echo "## Failed"; echo; echo "None."; echo
  fi
  q=$(ls "$OUT/quarantine" 2>/dev/null | wc -l)
  echo "## Quarantined"; echo
  if [ "$q" -gt 0 ]; then
    echo "$q cell(s) whose saved manifest disagreed with their directory name."
    echo "They ran a different model than their name says and are NOT scored."
    echo
    ls "$OUT/quarantine" | sed 's/^/- /'
  else
    echo "None. Every cell ran the model its name claims."
  fi
  echo
  echo "## Tables"
  echo
  echo '```'
  for d in "$OUT"/matrix "$OUT"/linnaeus; do
    [ -d "$d" ] && PYTHONPATH=. python3 scripts/score_matrix.py --dir "$d" 2>/dev/null \
      | sed -n '/corpus /,/reference/p'
  done
  [ -d "$OUT/matrix-test" ] && PYTHONPATH=. python3 scripts/score_matrix.py \
      --dir "$OUT/matrix-test" --split test 2>/dev/null | sed -n '/corpus /,/reference/p'
  echo '```'
  echo
  echo "## r0.py was patched by phase 2"
echo
if grep -q TRUNCATED ladder/rungs/r0.py 2>/dev/null; then
  echo "YES — the few-shot passage is capped at 600 characters. Any cell run"
  echo "AFTER phase 2 is not comparable with one run before it. Phase 2 is"
  echo "ordered last so that nothing is, but check the log if you re-ran."
else
  echo "No."
fi
echo
echo "## Phase 4 — the paid layers"
  echo
  echo "Rungs 0-6 on PsyTAR. Read the per-rung lines in LOG.txt: what matters is"
  echo "whether rung 2 corrected anything, whether rung 3's voting moved a"
  echo "verdict, and whether rung 4's judge is read by anything downstream."
  echo "On CADEC the answers were no, barely, and no."
  echo
  echo '```'
  grep -E "rung [0-6] \(" "$LOG" | tail -40
  echo '```'
} > "$SUM"

log "done — read $SUM"

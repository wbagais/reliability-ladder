#!/usr/bin/env bash
# plan_runs.sh — the four outstanding runs, in the order their value justifies.
#
# COSTED FROM TODAY'S MEASURED RATES, not from arithmetic:
#   LGL      ~45 s/document   (the slowest corpus by a wide margin)
#   TR-News  ~25 s/document
#   geo      ~20 s/document
#   PsyTAR   ~12 s/document
#   BC5CDR   ~10 s/document
#   FiNER     ~7 s/document
#   LINNAEUS ~15 s/document
# and the full ladder is about 5x rungs 0-1, because rung 3 samples the
# extractor three times per record and dominates everything else.
#
#   PHASE 4  ~2 h   rungs 0-6 on PsyTAR, 3 draws   THE ONLY NEW FINDING
#   PHASE 1  ~2 h   a fifth model across 6 corpora
#   PHASE 2  ~45 m  LINNAEUS, third fix attempt
#   PHASE 3  ~5 h   LGL + TR-News test splits      (LGL alone is 3 h)
#
# WHY THIS ORDER
#
# Phase 4 measures something no corpus but CADEC has: whether the PAID layers —
# self-correction, sampled voting, an LLM judge — pay anywhere else. The claim
# that they do not currently rests on one corpus. Everything else on this list
# adds a point to a claim already settled by four models or three corpora.
#
# Phase 3 is last despite being the largest because the geographic band already
# has three corpora and twelve cells, and its finding — that TR-News separates
# BELOW 1.0x — is not in doubt.
#
#   ./scripts/plan_runs.sh 4        # one phase
#   ./scripts/plan_runs.sh 4 1 2    # several, in that order
#   ./scripts/plan_runs.sh --dry    # what each would do
set -uo pipefail
cd "$(dirname "$0")/.."

DRY=""
[ "${1:-}" = "--dry" ] && { DRY=1; shift; }
PHASES="${*:-4}"

say() { echo; echo "########## $* ##########"; }
run() { [ -n "$DRY" ] && { echo "    $*"; return; }; eval "$@"; }

for phase in $PHASES; do
case "$phase" in

# ── 4 · DO THE PAID LAYERS PAY ANYWHERE BUT CADEC? ───────────────────
4) say "PHASE 4 · rungs 0-6 on PsyTAR, gpt-oss, 3 draws  (~2 h)"
   cat <<'NOTE'
   The whole matrix is rungs 0-1. Wejdan's CADEC work is the only measurement
   of rungs 2-6 anywhere in this study, and it found: self-correction fired 2-3
   times and corrected nothing, voting changed almost nothing, and the judge's
   verdict is read by nothing downstream. "The paid layers do not pay" is a
   one-corpus claim.

   PsyTAR is the corpus to test it on: it is the matched comparison, it is
   clinical, and it is where the free check's 80.9-90.3% lives. Three draws and
   one model, matching CADEC's own design, so the two are read the same way.

   What this can find that nothing else can:
     · does rung 2 correct anything when rung 1 rejects on a DIFFERENT
       vocabulary's conventions? (rung 1's semantic check encodes CADEC's
       annotation guide — measured 2026-09-05)
     · does voting help where the free check already sorts 2.0x?
     · is the judge read by anything, or is that a CADEC-specific wiring fact?
NOTE
   for d in 0 1 2; do
     run "MODELS=ollama/gpt-oss:20b CORPORA=psytar DRAWS=1 RUNGS=0-6 \
          OUT=out/full-psytar-d$d ./scripts/run_matrix.sh"
   done
   ;;

# ── 1 · A FIFTH MODEL ────────────────────────────────────────────────
1) say "PHASE 1 · qwen3:8b across six corpora, rungs 0-1  (~2 h)"
   cat <<'NOTE'
   qwen3:8b and NOT qwen3:4b. The 4b has no models.yaml entry, fell back to a
   2,000-token budget it spends thinking, and returned empty content on every
   call; given 8,000 it then exceeded the 300 s timeout. The 8b HAS an entry —
   8,000 tokens, 300 s — written after exactly that failure was diagnosed once
   before. Using it is reading the file rather than repeating the mistake.

   Value: a fifth family on a claim four families already agree on. Worth
   having, not worth prioritising.
NOTE
   run "ollama pull qwen3:8b"
   run "MODELS=ollama/qwen3:8b CORPORA='finer geo psytar lgl trnews bc5cdr' \
        DRAWS=1 RUNGS=0-1 ./scripts/run_matrix.sh"
   ;;

# ── 2 · LINNAEUS, THIRD ATTEMPT ──────────────────────────────────────
2) say "PHASE 2 · LINNAEUS on three models, third fix  (~45 m)"
   cat <<'NOTE'
   Two fixes have failed. The prompt rewrite reached gpt-oss and not the other
   three; the vocabulary filter changed nothing. From the records:

     granite4  emits sentence fragments  'The differentiation of adult'
     mistral   emits DISEASES            'kidney', "Ewing's tumour"
     llama3.1  emits nothing at all

   The untried hypothesis: the few-shot example is a WHOLE RESEARCH PAPER.
   CADEC's examples are two-line forum posts; LINNAEUS documents run to
   thousands of characters, and one of them plus the rules may exceed what a
   4-8B model holds usefully. Cutting the example to its first ~600 characters
   is the change.

   prep_corpus.py now predicts a 4.8% ceiling here, so even a perfect
   extractor gives a thin lane. This is worth 45 minutes and not more.
NOTE
   run "python3 - <<'PY'
import json, pathlib, re, sys
sys.path.insert(0, '.')
p = pathlib.Path('ladder/rungs/r0.py'); s = p.read_text()
old = '        body = \"\\\\n   \".join(text.strip().splitlines())'
new = '''        # TRUNCATED. CADEC's few-shot examples are two-line forum posts;
        # LINNAEUS's are whole research papers, and one of them plus the rules
        # appears to exceed what a 4-8B model holds usefully — granite4 emitted
        # sentence fragments, mistral emitted diseases, llama3.1 emitted
        # nothing. The mentions shown are unchanged; only the passage is cut.
        _t = text.strip()
        if len(_t) > 600:
            _t = _t[:600].rsplit(' ', 1)[0] + ' ...'
        body = \"\\\\n   \".join(_t.splitlines())'''
if old in s:
    p.write_text(s.replace(old, new, 1)); print('  few-shot passage capped at 600 chars')
else:
    print('  ! anchor not found — check r0.py line ~637')
PY"
   run "rm -rf out/matrix/linnaeus-{llama3.1_8b,mistral_7b-instruct,granite4_micro-h}-d0"
   for m in ollama/llama3.1:8b ollama/mistral:7b-instruct ollama/ibm/granite4:micro-h; do
     run "MODELS=$m CORPORA=linnaeus DRAWS=1 RUNGS=0-1 ./scripts/run_matrix.sh"
   done
   ;;

# ── 3 · THE GEOGRAPHIC TEST SPLITS ───────────────────────────────────
3) say "PHASE 3 · LGL + TR-News test splits, four models  (~5 h)"
   cat <<'NOTE'
   Last, and largest. LGL runs at 45 s/document and its test split is 60, so
   one cell is 45 minutes and four are three hours. TR-News adds ninety more.

   What it buys: bigger denominators under the geographic band. What it does
   not buy: a new finding. Three corpora and twelve cells already show the
   band, and TR-News separating BELOW 1.0x — the lane scoring worse than the
   records it declined to endorse — is the result, and it is not in doubt.

   Run this only if the card is otherwise idle.
NOTE
   run "MODELS='ollama/gpt-oss:20b ollama/llama3.1:8b ollama/mistral:7b-instruct ollama/ibm/granite4:micro-h' \
        CORPORA='trnews lgl' DRAWS=1 RUNGS=0-1 SPLIT=test OUT=out/matrix-test \
        ./scripts/run_matrix.sh"
   ;;

*) echo "unknown phase: $phase  (4, 1, 2, 3)";;
esac
done

echo
echo "  Every phase writes to its own OUT and skips cells already present."
echo "  A dropped session costs one cell."

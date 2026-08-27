# Dashboard M1: the read-only Workbench

## Why

spec.md (merged in !21) defines the Ladder Workbench — one interface over the
pipeline instead of hand-run CLI + ad-hoc re-scoring + JSONL reading. M1 is
the first milestone cut: the read-only tabs over existing artifacts. No
launcher, no writes of any kind; demo mode, the rung workbench and the R6
tabs are later milestones, but the tab bar and the data layer are shaped so
they land without rework.

## What was built

**`dashboard/`** — a thin FastAPI backend importing `ladder.*` directly, plus
a vanilla-JS single-page frontend (`dashboard/static/`). No build toolchain,
no database. Start it with:

    .venv/bin/pip install fastapi uvicorn httpx   # local extras, pinned in requirements.txt
    python -m dashboard                            # http://127.0.0.1:8321

The app is a **lens**: scores come only from `ladder.score.score_run` /
`bootstrap_ci`; records through `ladder.run.read_predictions`; ledger rows
through `Ledger.read` and per-rung cost through `Ledger.cost_by_rung` (the
pipeline's one accounting path); gold through `ladder.corpus.load_corpus`;
exclusions through `ladder.clean.load_exclusions`; the V4 gold replay through
`ladder.calibrate.run`. Nothing is re-implemented and no file format is
invented. Every heavyweight source (corpus, SNOMED index, `.llm_cache`) is
optional — its absence renders as a stated degradation, never an error.

### Tabs

- **R1 Data explorer** — corpus stats computed from data with warnings on
  mismatch against the recorded numbers (9,111 mentions; 928/115/3 code
  statuses — the absent count computes 4 on the current release and the
  warning says so); documents with gold spans highlighted in-text, including
  discontinuous segments; excluded mentions render as excluded, with their
  reasons; splits view; test split behind an explicit selection with a
  "spent split" banner; V4 zone strip (gold replayed through rung 1,
  local-rf2, ACCEPT 117 / BAND 170 / REJECT 0 on dev).
- **R3 Results & comparison** — runs list covering this checkout's `out/`
  AND the main checkout's `out/archive/` (found through the worktree's
  `.git` file; archived runs are marked); headline with bootstrap CIs;
  per-rung table; side-by-side comparison refusing mismatched splits and
  flagging rung-3 deltas as cross-draw; exports (SVG figure with provenance
  burned into the margin, CSV, scrubbed records JSON).
- **R4 Example walkthrough** — per-record rung timeline (V10) with
  "did not fire" ≠ "did not run" stated per node; per-rung panels driven by
  recorded `checks` and ledger rows only; gold overlay with the five-outcome
  label and a span-mode switch; `(-1,-1)` records render "unlocatable —
  schema-invalid". Record identity is the span key everywhere.
- **R5 Traceability** — outcome card → its records → one record's ledger
  rows, checks, zone history, and its prompts + raw replies from
  `.llm_cache` (≤2 clicks from headline to raw reply). Prompts are
  reconstructed through the rungs' own builders and looked up by request
  hash — verified against phaseF-test-1's real cache (extract, pick and
  judge calls all retained); misses render "not retained", never an empty
  reply. Prompt/reply views are local-only and excluded from every export.

### Visuals (V1–V6, V10)

Ladder curve small-multiples with three separate cost panels; record-flow
counts (242 of 314 routed; 45 withheld-correct; 16 unlocatable); detection
vs coding dumbbell; zone strip on gold; five-outcome composition bars
(exact and overlap side by side; `outdated`/`modernised` never folded);
CI band chart; per-record rung timeline. Shared laws implemented: semantic
zone colors as theme tokens (light + dark), `tabular-nums`, per-rung numbers
over the denominator the ledger names, `could_not_run` and absent
measurements as a hatched non-value.

### Hard constraints, each with a test

- **C1** — server refuses any non-loopback host; every `/api/export/*`
  payload is structurally scrubbed (`scrub_payload`) and then checked
  against the run's actual source texts (`assert_clean`); model free text
  (`sct_label`, judge `why`) is scrubbed too, since it echoes the post; all
  test fixtures use synthetic text.
- **C2** — every route is GET; a test asserts no dashboard module contains
  `subprocess`/`Popen`/`os.system`; no code path constructs a run
  invocation.
- **C3** — provenance (run id · split · span mode · backend · manifest-copy
  hash) on every number-carrying payload, footer component on every figure/
  table/drill-down; a walk-the-endpoints test enforces it.
- **C4** — caveats are data in `dashboard/caveats.py`, attached from the
  run's own ledger facts: rung 3 samples (not attached when rung 3 was
  disabled — a recorded state), 2B-judging-20B, minutes "at the declared
  rate", outdated/modernised never folded, backend-dependence, oracle
  ceiling, spent test split.
- **C5** — tokens / latency p95 / routed-to-a-person are three separate
  panels; `usd` carried alongside; a test asserts nothing fused.

### Golden test

`tests/test_dashboard_golden.py` pins the app's rendering of the archived
`phaseF-test-1` to the recorded values: F1 exact **0.204 [0.150–0.260]**,
overlap **0.215**, outcomes exact **60/0/91/2/0**, reviews_per_100 **77.07**,
denominators `r0_documents`/`r6_queue`, zero failure labels, flow
72/242/16/45. It found a real bug: scoring golds from record-touched
documents instead of the split's full list silently dropped a no-answer
document's false negatives (0.205 vs 0.204). Skips cleanly where the corpus,
index or archive is absent (CI), like the existing integration tests.

## Tests

44 new (`tests/test_dashboard_core.py`, `test_dashboard_app.py`,
`test_dashboard_golden.py`), all TDD'd — failing first, then the code. Full
suite: **636 passed, 7 skipped**. `python3 scripts/preflight.py` clean.

## Decisions logged

Five entries in `docs/decisions.md` (2026-08-26): the M1 build itself; split
inference + full-split denominators; export scrubbing scope; prompt
reconstruction; scope choices (V4 local-rf2 only, archive via the worktree
gitfile, Phase E `.r6` stems listed as-is, test docs behind the spent-split
banner).

## Descoped (M1 boundaries, per spec)

Launcher/workbench (M3), run monitor (M3), demo mode (M2), desk and other R6
tabs (M4), V7–V9 (M3). Rung 2 and rung 3 prompt reconstruction in R5 (rung 2
fired zero times on every measured run; rung 3's samples belong with a
voting view). OLS4 arm of V4 (network backend; the caveat and provenance
name the backend).

🤖 Generated with [Claude Code](https://claude.com/claude-code)

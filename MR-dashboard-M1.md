# Dashboard M1: the read-only Workbench — plus a Live run tab (refreshed 2026-09-09)

## Why

spec.md defines the Ladder Workbench — one interface over the pipeline
instead of hand-run CLI + ad-hoc re-scoring + JSONL reading. M1 is the
read-only tabs over existing artifacts. This MR was opened 2026-08-27 and
sat 281 commits behind main; the 2026-09-09 refresh brings it up to date,
fixes the three things main changed under it, and adds the one piece the
owner asked for: **running the ladder for real on an input**, the way the
plan page's "Ladder demo" pane shows it statically.

## What was built

**`dashboard/`** — a thin FastAPI backend importing `ladder.*` directly, plus
a vanilla-JS single-page frontend (`dashboard/static/`). No build toolchain,
no database. Start it with:

    .venv/bin/pip install fastapi==0.141.1 uvicorn==0.52.4 httpx==0.28.1
    python -m dashboard                            # http://127.0.0.1:8321

The app is a **lens**: scores come only from `ladder.score.score_run` /
`bootstrap_ci`; records through `ladder.run.read_predictions`; ledger rows
through `Ledger.read` and per-rung cost through `Ledger.cost_by_rung`; gold
through `ladder.corpus.load_corpus`; exclusions through
`ladder.clean.load_exclusions`; the V4 gold replay through
`ladder.calibrate.run`; and now a live run through `ladder.run.run_ladder`.
Nothing is re-implemented and no file format is invented. Every heavyweight
source (corpus, SNOMED index, `.llm_cache`, Ollama) is optional — its
absence renders as a stated degradation, never an error.

### Tabs

- **Data** (redesigned 2026-09-09, step 1 of the owner's sketch) — a row of
  filters with a document picker; one summary line (split, documents,
  reaction mentions, drugs, gold through rung 1 as a zone bar); then either
  the document — annotated text, hover a word for its code and vocabulary
  label, click to pin, send to Live — or the table with an "in run" column
  (the run's zones on each document and its pairing against gold, sortable
  by most missed). Totals, splits and exclusions behind a reference
  disclosure. Colour tokens now follow one-colour-one-meaning across the
  dashboard.
- **Results** — a narrative in six sections; runs from this checkout's
  `out/`, the **tracked `runs/archive/`** (new) and the main checkout's
  `out/archive/`; headline with bootstrap CIs; the integrated rung-flow
  diagram with actual and possible paths, clickable subsets; per-layer
  outcome composition; side-by-side comparison; scrubbed exports.
- **Walkthrough** — per-record rung timeline with "did not fire" ≠ "did not
  run"; per-rung panels from recorded `checks` and ledger rows only.
- **Traceability** — outcome card → records → one record's ledger rows,
  checks, zone history, prompts and raw replies. **Prompts now come from
  the run's own `<run>.r<N>.calls.jsonl`** when it wrote them (every run
  since 2026-09-03); hash-lookup reconstruction is the fallback for older
  runs and is labelled as such.
- **Live run** (new, 2026-09-09) — paste a text, or pick a dev/pool
  document, choose the rung to stop at, and the ladder runs **for real**:
  `run_ladder` in-process, every rung's own `apply`, the manifest's models
  through `llm.for_rung`, the same `.llm_cache`. The view is the run's own
  files read back from a scratch directory that is then deleted: each
  record rung by rung (code, zone, verdicts, what changed, outcome vs gold
  when the document has gold), every model call with its full prompt and
  raw reply, each rung's aggregate, and the three cost measures. It writes
  nothing under `out/`, never appears in the runs list, refuses the test
  split, runs one at a time, and carries a "one document is not a
  measurement" caveat on every render. It is the one POST route.
  **Round 2 (owner's review):** the view is per keyword — click a span in
  the text or a chip to follow one record; rung 0 is shown station by
  station (FIND → RETRIEVE → PICK → RESOLVE → TRIM → OUTPUT, from the
  record's own checks and the two calls, a fallback shown as a fallback);
  and a corpus document gets a diff against gold through the scorer's own
  pairing (found exact / overlap / missed / spurious, code right or wrong,
  a withheld right answer named as such), with the text coloured by
  agreement. **Round 3:** a rung rail at the top selects the rung and the
  whole view shows the run as that rung left it (← → keys, prev/next, a
  dot per rung on each record); gold and model stack in one cell, green
  over blue, with the words only one side has underlined and the gold code
  labelled through the registry.

### Hard constraints, each with a test

- **C1** — loopback only; every `/api/export/*` payload structurally
  scrubbed and checked against the run's source texts; model free text
  scrubbed too; the live run and prompt views are local-only and 404 under
  `/api/export/`.
- **C2** — every route is GET except `/api/live/run`, and the test pins
  that set; no dashboard module contains `subprocess`/`Popen`/`os.system`;
  nothing can target the test split, live included.
- **C3** — provenance on every number-carrying payload.
- **C4** — caveats are data (`dashboard/caveats.py`) attached from the
  run's own ledger facts; two new keys for the live run.
- **C5** — tokens / latency p95 / routed-to-a-person are three separate
  panels; `usd` alongside; nothing fused.

### Refresh fixes (2026-09-09)

1. **Phantom runs.** `discover_runs` read `<run>.r3.records.jsonl` as a run
   named `<run>.r3`; the b2-menu archive listed 219 runs of which 150 were
   rung snapshots. Per-rung files are now filed under their run.
2. **Tracked archive.** `runs/archive/` (36 runs, corpus-free) is a source,
   so a fresh clone is not an empty dashboard.
3. **Call traces.** R5 reads the run's call trace before reconstructing a
   prompt — rung 4 has had three menu modes since 2026-09-03 and only the
   trace knows which one a call used.

### Golden test

`tests/test_dashboard_golden.py` pins the app's rendering of the archived
`phaseF-test-1` to the recorded values: F1 exact **0.204 [0.150–0.260]**,
overlap **0.215**, outcomes exact **60/0/91/2/0**, reviews_per_100 **77.07**.
Still green after the refresh.

## Tests

96 dashboard tests (`tests/test_dashboard_core.py`, `test_dashboard_app.py`,
`test_dashboard_golden.py`, `test_dashboard_live.py`), all TDD'd. The live
tests are CI-safe: scripted extractor and judge bound through the same
`llm.for_rung` seam the run uses, the nine-concept registry fixture, rung 0's
real bare path, rungs 1/2/4/5/6 untouched, rung 3 disabled as a recorded
state. `python3 scripts/preflight.py` clean.

## Decisions logged

`docs/decisions.md`: the eleven M1 entries (2026-08-26/27) and three refresh
entries (2026-09-09).

## Descoped (per spec)

Launcher over a split / working manifest / promote (M3 R2), run monitor
(M3), demo mode (M2), desk and other R6 tabs (M4), V7–V9. Rung 3 sample
prompts in R5 for pre-trace runs.

🤖 Generated with [Claude Code](https://claude.com/claude-code)

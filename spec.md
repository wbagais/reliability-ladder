# Ladder Workbench — dashboard spec (implementation-ready)

A local, single-user, multi-tab web app over the reliability-ladder pipeline:
explore the corpus, tune each rung and see the effect, inspect results and
trace every number to its evidence — plus a licence-clean demo mode that
shows the real study results on synthetic examples.

**Governing rule:** the app is a *lens and launcher*. It never computes a
score its own way (`ladder.score.score_run` / `bootstrap_ci` only), never
runs a rung its own way (`python -m ladder.run` subprocess only), never
invents a file format (reads `out/*.records.jsonl`, `*.ledger.jsonl`,
`*.results.csv`, `*.manifest.json`, `.llm_cache/`, `manifest.json`,
`data/splits/`, `data/exclusions.csv`, and the archived baselines in the
main checkout's `out/archive/`).

**One interface.** The repo already has a run-monitor pair —
`docs/ladder-monitor.html` (static page over `runs/*.ledger.jsonl`, replay +
follow modes) and `scripts/ladder_top.py` (terminal twin, same ledger). The
Workbench **absorbs** them: their features and design rules become the Run
monitor tab (R6.5), and once that tab reaches feature parity,
`docs/ladder-monitor.html` is retired (deleted, with a decisions entry) so
there is exactly one web interface. `ladder_top.py` stays as the headless /
SSH companion — it reads the same ledger, so the two views cannot disagree
by construction. Three design rules from that pair are promoted to
app-wide law (see Visuals shared rules): per-rung numbers are drawn over
the **denominator the ledger names**, never the run total; `could_not_run`
renders as a **hatched non-value**, never a color, because the absence of a
measurement must not read as one; and every view of a run reads the
ledger's own fields — replay and live share one ingest path.

---

## Objective

Replace the current workflow (hand-run CLI + ad-hoc re-scoring + JSONL
reading) with one interface, and make the study presentable: to the
researcher on real data, to anyone else through demo mode.

**Non-goals:** not hosted (except possibly the demo build, §R7), not
multi-user, no database, no new experiment framework, no way around the
measurement rules below.

## Personas

- **Researcher** (operator): full access after an explicit operator unlock.
- **Demo viewer**: demo mode only; write controls absent from the DOM.

---

## Hard constraints (each has a test; violating any is a bug by definition)

- **C1 Licence.** CADEC text never leaves the machine: server binds to
  loopback; every export path (files, share payloads) is corpus-text-free —
  ids, offsets, codes, vocabulary labels only (the desk-file rule). Nothing
  containing corpus text is ever tracked in git.
- **C2 Test split is spent.** `phaseF-test-1` is final. Test results are
  read-only displays; no launcher/sweep can target `--split test`; the
  oracle generator's refusal on test is surfaced verbatim.
- **C3 Provenance.** Every figure/table/drill-down renders a footer: run id ·
  split · span mode (exact/overlap) · rung-1 backend · manifest hash.
- **C4 Caveats are data.** One caveat source, auto-attached: rung 3 numbers
  are SAMPLES (run id required; cross-draw deltas warned); rung 4 carries
  2B-judging-20B; minutes are "at the declared rate", never "measured";
  `outdated`/`modernised` never fold into `correct`.
- **C5 Three cost measures, never fused.** Tokens, latency p95, count routed
  to a person: three axes/panels. `usd` carried alongside, never summed in.
- **C6 Manifest is append-only.** The app edits a working copy; runs save
  `<run-id>.manifest.json` beside outputs (as the CLI does); promoting to
  `manifest.json` is an explicit diffed action that appends, never reorders;
  any other write to `manifest.json` fails a test.
- **C7 Remote models are deliberate.** A `local: false` model requires the
  `LADDER_ALLOW_REMOTE=1` consent per run, with the licence reason shown
  (prompts carry corpus text). Consent is never persisted.

---

## Tabs

### R1 — Data explorer (landing; read-only)

Stories: browse documents with gold spans highlighted in-text (incl. the
11.7% discontinuous spans); corpus stats (mentions by entity type, codes by
active/retired/absent, concept-less, post-coordinated, drug families);
splits view (dev/test/pool, seed, stratification); exclusions list with
reasons; zone occupancy of the gold standard under rung 1, per backend.

Criteria:
- Stats are computed from data, not hard-coded; mismatch with recorded
  numbers (9,111 mentions; 928/115/3 code statuses) renders a warning.
- Split filter defaults to dev+pool; selecting test shows a "spent split"
  banner. Excluded mentions render as excluded, not as errors.
- No control in this tab can write or launch.

### R2 — Rung workbench (tabs 0–6): configure → run on dev → compare → freeze

Controls map 1:1 to real config keys; manifest note text shown beside each:

| Rung | Keys | Pinned caveat |
|---|---|---|
| 0 | `rung0_step` S0/S1/S2, `rung0_retrieval` dense/lexical, `rung0_trim`, `rung0_menu_order` score/alpha, extractor (registry) | S3 not offered (measured out). Menu order costs 10–12pt coding. |
| 1 | `mode` observe/gate, lexical exact/contained, `negation_action`, `meddra_check`, `reject_inactive`, `snomed_backend` | Backend changes what a rejection rate means (0.06% vs 23.9%). `gate` confounds rungs 3–6. |
| 2 | `correctable` set, `max_attempts`, `allow_withdrawal` | Fires only on statable REJECT facts; show "N eligible" before running. |
| 3 | `enabled`, k, temperature, min-seen | Disabled is a recorded state. SAMPLES (C4). |
| 4 | judge model (family ≠ extractor, enforced), `tau` | 2B caveat; τ-sweep shows the coverage/precision shelf first. |
| 5 | gating source/thresholds | Show withheld-but-correct count live. |
| 6 | `mode` simulated/desk, `minutes_per_record`, resolutions file | Count is the headline cost. Oracle: dev-only ceiling (C2). |

Criteria:
- Working config serializes to a manifest copy accepted unchanged by
  `python -m ladder.run --manifest`.
- Runs launch via subprocess; progress = tailing the run's ledger (rows per
  rung); a dead process is distinguishable from a quiet one; one live run
  at a time.
- Before launch, show cache price: which documents replay from `.llm_cache`
  vs run cold (the cache key covers model params — a param change is cold).
- Result panel: shipped F1 exact AND overlap + CIs, detection/coding
  layers, five outcomes, three cost panels — vs a chosen baseline, both run
  ids visible.
- Freeze updates the session's working manifest only; promote = C6 flow.
- Split choices: dev, pool. Ablation mode (`ablate`) available beside stack
  mode.
- Operator unlock required for any launch/write; absent in demo mode.

### R3 — Results & comparison (read-only)

Stories: per-rung table (coverage, answered accuracy, errors/100,
zone/verdict counts) for any run; shipped headline with CIs; outcome
composition; three cost panels; side-by-side comparison of two runs (same
split + span mode required; rung 3 deltas flagged cross-draw); export
figures (SVG/PNG) with provenance burned into the margin.

Criteria: golden test pins the rendering of `phaseF-test-1` to recorded
values (F1 exact 0.204 [0.150–0.260]; reviews_per_100 77.07; outcomes
60/0/91/2/0). Runs list includes `out/` and `out/archive/` (read-only).
Exports contain no corpus text (C1).

### R4 — Example walkthrough

Stories: pick a document (search/filter by split, outcome, drug family);
see the post with per-rung panels: rung 0 extraction, rung 1 verdict+reason,
rung 2 fired-or-not (explicitly "0 eligible" when so), rung 3 votes, rung 4
verdict+confidence, rung 5 decision, final state (shipped/escalated). A
per-record rung timeline shows what changed at each rung — including
"nothing", stated. Gold overlay on demand with the five-outcome label and a
span-mode switch.

Criteria: record identity is by span key, never record_id (same rule as
scorer/votes/desk). `(-1,-1)` records render an explicit "unlocatable —
schema-invalid" state. Panels are driven by recorded `checks` (`r1_verdict`,
`r1_reason`, `r0_negated`, `rung0_retrieval`, `rung0_menu_order`, vote
counts, `single_sample`, `r2`, judge fields, `withheld`) and ledger rows —
no re-derivation.

### R5 — Traceability

Stories: any aggregate → its records (click "91 abstained" → those 91); any
record → its ledger rows (tokens, latency, usd, outcome per rung), its
`checks`, its prompts and raw model replies from `.llm_cache`, and its run's
manifest snapshot. Failure labels `timed_out` > `truncated` > `json_decode`
shown distinctly, filed under cost.

Criteria: ≤2 clicks from headline to raw reply. Cache misses render as "not
retained", not as empty replies. Prompt/reply views are local-only and
excluded from all exports (C1). Provenance footer at every level (C3).

### R6 — Supporting tabs (build after R1–R5; same pattern)

1. **Desk** — `scripts/r6_desk.py` workflow as a tab: queue = ABSTAIN
   residue; decisions `code|concept_less|uphold|skip`; span-keyed; measured
   seconds; vocabulary labels, never bare SCTIDs; search via rung 0's
   retriever; byte-compatible resolutions files; oracle generation dev-only
   and labeled.
2. **Vocabulary inspector** — `exists`/`is_active`/`finding_status`/`terms`/
   `replacements` for any code; local-rf2 vs OLS4 crosscheck for a pasted
   list.
3. **Retrieval explorer** — a phrase → dense and lexical candidate menus
   side by side, exactly as the model would see them.
4. **Gate probe panel** — planted-error detection profile + gold-replay
   error floor, re-runnable against the current rung 1 config.
5. **Run monitor** — absorbs the existing monitor pair. Two modes sharing
   one ingest path: **follow** (tail the newest/selected ledger live) and
   **replay** (animate any finished run's ledger — including the archived
   baselines — row by row). Renders: the headline counter; per-rung
   pass/fail/could_not_run bars over ledger-named denominators (hatch for
   could_not_run); the three cost tiles; a bounded live feed; failure-label
   counts; kill for a live run (operator only). Adds from `ladder_top.py`:
   the **Watch** panel — live checks derived from this project's own
   recorded mistakes (e.g. a rung reporting zero without a `disabled` row;
   a verdict column conflated with zones; per-record price fused with
   per-document) — and, when available, the compute panel (GPU clock vs
   temperature, the thermal-throttling check). Provenance comes from the
   run's own manifest copy, never hard-coded (the old page's baked-in
   header — stale models, a frozen denominator — is the defect this
   replaces). Parity criterion: everything the old page and TUI show is
   shown here; then `docs/ladder-monitor.html` is deleted.
6. **Cache browser** — entries by model/params/age; purge with cold-rerun
   warning.
7. **Decisions log reader** — `docs/decisions.md` searchable; pre-2026-08-23
   entries flagged with the old→new rung-id mapping.
8. **Manifest diff** — working copy vs `manifest.json` vs any run snapshot;
   home of the C6 promote flow.

### R7 — Demo mode: the real study, shown safely

Demo mode presents **two data layers, visually distinct and never mixed in
one chart**:

- **Real results layer (aggregates only).** A build step exports
  licence-clean aggregate snapshots from the archived runs — scores, CIs,
  per-rung tables, outcome counts, cost tables, curve/figure data, queue
  composition counts — as JSON under `dashboard/demo/results/` (tracked;
  aggregates contain no corpus text). R3's views and the §Visuals catalogue
  render these REAL numbers in demo mode, provenance-footed with their real
  run ids.
- **Synthetic example layer.** 5–10 invented forum-style posts (written
  from scratch, zero CADEC derivation), hand-annotated with real SNOMED
  codes to cover the show cases: clean extraction; near-miss wrong code;
  `outdated`; `modernised`; concept-less; denied (negated) mention;
  discontinuous span; `(-1,-1)` schema-invalid; abstain→escalate. Canned
  run artifacts + fake cache entries over this corpus (produced once by
  really running the pipeline, then checked in) power R1/R4/R5
  interactively — with a permanent "SYNTHETIC EXAMPLE" banner and demo
  provenance (`run demo-1 · split demo`).
- **Guided tour.** Click-through overlay in story order: explorer → one
  rung config change and its canned effect → the REAL results view → one
  synthetic example through all seven rungs → prompt drill-down → desk
  queue. Steps are captions anchored to live UI; skippable, resumable;
  leaving the tour leaves a browsable demo.

Criteria:
- Demo is a launch state. Structural isolation, tested: while active, no
  file under `data/cadec/`, real `out/`, or `.llm_cache/` is opened —
  except the pre-exported aggregate JSON, which is read from
  `dashboard/demo/` only.
- Real numbers appear only in aggregate views and labeled callouts; example
  views are synthetic-only. A viewer can always tell which they are looking
  at (banner + distinct provenance footer).
- Write controls absent from the DOM; exit requires restart.
- Runs on a fresh clone with app dependencies only (no Ollama, no RF2
  release, no corpus); a stub vocabulary table backs registry views for the
  demo's codes.
- All demo assets pass `scripts/preflight.py`.
- **Actual CADEC examples are never in the demo, by construction.** Showing
  real examples is what the local app in operator mode is for.

---

## Visuals catalogue — every chart earns its place by encoding a finding

Shared rules: provenance footer (C3); semantic zone colors as theme tokens
(ACCEPT/BAND/REJECT + outcome palette), light and dark; `tabular-nums`; no
chart fuses cost measures (C5); every per-rung number is drawn over the
denominator the ledger names, never the run total; `could_not_run` (and any
absent measurement) renders as a hatched non-value, never a color or a
zero; no decorative charts — each row below names the finding it makes
visible and its data source. Ship these in R3/R7; reuse components
elsewhere, the run monitor included.

| # | Visual | Encodes (the finding) | Data |
|---|---|---|---|
| V1 | **Ladder curve** — small multiples per rung: answered accuracy + errors/100 on top; three aligned cost panels (tokens/record, p95 s, reviews/100) below | What each rung buys and what it charges; rung 5's trade; one rung net negative, one silent | `results.csv` per rung |
| V2 | **Record flow** (alluvial/Sankey) — records → per-rung zones → shipped vs escalated, with shipped split correct/wrong and escalated split withheld-correct/wrong/unlocatable | Abstention's bill as a COUNT; 242/314 routed; 45 withheld already right | ledger + records `checks` |
| V3 | **Two-layer dumbbell** — detection F1 vs coding accuracy, exact and overlap, per run; oracle-ceiling marker on dev | The residual gap is span boundaries (detection unchanged, coding →0.99 under oracle) | `score_run` output |
| V4 | **Zone strip on gold** per backend | 57% of a perfect answer set is BAND — the paid rungs' bill; backend changes the answer | gold replay through rung 1 |
| V5 | **Outcome composition bars** — five outcomes in report order, exact & overlap side by side | Four kinds of wrong are not one; `outdated`/`modernised` visible, never folded | `score_run` tallies |
| V6 | **CI band chart** — F1 point + bootstrap interval per run; deltas render only with both intervals | The interval is the claim on 60 docs; test-vs-dev overlap read honestly | `bootstrap_ci` |
| V7 | **Prompt-shape cliff** — S0/S1/S2 as cost-vs-accuracy scatter (tokens vs F1) | Recalling an id: worst accuracy at highest price; broken, not weak | step-compare runs |
| V8 | **Recall@k curves** — dense, lexical, lexical-over-dense-corpus | The retrieval gain decomposes (+3.3 corpus / +21.0 scoring) and inverts at k=1 | retrieval measurement data |
| V9 | **Judge confidence histogram** + τ shelf (coverage/precision vs τ) | Confidence is two-valued; nothing to sweep — why rung 5 gates on verdicts | rung 4 ledger/checks |
| V10 | **Per-record rung timeline** (R4's core) — horizontal track, one node per rung, change/no-change/fired-empty states | Attribution per example; "did not fire" ≠ "did not run" | records `checks` + ledger |

---

## Implementation notes (binding where stated)

- **Layout:** in-repo, `dashboard/` (binding — its constraint tests live
  next to what they guard). Backend: thin FastAPI/Flask importing `ladder.*`
  for reads and shelling out to `python -m ladder.run` for runs; serves the
  SPA; loopback only. No database.
- **Key code entry points:** `ladder.run.read_predictions` (records),
  `ladder.score.score_run(records, golds, span_match, exclude, vocab)` and
  `bootstrap_ci(...)`, `ladder.corpus.load_corpus`/`read_split`,
  `ladder.clean.load_exclusions`, `ladder.registry.Registry(db)`,
  `ladder.llm` registry/model list, `scripts/r6_desk.py` functions for the
  desk tab.
- **Ledger row fields:** `run_id, rung, doc_id, record_id, zone, outcome,
  reason, tokens_in, tokens_out, api_calls, latency_ms, usd`
  (+`human_minutes`, `minutes_source` on rung 6).
- **Progress signal:** ledger line counts per rung (rung 0 writes one row
  per document; rungs 1–6 one per record; rung 3 adds document sampling
  rows).
- **TDD applies** — this is repo code. Golden tests (R3), constraint tests
  (C1–C7), span-key identity tests (R4), export-scrubbing tests (C1), demo
  isolation tests (R7). `python3 scripts/preflight.py` before every commit;
  one line in `docs/decisions.md` per user-visible decision.

## Milestones

1. **M1 read-only:** R1, R3, R4, R5 over existing artifacts + V1–V6, V10.
   No launcher, no writes.
2. **M2 demo:** R7 (dataset, aggregate export, tour) reusing M1 tabs; demo
   dataset doubles as M1's test fixtures.
3. **M3 workbench:** R2 (launcher, working manifest, cache pricing,
   promote) + run monitor at parity with the old pair (then delete
   `docs/ladder-monitor.html`), manifest diff, V7–V9.
4. **M4 rest of R6:** desk, vocabulary inspector, retrieval explorer, gate
   probe, cache browser, decisions reader.

**Done (per milestone):** stories' criteria met with tests; preflight clean;
fresh clone reaches every read-only view with clear degradation when
Ollama/registry/corpus are absent; decisions logged.

## Open questions

1. Viewer mode as the default at startup (recommended), operator unlock
   explicit?
2. Host the demo build publicly? Licence-possible (corpus-free by
   construction); needs a build-time proof it was produced from
   `dashboard/demo/` alone.
3. Config-sweep queue in R2, or does it invite unrecorded tuning?
4. Do test *documents* appear in the explorer, or results only
   (recommended) with an explicit reveal?

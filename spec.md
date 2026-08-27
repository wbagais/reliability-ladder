# Ladder Workbench — dashboard specification

A local, multi-tab web app for exploring the CADEC corpus, tuning each rung of
the reliability ladder interactively, and inspecting — record by record — what
every rung did and why. The spec is written against the repo as it stands
post-Phase F: all seven rungs measured, test split spent, article layer
current.

---

## 1. Objective

Give one person (the researcher/author) a single interface that replaces the
current workflow of hand-run CLI commands, ad-hoc re-scoring scripts, and
JSONL spelunking with:

1. a **data explorer** over the corpus, the splits and the gold annotations;
2. a **per-rung configuration workbench** — change a rung's settings, run it
   on the dev split, see the effect, freeze it, move up one rung;
3. an **overall results view** summarising any run in the project's own
   vocabulary (two span modes, two layers, five outcomes, three cost
   measures, CIs);
4. an **example inspector** — pick any document or record and watch each rung
   transform it;
5. **traceability** for every number and every record down to the prompt and
   the raw model reply;
6. the additional views in §9 that the project's artifacts already support;
7. a **demo mode** (§9bis) — a guided, licence-clean walkthrough of the
   whole interface on synthetic data, safe to show to anyone.

The dashboard is a *lens and a launcher* over the existing pipeline. It never
computes a score its own way: every number on screen comes from
`ladder.score.score_run` / `bootstrap_ci`, every run from `python -m
ladder.run`, every ledger row from the pipeline's own writer. Two accounting
paths is how a benchmark ends up with two numbers for the same run.

### Non-goals

- Not a public demo, not a hosted service, not multi-user. One machine, one
  person, `localhost` only.
- Not a new experiment framework. The manifest, the run ids, the cache and
  the out/ file formats stay exactly as they are; the app reads and invokes,
  it does not reimplement.
- Not a way around any measurement rule the repo already enforces (§3).

---

## 2. Users

One persona: **the researcher** — owns the repo, wrote the phases, is writing
the article. Deep context, low patience for re-deriving things by hand. A
secondary persona: **a demo viewer** (reviewer, reader, audience) — served by
demo mode (R7, §9bis), which runs on synthetic data with every
state-changing control structurally absent, so nothing costly, private or
licence-bound can be reached from a demo session.

---

## 3. Hard constraints (inherited from the repo — the app must enforce, not just respect)

These are requirements, each with its own acceptance criteria in §10.

- **C1 — Corpus text never leaves the machine.** CADEC is non-commercial and
  NON-TRANSFERABLE. The app binds to `localhost` only, serves no corpus text
  to any non-local origin, and its "export/share" features (screenshots
  excluded — those are the user's act) must strip corpus text the same way
  desk resolution files do: ids, offsets, codes, vocabulary labels — never
  the post text.
- **C2 — The test split is spent.** `phaseF-test-1` is final. The app may
  *display* test results (read-only), but every launcher, sweep, and config
  experiment is dev/pool only. There is no "run on test" button. The oracle
  desk generator is refused on test by the pipeline; the app surfaces that
  refusal, it does not soften it.
- **C3 — Every number carries its provenance.** Run id, split, span mode
  (exact/overlap), rung 1 backend (`local-rf2` vs `ols4`), and the manifest
  snapshot that produced it. A number the user can screenshot without its
  run id visible is a spec violation.
- **C4 — Standing caveats render with their numbers, automatically.** Rung 3
  values are SAMPLES (show run id, warn when comparing across draws); rung 4
  carries the 2B-judging-20B caveat; any minutes figure derived from
  `minutes_per_record` says "at the declared rate", never "measured";
  `outdated`/`modernised` are never folded into correct.
- **C5 — Three cost measures, never fused.** Tokens, latency p95, and count
  routed to a person are three axes/panels, never one currency. `usd` is
  carried alongside, never summed into a "total cost" figure.
- **C6 — The manifest is append-only and never silently mutated.** The
  workbench edits a *working copy*; a run launched from the app writes the
  copy beside its outputs (`<run-id>.manifest.json`) exactly as the CLI
  does. Promoting a working copy into `manifest.json` is an explicit,
  diff-reviewed action.
- **C7 — Remote models stay deliberate.** Selecting any model with
  `local: false` in `models.yaml` requires the same explicit
  `LADDER_ALLOW_REMOTE=1` consent, restated in the UI with the licence
  reason (rung prompts carry CADEC text verbatim), per run.

---

## 4. Requirement R1 — Data exploration tab

The landing tab. Everything read-only.

**User stories**

- As the researcher, I want corpus-level statistics (documents, mentions by
  entity type, codes by status active/retired/absent, discontinuous spans,
  concept-less mentions, post-coordinated gold, drug-family distribution) so
  that I can quote denominators without re-running scripts.
- As the researcher, I want to browse documents with their gold annotations
  highlighted in the text (spans, including discontinuous ones; codes with
  vocabulary labels; entity type; polarity examples) so that I can see what
  the answer key actually looks like.
- As the researcher, I want to see the split assignment (dev/test/pool, with
  seed and stratification) and filter every view by split, so that "which
  split is this from" is never ambiguous.
- As the researcher, I want the gold-through-rung-1 zone occupancy view
  (ACCEPT/BAND/REJECT on the answer key itself, per backend) so the "57%
  BAND" planning number is live, not quoted.
- As the researcher, I want to see the exclusions list (`data/exclusions.csv`)
  with each excluded mention's reason, so the denominator story is auditable.

**Acceptance criteria**

- Document browser renders gold spans in-text, handles the 11.7%
  discontinuous spans correctly, and shows each mention's code(s), label(s),
  `gold_kind`, and whether it is excluded.
- Corpus stats reproduce the recorded numbers (9,111 mentions; 1,046
  distinct codes: 928/115/3 active/inactive/absent against the pinned
  release) from the data, not from hard-coded text; a mismatch renders as a
  visible warning, not a silent overwrite.
- Split filter defaults to dev+pool. Selecting test shows a persistent
  banner: "Test is a spent, read-only split."
- Zone occupancy on gold is computed per backend and labeled with it (C3).
- No view in this tab can trigger a run or a write.

---

## 5. Requirement R2 — Per-rung configuration workbench (one tab per rung, 0–6)

The core loop: **configure → run on dev → compare → freeze → next rung.**

**User stories**

- As the researcher, I want each rung tab to expose that rung's real manifest
  settings as controls, with the manifest note/rationale text shown beside
  each control, so the UI teaches the same constraints the repo does.
- As the researcher, I want to launch a dev-split run with my working config
  under an auto-suggested run id, watch progress live, and see the scored
  result next to the current baseline when it lands.
- As the researcher, I want to "freeze" a rung's config into the session's
  working manifest so the next rung's experiments run on top of it — and to
  see, at all times, the diff between working manifest and `manifest.json`.
- As the researcher, I want an ablation mode (`ablate`) per rung — the rung
  alone on fixed input — beside the stack mode, because stack deltas are not
  attributable to one rung.
- As a demo viewer, I want run-launching controls visibly disabled until an
  explicit "I'm the operator" toggle is set, so nothing costly or
  state-changing happens by accident.

**Per-rung controls (from the real manifest/config surface)**

| Rung | Controls | Fixed caveats shown |
|---|---|---|
| 0 | `rung0_step` (S0/S1/S2), `rung0_retrieval` (dense/lexical), `rung0_trim`, `rung0_menu_order` (score/alpha), extractor model (registry list), reasoning effort / max_tokens (registry, read-mostly) | S3 was measured out of existence — not offered. Menu order is load-bearing (−10–12pt coding). Effort dial re-litigates a measured decision — link the decisions entry. |
| 1 | `mode` (observe/gate), lexical mode (exact/contained), `negation_action` (flag/reject), `meddra_check` (flag/reject), `reject_inactive`, `snomed_backend` (local-rf2/ols4) | Backend changes the meaning of every rejection rate (23.9% vs 0.06%) — switching re-labels every open view. Gate mode confounds rungs 3–6 — warn. |
| 2 | `correctable` reasons (multi-select), `max_attempts`, `allow_withdrawal` | Fires only on rung 1 REJECT with a statable fact; on runs where all rejects are `schema_invalid`, show "0 eligible" *before* the run. |
| 3 | `enabled`, k (samples), temperature, min-seen threshold | Disabled is a recorded state, not a skip. Results are SAMPLES; the tab always shows the current draw's run id and refuses cross-draw deltas without both ids on screen. |
| 4 | judge model (must differ in family from extractor — enforced), `tau` | 2B-judging-20B caveat pinned. Confidence near two-valued; τ-sweep view shows coverage/precision shelf before any gating choice. |
| 5 | gating source (verdicts), thresholds | Where a verdict is finally allowed to cost coverage; show withheld-but-correct count beside every setting change. |
| 6 | `mode` (simulated/desk), `minutes_per_record` (declared), resolutions file picker | Count routed is the headline cost. Minutes always "at the declared rate". Oracle generator: dev only, every output labeled ceiling; refused on test (C2). |

**Acceptance criteria**

- Every control maps 1:1 to a real config key; the app can serialize the
  working config into a manifest copy that `python -m ladder.run --manifest`
  accepts unchanged.
- Runs are launched via the existing CLI (subprocess), never an in-process
  reimplementation; progress is derived from tailing the run's ledger (rows
  per rung), and a dead process is distinguishable from a quiet one.
- The result panel shows: shipped F1 exact AND overlap with CIs, detection
  and coding layers, five outcomes, and the three cost measures — versus a
  selected baseline run, with both run ids visible (C3).
- "Freeze" updates only the session's working manifest; `manifest.json` on
  disk is untouched until the explicit promote action (C6), which shows a
  diff and appends, never reorders.
- Split selector for runs offers dev and pool only (C2).
- Cache-awareness: the app states before launching how much of the run will
  replay from `.llm_cache` (documents with unchanged prompts+params) vs run
  cold, so a "quick tweak" that invalidates the cache is priced before it
  is paid. (The cache key covers model params — a param change is a cold
  run, and the UI must say so.)

---

## 6. Requirement R3 — Overall results tab

**User stories**

- As the researcher, I want a summary view of any run: the per-rung table
  (coverage, answered accuracy, errors/100, zone/verdict counts), the
  shipped headline with CIs, outcome composition, and the three cost panels
  — the dashboard equivalent of `results.csv` + the re-score harness.
- As the researcher, I want to compare two runs side by side (e.g. dev
  baseline vs a workbench run; dev vs the final test run), with deltas
  computed only where comparison is legitimate (same split, same span mode;
  rung 3 deltas flagged as cross-draw).
- As the researcher, I want the ladder curve figure — accuracy and each cost
  measure per rung, drawn as separate aligned panels — exportable for the
  article.

**Acceptance criteria**

- Numbers come from re-scoring `records.jsonl` via `score_run`/`bootstrap_ci`
  (or reading the run's own `results.csv` for per-rung rows) — never a
  parallel implementation; a golden test pins the app's rendering of
  `phaseF-test-1` to the recorded values (F1 exact 0.204 [0.150–0.260],
  reviews_per_100 77.07, five outcomes 60/0/91/2/0).
- Exact and overlap are both always available; the active mode is displayed
  on the figure itself (C3).
- The three cost measures render as three panels; no view sums them (C5).
- Runs list includes everything under `out/` and the archived baselines in
  the main checkout's `out/archive/` (read-only).
- Export produces SVG/PNG of figures with provenance (run id, split, mode,
  backend) burned into the image margin — and never includes corpus text
  (C1).

---

## 7. Requirement R4 — Example walkthrough tab (output visualization / selection)

**User stories**

- As the researcher, I want to pick any document (searchable list, filterable
  by split/outcome/drug family) and see the source post with, side by side
  per rung: what rung 0 extracted, what rung 1 judged, whether rung 2 fired,
  what rung 3's votes were, rung 4's verdict, rung 5's decision, and where
  the record ended (shipped / escalated), so I can narrate one example's
  journey in the article.
- As the researcher, I want a "diff between rungs" rendering: for a selected
  record, what changed at each rung (code, label, zone, checks) — including
  "nothing", stated explicitly, because "did not fire" and "did not run"
  are different facts.
- As the researcher, I want gold overlaid on demand, with the outcome
  (correct / outdated / abstained / incorrect / modernised) per record, span
  match mode switchable.

**Acceptance criteria**

- Record identity across rungs is by span key, never record_id position —
  the same rule as the scorer, rung 3's votes and the desk.
- A record with unlocated `(-1,-1)` spans renders with an explicit
  "unlocatable — schema-invalid extraction" state instead of broken
  highlighting.
- Rung panels are driven by the recorded `checks` (e.g. `r1_verdict`,
  `r1_reason`, `r0_negated`, `rung0_retrieval`, `rung0_menu_order`, rung 3
  vote counts and `single_sample`, `r2` outcome, judge verdict/confidence,
  `withheld`) and the run's ledger rows — no re-derivation.
- Gold overlay honors the exclusions list; an excluded mention is shown as
  excluded, not as a false negative.

---

## 8. Requirement R5 — Traceability

**User stories**

- As the researcher, I want to click any record in any view and reach: its
  ledger rows (every rung, tokens, latency, usd, outcome), its `checks`
  dict, the prompts sent on its behalf and the raw model replies (from
  `.llm_cache`), and the manifest snapshot of its run — the full evidence
  chain for one number.
- As the researcher, I want to click any aggregate number and reach the
  records that compose it (e.g. click "91 abstained" → those 91 records),
  so no figure is a dead end.
- As the researcher, I want failure labels (`timed_out` > `truncated` >
  `json_decode`) surfaced distinctly wherever a record failed, filed under
  cost, not accuracy.

**Acceptance criteria**

- Every aggregate in R3 is drillable to its record set; every record is
  drillable to its call-level evidence. Two clicks maximum from headline to
  raw model reply.
- Cache entries are matched by the run's actual keys (model, params,
  prompt); a cache miss (e.g. purged entry) renders as "not retained", not
  as an empty reply.
- Prompt/reply views are local-only and excluded from any export path (C1 —
  prompts embed corpus text).
- The provenance footer (C3) is present on every drill-down level.

---

## 9. Requirement R6 — Additional views the project already supports (the "what else" review)

Ordered by how much manual work each currently replaces.

1. **Rung 6 desk, integrated.** `scripts/r6_desk.py` is a terminal UI; its
   whole workflow (queue from a run's ABSTAIN residue, span-keyed
   resolutions `code | concept_less | uphold | skip`, measured seconds,
   vocabulary labels never bare SCTIDs, search through rung 0's retriever)
   becomes a dashboard tab. Same resolutions file format, byte-compatible;
   the timer runs while the reviewer looks. This is the one tab that
   *creates* pipeline input, and it inherits the desk's own rules (no
   corpus text in rows; oracle generation dev-only and labeled).
2. **Vocabulary inspector.** A SNOMED lookup panel over the local registry:
   `exists` / `is_active` / `finding_status` / `terms` / `replacements`
   chains for any code; the backend crosscheck (local-rf2 vs OLS4) for a
   pasted code list. Replaces `python -m ladder.vocab_crosscheck` runs and
   settles "is this code real/retired/AU-extension" questions in one place.
3. **Retrieval explorer.** Type a mention phrase → see the dense and lexical
   candidate lists side by side (k, scores, dedupe, menu order as the model
   would see it). Directly explains S2 coding behavior and menu-order
   sensitivity; uses the same `KeywordTable`/embedding path as rung 0.
4. **Gate probe panel.** The planted-error detection profile (six corruption
   classes) and the gold replay (gate error floor) as live, re-runnable
   views with their standing figures — the §2 gate findings, kept honest
   against config changes made in R2's rung 1 tab.
5. **Run monitor.** All runs (live and historical): state, per-rung ledger
   progress, token/latency accumulation, failure-label counts; kill a live
   run. Replaces log tailing.
6. **Cache browser.** Entries by model/params/age and size; which run ids
   touch which entries; explicit purge with a "params changed = cold rerun"
   warning. Makes the cache's architecture visible.
7. **Decisions log reader.** `docs/decisions.md` rendered, searchable,
   filterable by date/phase, with rung-renumbering awareness (pre-2026-08-23
   entries flagged with the old→new id mapping). The article's raw material,
   finally greppable by a human.
8. **Manifest history / diff view.** The working manifest vs `manifest.json`
   vs any run's saved snapshot, as a three-way diff — the C6 promote flow's
   home.

Each of these ships with user stories and criteria at build time following
the same pattern as R1–R5; they are scoped here so the tabs bar can be laid
out once.

---

## 9bis. Requirement R7 — Demo mode

A demo of this dashboard collides head-on with C1: every real tab renders
CADEC text, and CADEC is non-transferable. So the demo is not "the app with
a tour on top" — it is the app running on a **separate, synthetic, tracked
demo dataset**, plus a guided tour. Two deliverables:

**R7a — The demo dataset.**

- A small synthetic corpus (5–10 invented forum-style posts, written for
  this purpose, no CADEC derivation) with hand-made gold annotations against
  real SNOMED codes, covering the cases the interface exists to show: a
  clean extraction, a wrong-code near miss, a retired code (`outdated`), a
  retired-gold successor (`modernised`), a concept-less mention, a denied
  (negated) mention, a discontinuous span, a schema-invalid `(-1,-1)`
  record, and an abstained-then-escalated record.
- Canned run artifacts over that corpus (records/ledger/results/manifest
  copy, plus matching fake cache entries for the prompt/reply drill-down),
  produced once by actually running the pipeline over the synthetic docs,
  then checked in — so every tab, including R5 traceability, is populated
  **without Ollama, without the RF2 release, and without `data/cadec/`**.
  A stub vocabulary table (the pattern the test suite already uses) backs
  the registry views for exactly the codes the demo corpus uses.
- All demo assets are tracked in-repo (e.g. `dashboard/demo/`), pass
  preflight, and are the one exception to "out-of-repo run artifacts" —
  legitimate because they contain no corpus text and exist to be shipped.

**R7b — The guided tour.**

- A scripted, step-through overlay that walks the tabs in story order: the
  data explorer → one rung tab with a config change and its (canned) effect
  → the results summary → one example's journey through all seven rungs →
  one drill-down to prompt and reply → the desk queue. Each step is a short
  caption anchored to the live UI element, advanced by click; skippable and
  resumable at any step.
- The tour narrates the project's real findings as labeled callouts (the
  measured numbers, quoted as static text with their run ids) while the
  interactive panels show the demo data's own numbers — the two must never
  be visually confusable (see criteria).

**User stories**

- As the researcher, I want to show the dashboard to a colleague, a reviewer
  or a conference audience without a licence conversation, so demo mode must
  contain zero CADEC-derived content end to end.
- As the researcher, I want the demo to run from a fresh clone with no
  downloads (no corpus, no RF2 release, no Ollama), so "try it" is one
  command.
- As a demo viewer, I want a guided tour that teaches me the ladder's story
  through the interface, and the freedom to leave the tour and click around
  the demo data myself.
- As the researcher, I want it to be impossible to mistake demo numbers for
  the measured results, and impossible for a demo session to write anything
  into real runs, the manifest, or resolutions.

**Acceptance criteria**

- Demo mode is an explicit launch state (flag or startup toggle). In it, the
  data-path layer resolves **only** the demo dataset: an automated test
  asserts no file under `data/cadec/`, `out/` (real runs), or `.llm_cache/`
  is opened while demo mode is active — the isolation is structural, not a
  filter.
- Demo mode forces viewer mode: launchers, manifest promote, desk writes and
  cache purge are absent from the DOM, not merely disabled (the R2 operator
  toggle does not exist in demo mode).
- A persistent, unmistakable banner marks every view: "DEMO — synthetic
  data; numbers are illustrative." Demo figures use a visually distinct
  provenance footer (C3 still applies: run id `demo-1`, split `demo`), and
  the tour's quoted *measured* numbers are typographically distinct labeled
  callouts, never rendered inside charts of demo data.
- The demo corpus and annotations pass `scripts/preflight.py` and contain no
  text derived from CADEC posts (written from scratch; reviewed against the
  C1 criteria before first commit).
- The full tour runs on a fresh clone with only the app's own dependencies
  installed; every tab it visits renders with demo data; abandoning the
  tour leaves a fully browsable demo app.
- Exiting demo mode requires an app restart into the real data paths — no
  in-session toggle that could mix the two datasets in one view.

---

## 10. Acceptance criteria for the hard constraints (§3)

- **C1:** the server refuses non-loopback connections; an automated test
  asserts no export path (files, clipboard payloads, share links) contains
  corpus post text; the preflight scan runs against anything the app writes
  into the repo tree.
- **C2:** no UI path constructs a run invocation with `--split test`; the
  splits offered by every launcher enumerate dev/pool only; attempting to
  point the desk's oracle generator at test surfaces the pipeline's own
  refusal message verbatim.
- **C3:** a shared provenance component (run id · split · span mode ·
  backend · manifest hash) is rendered by every figure, table and
  drill-down; its absence anywhere is a bug by definition.
- **C4:** caveat text is data (one source of truth), attached to rung 3,
  rung 4, minutes, and outcome-fold rules; removing a caveat requires
  changing that source, not a template.
- **C5:** code review + test: no component receives more than one cost
  measure as a single scalar; the summary layout renders three panels.
- **C6:** `manifest.json` file watch — if the app ever writes it outside the
  promote flow, a test fails; promote shows an append-only diff and refuses
  reorders.
- **C7:** selecting a remote model shows the consent gate with the licence
  rationale; the launch command includes the env var only after per-run
  consent; consent is never persisted.

---

## 11. Suggested architecture (informative, not binding)

- **Backend:** a thin local FastAPI (or Flask) layer inside the repo,
  importing `ladder.*` directly for scoring/registry/retrieval reads, and
  shelling out to `python -m ladder.run` for anything that produces run
  artifacts. No database: `out/`, `out/archive/`, `.llm_cache/`, `data/`
  and the manifest are already the store.
- **Frontend:** a single-page app served from the same process; tabs per
  R1–R6. Rendering the corpus text stays client-side over localhost only.
- **Long-running runs:** subprocess + ledger tailing for progress (rows per
  rung is already a reliable progress signal); one live run at a time,
  matching the single local Ollama instance.
- **Testing:** TDD applies — it is repo code. Golden tests pin the app's
  numbers to recorded run values; constraint tests cover §10. `scripts/`
  coverage history says untested glue is where the bugs were.

---

## 12. Open questions (decide before build)

1. **Where does it live?** In-repo (`dashboard/`, versioned with the ladder,
   preflight-covered) vs a sibling repo. In-repo recommended: C1/C6 tests
   want to live next to what they guard.
2. **Read-only mode default?** Should the app start in viewer mode with an
   explicit operator unlock (recommended — protects demos, C2/C6), or
   operator mode by default?
3. **Scope of the first milestone.** Recommended cut: R1 + R3 + R4 + R5
   (pure readers over existing artifacts — no launcher, no writes), then R2
   (launcher + working manifest), then R6.1 desk and the rest of R6. R7
   demo mode slots naturally right after the first milestone — it reuses
   the read-only tabs verbatim, and building its dataset early doubles as
   the fixture set for the tabs' own tests.
4. **Does the test split appear in the data explorer at all**, or only its
   results? Displaying test *documents* is safe for a spent split but
   normalizes browsing them; recommend results-only by default with an
   explicit reveal.
5. **Sweeps.** R2 deliberately launches one run at a time. Is a small
   config-sweep queue (dev only, cache-priced first) wanted, or does it
   invite exactly the unrecorded tuning the decisions log exists to
   prevent?
6. **Hosting the demo.** Demo mode contains no CADEC content, so C1's
   localhost rule need not bind it — a static or hosted build of demo mode
   (e.g. beside the article) is legally possible. Decide whether that is
   wanted; if yes, the demo build must be produced from the demo dataset
   alone by construction (a build-time test, not a promise).

---

## 13. Definition of done (per milestone)

- Every user story in the milestone has its criteria demonstrably met, with
  tests for the testable ones (constraints, scoring parity, span-key
  identity, export scrubbing).
- `scripts/preflight.py` passes with the dashboard code in the tree; no
  corpus text or key-shaped string in any tracked file.
- A cold clone with the standard preprocessing steps can start the app and
  reach every read-only view; launcher paths degrade with clear messages
  when Ollama or the registry index is absent.
- One line in `docs/decisions.md` per user-visible decision made during the
  build, as always.

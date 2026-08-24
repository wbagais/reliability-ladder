# Decisions & surprises log

Capture decisions, dead ends, and surprises *as they happen*. This is the raw
material for the InfoQ article — it evaporates if you reconstruct it in week 5.

Format: date — decision/surprise — why.

---

The log starts at the CADEC track. An earlier data-agnostic track on receipt
scans was retired on 2026-08-22 together with its results — see the retirement
entry below. Nothing in this file is derived from it.

## CADEC pharmacovigilance track (`ladder/`) — owner A, 2026-08-22

The v16 plan retargets the ladder to CADEC adverse-event posts, where rung 1 is
grounded in a real clinical vocabulary rather than in a JSON Schema. (At the time
of these entries an earlier data-agnostic track still existed alongside it; it
was retired on 2026-08-22 — see below.)

Format: date — decision/surprise — why.

### Verification of the plan against the data (before writing any code)

- 2026-08-22 — VERIFIED: corpus parses. CADEC v3 = 1,250 posts, **9,111** gold
  mentions across ADR (6,318) / Drug (1,800) / Finding (435) / Disease (283) /
  Symptom (275). The plan says "~6,754 entity mentions"; that figure is the
  published paper's count for a subset, not what v3's `sct/` files contain.
  Manifest records 9,111 as the number to reconcile against.
- 2026-08-22 — VERIFIED: `CONCEPT_LESS` exists — 445 mentions in `sct/`, 327 in
  `meddra/`. The plan's "one free gift" is real, and it is the abstention target.
  Caveat: the literal is uppercase, and grepping for `concept_less` finds nothing.
- 2026-08-22 — CONTRADICTS THE PLAN: "CADEC codes reactions, not drugs. There
  are no drug codes to score." v3's `sct/` files code **1,657 of 1,800** drug
  mentions, mostly to AMT product concepts (`3384011000036100 | Arthrotec |`).
  Kept the plan's scoring split anyway — drugs stay span-only, because AMT codes
  are Australian-specific and drug normalisation is not the interesting problem —
  but rung 1 had to learn that a product concept is not a semantic-type error.
- 2026-08-22 — CONTRADICTS THE PLAN: the record shape in plan §1 pairs
  `drug_text` with `reaction_text` in one object, which contradicts the plan's
  own safety constraint 3 ("never emits 'drug X causes Y'") and CADEC's own
  independent annotation of the two. **One record = one mention**, with an
  `entity_type` of reaction or drug. The pairing would have made every output a
  causal claim by construction.
- 2026-08-22 — DECISION: the four clinical entity types collapse to `reaction`.
  CADEC's "ADR" label is a causal attribution made by a human annotator;
  asking a model to reproduce it is asking for exactly the causal claim
  constraint 3 forbids. Only reaction-vs-drug is asked for or scored.
- 2026-08-22 — SURPRISE: 1,065 mentions (11.7%) have **discontinuous** spans
  (`40 44;54 62`), and 45 of them quote the segments in reading order rather
  than offset order ("swelling feet" for `[feet][swelling]`). A span-grounding
  check that compares concatenations calls the answer key ungrounded. It
  compares token bags instead.
- 2026-08-22 — SURPRISE: gold is not always one code. 252 mentions are
  post-coordinated (`A | x | + B | y |`, the mention needs both) and 3 are
  disjunctions (`A or B`, either is right). "Strict = exact SCT code equality"
  is undefined for 2.8% of the corpus. Gold rule written as "the predicted code
  is IN the gold set", with the affected 2.8% reported separately.
- 2026-08-22 — SURPRISE: CADEC's own gold fails span grounding **4 times in
  9,111** — three annotation typos (`rena  failure`, `microabrasion` vs
  `microabrasions`, `pain i stomach`) and one genuine boundary error. That
  0.04% is the floor rung 1's cheapest check can never get below on this corpus.
- 2026-08-22 — DECISION: vocabulary lookup comes from a **local SNOMED CT RF2
  release**, not BioPortal. The plan calls BioPortal the critical path and its
  own §10 risk table rates "no working vocabulary lookup" as high-likelihood.
  A local release removes the risk entirely: no key, no rate limit, no network
  inside the measurement loop, and the version pin is a directory name rather
  than a promise. `ladder/registry.py --build` turns the 5 GB release into a
  365 MB SQLite index in ~8 seconds; lookups are microseconds.
- 2026-08-22 — CONTRADICTS THE PLAN: MedDRA cannot be checked or scored here.
  The only MedDRA artefact available is `meddra_codes.csv`, which ships *inside*
  CADEC and is derived *from* it (its columns include `occurrences` and
  `posts`). Using it as an existence check is precisely the leakage the plan's
  own §4.1 warns against — the check would accept exactly the answer key.
  SNOMED CT is the only vocabulary gate; MedDRA is recorded and not scored.

### Building rung 1, and what the gold standard said about it

The method: replay rung 1 over CADEC's own annotations. Every rejection there
is a FALSE rejection by construction, so the gate's error floor is measurable
before any model output exists (`python -m ladder.calibrate --sweep`).

- 2026-08-22 — First run of the gate as the plan specifies it rejected **9.3%
  of the gold standard** (845 of 9,111). A validation gate with a 9% false
  positive rate does not measure a model; it manufactures errors. Three causes,
  all fixed:
- 2026-08-22 — CAUSE 1, and the big one — **the negation check rejects 427
  gold-correct mentions (4.7%)**. The plan gives negation its own boxed section
  and its own rejection reason, using "so far no gastric problems" as the worked
  example. That sentence is ARTHROTEC.1, and CADEC annotates `gastric problems`
  as an ADR coded 162076009. **CADEC annotates a mention regardless of
  polarity.** On top of that, NegEx scope rules misfire on forum prose: "I can't
  describe the horrible stomach pain", "I can finally clean my house without
  pain", "many doctors deny that there is a connection between joint pain ... and
  Lipitor" — all negate something other than the mention. CHANGED: negation is
  demoted from a rejection to an audit flag (`negation_action: "flag"`). The
  detector still runs and the rate is still reported, because polarity errors are
  a real safety class the F1 hides — but under this gold standard it cannot
  reject. `negation_action: "reject"` reproduces the plan as written.
- 2026-08-22 — CAUSE 2 — **the semantic-type check rejected 416 gold-correct
  reaction mentions**, and 413 of them for a reason that has nothing to do with
  semantics: SNOMED retires a concept's is-a relationships when it retires the
  concept, so a hierarchy walk over active relationships alone cannot place any
  retired concept, and "cannot place" was being read as "wrong slot".
  |Knee pain| (63 mentions), |Weakness of limb| (53), |Mentally dull| (38),
  |Bloating symptom| (34) — all clinically right, all retired. CHANGED: the
  index stores the descendant set twice, over active is-a rows and over every
  is-a row ever published; `finding_status()` returns finding / not_finding /
  unknown, and rung 1 may only reject on a positive `not_finding`.
- 2026-08-22 — CAUSE 3 — **115 of the 1,046 SCT codes CADEC uses (11%) are
  inactive** in the 2026-07 release, and 4 are absent entirely. Reading `exists`
  as "active in the current release" rejects 6.9% of gold. CHANGED: `exists()`
  means present in the release, active or not; inactivity is an audit fact.
  `reject_inactive: true` is available and costs 648 gold mentions.
- 2026-08-22 — RESULT: after the three fixes the false-rejection floor is
  **12 / 9,111 = 0.13%** — 5 codes absent from the release, 4 corpus typos, and
  3 genuine gold miscodings (|Eruption| for "Abdominal rash", an observable
  entity for "abdominal pressure"). Those last three are the check working.
- 2026-08-22 — SURPRISE: the plan's own §1 example record — "little blurred
  vision" coded 246636008 — lands in BAND, not ACCEPT. SNOMED's terms for that
  concept are Foggy / Hazy / Misty / Cloudy vision; it never uses the word
  "blurred". Correct code, zero lexical evidence. That is the BAND lane doing
  exactly its job, and it is why rung 1 must never be allowed to claim a code is
  right.
- 2026-08-22 — ZONE OCCUPANCY on gold at the final settings (whole corpus):
  ACCEPT 3,926 (43.1%), BAND 5,173 (56.8%), REJECT 12 (0.13%). On the frozen
  test split: 171 ACCEPT / 222 BAND / 0 REJECT of 393. **Well over half of a
  perfect answer set is unverifiable by string comparison.** That is the ceiling
  on how much of the batch rung 1 can ever settle for free, and the size of the
  pool rungs 3-6 have to pay for — a useful number to have before spending a
  single token on them.

### What rung 1 can and cannot catch (`ladder/probe.py`)

The false-rejection floor is only half the characterisation. The other half:
corrupt gold records in one known way at a time and see what the gate does.
Model-free, whole corpus, 8,666 coded records per corruption.

- 2026-08-22 — DETECTION PROFILE: hallucinated code 1.000 · span shift 1.000 ·
  span fabrication 1.000 · wrong semantic type 1.000 on reactions (0.000 on
  drugs, by design — no code is scored there). Deterministic checks are not
  approximately good at their job; on their own classes they are exact.
- 2026-08-22 — THE FINDING WORTH THE ARTICLE: a **near-miss** code — a real,
  active clinical finding that shares its head word with the right one, which is
  the confusion a normalisation model actually makes — is caught 0.1% of the
  time, and with the obvious lexical setting **19% of them are actively
  ACCEPTED**: rung 1 does not merely fail to catch them, it vouches for them,
  because the span text is a subset of the wrong concept's term. A random
  plausible wrong finding is caught 0.0% of the time but almost never accepted
  (it lands in BAND). So the plan's "wrong code is the class no deterministic
  check can catch" is right, and understated: the lexical lane can turn a fifth
  of the near-misses into false confidence.
- 2026-08-22 — CHANGED THE DEFAULT ON THE STRENGTH OF THAT: `lexical_mode` goes
  from `contained` to `exact`. Token containment is the intuitive choice for
  colloquial text — it accepts "bit drowsy" for |Drowsy| and lifts the ACCEPT
  lane from 43.1% to 54.5% of gold. It is also what produces the 19%. Exact
  normalised equality puts 0.1% of near-misses in ACCEPT. Eleven points of free
  settlement is not worth a gate that endorses one near-miss in five, and the
  cost is only that more records fall through to the paid rungs — which is what
  the rest of the ladder is for. Both numbers are measured, not argued:
  `python -m ladder.probe --lexical-mode contained|exact`.
- 2026-08-22 — Generalised: the failure mode is a validation check whose
  permissive setting looks kinder to the model and is really kinder to the
  *error*. Worth stating as a rule in the article — for any gate, measure the
  permissive setting's false-vouch rate on planted near-misses before shipping
  it, because the intuition ("be lenient with colloquial text") points the wrong
  way.

### Harness decisions

- 2026-08-22 — DECISION: splits are by **document**, 40 dev / 60 test, seed 42,
  stratified by drug family. The plan says "dev 40, test 60" in step 0 and
  "n(test) = 60" in §7.1, but §6 asks for a 600-800 record test split. Reading
  40/60 as documents reconciles both: 60 posts carry 393 mention records and
  still cost only 60 rung-0 calls. Splitting by mention would leak, since
  mentions from one post share its wording and its annotator. CADEC is 80%
  Lipitor, so stratification is not optional — an unstratified test split would
  be almost entirely one drug family, and the ~0.69 human span-agreement ceiling
  the plan cites was measured on the other one.
- 2026-08-22 — OPEN ISSUE for iteration 2: at 60 test documents the abstention
  target is thin — 7 CONCEPT_LESS mentions in 393. Abstention accuracy cannot be
  separated from noise at that size. Either raise n_test (documents are cheap:
  one rung-0 call each) or report abstention accuracy on dev+test pooled and
  say so.
- 2026-08-22 — RESOLVED CONTRADICTION: the plan assigns rungs 3 and 4 to A in
  §8 steps 5-6, and `r3.py`/`r4.py` to B in §8.2's ownership table. Followed
  §8.2, whose rationale is coherent (A = everything deterministic, no model
  calls; B = everything that talks to a model). A owns ledger, registry, schema,
  corpus, r1, r2, run.py; B owns score.py, r0, r3, r4, r5, prompts.
- 2026-08-22 — DECISION: `run.py` reports a missing rung rather than faking it.
  Half a ladder honestly labelled is a result; a ladder with a silently absent
  rung is not. The scorer is injected the same way (`--scorer module:function`,
  defaulting to `ladder.score` when B ships it), so accuracy columns are written
  empty rather than guessed.
- 2026-08-22 — DECISION: rung 2 abstention preserves the withdrawn answer in
  `checks["withheld"]` rather than deleting it. Safety constraint 5 — the
  system surfaces candidates for a human and has no authority to rule anything
  out — has to be true in the data structure, not just in the README.
- 2026-08-22 — DECISION: `CONCEPT_LESS` is an answer, never an abstention.
  Folding it into abstention would make the system look cautious where it was
  actually right, and would destroy the only clean abstention target the corpus
  offers.
- 2026-08-22 — DECISION: corpus and SNOMED release are gitignored, and
  `data/splits/*.json` stores document IDs only — no post text, no annotations.
  The CSIRO Data Licence is non-commercial and non-transferable, so the corpus
  cannot appear in the repo, in a release asset, or in a notebook output cell.

### Two changes asked for on 2026-08-22, after the first pass

- 2026-08-22 — CHANGE (requested): **rung 1 no longer filters.** It judges, and
  the verdict is recorded, counted and reported; the record's zone is untouched.
  `manifest.rungs.1.mode` = `"observe"` (new default) or `"gate"` (the plan's
  flow). Reason, and it is a good one: a filtering rung 1 confounds every rung
  above it. If rung 1 removes the records it dislikes, rung 4's judge is graded
  on a set rung 1 pre-cleaned, and the marginal contribution of rung 4 stops
  being attributable to rung 4. Observational rung 1 makes every rung a
  single-rung ablation on identical input.
  Mechanics: `Record.checks["r1_verdict"]` / `["r1_reason"]` carry the judgement,
  a `verdict` column was appended to the ledger, and reporting reads verdicts for
  rung 1 and zones for every other rung. Rung 2 — which runs last — reads the
  verdict rather than the zone, so **observe mode defers rung 1's coverage cost
  to rung 2 rather than cancelling it**; a test asserts both modes reach the same
  end state. Owner B's rung 3 fires on `checks["r1_verdict"] == "REJECT"`, which
  is now available in either mode.
- 2026-08-22 — CHANGE (requested): **MedDRA is wired in** — `MeddraTable`, a
  sixth rung-1 check, a `meddra_check` setting, fixture cases and a probe class.
  The leaked columns (`occurrences`, `posts`, `example_mentions`) were removed
  from `data/meddra_codes.csv`, which is what prompted this.
- 2026-08-22 — MEASURED, and the reason `meddra_check` defaults to `"flag"`
  rather than `"reject"`: removing those columns removes the *evidence* of
  derivation, not the derivation. The table is **666 codes, all 666 of which
  appear in CADEC's gold annotations and none of which do not** — the answer
  key's code inventory, about 3% of MedDRA's preferred terms. Two consequences,
  both now measured rather than argued:
    * On gold it looks harmless: `meddra_check="reject"` costs only 3 false
      rejections in 9,111. It looks harmless *because* the table is the gold.
    * On planted errors it looks miraculous: a hallucinated MedDRA code is caught
      **1.000** of the time with `"reject"` versus 0.002 with `"flag"`. Perfect
      detection by construction — anything outside the 666 is rejected — and it
      says nothing about whether a real MedDRA check would work.
  So the verdict is recorded and counted in rung 1's comparison, and is not a
  rejection reason. One manifest line switches it, and `MeddraTable.leakage()`
  prints the caveat wherever the number appears. A subscription MedDRA release
  makes all of this moot: point `vocabulary.meddra_csv` at one and `"reject"`
  becomes honest.
- 2026-08-22 — BUG found while adding the verdict column: `Ledger.zone_counts()`
  ignored its `rung` argument and counted every row in the run. It was only used
  in the fixture, where every row happened to be rung 1, so it had never been
  wrong yet. Now scoped, with a test.

### Merging the GitLab scaffolding repo — 2026-08-22

- 2026-08-22 — MERGED `git@gitlab.com:pushpdeep/ai-reliability-ladder.git`
  (`partner/main`, unrelated histories). It is a scaffolding overlay, not a
  competing fork: only three paths overlapped, and its README already describes
  this repo's `bench/ app/ schemas/ data/ docs/ tests/` layout. Brought in
  `scripts/preflight.py` + GitLab CI, `LICENSE`, pinned `requirements.txt`,
  `SETUP.md`, `CLAUDE.md`, `docs/plan.html` (v17), `manifest.template.json`,
  `ladder/vocab.py`, `ladder/rung0_ab.py`, `data/meddra_codes.example.csv`.
- 2026-08-22 — BUG FOUND IN THE MERGED `.gitignore`, and it was licence-critical:
  git only treats `#` as a comment at the START of a line, so
  `data/*_v1.json   # built datasets embed document text` is a pattern that
  matches nothing. Three lines were inert for that reason — `data/*_v1.json`
  (a built CADEC dataset embeds post text and would NOT have been ignored),
  `!data/sroie_v1.json`, and `*.ipynb`. All comments now sit on their own line
  and the patterns are asserted against real paths.
- 2026-08-22 — PREFLIGHT EARNED ITS PLACE ON ITS FIRST RUN: it flagged a
  ~30-word CADEC quotation in `ladder/fixture.py`'s docstring. A code comment is
  a committed file. Trimmed to the one clause the plan itself uses as its
  worked example.
- 2026-08-22 — v17 SUPERSEDES v16 ON LAYOUT. v16 §8.1 specifies a separate
  `ladder/` package, which is what this branch built. v17 §2 folds CADEC into
  the existing `bench/` as `bench/adapters/cadec.py` + `ladder/vocab.py` as a
  global resource, and adds a `resources` hook to the runner contract as "the
  one extension CADEC needs". Both now exist in the tree. Not reconciled
  unilaterally — see the open question at the end of this section.

#### THE INTEGRATION FINDING: the two vocabulary backends disagree on 24% of gold

`ladder/vocab.py` (EBI OLS4 over the network) and `ladder/registry.py` (a local
SNOMED CT RF2 release) answer the same three rung-1 questions and are
interchangeable in principle. They are not in practice.

Measured over all 8,666 CADEC gold mentions that carry an SCT code
(`python -m ladder.vocab_crosscheck --live 40`):

    6,593  76.1%  active international — both backends agree
    1,420  16.4%  active, but AU-extension module only — invisible to OLS4
      648   7.5%  retired — OLS4 indexes active concepts only
        5   0.1%  absent from both

**An OLS4-backed `exists()` reports 23.9% of the gold standard as codes that do
not exist.** The local RF2 index reports 5. Split by entity type: reactions
5.9% affected, drugs **100.0%** — because CADEC codes drugs to AMT, the
Australian Medicines Terminology, which is an extension module that the
international release OLS4 serves does not contain at all.

This is a property of the SOURCE, not a bug in either implementation, and it
cannot be patched: OLS4 cannot serve AMT. The offline classifier predicted
OLS4's answer correctly on 40/40 sampled codes, so the 23.9% is not an estimate.

Consequences, in order of importance:

1. A rung 1 built on OLS4 would report a ~24% rejection rate on a *perfect*
   answer set. That is the same failure this branch spent the day removing
   (9.3% → 0.13%), arriving from a different direction.
2. **Any drug-code check needs the AU release.** There is no configuration of
   OLS4 that can validate an AMT code.
3. Retired concepts are the recurring theme: OLS4 drops them, and a naive
   active-only hierarchy walk cannot place them. Both cost ~7% of gold.

Not resolved here, because `ladder/vocab.py` is not this owner's file. The
measurement is a runnable script rather than an assertion so it can be checked
rather than argued.

#### Open question for the joint block

Two implementations of rung 1 and of the vocabulary now sit in the tree:
`ladder/` (this branch, local RF2, measured) and `ladder/vocab.py` +
`ladder/rung0_ab.py` (the scaffolding, OLS4). v17's layout says the CADEC track
should live in `bench/` as an adapter. Reconciling them is a joint decision, not
a merge conflict — deliberately left for one.

### Unifying the two implementations — 2026-08-22

Decision: unify the vocabulary **backend** now; leave the v17 §2 package move
(`ladder/` → `bench/adapters/cadec.py`) for a joint block. The duplication that
actually hurts is two implementations answering the same question differently —
that is a correctness hazard, and it is small and testable to fix. The package
move is ~2,000 lines across ownership boundaries and would collide with whatever
owner B is writing in `bench/rungs/` right now. Unifying first also makes that
move easier: one vocabulary module to relocate instead of two to merge.

- 2026-08-22 — NEW CONTRACT: `schemas/vocabulary.py`, the `Vocabulary` protocol.
  v17 §4 calls this "the one extension CADEC needs" — SNOMED and MedDRA are
  global resources injected once per run, not per-item `trusted_record` fields.
  Two backends implement it: `ladder.registry.Registry` (local RF2, `lossy =
  False`) and `ladder.vocab.Ols4Vocabulary` (the network path, `lossy = True`).
  `ladder.vocab.select()` picks the local one when an index exists and warns
  loudly when it falls back, quoting the 23.9%. Every backend declares `name`,
  `release` and `lossy`, and the manifest records which one produced a number.
- 2026-08-22 — `ladder/vocab.py`'s public functions are unchanged in signature
  and now delegate to the selected backend, so `rung0_ab.py` and the CI smoke
  test keep working — and start getting the non-lossy answer. Caught mid-change:
  the first version rewired only `negated`/`grounded` and left `exists()` bound
  to the raw OLS4 call, so selecting the local backend silently did nothing for
  the checks that matter. The OLS4 transport functions are now `_ols_*` and only
  `Ols4Vocabulary` calls them.
- 2026-08-22 — MEASURED, and the reason the vocabulary-free checks unified too:
  the exact-substring span check false-rejects **725 of 9,111 gold mentions
  (8.0%)**, because 1,066 are discontinuous and a single (start, end) pair
  cannot express one. `Record.valid()`'s token-bag comparison false-rejects 4
  (0.04%). Same for negation — the character-window version has no notion of a
  cue inside the mention ("no energy" IS the symptom) or of a terminator ("but").
  Both now delegate; `ladder.vocab.negated`'s `window` is tokens, not characters.
- 2026-08-22 — ONE MedDRA CLASS. It had been written twice, here and in the
  scaffolding, with the same leakage analysis reached independently.
  `MeddraTable` survives because it also has `leakage()`, which turns the
  analysis into a number. It absorbs the scaffolding's sharper half — `mode`:
  `"reference"` (cross-check only; `search()` raises) vs `"answer_space"` (the
  task IS closed-set assignment over the list, which is a different and much
  easier task and must be declared). `ladder.vocab.MedDRA` is an alias.
  `agrees_with_sct()` is the one MedDRA use that carries no leakage at all,
  because it compares two predictions rather than a prediction against the key.
- 2026-08-22 — DELETED, as unused: `ladder/rungs/base.py` (its `Rung` protocol
  moved to `schemas/runner.py`, where v17 §4 says the runner contract lives, and
  its no-op rung advertised a `--rungs noop` flag that was never implemented);
  `manifest.template.json` (superseded by the committed `manifest.json`, and
  drifted out of sync with it); `Ledger.SCHEMA_VERSION`; `registry.SNOMED_ROOT`;
  `manifest.save_manifest`; `corpus.reaction_records` / `drug_records`;
  `vocabulary.FINDING_STATUS`; `vocab.NEG_CUES` (dead once `negated` delegated);
  `streamlit_app.RUNG_LABELS` and the import it alone needed; and four unused
  imports across `bench/`. Repo is pyflakes-clean.
- 2026-08-22 — KEPT AND MADE LOAD-BEARING instead of deleted:
  `schema.VERDICTS` and `schema.REJECT_REASONS` were enumerations nothing read.
  Rung 1 now asserts against them, so adding a reason without declaring it in
  the contract fails in the fixture gate rather than quietly in a results table.

### Retiring the SROIE track — 2026-08-22

- 2026-08-22 — MEASURED FIRST, THEN DELETED. An import-reachability scan from
  each track's entry points found **zero shared modules**: eighteen pre-v16
  modules were reachable only from the SROIE/app entry points, and the CADEC
  track imported not one line of them. The two tracks were not coupled; they were
  co-located.
- 2026-08-22 — DECISION: retire the SROIE track. CADEC is the study. Deleted
  `app/` (streamlit dashboard + review queue), `bench/pipeline.py` (a SECOND,
  field-shaped ladder), `metrics.py`, `harness.py`, `cli.py`, `normalize.py`,
  `flatten.py`, `prompts.py`, `parse.py`, `outputs.py`, `calibration.py`,
  `diagnostics.py`, `adapters/` (sroie + user_upload), `schemas/adapter.py`,
  `schemas/results.schema.json`, `data/sroie_v1.json`, `data/example_upload.json`,
  `spec.md`, `docs/data-format.md`, `.claude/launch.json`, `docs/article-outline.md`
  and nine test files. ~4,000 lines of code plus its results.
- 2026-08-22 — WHAT WAS DELIBERATELY KEPT: `ladder/llm.py` and `models.yaml` —
  the disk-cached model client is not task-specific and is what owner B's rungs
  0/3/4/5 will call. Plan v17 §3.1 is right that the cache is architectural, not
  a convenience.
- 2026-08-22 — **AND THE RESULTS WENT TOO.** Retiring the track but keeping its
  numbers would have left the article quoting figures from a pipeline no longer
  in the repo and no longer runnable — a claim nobody could check. So the earlier
  track's measurements are deleted from this log, from the article notes and from
  the README. The code and its numbers remain in git history at `e938f8d` for
  anyone who wants them; nothing forward of this point cites them, and the
  article stands on the CADEC measurements alone.
- 2026-08-22 — CONSEQUENCE, then cleanup: with SROIE gone, `bench/` held four
  files that were all CADEC. Consolidated into `ladder/` and deleted `bench/`.
  `bench/vocab.py` → `ladder/vocab.py`, `llm.py` → `ladder/llm.py`,
  `ladder_ab.py` → `ladder/rung0_ab.py`.
- 2026-08-22 — `schemas/runner.py` stripped to the `Rung` protocol. Its
  field-level `Runner` / `FieldResult` / `Cost` / `RunnerOutput` shape existed
  only for the retired track. `schemas/results.schema.json` deleted outright: it
  described a field-level `results.json` for a dashboard that no longer exists,
  and nothing read or wrote it. The CADEC track's output contract is the
  `results.csv` column list in `run.py`, which plan §8 step 7 specifies.
- 2026-08-22 — THE LAST DUPLICATE RUNG 1 IS GONE. `rung0_ab.py` carried its own
  `Rec` dataclass, its own `rung1()` and its own `REASONS` list, all predating
  the measurements — and that rung 1 reproduced three faults the measured one had
  already fixed: it rejected on negation (427 gold mentions), it rejected any
  code the active hierarchy could not place (every retired concept, 413 more),
  and it had two outcomes so it could not express BAND. It now uses
  `schema.Record`, calls `r1.apply`, and reports with `schema.REJECT_REASONS`.
  What it uniquely owns — the rung-0 A/B harness and the `honoured_tool` check —
  is kept, which is what the file is actually for.
- 2026-08-22 — Dependency footprint went from streamlit + plotly + pandas +
  jsonschema + pyyaml to **pyyaml**. Nothing in the measurement path needed the
  rest; they were the deleted dashboard's.
- 2026-08-22 — `scripts/preflight.py` checked for `app/results.reference.json`.
  With the app gone that warning was meaningless, so it now checks the two things
  that actually make a result reproducible: `manifest.json` and the frozen
  `data/splits/test.json`.

### The plan now matches the code — 2026-08-22

`docs/plan.html` and `CLAUDE.md` still described the pre-measurement design, and
`CLAUDE.md` listed the rung-1 two-outcome design under "do not silently reverse
these" — which this branch had reversed, with evidence, but only in this file.
Six claims in the plan now carry a MEASURED note pointing here: the mention count
(6,754 → 9,111), "no drug codes to score" (1,657 of 1,800 are coded), the
negation box (costs 427 gold-correct mentions as a rejection), the gold rule
(undefined for 2.8%), BioPortal as the vocabulary (and the 23.9% backend gap),
and rung 1's two outcomes (three, and it no longer routes). `CLAUDE.md`'s
decision list records each reversal with its measurement.

A plan that contradicts the code is a bug in the plan. Correcting it in place —
rather than only in a log — is what stops the next person rebuilding the thing
that was already measured and rejected.

### `--live` was never live — 2026-08-22

`vocab_crosscheck.live()` called the module-level `ols.exists()`, which delegates
to the SELECTED backend. Whenever `snomed.sqlite` exists — that is, on any
machine that can run the crosscheck at all — `select()` returns the local
Registry, so `--live` compared the local backend against itself: it agreed 40/40
and reported the offline prediction as wrong on 12. No HTTP was made; the
`cache/vocab` directory the transport writes to did not exist afterwards.

The failure mode is the dangerous one: it produced a REASSURING wrong answer. It
said the two backends were interchangeable, which is the exact claim this module
exists to refute. Fixed by instantiating `Ols4Vocabulary()` explicitly. Against
the real service the numbers invert — backends agree 28/40, the offline
prediction is right 40/40 — and all 12 disagreements are retired or
AU-extension codes, the two classes the offline mode predicts and nothing else.

A public delegating function and a backend-specific one that share a name is the
trap. `ladder/vocab.py`'s own docstring warns about it in the other direction
("calling these directly gets you the lossy answer"); this was the same hazard
mirrored.

### `run.py ablate` now exists — 2026-08-22

`run.py`'s docstring had advertised `python -m ladder.run ablate` since the
scaffolding merge; the subcommand was never registered, so it exited 2 on an
argparse error. Implemented rather than deleted, because the single-rung
ablation is what the README's "each rung stays a single-rung ablation on
identical input" actually requires: `ladder` measures a stack, where rung 4's
row is rung 4 applied to whatever rungs 1, 3 and 5 already did, while `ablate`
holds the input fixed and varies one rung. Each rung gets `[r.copy() for r in
base]`; rung 0 is not ablatable (it MAKES the records) so it is the `input` row;
marginal-cost columns stay empty because "marginal" is only meaningful
cumulatively. Both commands build rows through one extracted `snapshot_row()`,
so there is still exactly one accounting path over the ledger.

First thing it showed: rung 2 ALONE abstains nothing (coverage 1.000, all 393
still NEW), against 222 abstentions in the stacked run. Rung 2 reads
`checks["r1_verdict"]` and tau is 0.0, so with no rung 1 upstream it has nothing
to withdraw on. True, correct, and invisible in the stacked view — which is the
argument for having the command.

### Verification sweep over owner A's half — 2026-08-22

Every command owner A has shipped was run end to end against the licensed
corpus and a real SNOMED AU index, and all four measured claims in `README.md`
reproduce exactly: the false-rejection floor (12 / 9,111 = 0.13%), zone
occupancy on gold (ACCEPT 3,926 = 43.1%, BAND 5,173 = 56.8%, REJECT 12 =
0.13%), detection of hallucinated codes, span shifts and fabricated quotes
(1.000 each), and the lenient-vs-strict near-miss gap (0.18979 wrongly
ACCEPTED under `contained`, 0.0012 under `exact`).

Paths that had never executed before, and now have:

- `--predictions`. 393 synthetic rung-0 records with 49 planted corruptions
  came back as 30 `code_unknown` + 19 `span_ungrounded` — the 49, and nothing
  else. Blank `record_id`s were backfilled. This is the first non-zero rung 1
  rejection through `run.py`; the gold control cannot produce one.
- The split-discipline guard in `read_predictions`, which refuses a file
  carrying a POOL document and exits 1.
- `--scorer` injection, and with it the accuracy and marginal-cost columns.
- `rungs.1.mode = "gate"`. Rung 1 routes (coverage 0.875 at rung 1) and the
  FINAL coverage is identical to observe mode's, which is the design claim
  made concrete: observe defers rung 1's cost to rung 2, it does not cancel it.
- `registry --build` into a scratch DB: 8.5s, and stats and spot-check lookups
  are identical to the committed index. The build is reproducible.
- `preflight --history`: a real scan, 41 commits and 94 distinct paths.

`rung_order` cannot yet be ablated — `[0,1,2,3,5,4,6]` and `[0,1,3,5,4,2,6]`
both collapse to `[1,2]` while rungs 3-6 are missing, so the two orders produce
identical output. It becomes a real experiment when owner B lands.

### `vocabulary.snomed_backend` is inert — 2026-08-22

The manifest declares the backend and carries a long note on why the two are
not interchangeable, and `ablations` lists an `ols4` run. The key is read by
NOTHING: it appears in zero Python files, and all eight `Registry(...)`
construction sites take `vocabulary.snomed_db` directly.

No number published so far is wrong — the field happens to describe what
actually runs. The hazard is forward-looking, and it is the shape of failure
this repo keeps finding: set it to `"ols4"` and the run silently keeps using
the local index while the run's own output manifest labels it `ols4`. Against
`CLAUDE.md`'s rule that a rung 1 rejection rate must never be reported without
naming the backend that produced it, a backend field that looks honoured and
is not is worse than no field. Same class as the `--live` bug fixed today.

Not wired in this pass: it needs `Ols4Vocabulary` checked against everything
rung 1 calls, not merely against the `Vocabulary` contract, and it changes what
a manifest key MEANS — which is a joint decision, per this file's own rule.

## 2026-08-22 — independent reproduction, second machine

First run of the pipeline outside A's machine. New SNOMED CT-AU build, freshly
extracted corpus, `data/` populated from scratch. Everything below is measured
locally and reproducible with the commands recorded beside each figure.

### Provenance corrected

- **Corpus is CADEC v2, not v3.** The DAP collection `csiro:10948` is at edition
  v3, and the collection's own `collection_import_sha256sum.txt` lists exactly
  two files: `CADEC.v1.zip` and `CADEC.v2.zip`. There is no v3 corpus. The
  manifest pinned the collection edition as if it were the corpus version.
  Now recorded as both, distinguished. Checksums committed to
  `docs/cadec-checksums.txt`.
- **Working copy verified byte-identical to the archive.** `diff -rq` against a
  clean extraction of `CADEC.v2.zip`: zero differences. Six `.ann` files differ
  between v1 and v2 — that is the corpus revision, not local edits. Example,
  `LIPITOR.320`: `T1 ADR 0 17 cognitive ability` became
  `T1 ADR 0 28 cognitive ability deminished`. v1 truncated the span before the
  word that makes the mention a reaction.
- **`cadec_root` path was wrong** in the manifest and is corrected.
- **`.gitignore` enumerated spellings of the corpus path**, so any unanticipated
  extraction layout was a hole. `unzip -d data/` created `data/data/` holding
  both corpus zips, untracked and unignored. Replaced with `data/*` plus an
  explicit exception for `data/splits/`.

### Reproduced exactly

| Figure | Documented | Measured here |
|---|---|---|
| Zone occupancy on gold | 3,926 / 5,173 / 12 | **identical** |
| | 43.1% / 56.8% / 0.13% | **identical** |
| CADEC codes inactive in the release | 115 | **115** |

### Reproduced with a discrepancy

Active codes measured 928 against a documented 927; distinct codes 1,047 against
1,046. The two move together, so one distinct code separates the counts.
`any_of` occurs exactly 3 times in gold; if only the first alternative was
counted previously, and one alternative is otherwise unique, that produces
precisely this difference. **Open.**

### Gold defect, identified with evidence

`data/cadec/sct/LIPITOR.511.ann` line 3:

    TT3   67849003 | Excruciating pain | + 20070731 | pain in lower limb |   38 66   excruciating pain in my legs

`20070731` is a date, not an SCTID, and is not a well-formed identifier. The
term beside it is a real concept, so a code was dropped and a release date left
in its place. Survived the v1→v2 revision. The parser reads it faithfully — this
is a corpus defect, not a parsing bug. Genuine absent codes: **3, not 4.**
Handling: a documented gold-defect list, never a silent filter.

### FINDING — pooled ratios across drugs and reactions describe neither

Drugs are span-checked only, never code-scored: CADEC codes them to AMT. But
every headline ratio pools drugs and reactions into one denominator. Split:

| Pooled figure | Drugs | Reactions |
|---|---|---|
| 11% of CADEC codes inactive | 46.8% (58/124) | **6.2%** (57/923) |
| 23.9% backend disagreement | ~100% | **5.9%** |
| 43.1% ACCEPT on gold | 76.0% | **35.0%** |

Same cause each time. Drug names appear in patient text as printed, so they
match lexically; reactions are written in the reporter's own words. Any
denominator containing both is a drug-weighted average reported as if it
described the surface the pipeline grades.

**The headline claim changes.** Deterministic checking confirms 43% of a perfect
answer set pooled — but **35% on reactions**. The pooled figure understates the
problem by 8 points.

Caution: drug BAND occupancy is 23.9%, numerically identical to the backend
disagreement figure and completely unrelated. Reword one if both appear.

### FINDING — check order determines the reason table

`r1.zone()` returns on first failure. Correct for a verdict; wrong for a reason
table. First model output ever produced (granite4:micro-h, 2 dev docs, mode A):

    verdict reasons: span_ungrounded 6 (100%)
    full audit set : span_ungrounded 6, code_unknown 6

100% of the code failures were invisible. The model fabricated every code it
emitted — 3/3 distinct codes absent from a ~400k-concept release — and the
harness reported a span problem.

**The bias is latent on gold and only appears on model output.** Measured: on
all 9,111 gold mentions the verdict reason set and the full audit set are
identical, because gold spans ground by construction. It is invisible in exactly
the regime the validator was tuned in.

Fix: `zone()` unchanged — its ordered short-circuit is correct and its numbers
are measured. Added `all_reasons()`, a parallel pass running every check
unconditionally into `checks["r1_audit"]`. 93 tests still pass; no measured
figure moved.

### FINDING — missing vocabulary degrades silently to BAND

`zone()` returns `ZONE_BAND` when `vocab is None`. No warning. A run configured
without a registry produces plausible verdicts for every record. Nothing above
rung 1 can distinguish "plausible but unverifiable" from "never checked" — they
are the same value. Should be a hard failure. **Open.**

### First model run — granite4:micro-h, mode A, 2 dev docs

| | Result |
|---|---|
| JSON parsed | 2/2 |
| Span text verbatim in post | 6/6 |
| Character offsets correct | **0/6** |
| Codes existing in SNOMED | **0/3 distinct** |

The model finds reactions correctly and invents both mechanically checkable
fields. Offsets are wrong but recoverable by string search — every span text was
present in the source. Whether rung 0 should compute offsets deterministically
instead of asking for them is a manifest flag with both arms measured, not a
silent fix: it changes what rung 0 means.

Sample size is 2 documents. Nothing here is a claim about the model.

### Aligner

`concept_less` is a real `gold_kind`, 445 mentions (4.9%) — 302 reaction, 143
drug. Findable but not gradable. A single F1 must either drop them, handing the
model a lane where wrong codes cost nothing, or grade them, penalising it for an
answer that does not exist.

Split into two scorings, never fused, on the same principle as the cost triple:
`span_*` over every gold, `code_*` over gradable golds only.

Also fixed: sub-threshold cells were left in the cost matrix, so the assignment
could be steered by pairs the threshold then discarded. Now zeroed before
matching. The scipy fallback silently downgraded bipartite matching to greedy;
the matcher is now reported in every result.
## 2026-08-22 — rung 0 A/B on the dev split (40 docs), granite4:micro-h

Offsets recovered by search in both arms so span grounding does not mask the
code check. Reactions only; drugs are span-checked, never code-scored.

| | A — recall only | B — tool prompt |
|---|---|---|
| mentions emitted | 176 | 159 |
| rejected by rung 1 | 176 (100%) | 92 (58%) |
| accept / band | 0 / 0 | 0 / 67 |
| **code correct** | **0 / 107** | **0 / 96** |
| null codes emitted | 0 | 59 |
| span precision / recall | 0.679 / 0.459 | 0.645 / 0.410 |
| tokens | 19,701 | 20,431 |
| wall clock | 276s | 2,410s |
| JSON parse failures | 0 | 2 |
| overrode its own lookup | — | 29 / 29 |

### The rejection rate is not the result

B's rejection rate halves. Its code accuracy does not move: zero in both arms,
across 203 graded mentions. The entire difference is 59 null codes — B declines
a third of the time, and a record with no code cannot be rejected for a bad one,
so it lands in BAND. Those 67 BAND records are abstentions, not successes.

**The tool prompt bought abstention, not accuracy**, at 8.7x the latency and
slightly worse span recall. This is the failure mode `compare()` was written to
catch: the errors moved rather than disappeared. Reading the rejection rate
alone would have reported tool access as a 42-point improvement.

### The tool was never called

`honoured_tool` is never True: 130 None, 29 False. `vocab.search` runs AFTER
generation, so the tool block is prompt text and nothing more. Where a search
did return candidates, the model overrode its own lookup 29 times out of 29.

So the A/B contrast measures PROMPT WORDING, not tool access. The docstring at
rung0_ab.py:113 says "the model searched, got candidates back" — it did not.
Either build a real tool loop or rename the ablation. Do not publish the current
framing.

### The model cannot code, in either arm

0 correct out of 203 graded mentions. Not poor — categorically incapable. It
locates reactions at F1 0.548 and never once produces the right SNOMED code.
164 of 176 codes in mode A do not exist at all, so it cannot be right by
accident.

Extraction and normalisation are different capabilities. A single accuracy
number over both would report roughly half the task working as one middling
score, and would hide that the half a vocabulary lookup solves is at zero. Same
pooling error as drugs/reactions, one level up.

Scope: one model, one size, 40 dev documents, greedy decoding. This says nothing
about what LLMs can do; it says what the harness can now distinguish.

### An HTML wiki, and why not plan.html — 2026-08-22

`docs/wiki/` — 23 cross-linked pages generated by a stdlib-only `build.py`.
Home, Getting Started, Architecture, Contributing, Glossary, Troubleshooting,
one page per rung, and nine reference pages.

Not folded into `docs/plan.html`, and not a wholesale publish of `docs/`.

The plan is an ARGUMENT: public, article-facing, comparatively stable. The wiki
describes CODE, and changes whenever the code does. Merging them grows the
public plan an implementation appendix that goes stale, and buries the thing you
would hand a new contributor inside a 166 KB file.

The wholesale publish is worse, and the reason is the licence. GitLab Pages is
public and the docs are not uniformly publishable: `article-iterations.md` and
`decisions.md` each carry the "so far no gastric problems" fragment, and
`article-build-log.html` two more. The pages job copies ONE named file. Widening
it to a glob would convert a curation decision into an accident, and publish the
raw build log with the corpus fragments in it. Whitelist by name, always.

Every wiki example is SYNTHETIC for the same reason — a 42-character invented
post carries the rung 1 walkthrough that `ARTHROTEC.101` carried in conversation.
Verified: the synthetic offsets are real and rung 1 returns the documented
ACCEPT/BAND on them. Note preflight would NOT have caught the real post: its
CORPUS_TELLS are four narrow regexes and the ARTHROTEC.101 text trips none of
them. Preflight is a backstop, not the definition of the rule.

`PAGES` in `build.py` is the single source of navigation — sidebar, Home index
and link checker all read it. `--check` fails on a broken link AND on any page
nothing links to, so a page cannot rot quietly while the code moves under it;
it is wired into CI as its own `check`-stage job, stdlib-only and not
`allow_failure`. Generated `site/` is gitignored: committed build output is
exactly the stale-data problem the wiki exists to avoid.

`docs/rung1.md`, written an hour earlier, was deleted rather than left beside
`docs/wiki/content/r1.md`. Two copies of one explanation is the failure mode,
not the deliverable.

### Ownership, measured rather than asserted — 2026-08-22

The wiki now names the owners — owner A is Wejdan Bagais, owner B is Pushpdeep
Mishra — and `docs/wiki/content/authorship.md` records who has written what,
taken from `git blame` and `git shortlog` rather than from the plan.

The two disagree, in both directions.

The plan assigns owner B rungs 0, 3, 4, 5 and `ladder/score.py`. None of those
files exist. What owner B has actually written is the licence and CI boundary
plus the model client: `scripts/preflight.py` (147 of 155 surviving lines),
`.gitlab-ci.yml` (97 of 112), `ladder/stub_llm.py` (all 123), and substantial
edits into two of owner A's files — `ladder/vocab.py` (136 lines) and
`ladder/rungs/r1.py` (91). And owner A wrote `ladder/rung0_ab.py`, 230 of 288
lines and the file's creation, which the plan lists under rung 0 as B's.

Owner A built the ladder; owner B built the guard rails around it and the client
that will drive rung 0. The plan's division of the RUNGS has not been exercised
yet, because rungs 3-5 are unwritten. Both statements are descriptions, not
criticisms: the plan is forward-looking and blame is backward-looking.

Recorded because the plan's owner labels are load-bearing in a paper about who
built what, and a reader who takes them at face value would attribute preflight
and the CI licence gate to the wrong person.

One caveat kept with the numbers: 22 of 52 commits carry a
`Co-Authored-By: Claude` trailer, all authored under Wejdan's git identity, so
blame attributes those lines to Wejdan. The authorship page says so rather than
presenting the column as hand-typed lines.

## 2026-08-23 — GPU re-measurement, and rungs 0–3 end to end

Everything measured on 2026-08-22 was produced on CPU inference: the NVIDIA
driver was absent, Ollama reported "100% GPU" from its own placement estimate
rather than from the device, and generation ran at 4.4 tok/s under contention
from a video call. With the driver installed, the same model runs at 62 tok/s
and holds 2,169 MiB of VRAM.

### Determinism is bounded by the hardware

Same model, same 40 documents, `temperature=0, seed=0`, greedy:

| | CPU | GPU |
|---|---|---|
| mentions emitted | 176 | **169** |
| tokens | 19,701 | 19,354 |

Three consecutive GPU runs are byte-identical (169 mentions, 19,354 tokens), so
determinism holds WITHIN a backend and not ACROSS one. A run must record its
compute backend the same way it records the SNOMED release; two people following
identical instructions on different hardware get different numbers and neither
is wrong.

That is version-dependence at a third level, alongside the vocabulary release
(927 vs 928 active codes) and the corpus version (v1 vs v2 span boundaries).

**Every CPU-era figure below 2026-08-23 is superseded.** They describe 176
mentions that no longer exist.

### Rungs 0–3, one run, mode A, dev split

Rung 0 ran once; the scorer and rung 3 consumed the same records.

| | |
|---|---|
| mentions emitted | 169 |
| rejected by rung 1 | 166 (98%) |
| span precision / recall / F1 | 0.683 / 0.451 / **0.543** |
| **code accuracy** | **0 / 105** |
| rung 3 offered | 158 |
| rung 3 rescued | **0** |
| rung 3 declined | **158 (100%)** |
| code accuracy after rung 3 | **0 / 105 — unchanged** |
| rung 0 cost | 19,354 tokens, p95 7.5s |
| rung 3 cost | 72,539 tokens, 254s |

### Rung 3 has a measurable price and a measured benefit of zero

Self-correction spent 3.7x rung 0's entire token budget and moved code accuracy
by exactly zero records. 158 of 158 declined: told a code does not exist, the
model never proposes another. Not one `still_failing`, not one `unchanged` — the
refusal is total and uniform.

That is a capability boundary drawn precisely rather than a negative result. The
model locates reactions at F1 0.543 and has no SNOMED knowledge at all, and it
behaves as if it knows that: it declines rather than re-guesses.

Note what a naive report would have said. Rung 3 makes rung 1's rejection rate
collapse if declines are allowed to null the code — which is why rung 3 does not
have that authority. It records `checks["r3_declined"]` and leaves the record
intact; rung 2 owns abstention. An earlier draft of rung 3 counted `withdrew` as
an outcome while never actually clearing `rec.sct`, so the report and the records
disagreed. Found by printing before/after on two documents.

### Extraction and normalisation are different capabilities

F1 0.543 at finding reactions. 0.000 at coding them. A single accuracy number
over both would report half a working system as one middling score and hide that
the half a vocabulary lookup solves is at zero.

Same pooling error as drugs/reactions, one level up.

### The BAND zone, demonstrated

Three records — the only ones in the run rung 1 did not reject:

    LIPITOR.401#3   60551006  'loss of balance'
    LIPITOR.935#1   39249009  'constipitation'
    LIPITOR.935#2   39249009  'no control over urination'

All three: code exists, active, is a clinical finding, `lexical_match` False.
Everything rung 1 can check, passed. Gold says all three are wrong.

The third pair is the clearest case in the corpus so far: one code assigned to
both `constipitation` and `no control over urination` in the same document.
Opposite conditions. Rung 1 validates codes in isolation, never against each
other or against what the text means, so it cannot notice.

**A deterministic checker cannot be a scorer.** The 56.8% BAND zone measured on
gold is not a limitation to engineer away — it is the honest size of what codes
alone cannot settle. (`constipitation` is also a patient misspelling, which is
the colloquial-text problem in one word.)

Scope: one model, one size, 40 dev documents, one hardware configuration.

---

## 2026-08-23 — model selection centralised; rung 3 first run through the pipeline

**Rungs must not choose models.** Four rungs each resolving their own model is
four places to change and three to forget, and a rung whose number changes
meaning when someone edits a config is not a measurement. Model resolution now
happens in exactly one place — `ladder.llm.for_rung`, called by `run.py`, which
injects `cfg["llm"]`. A rung only ever sees a plain callable:

    raw, usage = cfg["llm"](prompt, source, mode)

**Bound by ROLE, not by rung number.** `manifest.model` names an `extractor` and
a `judge`; `ROLE_BY_RUNG` maps 0/3/5 to extractor and 4 to judge. Roles because
that is how the plan constrains them: rung 4 must be a different model family or
it shares the extractor's blind spots, while rungs 3 and 5 correct and re-sample
the extractor's own work and are the extractor by definition. A single global
model setting would silently violate the rung 4 rule.

**One transport for local and hosted.** Ollama speaks the OpenAI-compatible
protocol at `/v1`, so `ladder.llm.LLMClient` reaches it and every hosted
provider through the same `chat()`. The separate adapter written earlier the
same day was deleted rather than kept — a second call path is a second set of
numbers. `stub_llm.py` keeps only `load_items`.

**Default is local, and remote is a deliberate act.** `ollama/gpt-oss:20b`.
Rung prompts carry CADEC post text verbatim, and CADEC is non-commercial and
NON-TRANSFERABLE, so any provider with `local: false` puts licensed text on
someone else's machine. `Caller` refuses one unless `LADDER_ALLOW_REMOTE=1`.

**Markdown fences are stripped but counted.** A fence around JSON is a transport
convention, not a modelling failure, and counting it as a parse error would
misattribute formatting as a reliability cost. `Caller.fenced` records it, so
the strip is never silent. Measured: claude-haiku-4-5 fences, granite4 does not.

**Rungs 3, 4 and 5 had never been run through `run.py`.** All three called
`ledger.write()`, which does not exist — the method is `log()` — and all three
omitted the `doc_id` that `log()` requires. Found only by running them; the
test suite is green either way. A rung that imports cleanly and passes its unit
tests can still be unable to run, which is an argument for the end-to-end run
being part of CI rather than a thing someone remembers to do.

**Two return conventions, normalised in the runner rather than legislated.**
r1/r2 return `records`; r3/r4/r5 return `(records, aggregates)`, and owner B's
`scripts/ladder_run.py` unpacks the tuple. Rewriting either owner's rungs to
match the other would have broken the other's runner, so `run_ladder` accepts
both shapes and files the aggregates under `result["aggregates"]`. r3's
annotation said `-> list[Record]` while returning a tuple; the annotation was
the thing that was wrong.

**Rung 4 keeps its own config keys.** It reads `judge_llm` and compares
`judge_model` against `extractor_model`, raising if they match, because a model
judging its own output measures self-consistency rather than correctness. The
runner fills those keys from the same `for_rung` resolution as every other
rung, so the guard is enforced without rung 4 choosing anything. Set for the
first run: extractor `ollama/gpt-oss:20b`, judge `ollama/ibm/granite4:micro-h`
— two different families, both local.

**First 0→5 run, one dev document (ARTHROTEC.107), claude-haiku-4-5, mode A.**
Order `[1,3,5,4,2]`; rungs 5 and 4 reported missing, not faked. R0 emitted 2
mentions, rung 1 rejected both `span_ungrounded`, rung 3 attempted the one
correctable record and returned `still_failing`, rung 2 abstained on both.
Coverage 1.0 → 0.0.

**Rung 0's failures separate cleanly, and only one is about medicine.** On
ARTHROTEC.1, mode A: claude-haiku-4-5 emitted 3 mentions with 2 of 3 codes real
(`271782001` for "drowsy" is gold exactly); granite4:micro-h emitted 2 with 0 of
2 real, and across 10 dev documents 0 of 26 real — codes shaped like SNOMED and
clustered (`41493009`, `41493006`, `41456009`), i.e. confabulated digits. Both
models quote spans verbatim (77% on the 10-doc run) and both get the character
offsets wrong (19% and 0%). Coding ability is a model-capability axis; offset
arithmetic is not — it fails at every size, which is what `rung0_offsets:
"search"` exists to bypass. Every rejection so far reads `span_ungrounded`, so
the code quality underneath is invisible in the verdict; the report's
"hidden by check order" column is the only place it shows.

## 2026-08-23 — one team; rung 0 becomes a rung

**The A/B owner split is retired from the live files.** It did its job — whole
files to one person each, a fixed rung interface between them — and the repo now
has all seven rung slots and no reason to keep the boundary. Removed from the
code, the plan, the wiki and the READMEs. NOT removed from this log, the build
log or the dated handoffs: those are records of what was true when written, and
rewriting them would make the provenance worse, not better. The plan's §5 and
§8.2 are now organised by mental model — the spine, the model surface, the
contracts — because that was always the load-bearing part of the split. Whose
name was on a file was not.

**`rung0_ab.py` is gone; `ladder/rungs/r0.py` holds both the rung and the
ablation.** Rung 0 was the only rung living outside `rungs/`, which is why it
could be measured but not run: `run.py` dispatches on `ladder/rungs/rN.py`, so
rung 0 was permanently "not implemented" while a complete implementation sat one
directory away. `apply()` is the rung entry point and takes an EMPTY record list
— it raises rather than appending if handed a populated one, since rung 0 twice
over a split doubles every mention and every number above it. `run()` /
`compare()` are the ablation, calling the same `rung0()`, so the experiment and
the rung cannot drift apart. Five importers repointed.

**`--limit N` announces itself.** A run on 1 of 40 documents is a different
experiment from a run on dev, so the flag prints the truncation and names the
documents. A smoke number filed as a split number is the easiest lie to tell by
accident.

**First full 0→6 run, entirely local, one dev document (ARTHROTEC.107).** Order
`[0,1,3,5,4,2,6]`; only rung 6 reported missing. Rung 0 emitted 3 mentions, rung
1 rejected all 3 `span_ungrounded`, rungs 3/5/4 moved nothing, rung 2 abstained
on all 3. Coverage 1.0 → 0.0.

**The default extractor could not parse its own output, and the swap is the
finding.** `ollama/gpt-oss:20b` is a reasoning model: on rung 0 it spent the
full 2000-token ceiling on thinking and never closed the JSON, so
`parse_failed=1` and zero records — a ladder that runs perfectly over nothing.
Extractor moved to `ollama/ibm/granite4:micro-h`, which parses, and gpt-oss took
the judge seat, where a short verdict fits the budget. This keeps rung 4's
different-family rule satisfied with two local models and no corpus text
leaving the machine. Worth stating plainly: reasoning models and a strict JSON
contract interact badly, and the failure looks like an empty result rather than
an error.

## 2026-08-23 — offset recovery on; the ladder does real work, and the judge fails interestingly

**`rung0_offsets: "search"` is now the manifest default, and it works.** All
three records on ARTHROTEC.107 came back `search_unique` with correct spans, and
rung 1's rejection reason moved from `span_ungrounded` to `code_unknown`. The
model's character arithmetic is simply discarded: it quotes verbatim, so the
quote is a better key than the offsets it claims. This is the change that let
rungs 3, 4 and 5 see anything at all — before it, every record failed the first
check and nothing above rung 1 had a fact to act on.

**Rung 3 declined all three.** Given "code 41456009 does not exist", the
extractor returned null rather than a replacement. That is `allow_withdrawal`
working as specified and counted apart from a correction — self-correction can
only recover what the model could have got right unaided, and granite could not.

**Rung 4 affirmed a code that does not exist, at 0.95 confidence, with a
fabricated term for it.** Verbatim: *"SNOMED CT 41456009 represents rectal
hemorrhage"*. Rung 1 had already established that 41456009 is not in the
release. The judge is a different model family from the extractor — the plan's
requirement — and it still confabulated a label for a hallucinated code, because
nothing in a judge prompt touches the vocabulary. This is the clearest evidence
yet for the ordering claim: a free deterministic existence check catches what a
paid second model asserts confidently in the opposite direction.

It was not uniformly wrong. On "might not survive" it returned `span_ok: false`
with *"a fear, not an adverse reaction"* — a genuine catch that no deterministic
check could make, and exactly the work rung 4 is for. Two of three agreed with
rung 1; the disagreement was the judge being wrong.

**Rung 5 still cannot vote, and now says so in the ledger.** All three records
came back `not_resampled`: rung 5 matches mentions by `(doc_id, spans)`, and at
temperature 0.7 the three samples find different phrases, so the keys never line
up. Not a bug in rung 5 — a property of voting over an extractor whose spans
move between samples.

**Every rung now reports its own cost.** Rungs 3, 4 and 5 were logging ledger
rows with `tokens=0/0` while making real calls, and rung 5's `not_resampled`
path returned before its ledger write entirely, so a run where nothing matched
reported voting as free. Fixed in all three: the k sampling calls are logged as
a DOCUMENT cost, paid whether or not a record is re-found, and every per-record
row carries the call that produced it. First fully-accounted run: 4148 tokens
over 10 calls across six rungs, $0.00 because everything is local.

**`Caller.sampler(temperature)` — the bug centralisation introduced.** The
shared caller was greedy and never varied `sample_index`, which is part of the
disk-cache key, so rung 5's k votes all hit ONE cache entry: unanimity that was
never measured, in 0.00s, for free. Each draw now gets its own sample index, so
samples differ from each other and stay reproducible across runs. `sampler()`
refuses temperature 0 outright.

## 2026-08-23 — rung IDs renumbered to match execution order

**Decision: rung IDs now equal execution position.** `rung_order` becomes
`[0,1,2,3,4,5,6]`. Previously ID was identity and order was configuration, and
the two differed — the pedagogical numbering put abstention second while the
runtime order ran it last. Having to hold both mappings at once was the cost,
and it was judged to outweigh the benefit.

**THE MAPPING. Every number in this log above this entry uses the OLD IDs.**

| old | new | rung |
|-----|-----|------|
| 0 | 0 | bare LLM |
| 1 | 1 | deterministic |
| **3** | **2** | self-correction |
| **5** | **3** | voting |
| 4 | 4 | LLM judge |
| **2** | **5** | abstention |
| 6 | 6 | human loop |

Read anything dated before 2026-08-23 through that table. "Rung 2 abstained on
all 3" in an earlier entry means what is now rung 5; "rung 3 declined all three"
means what is now rung 2. The measurements themselves are unaffected — only the
labels moved.

**What this costs, recorded so it is not rediscovered as a surprise.** The rung
numbers came from the brief and were shared with anyone else running this
ladder, so results are no longer directly comparable to the brief or to other
groups without applying the table above. And the ordering claim is no longer a
one-line ablation: running abstention early used to be a `rung_order` edit, and
now it means renumbering again. If that ablation is wanted later, it has to be
done by editing `rung_order` away from the identity permutation, which
reintroduces exactly the ID/order gap this change removed — that is the
trade, and it was made deliberately.

**`rung_order` stays in the manifest.** It is now the identity permutation, but
keeping the key means the runner still reads order from configuration rather
than from a sort, so the ablation remains possible even though it is no longer
free.

## 2026-08-23 — cold integration run, all rungs, one document

**First run with the cache cleared, so every call is real.** 31s wall,
10 model calls, 4439 tokens, $0.00 (all local). Order `[0,1,2,3,4,5,6]`,
ARTHROTEC.107, extractor `ollama/ibm/granite4:micro-h`, judge
`ollama/gpt-oss:20b`.

| rung | layer | rows | calls | tok in | tok out | p95 ms |
|------|-------|------|-------|--------|---------|--------|
| 0 | bare LLM | 1 | 1 | 200 | 150 | 3899.7 |
| 1 | deterministic | 3 | 0 | 0 | 0 | 0.4 |
| 2 | self-correct | 3 | 3 | 687 | 107 | 751.0 |
| 3 | voting | 4 | 3 | 600 | 807 | 0.0 |
| 4 | LLM judge | 3 | 3 | 823 | 1065 | 4311.0 |
| 5 | abstention | 3 | 0 | 0 | 0 | 0.0 |

**Latency was missing from rungs 2 and 4 and is now recorded per call.** Both
were writing `latency_ms=0.0` on rows for calls that took seconds — rung 4's
judge is the slowest thing in the ladder at 4.3s p95 and was reporting as free
on one of the three cost measures. Taken from the `seconds` the caller already
returns, per call, never derived from a total.

**Rung 3's p95 reads 0.0 and that is an artefact worth naming.** It writes two
kinds of row: one DOCUMENT row carrying the k sampling calls (9.7s here) and one
row per record. Three of its four rows are per-record `not_resampled` rows with
no call of their own, so a percentile over all four lands on a zero. The rows are
individually right; a single p95 over a rung that bills per document and reports
per record is the wrong summary. Either bill rung 3's latency per document or
report the two row kinds separately — not resolved here, but it must not be read
as "voting is instant".

**Outcomes unchanged from the warm run**, which is itself the result worth
having: clearing the cache reproduced the same verdicts. Rung 1 rejected all
three `code_unknown`, rung 2 declined all three, rung 3 found nothing to vote on
(`not_resampled` ×3), rung 4 returned fail=2 pass=1, rung 5 abstained on all
three. Coverage 1.0 → 0.0.

## 2026-08-23 — merging across the renumber

**A rename plus an edit to the same file is a conflict git cannot resolve by
path, and resolving it by path would have been silently wrong.** Main's
`5258eff` added denominator names and three-valued `evaluable` to
`ladder/rungs/r3.py`, `r4.py` and `r5.py` under the OLD numbering, while this
branch had renamed those files. Git paired them by filename, which would have
merged self-correction's edits into the voting file — a merge that compiles,
passes imports, and is nonsense.

Resolved by identity instead: each of main's files was remapped through the
old→new table FIRST, then three-way merged onto the file that now holds that
rung. `r3(self-correct) → r2`, `r5(voting) → r3`, `r4 → r4`. Voting merged
clean; the other two conflicted only where both sides had added a keyword to the
same `ledger.log(...)` call, and both keywords were wanted.

**This is the renumber's first bill, and it will not be the last.** Any branch
cut before 2026-08-23 that touches a rung file will hit the same thing. The
procedure is written down here rather than rediscovered: remap by identity, then
merge — never merge by path.

Verified on the merged tree: 93 tests, fixture gate passes, and a cold run with
the cache cleared carries both features on the same ledger rows — `denominator`
and `evaluable` from main, `latency_ms` from this branch.

## 2026-08-23 — renumber audit: four classes the first pass missed

Auditing every `rung N` against the label beside it found four kinds of miss.
Recorded because each is a pattern, not a one-off, and the same shapes will
recur in anything else renamed mechanically.

**1 · Word boundaries that are not boundaries.** `\bRUNG 3\b` never matched
`f"\nRUNG 3 — self-correction"`, because in the SOURCE the preceding characters
are a literal backslash and `n` — `n` is a word character, so there is no
boundary before `R`. Two report headers printed the wrong rung until this was
caught.

**2 · Files nobody thought to list.** `ladder/schema.py` and
`docs/wiki/build.py` were not in the first pass. schema.py's zone comments named
rung 2 for abstention; build.py's navigation named every rung page wrongly and
listed them out of order.

**3 · Identifiers vs strings.** `scripts/ladder_run.py` had its label strings
remapped but not its module names, so it passed the VOTING module under the
self-correct label — `call(r3, "r2", ...)`. `scripts/full_run.py` imported `r2`
and called `r3.apply`, a NameError waiting to run. Both would have executed the
wrong rung, or crashed, without any test noticing: no test imports those
scripts.

**4 · Applying the mapping twice.** Re-running the remap over
`ladder/rungs/r2.py` and `r3.py` — already correct — cycled them a second time
and produced "Rung 5 — self-correction" and "Rung 2 — voting". A permutation is
not idempotent, and a rename script that is safe to re-run is a different script
from one that is safe to run once. Recovered from the committed tree rather than
by remapping backwards.

**What the audit could NOT catch, and what did.** The test suite stayed green
through every one of these: 93 tests pass on a tree where `full_run.py` raises
NameError and the wiki names every rung wrong. What caught them was reading each
number against the word next to it. Docstrings, print headers, navigation labels
and script identifiers are not covered by any assertion in this repo.

Verified after: rung docstrings, wiki page titles, wiki navigation, plan.html's
step list and glossary, schema.py's zone comments and both scripts all agree
with the new ids. 93 tests, fixture gate passes, cold run exercises all seven
slots in order.

## 2026-08-23 — the pipeline failure: two faults that arrived from opposite directions

`tests/test_ledger_coverage.py` landed on main in `4142b00` while the renumber
was in flight on a branch. Neither side's tests could see the other, and both
were green in isolation. Two separate faults.

**1 · The test was written against the old ids.** It parametrised over
`["r3","r4","r5"]` — self-correction, judge, voting — and special-cased `r5`
for the per-document sampling rows. After the renumber those ids mean voting,
judge and abstention, so the test asserted document rows on the rung that makes
no model calls at all. Now `["r2","r3","r4"]` with the document-row case on
rung 3.

**2 · It could never have passed in CI, renumber or not.** It needs the
licensed corpus, the SNOMED index and a reachable model. CI has none of the
three. `@pytest.mark.integration` was on it, but no marker was ever registered
and the CI job ran plain `pytest tests/ -q`, so the marker deselected nothing
and pytest only warned. The test then failed on a 404 from a model that was
never going to be there — a red suite that says nothing about the code.

Fixed at both ends, deliberately: the test now checks each prerequisite and
SKIPS with the reason ("no vocabulary index at …"), and `pytest.ini` registers
the marker so the CI job's `-m "not integration"` actually deselects. Belt and
braces, because a suite that goes red for environmental reasons stops being
read, and a marker that deselects nothing is not a guard.

**It also picked its own models.** `S.judge("llama3.2:3b")` hard-coded a model
that is not installed here, and `S.voter(0.7)` bypassed the shared caller. Both
now resolve through `ladder.llm.for_rung` from the manifest, so the test is not
a second place a model is chosen — and rung 3's samples go through
`Caller.sampler`, the same path the runner uses. Where judge and extractor
resolve to the same model the test skips and says why, rather than tripping
rung 4's self-judge guard.

Verified: 100 pass locally with everything present; 96 pass and 4 deselect under
the CI invocation; 3 skip with a stated reason when the manifest points at an
absent corpus and index.

---

## 2026-08-23 — a second judge: same non-discrimination, opposite direction

`qwen2.5:7b` through the identical 395-record gold control that `llama3.2:3b`
ran. Same input set — rung 1 split it 76 ACCEPT / 153 BAND / 166 REJECT, third
reproduction of those figures.

|  | llama3.2:3b | qwen2.5:7b |
|---|---|---|
| span_ok, gold | 3% | 83% |
| span_ok, model output | 3% | 83% |
| code_ok, gold (correct codes) | 92% | 21% |
| code_ok, model output (0/105 correct) | 86% | 21% |
| parse failures | 204/395 | 1/395 |

**Gold and model output score identically within each judge**, on both channels,
for both models. The small judge fails almost every span and passes almost every
code; the large one does the reverse. Neither distinguishes a correct answer
from a fabricated one. Two models, two sizes, two families, same result.

The 7B code channel is the sharper finding: it rejects 79% of human-annotated
**correct** codes, at the same rate it rejects codes that exist in no release.
By rung 1 verdict — ACCEPT records score code_ok 29%, REJECT records 21%. Eight
points apart on a distinction that is a database lookup.

**What did improve: availability.** 204 parse failures to 1. The 43%/58%
input-dependent failure rate was a property of llama3.2:3b, not of LLM judging.
A larger model fixed it completely and changed nothing about discrimination.

Agreement with rung 1 is now at its fourth value across four configurations —
100% / 98% / 49% / 44% — with no relationship to whether the judge was doing
useful work.

Cost: 209,354 tokens, 5,545s. **Backend confound:** qwen2.5:7b is 4.7 GB and the
card has 4 GB VRAM, so it ran partially on CPU (2,789 MiB resident, 47% GPU
utilisation). Timing is not comparable to the llama run; discrimination is not a
timing property, so the finding stands. Recorded because determinism is bounded
by the backend — see the CPU/GPU mention-count entry.

Run: `LADDER_JUDGE=qwen2.5:7b LADDER_N=0 PYTHONPATH=. python3 scripts/r4_gold_control.py`

---

## 2026-08-23 — the manifest's model config had never been reached

`ladder/llm.py:for_rung` centralises model selection so rungs never pick a
model. Correct design. The strings it resolved were `ollama/ibm/granite4:micro-h`
and `ollama/gpt-oss:20b` — the first has a vendor prefix the local Ollama tag
does not carry, the second was never pulled. Both 404.

Nothing caught it because **no measured run goes through `for_rung`.** Every
figure in this repo came from `scripts/*.py` naming models inline. The rungs do
not pick a model, as specified; the scripts do, and they are what ran.

Found by the ledger coverage tests — the only tests that call a model. 97 others
passed. Same shape as the dead ledger call sites: a centralisation that is right
in design and unreached in practice, sitting behind a green suite.

The 404 is also environmental-looking. "Model not found" reads as a missing
prerequisite rather than a config error, and the test guards were written to
skip on missing prerequisites. One more line in those guards and this would have
skipped silently instead of failing.

Fixed to `ollama/granite4:micro-h` and `ollama/qwen2.5:7b`. Judge remains a
different family from the extractor, as required, and qwen is the judge with
1/395 parse failures against llama3.2:3b's 204.

---

## 2026-08-23 — the scorer, and the rung 0 prompt-engineering study

**TDD is now a hard rule** (CLAUDE.md, "How to work"). Every change below was
written test-first. The reason is local, not doctrinal: every number here is
evidence for an article, and a check nobody watched fail is a check nobody has
shown to work.

**`ladder/score.py` exists.** The accuracy axis was the single blocking gap —
`load_scorer` returned `None` and every accuracy column was written empty.
Gold is keyed by SPAN, never position, which is the whole design: index-keyed
comparison scores a *perfect* extraction 0.216 when it is listed in another
order. `span_match` is a declared choice — `exact` is the headline, `overlap`
exists because rung 3 keys on exact spans and its temperature-0.7 resamples
never align, which is why every rung 3 record comes back `not_resampled`.

**A bug found by writing the tests, not by running the code.** `run.py:450`
builds gold as `{record_id: GoldMention}` and hands that whole dict to the
scorer. `record_id` is `f"{doc_id}#{index}"` — a POSITION. Rung 0 numbers its
records by the order the model emitted them; the annotation file numbers gold
by the order it was annotated. Looking a record up by its own id would have
graded most mentions against somebody else's answer, silently. The scorer
therefore accepts the collection and re-keys it by span itself.

**Rung 0 gained four steps, S0–S3.** Scope is identical in all four — same
mentions, same record keys, same scorer — and the ONLY thing that varies is
where the code comes from: S0 recalls label and code; S1 recalls the label and
resolves the code from the vocabulary; S2 picks the label from a shortlist
retrieved for the mention; S3 picks it from one fixed keyword list. Run with
`--rung0-step`, which writes the choice back into the manifest copy saved
beside the results, so two runs can never look identical on disk.

Two things collapsed into the baseline rather than becoming steps, because
neither is prompt engineering: naming CONCEPT_LESS (it is task specification —
4.1% of gold reaction mentions have no code, and a prompt that never says so
asks the impossible on those) and locating spans deterministically (the model's
character arithmetic is wrong at every model size).

**`Record.sct_label`, appended.** What the model SAID its code means. A bare
code is an unverifiable claim; a code plus a label is checkable against the
vocabulary for free, with no extra model call. Rung 1 gained `label_check`,
default `"flag"` — the same posture as `meddra_check` and the negation cue, and
for the same reason: "rectal bleeding" against |Rectal hemorrhage| is one
concept in two wordings and the false-rejection floor is unmeasured.

### Measured 2026-08-23, over all 7,311 gold reaction mentions

| | |
|---|---|
| exact search on the patient's own words returns nothing | **57.1%** |
| ...returns something, gold code absent | 15% of hits |
| gold code found by searching the raw quote | **36.5%** — the ceiling for "search the span" |
| gold reaction mentions that are CONCEPT_LESS | 4.1% (302) |
| quote occurs more than once in its document | 14.5% (906) |
| ...of those, first occurrence is the right one | 33.9% — so dropping the offset anchor risks 9.6% of all mentions |
| multi-candidate sets where two share an IDENTICAL label | **76.8%** |
| MedDRA terms matching no SNOMED description | **36.2%** (241 of 666) |

The label collision number is why a pick is an INDEX and never a label string.
The 36.2% is why S3 is a *leaky* ceiling: a third of the answer-key-derived
list cannot reach a SNOMED code at all, so S3 measures MedDRA↔SNOMED term
overlap as much as it measures closed-set assignment.

### Two prompt defects found by running it, and fixed

**The pick menu numbered mentions and candidates alike.** With mentions as
`0.` and candidates as `0)`, granite4:micro-h replied `{"i":17,"choice":17}`
and `{"i":11,"choice":"Bleeding"}` — it conflated the two numbering systems and
then answered with a name. Every record came back `no_pick`. Mentions are now
`reaction N` and candidates `[N]`, and the reply key is `reaction`.

**Telling the model not to code made it stop finding.** The first FIND prompt
ended "Finding it is the whole task here", and the model returned whole
SENTENCES as spans — `"Hospitalization due extreme rectal bleed that required
blood transfusion."` where S0 and S1 both returned `"extreme rectal bleed"`.
That is scope drift between steps, which would have made the study
uninterpretable. There is now a test asserting all three prompts share the same
span instruction verbatim.

**S3's first failure was mine: the menu was printed once per mention.** 666
keywords rendered per-mention put **1,998 candidate lines** and ~13.7k tokens
into one prompt — the same list three times, each copy numbered identically.
The model replied with 14 tokens of invalid JSON (a stray trailing quote) and
answered 1 of 3 reactions, so every pick was discarded and S3 scored 0.0.

NOT a context limit: granite4:micro-h's window is 1,048,576 tokens. Printing a
shared list once fixed it outright, and `_blocks(pairs, shared=...)` now does
that for S3 while S2's genuinely-different shortlists still repeat:

    prompt tokens      16,899 -> 5,768
    completion         14, invalid JSON -> 22, valid
    reactions answered 1 of 3 (discarded) -> 2 of 3
    coverage           0.0 -> 0.667
    latency            16.1s -> 6.1s

**S3's real failure, now visible.** The model picked `choice: 1` and
`choice: 0` — the FIRST TWO ENTRIES of the 666-item list:

    list position 0 = Pain     -> chosen for "might not survive"
    list position 1 = Myalgia  -> chosen for "extreme rectal bleed"  (Muscle pain)

It is not searching the menu, it is anchoring on the top of it. One of three
mentions got no pick at all. A long menu buys position bias, not selection —
which is a finding about closed-set assignment, and it only became visible once
the rendering bug stopped masking it.

**A limitation of `label_check` this exposed.** Both wrong answers above carry
`label_verified: True`, because |Myalgia| really is a term for 68962001 and
|Pain| really is one for 22253000. The check confirms label-to-CODE
consistency and says nothing about label-to-SPAN correctness. It catches a
model that names one concept and emits another's id; it cannot catch a model
that is confidently, coherently wrong. Do not read it as an accuracy signal.

A malformed reply is recorded as `pick_parse_failed`, distinct from `no_pick`:
reporting one as the other would be a lie about what the model did.

### Not done

The four dev runs. Everything above except the corpus-wide measurements is
still ONE document, ARTHROTEC.107.

---

## 2026-08-24 — Registry.search() is literal substring matching

Found while building the rung 6 desk, which needed to offer a reviewer
candidates and offered nothing for most records.

`Registry.search(text, k)` matches the query as a literal substring of SNOMED
labels. No tokenisation, no stemming, no term overlap:

    'low back pain'    -> 3 results
    'lower back pain'  -> 0
    'back pain lower'  -> 0
    'lower back'       -> 1
    'back'             -> 2

The full phrase does not appear character-for-character in any label, so
nothing matches. Case is NOT the mechanism.

**141 of 343 gold reaction spans return a candidate. 202 return nothing — 59%.**
Of those 202, **0** are recovered by lowercasing. These are the annotators' own
phrases, the ones a human judged codable, and the lookup finds nothing for six
in ten.

Blast radius, because several rungs lean on this:

- **Rung 0 mode B.** The post-hoc lookup returns empty for most mentions, so
  `honoured_tool` is None rather than False far more often than its docstring
  implies. The arm's failure has a simpler explanation than the one currently
  written into the code.
- **Rung 1's `lexical_match`.** If it uses the same matcher, ACCEPT vs BAND is
  partly an artefact of substring matching — and the 43.1% pooled / 35.0%
  reactions-only accept rates inherit it. UNVERIFIED; check before the article
  quotes those figures again.
- **Rung 6's strata.** "No candidates" mostly means the search missed, not that
  the record is intrinsically hard to code. The 27s median therefore measures
  reviewing records the lookup failed on, and the 1.2 reviewer-hour
  extrapolation is not the coding-from-scratch cost it was designed to be.

The fix is not small — proper matching means tokenising labels and scoring
overlap, in a component every rung uses. A to decide.

Also fixed in scripts/r6_desk.py: search results use the key `label`, not
`term` or `fsn`, so candidates were displayed as bare SCTIDs with no text. The
reviewer picked blind for all six records.

---

## 2026-08-24 — the keyword table, and four corrupted codes in the answer key

**`ladder/keywords.py` — a two-column `keyword,code` CSV built from the SNOMED
release alone.** 299,523 keywords -> 172,206 codes, 14 MB, written to
`data/keywords.csv`: cleaned DATA, not a cache. It is produced before any rung
runs and a run whose keyword table changed is a different run, so it belongs
with the corpus and the splits. `.gitignore` covers `data/*` except
`data/splits/`, so it stays unpublished like `snomed.sqlite`. Rung 0 deals in
WORDS: it names the concept, the table maps the name to a code, and the model
never emits a nine-digit integer it could mistype. "Did it name the right
concept" becomes separable from "did it recall the right id".

Restricted to concepts whose FSN semantic tag is `(finding)` or `(disorder)`.
Measured over CADEC's 923 distinct gold reaction codes:

    every concept in the release   1,822,645 rows   99.95% of coded mentions
    tag in {finding, disorder}       521,946 rows   99.90%   <- built

The 0.05% difference is four mentions; the exclusion removes every organism,
product, substance and qualifier — the class that produced |California chicken
(organism)| for a rectal bleed and let |Gaseous substance| outrank the right
answer for "gas". 55,501 keywords collide (two concepts, one label); the tie is
broken by lowest concept id — arbitrary but STABLE, since a table that
reshuffled between builds would move every number derived from it.

**Rejected: a refset filter.** SNOMED's Clinical finding foundation reference
set (126,101 members) looked like the principled way to exclude junk, but it
covers only 94.1% of gold codes against 99.96% for the tag allowlist — 150x
more lossy. Rejected on measurement. Also rejected: topping a list up with the
gold codes it misses (that is answer-key derivation, the exact defect of the
666-term MedDRA list), and a frequency list from the pool split (does not exist
in deployment, so it cannot generalise).

### 100% coverage is unreachable, and the answer key is why

Four of CADEC's 1,047 distinct gold codes (0.38%) are absent from the release.
None is a retired concept. **All four fail the Verhoeff check digit** that
terminates every SNOMED identifier, so none was ever issued by SNOMED — they
are corrupted strings, and each corruption is identifiable:

    20070731            NOT A CODE — a date, 2007-07-31 in RF2's YYYYMMDD
                        effectiveTime format. Sits in the post-coordinated pair
                        ['67849003', '20070731'] where 67849003 is |Excruciating
                        pain|, correct for "excruciating pain in my legs". A
                        release date leaked into the code column.
    21499005            transposition of 24199005 |Feeling agitated| — the 4 and
                        the 1 are swapped. Gold text "Severe aggitation".
    81680008            81680005 |Neck pain| with the check digit wrong. Single
                        character. Gold text "pain neck".
    21290011000036100   17 digits in the AU extension namespace shape, for
                        "testosterone". A mistyped AMT identifier.

Three affect reaction mentions (~4 of 7,273). **They are NOT corrected.**
Editing gold so our numbers improve is how a benchmark stops being evidence.
They are recorded here so the 99.95% ceiling is explained rather than
mysterious, and `ladder/registry.py`'s older note ("three annotation typos, one
code CADEC got wrong") is now precise: all four are Verhoeff-invalid.


### Preprocessing is now four steps, in order

    python -m ladder.registry --build     RF2 -> SQLite index      (existing)
    python -m ladder.keywords --build     data/keywords.csv        (new)
    python -m ladder.clean    --build     data/exclusions.csv      (new)
    python -m ladder.run init             freeze the splits        (existing)

**`ladder/clean.py` — exclusions, not corrections.** 7 of 7,311 gold reaction
mentions (0.10%) cannot be answered and now leave the denominator with a stated
reason: 3 carry only Verhoeff-invalid codes, 4 quote text that is not at their
offsets (`'renal failure'` vs `'rena  failure'`, `'pain in stomach'` vs
`'pain i stomach'` — off-by-one annotation slips). `score_run(exclude=...)`
reports the count; `run.py` applies the list to the answer key once, at load.
The temptation to repair rather than exclude is the thing being refused: 21499005
is obviously 24199005 and 81680008 is obviously 81680005, and editing an answer
key so the system under test scores better is how a benchmark stops being
evidence.

**A collision-ordering bug the real data exposed.** The tiebreak documented as
"lowest concept id" compared ids as STRINGS, so `"224968006" < "24199005"` and
|Feeling agitated| resolved to the wrong concept. Now numeric, which also
prefers core international concepts over extensions. Collisions 55,501 ->
51,082.

**Audited and needing nothing:** duplicate gold spans (0), mentions with no
spans (0), empty mention text (0), mentions with neither a code nor
CONCEPT_LESS (0).

**Audited and NOT a preprocessing problem: 850 overlapping gold pairs.** Gold
reaction mentions nest and cross one another. That is legitimate annotation,
not corruption, but it means `span_match="overlap"` is looser than it looks — a
prediction can overlap two different gold mentions and the matcher takes the
first in prediction order. Exact matching is unaffected. Stated here so the
overlap column is read with the caveat attached.

---

## 2026-08-24 (later) — "keywords, not sentences", and the collision that cost 10%

**The table was built from every description row.** FSN, preferred term and
every synonym alike, which is how 42-word TNM staging text ended up in a column
labelled `keyword`. SNOMED makes the distinction itself and the build now
respects it — measured over finding/disorder concepts:

    Synonym/preferred    197,537 rows   median 4 words
    Synonym/acceptable   135,949 rows   median 4 words
    FSN/preferred        188,459 rows   median 6 words   14.4% over 8 words

The FSN exists to disambiguate, not to be said, and dropping it costs nothing
because every concept has a preferred synonym. Also dropped: descriptions over
10 words (10,715) and Read/CTV3 migration artifacts such as `#radius &/or ulna`
and `([provider initiated encounter] or [patient asked to come in]) or` (7,582)
— together 0 gold mentions. `keywords.py` now reads the RF2 description file
directly, because the SQLite index carries no `typeId`.

**A 10-point error in my own reporting, and the design change it forced.** The
"99.90% coverage" logged earlier counted concepts that HAVE a qualifying
synonym. It did not account for deduplication. Measured against the built file:

    one row per keyword, numeric tiebreak       164,182 codes   89.85%
    one row per keyword, preferred > acceptable 168,490 codes   93.50%
    a keyword may repeat                        180,446 codes   99.90%

A keyword is not a unique key. |coma| is both 371632003 and 50061006, |neuroma|
both 443892003 and 154622009, and every tiebreak discards a concept CADEC
actually uses — 111 gold codes, 10.05% of mentions. The table now allows a
keyword on several rows: still two columns, 12% more rows, full coverage
restored, and 27,307 keywords (9.8%) explicitly ambiguous. `lookup()` returns a
LIST; one element is the common case at 90.2%.

The ambiguity is not a defect to hide. It is the disambiguation rung 0 exists
to perform, now visible and countable instead of resolved by a coin flip inside
a build script.

    279,059 keywords -> 180,446 codes, 313,780 rows, median 4 words

---

## 2026-08-24 (later still) — "outdated" is a fourth outcome, not a kind of wrong

**The distinction the scorer could not make.** A model that emits `162076009`
for a mention now coded `12063002` named a real SNOMED concept and lacked
eleven years of releases. A model that emits `999999999` invented a number.
Both scored `incorrect`, so the article could not say which one it was looking
at — and "the local model hallucinates codes" and "the local model learned an
older SNOMED" are different claims with different fixes.

`score_run` now reports FOUR outcomes:

    correct     the code is in the gold set for that mention
    outdated    a RETIRED concept whose successor IS the gold code
    abstained   no code — CONCEPT_LESS, or nothing at all
    incorrect   everything else

**`outdated` is never folded into `correct`.** Precision, recall and F1 count
`correct` only. The answer is still stale, and a pharmacovigilance system that
files a retired code has filed a retired code. What changes is that the error
now has a name.

**Two association types count, and the exclusions are the point.** SNOMED
records succession in `der2_cRefset_AssociationSnapshot`, now loaded into the
SQLite index as an `association` table. Active rows in the AU release, by type:

    REPLACED BY             900000000000526001   147,402   <- followed
    POSSIBLY EQUIVALENT TO  900000000000523009    48,891
    SAME AS                 900000000000527005    43,654   <- followed
    MOVED TO                900000000000524003    20,561
    PARTIALLY EQUIVALENT TO 734138000             15,815
    WAS A                   900000000000528000    12,919
    (six more)                                     8,832

Only SAME AS and REPLACED BY. POSSIBLY EQUIVALENT TO says *possibly* — 48,891
rows of maybe, and crediting them turns `outdated` into a wastebasket for near
misses. WAS A points at a PARENT, which is a broader concept and not the same
one: |Pain| is not a stale spelling of a headache. MOVED TO points at a module,
not a concept at all. The refsetId is STORED rather than filtered at build
time, so revisiting this is a scoring change and not a rebuild.

**Chains are followed to the end.** SNOMED retires successors too, so a
one-hop lookup reports a code as unreplaced when a current equivalent exists
one more release along. An ACTIVE concept never gets a successor even if a
stray row names one — nothing replaced it, it is still here.

**A missing index degrades toward `incorrect`, never toward `correct`.**
`Registry.replacements` returns `[]` when the `association` table is absent,
and `score_run` without a vocabulary reports `outdated: 0` with the error
still counted. The 365 MB SQLite is built once and shared between checkouts,
so a mid-upgrade index is a normal state, not an error — and a missing table
must never be able to raise a score. `python -m ladder.registry --associations`
adds the table to an existing index in seconds; the full rebuild reads 1.8 M
concepts and walks the is-a graph twice, and where the index is reached through
a symlink `build(force=True)` would replace the symlink with a private copy and
silently fork the two checkouts.

**Rung 1 flags, it does not reject.** `outdated_check: "flag"` — the same
posture as `meddra_check`, `negation_action` and `label_check`, and for the
same reason: rejecting would throw away a model that named a real concept.
`R_CODE_OUTDATED` is appended to `REJECT_REASONS` so it is nameable and
countable, not so it can fire. Rung 1 writes `sct_outdated` and
`sct_replacement` into `checks` even when `reject_inactive` has already
rejected the record, because the two settle different questions — "is it
retired" and "is there a current equivalent" — and the second is the fact rung
2 would state back.

### Measured 2026-08-24, over all 7,311 gold reaction mentions

| | |
|---|---|
| gold mentions whose every code is retired | 407 (5.6%) |
| ...of which SNOMED records a SAME AS / REPLACED BY successor | **111 (27.3%)** |
| distinct retired gold codes | 57 |
| ...with a successor | 24 |
| active association rows loaded into the index | 302,074 |

**A finding this raises and does NOT act on.** `ladder/clean.py` excludes all
407 retired-gold mentions from the denominator, on the stated grounds that the
keyword table holds active concepts only, so they "cannot be answered through
it". The `outdated` logic says the opposite for 111 of them: they have a
current equivalent, so a model naming that equivalent is answering correctly
against a stale answer key. Symmetry argues those 111 should re-enter the
denominator and score `outdated` in the other direction. That is a change to
the answer key's inventory, which is exactly the class of change this repo
requires a measurement and a decision for, so it is recorded here rather than
made quietly. The other 296 have no successor and the exclusion stands.

### Two tests that were wrong, found by adding a correct one

`test_appended_reasons_go_at_the_end` asserted `REJECT_REASONS[-1] ==
R_LABEL_MISMATCH`. It was written to protect append-only ordering and it
pinned the NEWEST reason instead, so it failed the moment a reason was
appended correctly. It now asserts on the frozen PREFIX, which is the
invariant it meant.

`tests/test_ledger_coverage.py` guarded "no reachable model" with
`(RuntimeError, SystemExit, OSError)`, which is not what an OpenAI-compatible
endpoint raises when the manifest names a model tag the local ollama does not
hold — that is `openai.NotFoundError`. Merging origin/main brought model
strings resolving on another machine and three tests went red for an
environmental difference. The guard now also skips on openai's
NotFound/Connection/Auth/Permission errors, and deliberately NOT on
`APIError`: a 400 means we sent a bad payload, which is our bug and stays a
failure.

`ladder/run.py`'s `snapshot_row` — the function that writes every number the
article quotes — had no test coverage at all. It has some now
(`tests/test_run_rows.py`), which is how the two new columns are known to
reach the CSV: `write_results` uses a `DictWriter` over `CSV_COLUMNS`, so a
key nobody declared is silently dropped.

---

## 2026-08-24 — S3 dropped, and rung 0 resolves through the keyword table

**The study is three steps now: S0, S1, S2.** Scope is still identical in all
three; the only thing that varies is where the CODE comes from.

    S0  label and code recalled from the model's own weights
    S1  label recalled, code resolved from the KEYWORD TABLE by that label
    S2  label PICKED from a shortlist retrieved for the mention

### Why S3 went, and why nothing replaces it

S3 was closed-set assignment over one fixed list printed in the prompt. Every
candidate list that could fill that slot fails its own measurement:

| list | size | ceiling |
|---|---|---|
| the MedDRA list CADEC ships | 666 | it IS the answer key's inventory |
| SNOMED Clinical manifestation refset | 743 | **48.7%** of gold |
| the keyword table | 227,554 | cannot be printed at all |
| a list retrieved per mention | 20 | that is S2 |

The MedDRA list was never a method — all 666 of its codes appear in CADEC's
gold annotations and none do not, so S3 measured a declared ceiling. The
ontology-native replacement is the honest version of the same idea and it caps
at under half the corpus, which is a worse ceiling than the one it was meant
to remove. The real table is three orders of magnitude too large to render.
And a list retrieved for the mention is S2 by another name, so a fourth step
would be a duplicate rather than a contrast.

S3's own last measurement is worth keeping: shown a 666-item menu, the model
picked positions 1 and 0 — |Myalgia| for "extreme rectal bleed". A long menu
buys **position bias, not selection**. That finding is about long printed
menus in general, which is the thing being retired.

**What went with it.** `keyword_list`, `keyword_meddra`, `KEYWORD_CSV`, and
`_blocks(pairs, shared=...)` — the shared-menu renderer that printed one
identical list once. None had another caller. Dead scaffolding in a
measurement harness is scaffolding somebody later mistakes for a code path in
use; the measurement it encoded (a 666-item list rendered per mention put
1,998 candidate lines and ~13.7k tokens into one prompt) survives here, which
is where a finding is supposed to outlive its mechanism.

**Rung 0 no longer touches the MedDRA CSV at all.** It was reachable only
through S3. `meddra_mode` stays `reference`: the list cross-checks a code
produced by other means, and retrieval from it is refused. There is a test
asserting the string `meddra_codes.csv` does not appear in `r0.py`.

### Rung 0 resolves names through data/keywords.csv, not through the registry

`Registry.resolve` searched every description in the release — organisms,
products, substances and qualifiers included. That is the class that answered
|California chicken (organism)| for a rectal bleed and let |Gaseous substance|
outrank the right concept for "gas". `KeywordTable.resolve` has the same
return shape (`code`, `rank`, `ambiguous`, `label`, `candidates`) over a table
restricted to findings and disorders, so the swap is one line at the call site
rather than a rewrite.

**No fallback to the registry.** A name absent from the table is UNRESOLVED.
Falling back would reinstate the search the table exists to replace and would
make "which of the two answered" unrecoverable from the record. Rung 0 still
does not retry: it walks its remaining names and stops, because a retry loop
here IS rung 2.

**A missing table raises.** `python -m ladder.keywords --build` is one of four
preprocessing steps, and resolving nothing silently would report a build step
nobody ran as a model that named no concepts.

**THE REGISTRY DOES NOT GO AWAY, and this is the part to not get wrong.** Rung
1 needs `exists` / `is_active` / `finding_status` / `terms` over the WHOLE
release. The keyword table is deliberately filtered: 82249009 |California
chicken (organism)| is real and active, rung 1 must be able to look it up in
order to catch it, and rung 0 must never be able to reach it. S2's shortlist
also still comes from the registry. `code_source` is now `"keyword_table"` for
S1 and `"shortlist"` for S2, where both used to say `"tool"` — one label for
two different sources is one label too few.

### A documentation error found while wiring this

`ladder/keywords.py`'s docstring described a table where "a keyword may
repeat" — 279,059 keywords, 313,780 rows, 180,446 codes, 99.90% gold
coverage. The code does not build that table. It drops retired concepts and
writes ONE ROW PER KEYWORD. Both designs were built; the docstring was left
describing the earlier one. Corrected in place, and re-measured rather than
re-estimated:

    keywords                       227,554
    rows                           227,554   (one per keyword)
    codes                          127,515
    keywords naming two concepts       103
    codes left with no keyword          32   (none used by CADEC)

The apparent coverage regression — 99.90% to **94.11%** of coded gold reaction
mentions — is entirely the 407 mentions whose every gold code is retired, which
`ladder/clean.py` already excludes from the denominator for the same reason
this build drops them. With the exclusions applied, which is how the ladder
actually reads gold:

    coded gold reaction mentions   6,595
    reachable through the table    6,592   **99.95%**

The three misses are 1806006, 183202003 and 251377007, one mention each. 99.95%
is the ceiling for any release-derived table, and the cause is the answer key:
three distinct gold codes are absent from this SNOMED release entirely.

The `lookup()` contract is unchanged and still returns a LIST — this build
never puts two codes under one keyword, but ambiguity is a property of
vocabularies rather than of one filter setting, and a signature that changes
when a filter changes is a signature that will be wrong again the next time
one does.

`manifest.rungs.0.keyword_table` records the path, so a run whose keyword
table moved is visibly a different run.

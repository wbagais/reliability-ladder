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

## 2026-08-24 — exact-term retrieval finds nothing for 59% of gold spans

Found while building the rung 6 desk, which needed to offer a reviewer
candidates and offered nothing for most records.

**Correction to the first version of this entry.** I wrote that `search()` was
literal substring matching. It is not. `search()` calls `codes_for_term()`,
which is `WHERE norm=?` — exact equality on the normalised term, and
`normalise_term()` lowercases, drops the semantic tag and squashes punctuation.
The evidence was in front of me and I read it backwards: `'back'` returning 2
results rules substring matching out, because substring matching would return
hundreds. The mechanism is exact match, and A documented the choice in the
docstring: fuzzy local search "would quietly become a different experiment from
the OLS4 one it is meant to be comparable with."

So this is not a bug. It is the measured consequence of a deliberate design
decision, which makes it more interesting rather than less.

**141 of 343 gold reaction spans return a candidate. 202 return nothing — 59%.**

    'low back pain'    -> 3 results
    'lower back pain'  -> 0        no description normalises to this
    'back'             -> 2

These are the annotators' own phrases, the ones a human judged codable. Exact
term retrieval finds six in ten of them absent from the vocabulary's
description table. That is a ceiling on any rung that depends on term lookup,
and it is a fact about the gap between patient language and terminology
descriptions rather than about the matcher.

Consequences:

- **Rung 0 mode B.** The post-hoc lookup returns empty for most mentions, so
  `honoured_tool` is None rather than False far more often than its docstring
  implies. Its failure has a simpler explanation than the one written into the
  code — most of the time there were no candidates to honour.
- **Rung 6's strata.** "No candidates" means the term is not in the description
  table, not that the record is intrinsically hard. The 27s median measures
  reviewing records the exact index could not serve, and the 1.2 reviewer-hour
  extrapolation is not the coding-from-scratch cost it was designed to be.
- **Rung 1's `lexical_match` is NOT affected.** Checked: it is a separate
  function comparing normalised text against a given code's own terms, with
  `mode="exact"` chosen by measurement. The 43.1% / 35.0% accept rates stand.

Open question for A, not a defect report: is exact-term retrieval the right
choice for rung 6 candidates, where the OLS4 comparability argument does not
apply? A reviewer needs recall, not comparability.

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

---

## 2026-08-24 — `usd` was a column of zeroes, in four rungs

`ladder/llm.py:Caller.__call__` has always computed the dollar cost of every
call from `models.yaml`'s per-Mtok rates and returned it in `usage["usd"]`.
Rungs 0, 2, 3 and 4 all dropped it, so `Ledger.totals()["usd"]` was 0.0 for
every run — including the ones that cost money.

**The bug hid because zero was RIGHT for the default configuration.** Local
ollama is free, `local: true` is the default, and a number that is correct by
accident for the configuration you run every day is the hardest kind to
notice. It was wrong for exactly the configurations the study needs it in: the
claude-sonnet-5 comparison these steps were measured against, and any hosted
judge at rung 4.

**Fixed in all four, not just rung 0.** Fixing one would have left
`totals()["usd"]` reporting one rung's spend as the run's spend, which is
worse than a zero — a zero is visibly absent, a partial total reads as a
total. Rung 3 mattered most: it bills k sampling calls as a DOCUMENT row, paid
whether or not a record is re-found, so a dropped price made the most
expensive rung the cheapest on paper.

A caller that reports no `usd` at all logs 0.0 rather than raising, and there
is a test for that: a stub or an older caller is a normal state, and a cost
column is not worth a crash.

**Cost is still three separate measures** — tokens, latency p95, records
routed to a person. `usd` is carried alongside them and never fused into them.
That is unchanged; what changed is that it is now carried at all.

---

## 2026-08-24 — dense retrieval beats lexical by 24 points, and the 41.7% could not be reproduced

**Measured before wiring, as required.** Same 6,595 scorable coded gold
reaction mentions (exclusions applied), same k, same answer key. The only
thing that changes between the rows is the retriever.

|  | recall@1 | @5 | @10 | @20 | @50 |
|---|---|---|---|---|---|
| lexical (`Registry.shortlist`) | 19.5% | 52.4% | 57.6% | **61.8%** | 66.7% |
| dense (`granite-embedding:30m`) | **63.8%** | 76.7% | 82.1% | **86.1%** | 90.3% |

**Dense's single top hit (63.8%) beats the lexical top-20 (61.8%).** That is
the headline, and it is why the default moved.

### CORRECTED SAME DAY: that comparison changed TWO things, not one

The table above is not a clean A/B and the first write-up of it was wrong. The
two retrievers were searching DIFFERENT CORPORA as well as scoring
differently:

    lexical   1,822,645 description rows over 721,187 concepts, every
              semantic type, filtered to findings only AFTER ranking
    dense       227,554 keyword rows over 127,515 concepts, findings and
              disorders, active only, filtered BEFORE ranking

So "embeddings are worth 24 points" was attributing a corpus change to the
scoring function. Re-measured with the SAME Jaccard scoring over the SAME
keyword table, so exactly one thing varies per row:

| | recall@1 | @5 | @10 | @20 | @50 | corpus scan |
|---|---|---|---|---|---|---|
| lexical over descriptions | 19.5% | 52.4% | 57.6% | 61.8% | 66.7% | 407.7s |
| lexical over keywords.csv | 48.6% | 57.2% | 61.1% | 65.1% | 69.6% | 32.2s |
| dense over keywords.csv | 63.8% | 76.7% | 82.1% | 86.1% | 90.3% | 21.8s |

**At k=20 the split is +3.3 points of corpus and +21.0 points of scoring.** The
conclusion holds and dense still wins on scoring alone, but the honest number
for "what embeddings bought" is 21.0, not 24.3.

**At k=1 it inverts: +29.1 of corpus against +15.2 of scoring.** Filtering to
findings and disorders BEFORE ranking is what clears the top slot — the
description table's organisms, products and substances were crowding it, which
is the same defect that produced |California chicken (organism)| for a rectal
bleed. Rank 1 is where corpus hygiene pays and rank 20 is where scoring does.

**The 19x speed-up was also mostly corpus size**, not cosine: 408s to 32s is
the smaller table, 32s to 22s is the matrix multiply.

Found because the number was questioned, not because a test caught it. A
retrieval comparison has THREE declared choices — corpus, scoring, k — and a
row that varies two of them measures neither.

**Both motivating defects are gone, and they were the stated reason:**

    "extreme rectal bleed"  ->  0.902  12063002  rectal bleeding      (rank 0)
    "bleed"                 ->  0.866  131148009 bleeding             (rank 0)
    "cramping"              ->  0.884  279093005 cramping pain        (rank 0)

The lexical path ranked |Rectal| above |Rectal hemorrhage| for the first,
because Jaccard's denominator penalises every extra word in a correct term,
and never reached "bleeding" from "bleed" for the second, because there is no
stemming. Neither is a weighting choice.

**Dense has its own failure mode and it is not being hidden.** `"gas"` returns
|gas gangrene|, |gas gangrene smell|, |gas gangrene-back| — surface-similar
clinical compounds, none of them right. The lexical path failed the same query
differently (|Gaseous substance|). Embeddings move the errors; they do not
remove them.

`rung0_retrieval` is `dense | lexical` and the lexical path is KEPT, not
deleted: a recall number produced under one retriever is only interpretable
next to the other, and `checks.rung0_retrieval` is written onto every record
so two runs differing only in retrieval cannot look identical on disk.

### The 41.7% in the brief could not be reproduced, under any denominator

The working note carried "S2 is 41.7% (shortlist recall@20)". Measuring
`Registry.shortlist`'s own output across every denominator and k available:

| denominator | n | @1 | @5 | @10 | @20 | @50 |
|---|---|---|---|---|---|---|
| coded reactions, exclusions applied | 6,595 | 19.5% | 52.4% | 57.6% | 61.8% | 66.7% |
| coded reactions, no exclusions | 7,009 | 18.7% | 51.1% | 56.3% | 60.5% | 65.2% |
| ALL reactions, CONCEPT_LESS a miss | 7,311 | 17.9% | 49.0% | 54.0% | 58.0% | 62.5% |
| ALL gold mentions, drugs included | 9,111 | 14.4% | 39.3% | 43.3% | 46.5% | 50.2% |

Nothing lands on 41.7%. The closest cell is 43.3% — recall@**10** over ALL
gold mentions including drugs, a denominator a findings-only retriever cannot
answer by construction.

**The reimplementation was verified before the disagreement was reported.**
`Registry.shortlist` rescans every description row per call, which is ~0.6s a
mention and hours over the corpus, so the sweep uses an inverted index with
the identical Jaccard, the identical tie-break and the identical
`findings_only` filter. Checked against `reg.shortlist` itself on 40 sampled
mentions: **40/40 identical candidate lists**. The disagreement is therefore in
the corpus, the denominator or the k of the original figure — not in the
rewrite. Recorded as unreproducible rather than quietly replaced, and 41.7%
should not be requoted until whoever produced it can say which denominator it
was over.

### The build had to survive a bad minute

The first full build reached 184,832 of 227,554 keywords — 24 minutes — and
died on one 400 from the local ollama. Re-running the same batch afterwards
succeeded, and bisecting the whole surrounding window found no offending row:
the server was briefly unwell under memory pressure from a concurrent job, and
the input was fine.

A failing batch is now retried with backoff, then SPLIT recursively until a
single row is isolated and zeroed — one unembeddable keyword costs one row,
holding its position so the sidecar keeps indexing the matrix correctly. A
batch where NOTHING embeds raises instead: that is the embedder, not 512
simultaneously bad keywords, and it should fail at minute 24 rather than write
175 MB of zeroes that answer every query with silence and look like a
retrieval result. The rebuild: 227,554 vectors, dim 384, 433.6s, 0 retries, 0
zeroed.

### Verified end to end on ARTHROTEC.107

S0, S1 and S2 all run through rungs 0-1 with `ollama/ibm/granite4:micro-h`.
`checks.rung0_retrieval` reads `dense` on S2, `code_source` reads
`keyword_table` on S1, `sct_outdated` and `sct_replacement` are written, and
`sct_outdated` / `sct_abstained` reach the results CSV. This is WIRING
verification on one document with a 2B model — it is not the study, and none
of its numbers should be quoted as one.

**One thing it exposed, recorded and NOT fixed.** S0 asks for a scalar
`sct_code` and granite4:micro-h returned a LIST. `_step_s0` does
`str(code) if code is not None else None`, so the record's `sct` became the
literal string `"['21456007', '...']"` — which can never be a valid code, so
those mentions score 0 by construction. That is a RECORDING defect rather than
a model defect: it makes "the model named two codes" indistinguishable from
"the model emitted garbage", and the first is a real thing a model does. What
the right behaviour is — take the first, treat it as a parse failure, or count
it as its own outcome — is a decision about what S0 measures, so it is logged
here rather than chosen quietly. **It will bias S0 downward in the dev runs
until it is settled.**

---

## 2026-08-24 — the lookup-vs-RAG 2x2, and why its bottom row is unmeasurable at 2B

**The question.** Rung 0 currently retrieves on the patient's raw words. Would
asking the model to name the concept first, and retrieving on THAT, match
better? A 2x2 answers it: perfect label vs actual model label, crossed with
exact keyword-table lookup vs dense retrieval.

**The top row, over all 6,595 scorable coded gold reaction mentions:**

| | lookup | RAG@20 |
|---|---|---|
| perfect label (gold's own preferred term) | 99.3% | **99.3%** |
| actual model label | ? | ? |

Retrieving on the correct clinical term scores 99.3% at k=20 and 96.5% at
k=1, against 86.1% / 63.8% for the patient's raw words. Enormous headroom on
paper — but note what the ceiling IS: **99.3% is the same number an exact
lookup already gets**, because a perfect name needs no retrieval. The two
columns of the top row coincide by construction. Retrieval can only be worth
something on an IMPERFECT label, which is the bottom row.

**The bottom row could not be measured, and the reason is the finding.** Run
on ARTHROTEC.107 with `ollama/ibm/granite4:micro-h` at S1:

    gold "rectal bleed"    12063002   model proposed: "AFTERPROMPT"
    gold "extremely sick"  213257006  model proposed: CONCEPT_LESS
    gold "felt I might not survive"   CONCEPT_LESS — no code to retrieve

    perfect label   lookup 2/2   RAG 2/2
    actual label    lookup 0/2   RAG 0/2

`AFTERPROMPT` is a prompt artifact, not a clinical term. Dense retrieval
cannot rescue it because there is no concept in it to be near. **At this model
size the bottleneck is not lookup-vs-retrieval — it is that the model does not
name concepts at all**, which is one step earlier than the thing the 2x2 was
built to compare. Two coded mentions in one document: an OBSERVATION, not a
rate, and emphatically not evidence that RAG fails to help.

Answering the question properly needs a model that produces clinical labels.
`claude-sonnet-5` is the one the earlier ARTHROTEC.107 comparison used, and it
is a licence decision (CADEC is non-transferable; `LADDER_ALLOW_REMOTE=1`) as
well as a cost one.

### A recording gap the experiment exposed

`_resolve_labels` wrote `label_unresolved: True` and discarded the names the
model actually proposed — `sct_label` holds only the name that WON. So two
completely different failures were identical on disk:

    the model named nothing usable                    -> a MODEL failure
    the model named a real concept the table lacks    -> a VOCABULARY failure

The first needs a better model or a better prompt; the second needs a wider
table. Rung 0 could not tell them apart, and neither could anyone reading the
records afterwards. `checks["labels_proposed"]` now records every name the
model offered, on success and on failure alike — which is also what makes the
2x2's bottom row measurable at all, since an imperfect label that was thrown
away cannot be retrieved on.

Found by running the experiment, not by a test. The tests came after.

### Schema enforcement — revisited, and the first framing was wrong

Enforcing a JSON schema on rung 0 was raised as a way to guarantee one code
per mention (see the `sct_code`-as-a-list defect). The objection recorded
earlier — that it would delete rung 0's JSON-parse-failure counter-metric — is
too strong, and the better reading is that enforcement MOVES the failure
rather than removing it:

  * a constrained model can still truncate mid-structure, answer
    `{"mentions": []}` for a post with three reactions, or fill a required
    field with a plausible wrong value. Those are the same reliability
    failures without the JSON costume, and they stay countable.
  * grammar constraints are known to cost output QUALITY — probability mass
    goes to satisfying the schema instead of answering. So enforcement is an
    INTERVENTION with a price, not a free repair.

Which makes it an A/B like `rung0_mode`, not a switch: run both arms and
report what enforcement removed and what it cost. That is strictly more
evidence than either arm alone, and it keeps a non-zero failure rate that
measures something more interesting than well-formedness. NOT BUILT — recorded
so the decision is made deliberately.

---

## 2026-08-24 — why dense retrieval misses 13.9%, and why a hybrid does not fix it

**The misses were categorised rather than guessed at.** 918 of 6,595 gold
mentions have no gold code in the dense top-20:

| | | |
|---|---|---|
| 821 | 89.4% | the gold code IS in the table; retrieval ranked it below 20 |
| 79 | 8.6% | the query is a SENTENCE, not a term |
| 15 | 1.6% | post-coordinated gold (A + B); retrieval returns one concept |
| 3 | 0.3% | the gold code is not in the keyword table at all |

**The largest category is not what it looks like.** Reading the examples, a
substantial part of "genuine semantic miss" is retrieval finding the concept
the SPAN literally names while gold names a different one:

    "little blurred vision"   gold |Hazy vision|
                              retrieved: blurred vision, blurry vision
    "gastric problems"        gold |Excessive upper gastrointestinal gas|
                              retrieved: stomach problem, gastrointestinal tract problem

Those are not retrieval failures. They are the answer key selecting one
concept where several fit, and no retriever can be graded on them fairly.
Alongside them sit real misses ("extremely sick" -> |Generally unwell|) and
one clearly fixable kind — **typos**: `"Insomina"` is |Insomnia| with two
letters transposed, and the embedder put `inflared innominate` at rank 0. The
category has not been split further because doing it properly means deciding
which of those readings the answer key should have taken, which is not a
retrieval question.

**The second category is the actionable one, and it is the same defect as
S0's span drift.** 79 misses are queries like `"I can't stand or walk for any
lengths of time"` (gold |Reduced mobility|) — a sentence retrieved against a
table of 4-word terms. Retrieval is being asked the wrong question. This is
exactly what "have the model name the concept first" would fix, which is the
independent case for query rewriting.

### A hybrid was tested at equal budget, and lost

Union of dense top-20 with a second retriever's top-20 is 40 candidates, so
the honest comparison is dense top-40, not dense top-20:

| | recall | candidates |
|---|---|---|
| dense@20 | 86.1% | 20 |
| **dense@40** | **89.5%** | 40 |
| hybrid dense@20 + lexical@20 | 88.0% | 40 |
| hybrid dense@20 + char-trigram@20 | 89.3% | 40 |
| hybrid dense@20 + lexical@10 + char@10 | 88.8% | 40 |

**Every hybrid loses to simply asking dense for more.** Spending 20 extra
slots on more dense results beats spending them on a second retriever, and the
character-trigram variant — the one built specifically for the `Insomina`
case — does not even break even. So the fix for "retrieval misses 14%" is
`rung0_shortlist_k`, not a second index.

NOT BUILT, deliberately: raising k has its own cost at the PICK step, where a
long menu bought position bias rather than selection (measured at the retired
S3, 666 items). The retrieval-vs-pick trade-off is a rung 0 experiment in its
own right, and 89.5% recall the model cannot use is not 89.5%.

### Multi-label: the feature is right, the stated reason is not

Rung 0 asks for up to three concept names. The implied justification is that a
mention has several plausible readings. Measured over the corpus:

    distinct coded gold span texts                     3,272
      ...coded MORE THAN ONE WAY anywhere in CADEC        24   (0.7%)
    mentions whose exact wording is coded >1 way         256   (3.9%)

So genuinely ambiguous wording is rare. The real work multi-label does is
compensate for EXACT lookup being brittle: three shots at a string match,
free, in one call. `"high blood pressure"` (|Venous pressure above reference
range| / |Blood pressure above reference range| / |Hypertensive disorder|) is
a real case, but it is 0.7% of the vocabulary problem, not the reason.

**Which means the answer depends on the retriever, and that is testable.**
With exact lookup, multi-label is the only retry there is — keep it. With
dense retrieval, ONE label already returns k candidates, so the retries are
largely redundant, and the hybrid result above is suggestive: splitting a
candidate budget across sources lost to spending it all on one. Whether that
carries over to splitting across three labels is a HYPOTHESIS, not a
measurement — same method, three queries is not the same as two methods, one
query. `checks["labels_proposed"]` and `label_rank` are what settle it, and
they need a model that names concepts.

---

## 2026-08-24 — the DECIDE step, shared by S1 and S2

**Multi-label was never doing what it was for.** The prompt asks for up to
three concept names to raise the chance that SOMETHING maps. `resolve()` then
walked the list and returned the FIRST that mapped, so the alternatives only
ever fired on a total miss. Measured on the real keyword table:

    span:      "extreme rectal bleed"
    proposed:  ['rectal pain', 'rectal bleeding', 'rectal hemorrhage']

    'rectal pain'        -> 77880009    <- WON, on list position alone
    'rectal bleeding'    -> 12063002    <- right, mapped fine, discarded
    'rectal hemorrhage'  -> 12063002    <- right, mapped fine, discarded

All three mapped. The wrong one won because the model happened to write it
first, and **the span text was never consulted at the decision point.** That
is not three shots at a mapping; it is one shot with two spares.

**The missing half is a DECIDE step**, and S2 already had it: show the
candidates next to the original wording and let the model say which matches.
`_decide()` is now factored out and **shared** — not a new rung 0 step. What
distinguishes S0/S1/S2 is where the CODE comes from, and that is unchanged:
S0 memory, S1 the keyword table, S2 retrieval. Adding a fourth step for a
mechanism both already need would have split the study along the wrong axis.

**What S1 does now:**

    call 1   propose up to three names
    lookup   map EVERY name, dedupe by code, keep proposal order
    call 2   decide against the original span   <- only when >1 candidate

**One candidate is not a choice**, so S1 pays for the second call only when
there is something to decide. Its call count is therefore data about the
corpus rather than a constant, and it is reported as cost like every other
call-count difference in the study.

**Ambiguous keywords now contribute all their concepts.** |coma| is both
371632003 and 50061006; `resolve()` took `hits[0]`. Choosing between two
concepts sharing a keyword is the same judgement as choosing between two
names, not a coin for a build script to flip.

**Menu position is not mention position.** Only mentions with something to
decide go in the menu, so a mention resolved without a pick must not occupy a
slot — padding it would assign one mention's answer to another, silently.
There is a test for exactly that.

### A vacuous check, caught by an old test failing

The first implementation filled `sct_label` from the VOCABULARY's term for the
chosen code. `schema.py` defines that field as "what the MODEL said that code
means", and rung 1's `label_check` compares it against the vocabulary's own
words for the code — so filling it from the vocabulary makes the check
**incapable of failing**. It would have passed 100% forever and looked like a
clean bill of health.

The record now keeps the model's own proposing name; the MENU still shows the
vocabulary's FSN, because showing the model its own wording back invites it to
prefer whichever it wrote first, which is the bias being removed. Two
different strings for two different jobs.

**S2 still has this defect.** Its retrieved candidates carry no proposing
name, so `sct_label` comes from the menu and `label_check` is vacuous for S2
records. Not fixed here — S2 genuinely has no model-proposed label to record,
so the honest options are to leave the field empty for S2 or to accept that
the check only applies to S1. Recorded, not chosen.

### What this changes about "is the lookup a tool?"

It was not, and the distinction is already in the notes for mode B:
`vocab.search()` ran AFTER the model replied and its results never reached the
model, so it measured "would a search have found the code it invented?".

With the decide step, the lookup result DOES reach the model — as a second
PROMPT, not as a tool response. No function-calling protocol, no mid-
generation call, no loop the model controls. That is two-turn retrieval
augmentation, and it is worth naming precisely, because the tool ablation
(`--compare`) is about real tool access and this still is not that. The model
gets its guess checked and a chance to revise; it does not get to decide when
to look something up.

**Both calls are the SAME model.** `ROLE_BY_RUNG` binds rungs 0/2/3 to
`extractor` and only rung 4 to `judge`, so the decide step is the model
reconsidering its own proposals, not a second opinion. If the model cannot
tell rectal bleeding from rectal pain, asking it twice will not help — what
the step removes is the ARBITRARY loss of a right answer to list position.

---

## 2026-08-24 — the 2000-token cap was measuring the harness, not the model

**Every rung 0 number produced with `gpt-oss:20b` was a harness artefact.**
`LLMClient.chat` hard-coded `max_tokens=2000`. Measured on ARTHROTEC.107:

    S0   389 in / 2000 out   parse_failed / json_decode
    S1   341 in / 1830 out   extracted, 2 mentions
    S2   308 in / 2000 out   parse_failed / json_decode

Exactly 2000 on both failures is a cap, not a coincidence. `gpt-oss:20b` is a
REASONING model — it emits a chain of thought before the answer, so a budget
tuned for a 2B instruct model truncates it mid-JSON every time. The ledger
recorded that as `parse_failed`, which is the specific number rung 0 exists to
report: **the harness's own limit was being published as the model's
reliability.**

`max_tokens` is now REGISTRY DATA (`ModelInfo.max_tokens`, `models.yaml`),
defaulting to `DEFAULT_MAX_TOKENS = 2000` and set to 16000 for `gpt-oss:20b`.
A per-model property belongs in the registry for the same reason `sampling`
does — a rung must not know which family it is calling.

With the cap raised, on the same document:

    S1   341 in / 1830 out   2 mentions
    S2  1070 in / 5207 out   3 mentions   <- was parse_failed

### S0 still fails, and it is not the cap

S0 burns all 16,000 completion tokens and returns an EMPTY string. S0 is the
step that asks the model to recall a nine-digit SNOMED identifier from memory,
and the reasoning model appears to loop on it rather than commit. Recorded as
an observation on one document, not a rate — but note the shape: the failure
is specific to the step whose task is exact-id recall, which is the thing S1
exists to remove.

### What the models actually produced, and the span problem it exposes

| step | span | code | outcome |
|---|---|---|---|
| S1 | `'extreme rectal bleed'` | **12063002** | scored **incorrect** |
| S2 | `'extreme rectal bleed'` | **12063002** | scored **incorrect** |

Gold is `12063002` |Rectal hemorrhage|. **Both steps got the code exactly
right and were scored wrong**, because gold's span is `'rectal bleed'` (28,40)
and the model's is `'extreme rectal bleed'` (20,40) — eight characters wider,
so exact span matching finds no gold mention there and calls it a false
positive.

    span_match   S1                       S2
    exact        P 0.00  R 0.00  F1 0.00  P 0.00  R 0.00  F1 0.00
    overlap      P 0.50  R 0.33  F1 0.40  P 0.33  R 0.33  F1 0.33

This is the intensifier-boundary problem from the other direction. 506 gold
mentions (6.9%) START with an intensifier and KEEP it — "severe stomach pain",
"extremely sick" — so a "drop the intensifier" instruction would break those.
Here gold DROPPED it and the model kept it. The convention is not stateable as
prose in either direction, which is why the note that it is a few-shot job
stands, and why the exact/overlap gap has to be reported rather than one
number chosen.

S1's proposed labels also show the decide step is now reachable with a capable
model: `['Rectal hemorrhage', 'Rectal bleeding', 'Severe rectal bleeding']` —
three real clinical names where granite4:micro-h produced `AFTERPROMPT`.

---

## 2026-08-24 — a truncation is not a model failure

Raising `max_tokens` for `gpt-oss:20b` fixed S2 and left the real defect in
place: **the ledger could not tell a cut-off reply from a bad one.** S0 burns
all 16,000 completion tokens and returns an EMPTY STRING, and that was logged
`parse_failed / json_decode` — the same label as a model that emitted
malformed JSON, which is the specific reliability number rung 0 exists to
report.

Raising the cap does not fix that. It moves where the confusion happens. The
provider already says which occurred, so it is now recorded:

    LLMResponse.truncated     finish_reason == "length"
    usage["truncated"]        passed through to the rung
    agg["truncated"]          counted per run
    ledger reason             "truncated", not "json_decode"

The two counts OVERLAP on purpose. A truncated reply IS unusable, so it stays
a parse failure; what must not happen is the cause becoming unrecoverable. The
flag is cached alongside the text, because a cached reply that was truncated
is still truncated and losing it would make one run report two different
failure counts.

### Is 2000 too low as the default?

Not for the models it was written for. Measured completion tokens on
ARTHROTEC.107:

    granite4:micro-h   S0 185   S1 164   S2 167      ~10x headroom at 2000
    gpt-oss:20b        S0 16000 (truncated, empty)
                       S1 1830
                       S2 3303 + 1904 = 5207

A reasoning model needs 10-30x what an instruct model does, and the spread is
a property of the MODEL, not of the task — which is exactly why the budget is
registry data now. The default stays 2000: raising it globally means a model
stuck in a loop burns 16k tokens per document instead of 2k, on every document
in the split, and tokens per record is one of the three cost measures. With
truncation recorded, a too-low budget is now VISIBLE rather than silently
recorded as unreliability, which is the property that makes a conservative
default safe.

### S0 with a reasoning model: 16,000 tokens, empty output

Not the cap — it was 2000, then 16000, and both produced nothing. S0 is the
step that asks for a nine-digit SNOMED identifier from memory. The model
appears to loop rather than commit to an id it cannot recall. One observation
on one document, but the shape is worth stating: the failure is specific to
the step whose task is exact-id recall, which is the thing S1 exists to
remove.

### What the three steps actually produced

    S0   1 call    389 in / 16000 out   truncated, empty, 0 records

    S1   1 call    341 in / 1830 out    2 records
         {"mentions":[
           {"span_text":"extreme rectal bleed",
            "sct_label":["Rectal hemorrhage","Rectal bleeding",
                         "Severe rectal bleeding"],"confidence":0.95},
           {"span_text":"extremely sick",
            "sct_label":["Severe illness","Severe sickness",
                         "Critical illness"],"confidence":0.8}]}
         -> 12063002 (rank 0, 1 candidate, no decide call needed)
         -> "extremely sick": all three names miss the keyword table entirely

    S2   2 calls   1070 in / 5207 out   3 records
         finds all three spans, picks 3 of 3
         -> 12063002 | 162471005 |Symptom very severe| | 17029006 |Feeling despair|

**S1 named the right concept first try.** `Rectal hemorrhage` is the gold
label; it mapped, and because only one candidate survived, no decide call was
needed. Against granite's `AFTERPROMPT` this is a different class of model.

**S1's second mention shows the keyword table's edge.** `Severe illness`,
`Severe sickness` and `Critical illness` are all reasonable English for
"extremely sick" and NONE is a SNOMED synonym of |Generally unwell|. Three
plausible names, zero candidates — the failure multi-label was supposed to
prevent, and it is a VOCABULARY failure rather than a model one. `dense`
retrieval over the same labels would have offered something; exact lookup
offers nothing. That is the strongest argument yet for the lookup-vs-RAG
question, and it is now visible only because `labels_proposed` is recorded.

---

## 2026-08-24 — S0 fixed, one source of truth for models, and a stale cache

### S0's failure was a separate reasoning channel, not a loop

`gpt-oss:20b` writes its chain of thought to a **separate `reasoning` field**
and leaves `content` EMPTY until it finishes. S0 — the step that asks the
model to recall a nine-digit SNOMED identifier from memory — spent its entire
budget there and returned nothing. Measured on ARTHROTEC.107:

    default effort, 16000 cap   16000 tokens   content EMPTY   truncated
    default effort, 32000 cap    2306 tokens   content OK        34s
    reasoning_effort=medium      8000 tokens   content EMPTY   truncated
    reasoning_effort=low          104 tokens   content OK         2s

`reasoning_effort` is registry data in `models.yaml`, like `max_tokens` and
`sampling`, and is omitted for models that declare none — sending it to a
model with no reasoning channel is at best ignored and at worst a 400.

### But `low` is not a speed-up, it is a different experiment

The 104-token result was tempting and wrong. Measured over 3 documents,
17 gold reaction mentions:

| setting | S0 | S1 | S2 | tok_out | sec |
|---|---|---|---|---|---|
| `reasoning_effort=low`, cap 8k | **1** | 10 | 9 | ~900 | ~1 |
| default effort, cap 32k | **11** | 12 | 13 | 5.8–28.6k | 106–539 |

**S0 finds ONE mention of seventeen at low effort.** It stops truncating and
starts missing instead, which is the same failure wearing a cheaper coat. S1
and S2 lose less (10 vs 12, 9 vs 13) but they lose.

And the effort **cannot differ per step**: scope is identical across S0/S1/S2
by design, and a step that thought harder than its neighbours would make the
comparison meaningless. So `reasoning_effort` is left UNSET with a 32000 cap,
and the cost is reported rather than avoided — the dev split takes hours, not
minutes. The mechanism stays in the registry for when a model needs it.

### `manifest.model` is now the ONLY place a model is named

`ladder/llm.py` carried `DEFAULT_MODEL = "ollama/gpt-oss:20b"` while
`manifest.model.extractor` said `granite4:micro-h`. "Which model produced this
number" therefore had two answers depending on whether a manifest reached the
call — the exact defect that centralising model selection was supposed to
remove, because the run still produces numbers, just not the ones the manifest
describes.

`resolve()` now RAISES on a missing entry. Order is `--extractor` >
`LADDER_MODEL_SPEC` > manifest, and nothing after.

**Extractor moved to `ollama/gpt-oss:20b`** on measurement, and the cost is
stated in the manifest rather than buried: **the judge is now the WEAKER
model.** `granite4:micro-h` (2B) is the only locally installed family that
differs from the extractor, and rung 4 refuses to self-judge, so rung 4 is a
2B model grading a 20B one. That is the wrong way round and every rung 4
number has to be read with it said. A third local family would fix it.

### The cache key was incomplete, and it bit within minutes

The key was `(model, messages, temperature, sample_index)`. `max_tokens` and
`reasoning_effort` were absent, so rerunning S0 after lowering the effort
served the **old entry** and reported 16,000 tokens and a truncation that no
longer happened. A cache that survives a parameter change is not a cache, it
is a stale result presented as a fresh one. Both are now in the key.

Worth noting how it was found: a `rm -rf .llm_cache out/final_S*` was aborted
by zsh's `nomatch` on the glob, so the delete never ran and the stale entry
was served. The bug was real either way; the shell just made it visible on the
first rerun instead of the tenth.

---

## 2026-08-24 — a reasoning runaway, and the timeout that bounds it

**The dev-split run did not finish; it stopped.** S1 over `gpt-oss:20b`
completed 30 of 40 documents and then made no progress for 25 minutes. Ollama
was healthy and the model loaded — one call was generating toward the 32,000
token cap on a **761-character forum post**.

Measured over the 30 calls that DID complete (dev documents, median length
309 characters):

    completion tokens   median 1,029   p90 3,244   max 7,836
    latency seconds     median    32   p90    98   max   694

**Ninety percent finish under 3,244 tokens. The tail is what makes the run
unbounded** — and 694 seconds for one call was already the warning that the
3-document config measurement was too small a sample to see.

That is the real lesson about the earlier `reasoning_effort` decision: the
3-document comparison said "default effort, 32k cap" was the honest choice
because `low` found 1 gold mention of 17. It was right about quality and blind
to the tail, because three documents cannot show you a distribution's tail.

### The fix is a timeout, not a smaller cap

    max_tokens   8000    covers every call that terminated (max 7,836)
    timeout_s     300    bounds the ones that do not

`timeout_s` is registry data like `max_tokens`, `sampling` and
`reasoning_effort`. A timeout **does not raise**: it returns an empty response
flagged `timed_out`, so one runaway document costs ONE RECORD instead of the
whole run. A run that dies on a tail document has measured nothing; a run that
records the timeout has measured 39 documents and one timeout, which is a
result.

**A timeout is not cached.** It is a property of this run — of load, of this
machine — not of the question. Caching it would make that document's answer
permanently unavailable on every later run, which is the opposite of what the
cache is for.

**`timed_out` and `truncated` overlap on purpose** and are recorded
separately, exactly like `truncated` and `parse_failed`. Nothing usable comes
back either way; the causes differ — one is the model writing too much, the
other is it writing too slowly — and only the second is a property of the
machine rather than of the model. The ledger `reason` is now
`timed_out` > `truncated` > `json_decode`, most specific first.

Three layers of the same principle now: a cut-off reply must never be counted
as a model that cannot produce JSON, and a hung machine must never be counted
as either.

---

## 2026-08-24 — rung 0 measured on the dev split: S0, S1, S2

First numbers over more than one document. 40 documents, 226 scorable gold
reaction mentions, `ollama/gpt-oss:20b`, `reasoning_effort: low`, rung 1 in
observe mode.

| | records | P | R | F1 | correct | abstained | wrong | calls | tokens |
|---|---|---|---|---|---|---|---|---|---|
| S0 exact | 105 | 0.029 | 0.013 | **0.018** | 3 | 6 | 48 | 40 | 43,998 |
| S1 exact | 161 | 0.205 | 0.146 | **0.171** | 33 | 15 | 29 | 57 | 36,079 |
| S2 exact | 148 | 0.264 | 0.173 | **0.209** | 39 | 1 | 27 | 75 | 68,906 |
| S0 overlap | 105 | 0.029 | 0.013 | 0.018 | 3 | 10 | 79 | | |
| S1 overlap | 161 | 0.366 | 0.261 | 0.305 | 59 | 20 | 63 | | |
| S2 overlap | 148 | 0.392 | 0.257 | 0.310 | 58 | 3 | 66 | | |

**S0 is not a weaker step, it is a broken one.** F1 0.018 against S1's 0.171
and S2's 0.209 — an order of magnitude, on identical scope, identical spans
and the same model. It also costs MORE than S1 (43,998 tokens against 36,079)
to be ten times worse, because recalling an identifier takes more deliberation
than recalling a name. **The single most expensive thing rung 0 can be asked
to do is the one thing it cannot do.**

**S1 and S2 are close, and S2 costs nearly twice as much.** F1 0.171 vs 0.209
exact, 0.305 vs 0.310 on overlap — where they are within half a point. S2 pays
75 calls and 68,906 tokens for that; S1 pays 57 calls and 36,079. On the
overlap reading, retrieval buys almost nothing over an exact keyword lookup at
1.9x the cost. On the exact reading it buys 3.8 points of F1.

**Every step's exact/overlap gap is large** — S1 0.171 -> 0.305, S2 0.209 ->
0.310. That gap is span boundaries, not coding: the model quotes "extreme
rectal bleed" where gold says "rectal bleed". Same concept, eight characters
wider, scored as both a false positive and a false negative under exact
matching. The gap is the intensifier problem measured end to end, and it is
why both numbers are reported and neither is "the" result.

**S0 is the only step that fails to parse: 5 of 40 documents (12.5%).** S1 and
S2 parse 40 of 40. Same model, same effort, same documents — the difference is
that S0's schema demands a nine-digit integer the model does not have.

### The escape hatch did not stop the fabrication

S0 was given a legal way to decline: name the concept, answer `null` for the
id. It used it 13 times in 105 records (12.4%), which is a real and useful
abstention rate.

It also still invents. On ARTHROTEC.107 the model answered `sct_label:
["Rectal hemorrhage"]` — correct — with `sct_code: "2714004"`, which is not a
SNOMED concept, in the same reply that was told never to invent one and shown
`null` as acceptable. **Offering an abstention reduces fabrication; it does not
remove it.** That is the S0 finding, and it is the argument for rung 1
existing at all.

### Cost, per document

    S0   1.00 calls   1,100 tokens
    S1   1.43 calls     902 tokens     <- 0.43 = the decide step, when needed
    S2   1.88 calls   1,723 tokens

S1's second call fires only when more than one distinct concept survives the
lookup. 43% of documents needed one; the rest were decided by the vocabulary
alone and paid nothing.

### Not measured

The dev split is 40 documents and every figure above is a rate over 226
mentions, not a confidence interval. S1 vs S2 differ by 3.8 points of exact F1
and 0.5 on overlap — neither gap is large enough, at this n, to call a winner
without the test split.

---

## 2026-08-24 — S2 frozen as rung 0

The prompt-engineering study is closed. `manifest.rungs.0.rung0_step` is
`"S2"`, chosen on the dev-split measurement in the entry above.

**Why frozen rather than passed per run.** Rungs 1-6 all consume rung 0's
output, so a ladder measured against three different rung 0s produces numbers
that cannot be compared to each other or to anything published. One rung 0, in
configuration, where the manifest copy saved beside the results records it.
`--rung0-step` still overrides for a single run — that is how the study is
reproduced — and it writes the choice into that copy, so two runs can never
look identical on disk.

**What the choice costs, stated rather than buried.** S2 wins exact F1 by 3.8
points (0.209 vs 0.171) and ties S1 on overlap within half a point (0.310 vs
0.305). It pays **1.9x the tokens** for that — 68,906 against 36,079 — and 75
calls against 57. On the overlap reading, retrieval buys almost nothing over
an exact keyword lookup at nearly twice the price. The exact reading is what
carries the decision, and the cost is real: it is reported in the ledger's
three measures and is not netted off against the accuracy gain.

**`rung0_step: null` was never "the default step".** It is the pre-study A/B
mode path. Leaving it null after the study would have run the whole ladder on
a rung 0 that no measurement in this repo describes — which is the failure the
freeze exists to prevent, and it would have been invisible.

**Not settled by this.** 226 mentions over 40 documents is a rate, not a
confidence interval, and S1 vs S2 is 3.8 points of exact F1. The test split is
what would call it properly. S2 is frozen because the ladder needs A step to
be frozen, not because the gap is large.

---

## 2026-08-25 — rung 0 review: four enhancements, one rejected on re-measurement

A deep review of the frozen S2 ran it on 3 dev documents (F1 strict 0.33; the
losses were recall — 3 of 7 gold mentions attempted — and one modifier-pulled
wrong pick). Four changes came out of it, each TDD'd; one planned change died
on its own measurement.

**1. Dense shortlist now dedupes by CONCEPT** (`EmbeddingIndex.search`).
Synonyms of one concept cluster in embedding space, and 46.8% of codes carry
more than one keyword (mean 1.78, max 27) — a live top-5 for "extreme rectal
bleed" held 12063002 twice and 414991007 twice. `Registry.shortlist` already
dedupes by cid, so the two retrievers now agree on what a slot means. Measured
over the same 6,595 gold mentions (the 86.1% baseline reproduced exactly
first, validating the harness):

    k          1      5      10     20     50
    undeduped  63.7%  76.7%  82.1%  86.1%  90.3%
    deduped    63.7%  77.7%  83.2%  87.0%  91.1%

+0.9pt recall@20 for zero extra cost, and menus with no duplicate lines.

**2. Declining the pick menu is no longer CONCEPT_LESS.** The old reading —
"shown every candidate the vocabulary has, declining is an assertion" — was
false: the menu is k of 227,554, and it misses the gold code for 13.0% of
coded mentions even deduped. The scorer credits CONCEPT_LESS as CORRECT
against concept-less gold, so a decline was scored as a vocabulary-wide claim
the model never made. A decline now degrades to `sct = None` (abstained),
flagged `declined_shortlist` and counted. Same for S1's menu (its own names'
codes). CONCEPT_LESS remains reachable where the model actually asserts it:
the S0/S1 sentinel. Note the trade: S2 can no longer score CORRECT on
concept-less gold — the credit it loses is credit it had not earned.

**3. `no_pick` / `bad_pick` / `declined_shortlist` aggregate into `agg`** —
they were per-record flags only, so a run where the model fumbled every menu
printed a clean summary.

**4. Two coverage rules added to the shared `_RULES` (all three steps, scope
parity kept).** Measured first, per the rule about prompt rules: 385 gold
mentions (5.6%, exclusions applied) are an exact repeat of an earlier span in
the same document — CADEC annotates every occurrence, the model dedupes
("spotting" reported once where gold has it twice). And gold codes general
malaise ("extremely sick" is 213257006), which S2 skipped on the first dev
document. Rules: report a reaction every time it is described; vague and
general states count.

**REJECTED: trimming intensifiers, again, now with the sign measured.** The
plan proposed "quote the symptom without severity words" after watching gold
say "rectal bleed" where the model said "extreme rectal bleed". Re-measured:
gold KEEPS a leading intensifier 3x more often than it drops one — 469
mentions (6.8%) start with one and keep it, 151 (2.2%) have one immediately
before the span and excluded. The two dev misses are the minority convention.
The rule stays out, the existing test guarding it stays, and the few-shot
example below models the majority convention (intensifier kept).

**NEW ARM, unmeasured: `rung0_fewshot`** (default False). A synthetic worked
example — never CADEC text; a test asserts it — appended to every extraction
prompt, teaching the three things prose could carry plus the one it could
not: repeats reported again, vague states reported, treatments excluded,
intensifier kept. Off until measured against the frozen S2 on dev.

**MEASURED SAME DAY — the arms, dev split, 40 docs, 226 gold mentions,
gpt-oss:20b, effort low, rung 0 only.** Baseline is the frozen S2 row from
2026-08-24. Arm 1 is the committed changes with the example OFF; arm 2 turns
`rung0_fewshot` on. Both arms carry the dedupe and the decline change, so the
few-shot delta is arm2 - arm1, not arm2 - baseline.

    |                     | F1 exact | F1 overlap | mentions | calls | tokens  |
    | frozen S2           | 0.209    | 0.310      | ~92      | 75    | 68,906  |
    | arm 1 (rules only)  | 0.204    | 0.308      | 184      | 77    | 97,878  |
    | arm 2 (+ few-shot)  | 0.266    | 0.363      | 196      | 77    | 106,627 |

**The rules alone are a wash; the example is what cashes them in.** The
coverage rules doubled emitted mentions (recall exact 0.181 vs an estimated
~0.15 baseline) and paid for it in precision — F1 flat. With the worked
example added, precision comes back (0.294 exact) while the recall holds:
+5.7pt exact and +5.3pt overlap over the frozen S2, which is a bigger step
than S1->S2 was (+3.8 exact). Zero parse failures in either arm; the decline
change (which can only remove credit) is included in both, so the gains are
conservative.

**Cost, stated:** arm 2 is 1.55x the frozen baseline's tokens (106,627 vs
68,906). Same call count (77 vs 75).

**Not flipped in the manifest.** `rung0_fewshot: true` would change the
frozen rung 0 that rungs 1-6 are measured against — the same freeze argument
as 2026-08-24 — so turning it on is a joint manifest edit, proposed but not
taken unilaterally. Until then the arm is reproducible with the flag.

---

## 2026-08-25 — dev failure analysis turned into five changes; F1 overlap 0.310 -> 0.430

The arm-2 dev run was decomposed instead of admired: of 226 gold, 68 FN
(concentrated in symptom-dense posts; 20 of them CADEC Symptom/Disease/
Finding mentions the "adverse reaction" wording told the model to skip),
45 paired mentions where the GOLD CODE WAS ON THE MENU and the model picked a
qualified sibling, 32 retrieval misses, 20 boundary-only, 10 concept-less
gold that S2 could no longer answer after the decline revision.

Five changes followed, all committed together and measured as one arm
(attribution inside the bundle is not claimed):

1. PICK prompt states the base-concept rule — gold is |Abdominal pain| for
   "Very very severe abdonimal pain"; plain beats qualified.
2. Scope widened to the answer key's: every condition experienced, including
   what the drug was taken for (CADEC_TYPE_MAP folds Symptom/Disease/Finding
   into REACTION).
3. Whole-post exhaustiveness stated.
4. "choice": "no_concept" — the explicit CONCEPT_LESS assertion; null stays
   "none of these".
5. Pool-derived few-shot: rung0_fewshot_docs = ARTHROTEC.22 + ARTHROTEC.110,
   rendered at runtime from data/, POOL ONLY (dev/test refused — an example
   from a scored split carries its own gold in-prompt). Few-shot examples
   come from pool, never dev: dev is the measurement.

Dev, 40 docs, 226 gold, gpt-oss:20b effort low:

    |                   | F1 exact | F1 overlap | mentions | tokens  |
    | frozen S2         | 0.209    | 0.310      | ~92      | 68,906  |
    | arm 2 (synthetic) | 0.266    | 0.363      | 196      | 106,627 |
    | arm 3 (all five)  | 0.289    | 0.430      | 240      | 126,871 |

Decomposition moved the right way: FN 68 -> 53, pick-past-gold 45 -> 34,
retrieval misses 32 -> 35 (more mentions found, more retrievals attempted).
The model never answered no_concept (0 uses) — the hatch exists, unused so
far. Overlap gained 3x what exact did: the new mentions are FOUND but their
boundaries still disagree with gold, so span conventions are now the
largest remaining gap, followed by the 34 residual picks and the retrieval
misses (dense on "extremely sick" cannot surface |Generally unwell|).

Cost, stated: 1.84x the frozen baseline's tokens. Same 77 calls.

Risk, stated: three prompt iterations have now been tuned against the same
40 dev documents. The test split has never been touched and remains the
only number that can go in the article.

---

## 2026-08-25 — arm 4 lost to arm 3, and the retreat is the finding

Three approved enhancements were bundled as arm 4: FIND asks for up to three
concept NAMES and retrieval queries span + names merged (targeting arm 3's
35 menu misses), k 20 -> 40 deduped (offline recall@40 90.2% vs 87.0%), and
a third pool example (LIPITOR.968, span conventions) plus a worked
no_concept line in the PICK prompt.

    | arm   | names | k  | examples | F1 exact | F1 overlap | FN | pick-past-gold | retr-miss |
    | 3     | no    | 20 | 2        | 0.289    | 0.430      | 53 | 34             | 35        |
    | 4     | yes   | 40 | 3        | 0.236    | 0.411      | 63 | 47             | 23        |
    | 4b    | yes   | 20 | 3        | 0.232    | 0.421      | 63 | 40             | 27        |
    | FINAL | no    | 20 | 2        | 0.294    | 0.447      |    |                |           |

**Name-augmented retrieval did exactly what it promised and still lost.**
Menu misses fell 35 -> 23, and the cost surfaced two steps away: the find
step emitted fewer and worse-bounded mentions (asking for names competes
with finding spans at low effort), and the pick step erred more. k=40 made
picks worse again (34 -> 47 at k=40): MENU RECALL IS NOT MENU ACCURACY, and
the k=20 + dedupe setting stands on that measurement, not on the recall
table. The merge machinery stays (inert without labels, exercised by tests);
the sct_label field is out of the FIND prompt and a test keeps it out.

**An isolation run was voided and rerun honestly.** Arm 4d meant to isolate
the third example but left `"sct_label"` in FIND's JSON template while the
prose said not to give one — a self-contradictory prompt measures nothing.
The third example therefore has NO clean solo measurement; it went out with
the bundle, recorded as unproven rather than harmful.

**FINAL is arm 3 plus only the no_concept worked line** (used twice on dev,
first uses ever) and it edges arm 3: exact 0.294, overlap 0.447, 240
mentions, 129,792 tokens. Against the 2026-08-24 freeze: F1 exact 0.209 ->
0.294, overlap 0.310 -> 0.447, at 1.88x tokens. Five dev-tuned prompt
iterations now: the test split remains untouched and is the only number
that can go in the article.

**Also surfaced, not acted on:** the extraction rule "do not report anything
they say they did NOT have" contradicts the answer key — CADEC annotates
mentions regardless of polarity (the 2026-08-22 negation note measured 427
gold mentions, 4.7%), e.g. DICLOFENAC-SODIUM.5's "no stomach pains" is
annotated. Changing scope again is a decision, not an edit; it would also
collide with rung 1's negation flag. Parked.
- 2026-08-25 — **Arm 5: `reasoning_effort` default vs `low`, re-measured on the final config — `low` stays.** Same 40 dev docs, same prompts, only the effort changed (models.yaml edit for the run, reverted after). Default effort: F1 exact 0.309 / overlap 0.448 vs low's 0.294 / 0.447 — +1.5pt exact, +0.1pt overlap, inside the ±3pt noise band. The costs are not inside any noise band: 340,787 tokens vs 130,246 (2.6x), ~2.2 h wall vs ~12 min (~10x, p95 doc latency 626 s), and 2 parse failures + 2 truncations where low had zero — the extra thinking pushes replies into the token cap. Pick-past-gold improved (33 -> 29), FN worsened (56 -> 59); the residue composition barely moves. The 2026-08-24 quality concern ("low finds 1 of 17") was an S0 artifact — under S2's find-then-pick shape, effort adds nothing the retrieval step hasn't already supplied. Full run: out/r0-enh-arm5-effort.*.
- 2026-08-25 — **First full-ladder run against the frozen rung 0 (dev, 40 docs): `out/full-ladder-dev-1.*`.** End to end the ladder answers 32 of 240 records (P exact 0.567, R 0.075) and abstains 208. Per rung, against exact-match truth on the pre-abstention codes: **rung 1** concentrates correctness for free — ACCEPT 32 records at 75% correct vs a 28% base rate, REJECT 10 at 0% correct (the error floor holds; all ten are ungrounded spans), BAND 198 at 22%. **Rung 2 fired zero times** — the only rejects were `schema_invalid` span failures, which carry no code-fact to state back; on this config its trigger set is empty, not broken. **Rung 3 is net negative as built**: 206/240 `not_resampled` (the known span-keying failure), and where matching succeeded it OVERWROTE 9 of the 32 rung-1-ACCEPTed codes with memory-recalled winners — |Fever| for "stiff neck" and "vertigo", |Hypoglycemic syndrome| for "weight gain" — because its resamples use a recall-style prompt while rung 0's S2 codes came from retrieve-and-pick. Voting over a different answer distribution than the one being verified replaces verified codes with hallucinations. Do not re-run rung 3 against S2 until its sampler goes through the same retrieve-and-pick path. **Rung 4** (granite4:micro-h, 2B, judging 20B): pass = 33% correct vs fail = 17% — real signal, 2:1, but gating BAND on "pass" yields 26% precision, far below shippable. **Rung 5** works as designed (withdraws to `checks.withheld`, keeps rung-1 ACCEPTs) and its bill is now measured: 43 correct answers withdrawn to buy 0.567 precision. Cost: rungs 3+4 spent 239k tokens (1.8x rung 0's 130k) and returned negative value on this run.
- 2026-08-25 — **S0/S1/S2 re-compared under the final enhanced config — the S2 freeze stands.** The freeze-time comparison predated every enhancement, and all three steps share `_RULES` and the pool few-shot block, so the gaps could have moved. They did not reorder. Same 40 dev docs, same scorer: S0 F1 exact 0.026 / overlap 0.031 (137k tokens, 3 parse failures); S1 0.243 / 0.369 (66k tokens, cheapest by 2x); S2 0.296 / 0.451 (130k tokens). The enhancements lifted S1 too (0.171 -> 0.243 exact), so they are prompt-level gains, not S2-specific ones. S2 beats S1 by +5.3 exact / +8.2 overlap at 2.0x S1's tokens — the same declared trade as at the freeze, now larger. S0 got WORSE relative to the others and remains the only step that fails to parse: its schema still demands the one thing the model cannot do. Runs: out/step-compare-S0.*, out/step-compare-S1.*, out/r0-enh-final.*.
- 2026-08-25 — **Phase A: the scorer separates detection from coding, carries bootstrap CIs, and stops blaming answers to excluded questions.** `score_run` now returns `detection` (span-level P/R/F1, codes ignored) and `coding` (accuracy conditional on a matched span) beside the headline; recall = detection.recall × coding.accuracy by construction. `bootstrap_ci` resamples DOCUMENTS (mentions within a post share a call, an author and a topic — resampling mentions would report a band ~√6 too tight); per-document counts are computed once and 1,000 draws are arithmetic. Predictions overlapping an EXCLUDED gold mention now leave the denominator with it (previously only an exact span-key match did; 10 of arm 2's 38 false positives were answers to excluded questions).
- 2026-08-25 — **S0/S1/S2 re-run under the full enhanced config (few-shot pool examples, all prompt rules): S2 confirmed, and the two layers say WHY.** Dev, 40 docs, 226 gold; F1 [95% CI] / detection F1 / coding accuracy, overlap mode: **S0** 0.031 [.007–.062] / 0.688 / **0.046** — 166 records, 3 parse fails, 137k tokens; **S1** 0.369 [.289–.439] / 0.766 / 0.482 — 216 records, 0 fails, **66k tokens**; **S2** 0.451 [.370–.527] / 0.765 / **0.590** — 240 records, 0 fails, 130k tokens. Detection is IDENTICAL for S1 and S2 (0.766 vs 0.765) — the design claim that scope is shared and only coding changes is now a measurement, not an assumption. S0's detection is also lower (0.688): asking for nine-digit ids damages extraction itself, not just coding. S2's edge over S1 is entirely coding accuracy (0.590 vs 0.482; exact 0.691 vs 0.520) at 2.0× S1's tokens. The marginal CIs overlap — S2 wins every layer in the same direction, but a paired per-document test is the honest next refinement if the freeze is ever revisited. S2 stays frozen. Runs: `out/step-compare-S0.*`, `out/step-compare-S1.*`, `out/r0-enh-final.*`.
- 2026-08-25 — **Phase B(a): denied reactions are extracted, flagged `negated`, and kept.** The extraction rule "Do not report anything they say they did NOT have" fought the answer key — CADEC annotates a mention regardless of polarity (427 gold mentions, 4.7%; DICLOFENAC-SODIUM.5's "no stomach pains" is gold) — so all three step schemas now ask for `"negated": true|false` and the shared `_RULES` says a denied reaction is still recorded (scope parity kept; the legacy A/B `BASE` prompt is untouched, it predates the study). The model's claim is written to `checks.negated` AND duplicated to `checks.r0_negated`, because rung 1's cue check (untouched, the deterministic cross-check) does `rec.checks.update(...)` with its own `negated` — in a full-ladder run that key ends up holding the CUE verdict, and `r0_negated` is the copy that keeps model-vs-cue readable from disk. Prompt change ⇒ cache misses ⇒ the phaseB-1 dev run repays the full extraction cost.
- 2026-08-25 — **Phase B(b): query rewriting for S2's dense retrieval — measured offline and REJECTED, not wired.** Protocol identical to the 2026-08-24/25 retrieval measurements — same 6,595 coded gold reaction mentions (exclusions applied), same deduped index, same k — and the raw condition reproduced the deduped baseline exactly (63.7 / 77.7 / 83.2 / 87.0 / 91.1 at k=1/5/10/20/50), validating the harness before any other row was read. Two rewrite variants: `lead` strips leading intensifiers/articles/fillers ("extreme", "severe", "a", "my", "a little", ...; 466 of 6,595 queries changed), `full` also drops degree words anywhere in the span (519 changed). Both LOSE at every k ≥ 5: recall@20 86.5% (lead) and 86.3% (full) against 87.0% raw; the only gain anywhere is +0.2pt at k=1 for lead, inside noise. The changed-subset decomposition is unambiguous: at k=20 `lead` rescues 26 mentions and breaks 62, `full` rescues 26 and breaks 71 — the embedder already absorbs qualifiers ("extreme rectal bleed" → 12063002 at rank 0, score 0.902) and stripping them deletes signal. Same lesson as the intensifier-trim rejection, now on the retrieval side: the qualifier is information, not noise. Per repo precedent (S3, `_blocks(shared=)`), the mechanism is not kept unwired in production code; the harness protocol and strip lists are recorded here and the finding is what survives.
- 2026-08-25 — **Phase B(d): the span trimmer — boundary conventions LEARNED from pool gold, not legislated.** Exact detection 0.429 vs 0.765 overlap is 34 points of boundary convention, and the hand-written trim rule was already rejected once (gold keeps a leading intensifier 3:1). `ladder/trim.py` learns three token sets from POOL gold only (dev/test refused, same wall as `rung0_fewshot_docs`): `lead_drop`/`trail_drop` — tokens gold leaves immediately OUTSIDE a boundary ≥95% of ≥20 sightings (learned: articles, conjunctions, "experienced/had/having", punctuation — and correctly NOT "my" or the intensifiers); and `cut_drop` — the interior clause cut, tokens whose inside_rate (occurrences inside gold spans / all occurrences) is ≤2% over ≥50 sightings ("that", "when", drug names, dosages). A predicted span is truncated before the first interior cut token (never position 0), then edge-trimmed; a trim that would empty the span is not made; the original text stays on the record as `span_untrimmed`. Applied in rung 0 AFTER locate() and after retrieval (the menu is built on the model's full quote), behind `rung0_trim` (default False), cfg-injectable rules. **Structure measured first on the baseline dev records**: of 70 overlap-matched-but-not-exact pairs, 46 are pred⊃gold and the volume is trailing clauses ("pain that wakes me up"), 23 pred⊂gold (unfixable by trimming), 1 crossing. **Offline on `r0-enh-final`**: edge-only F1 exact 0.296→0.301; +interior cut at 0.02/50 → 0.305 with overlap byte-identical (0.451); looser cut points (0.05/30, 0.10/20) raised exact further but cut spans out of their overlap matches (overlap det 0.765→0.748/0.739) and were REJECTED — exact gains that cost overlap are boundary damage, not boundary correction. Thresholds were chosen against dev — declared: this is the sixth dev-tuned iteration; test stays untouched.
- 2026-08-25 — **Phase B(c): the negation arm measured, a pick-step interaction found and fixed, and the combined config wins — F1 exact 0.296 → 0.362, overlap 0.451 → 0.479.** The first run (`out/phaseB-1.*`) looked like a regression (0.260/0.386) and the two-layer scorer localised it: detection was UNCHANGED-to-better (exact det 0.444 vs 0.429; overlap det 0.767 vs 0.765) while coding collapsed on pick failures — `no_pick` 8 → 32 (18 of them ONE document, LIPITOR.460, whose pick reply was literally `{"picks":[]}` after 231 reasoning tokens; the baseline coded 16/17 on that document) and `bad_pick` 10 → 14, all the string `"null"` where the prompt says null. The decisive audit: the negation change FOUND 4 denied gold mentions the old prompt told the model to skip (DICLOFENAC-SODIUM.6's "drowsiness", "grogginess", "memory loss" among them) — and the pick step then DECLINED every one, reasoning "they did not have it, so no concept applies". Gold codes a denied reaction with the concept being denied, so three fixes followed, TDD'd: the menu marks denials (`reaction 3: [denied] "..."`), the PICK prompt states that denial is never a reason to answer null or no_concept, and the string "null"/"none" is normalised to the null decline (a transport convention, like fences and the old "i" key). Plus one scope patch: "No side effect"/"I was well" arrived as negated mentions, so `_RULES` now excludes blanket wellness statements. Re-run (`out/phaseB-2.*`): **exact 0.358 [0.285–0.434], overlap 0.479 [0.393–0.562]** vs baseline 0.296 [0.221–0.357] / 0.451 [0.373–0.524]; detection 0.501/0.783, coding 0.714/0.611 — every layer up in both modes. The three denied gold mentions score CORRECT; pick failures fell to no_pick 7, bad_pick 0; the empty-picks reply did not recur (LIPITOR.460 codes again). Cost: 137,828 tokens, 77 calls (+5.8% tokens over baseline's 130,246). **With the pool-learned trimmer applied (rung0_trim, now TRUE in the manifest per the approved Phase B plan): exact 0.362 [0.294–0.433], overlap byte-identical 0.479.** The marginal CIs overlap the baseline's; the paired read is that detection and coding moved together and the denied-mention recall is structural, not sampled. Seventh dev-tuned iteration — declared; the test split remains untouched. Residue: 2 negated FPs on LIPITOR.54 ("no cramping", "no torn rotator cuff" — denials gold does not annotate there), and pick-past-gold remains the largest coding class.
- 2026-08-25 — **Phase B(e): menu order is load-bearing — alphabetising S2's menu costs 10–12 points of coding accuracy.** One presentation arm, run cheap against the cached FIND replies (292 s): `rung0_menu_order: "alpha"` re-sorts the SAME deduped candidates alphabetically before numbering, changing nothing else. Detection is byte-identical to phaseB-2 (0.515 exact / 0.783 overlap — the control held), and coding fell from 0.704/0.611 to 0.600/0.491 (F1 0.362/0.479 → 0.309/0.385; incorrect 60 → 78 overlap-paired). Read: the pick anchors on early menu slots, so the dense retriever's best-first ranking is not presentation neutral — it supplies a real fraction of S2's coding accuracy, and any future menu change (k, dedupe, wording) must hold order fixed or it is measuring two things. The flag stays as a declared arm (`"score"` default, on every record as `checks.rung0_menu_order`); run: `out/phaseB-arm-alpha.*`, manifest edited for the run and reverted.
- 2026-08-25 — **Phase C setup: BioMistral-7B imported into ollama as `biomistral:7b-q5_k_m` (machine state; science not started).** Source: the OFFICIAL `BioMistral/BioMistral-7B-GGUF` HF repo, file `ggml-model-Q5_K_M.gguf`, 5,131,409,536 bytes, sha256 `3415073c45bc0aa3e6a6441adcdeb64e542a9544d2055e6c280903d729b11e7b` — verified equal to the repo's LFS oid at import. Q5_K_M chosen over Q4_K_M for judge quality (disk and RAM are not the constraint). Base model is Mistral-7B-Instruct-v0.1, so the Modelfile uses the `[INST]` template, stop tokens `[INST]`/`[/INST]`, `num_ctx 8192` (judge prompts carry a whole post). Modelfile, verbatim, for rebuilds: `FROM ./ggml-model-Q5_K_M.gguf` / `TEMPLATE """[INST] {{ if .System }}{{ .System }}\n{{ end }}{{ .Prompt }} [/INST]"""` / the two stop PARAMETERs / `PARAMETER num_ctx 8192`. Smoke-tested through the same `/v1/chat/completions` path `ladder/llm.py` uses, temperature 0, a judge-shaped prompt on SYNTHETIC text: valid JSON in the r4 schema, `finish_reason stop`, 39 completion tokens — and two quirks to quantify in the real re-judge: it echoed the `why` placeholder verbatim and answered `confidence: 0.0`. NOT yet done (next session, per the phase plan): models.yaml registration (TDD), `manifest.model.judge` swap, the 240-record re-judge of `full-ladder-dev-1` vs granite's 33%-vs-17% signal, and the rung 5 tau sweep.
- 2026-08-25 — **Phase C harness: the re-judge replay, and two rung-4 call-path defects it exposed.** `scripts/rejudge_r4.py` re-judges a finished run's records with the CURRENT `manifest.model.judge` — rung 4 is one call per record and reads nothing a saved record does not carry, so a judge swap costs 240 calls, not a ladder re-run. Two replay corrections, both TDD'd (`tests/test_rejudge_r4.py`): rung 5 ran AFTER rung 4, so the saved `sct` is null on all abstained records and the pre-abstention code is restored from `checks.withheld` first (188 of 240); and `r4.apply` overwrites `checks.r4*`, so the incumbent's verdicts are stashed once under `checks.r4_prior` (first stash wins — rerunning over own output cannot clobber the baseline). The replay's first pass then exposed two live defects. (1) **Every rung-4 call sent the post TWICE**: r4's template embeds `{source}` AND passed `source` as Caller's `text`, which appends it again as a `POST:` section — judge prompts at median 582 tokens where once-only is ~360. Invisible with granite (it answered anyway; the cost was just tokens), found only because BioMistral stops answering above ~430 prompt tokens. Fixed: Caller sends the bare prompt when `text=""` and r4 passes `""`; contract test asserts the post reaches the judge exactly once. **r2 has the identical defect** (template embeds source, call passes it again) — flagged for its own session, no measured number invalidated (r2 fired zero times on this config). (2) **A reply that stops one brace short is a transport dent, not a failed judgement**: 91 of BioMistral's 240 replies were a complete, correct-schema judgement that hit EOS immediately before the closing `}` — finish_reason stop, not truncated, valid JSON the moment the brace is appended. Same class as a markdown fence: `Caller._reclose` repairs it centrally, counts it in `caller.unclosed`, and fires only when the text does not parse, text+`}` does, and the result is non-empty (a bare `{` must not become a fabricated `{}`). Recovery: 2 → 73 records judged.
- 2026-08-25 — **Phase C result: BioMistral-7B is REJECTED as the rung-4 judge, and the judge reverts to granite4:micro-h — the 2B-judging-20B inversion stands as the measured lesser evil.** The hypothesis was that a domain-adapted 7B fixes the weaker-judge inversion. Measured on the 240-record re-judge of `full-ladder-dev-1` (dev, exact-span `outcome()` with exclusions and the registry), it fails on three independent grounds. (1) **It cannot deliver the reply**: through the original (doubled-post) path, 208/240 unparseable — 180 replies are literally `" {"` then EOS. After BOTH harness repairs, still 167/240 unjudged: instant-EOS is prompt-length-driven (answers at median 324 prompt tokens, EOSes at median 435; 500+ tokens = 100% EOS), so the longest third of posts cannot be judged at all, plus template echoes (`"why": "one short sentence"`, verbatim) and trailing-comma stops no single-brace repair reaches. (2) **No discrimination**: all 73 parsed verdicts are "fail" — span_ok is granted 67/73 but code_ok 1/73; it calls 386661006 wrong for the literal span "Lower Back Pain". Its fail rows are 23.3% correct vs 24.6% among its unjudged — zero separation, vs granite's stored 28.0% pass / 15.6% fail. (3) **Confidence is flat 0.0 on all 73** (the smoke-test quirk, now census), so the planned rung-5 tau sweep on the new judge's risk-coverage curve is formally impossible — skipped, contingency stated in the phase plan and not met. The optional S2 extractor arm is DECLINED on the same evidence: a model that cannot close a 4-field JSON object is not a candidate for S2's find-then-pick schemas. `biomistral:7b-q5_k_m` stays registered in models.yaml (max_tokens 512, timeout_s 120, no reasoning channel) so the arm is reproducible; `manifest.model.judge` is granite again and the manifest note records the round trip. Runs: `out/rejudge-biomistral-3.*` (final), `out/rejudge-biomistral.*` / `-dedup.*` (the two diagnostic passes). Lesson for the article: domain adaptation (PubMed-continued pretraining) does not buy instruction-following, and a judge is an instruction-following job first.
- 2026-08-25 — **Granite re-judged through the fixed (post-once) path: its pass/fail separation COLLAPSES — rung 4's signal is prompt-form-dependent.** Same 240 records, same scorer, only the duplication removed (`out/rejudge-granite-dedup.*`): granite's verdicts move on 57 of 240 records (32 pass→fail, 17 fail→pass, parse failures 2→9), and the correctness split goes from pass 28.0% / fail 15.6% (stored run, doubled post) to pass 25.4% / fail 23.6% — the ~2:1 ratio the full-ladder entry reported is gone at n=240, roughly 1.5–2 SE of movement. Read: repeating the post (before the claim AND after the schema instruction) was load-bearing for the 2B judge's separation, the same lesson as Phase B(e)'s menu order — presentation is never neutral for small models. The duplication stays fixed anyway: it was an unintended defect, not a designed feature, and a signal that lives in an accident is not a signal the article can stand on. Two caveats recorded: the full-ladder entry's "33% vs 17%" could not be reproduced exactly under this replay's scorer path (28.0/15.6 over all 240; 28.8/19.0 over coded records; direction and ordering reproduce under every denominator tried — the prior session's exact denominator was not recorded, which is its own lesson: state the denominator next to every rate). And granite's confidence field under the fixed path is nearly two-valued (133 of 231 at 0.9; τ=0.95 keeps 13 records at 53.8% precision, 5.4% coverage) — a real but tiny high-precision shelf, too thin to gate on at this n.
- 2026-08-26 — **r2's double-post defect fixed, same fix as rung 4's.** r2's `PROMPT` embeds `{source}` AND `correct()` passed `source` as Caller's `text`, so Caller appended the post a second time as a `POST:` section — the identical defect the Phase C replay found in r4 (fixed 2026-08-25), flagged then for its own session. Fixed the same way, TDD'd: `correct()` now passes `llm(prompt, "", "correct")`, and `tests/test_contracts.py::test_rung_2_is_sent_the_post_exactly_once` mirrors r4's contract test (the post reaches rung 2 exactly once, via Caller's bare-prompt-on-empty-text path). No measured number is invalidated: rung 2 fired zero times in the 2026-08-25 full-ladder run — its trigger set (rung 1 REJECT with a correctable reason) was empty. Full suite green, 551 passed.
- 2026-08-26 — **Phase D step 1: rung 3 DISABLED in the manifest, and "disabled" is now a recorded run state.** `manifest.rungs.3.enabled: false` per the 2026-08-25 full-ladder finding (206/240 not_resampled; 9 of 32 verified-ACCEPT codes overwritten with recall hallucinations). `run_ladder` treats `enabled: false` generically: it skips the rung BEFORE model resolution, writes a `disabled` ledger row and an `{"disabled": true}` aggregate entry, and prints it — so "rung 3 did not run" stays distinguishable from "rung 3 found nothing" in every artifact of the run. TDD'd (`tests/test_r3_repair.py`); re-enable requires both Phase D fixes plus the dev measurement.
- 2026-08-26 — **Phase D fix (a): rung 3 matches votes to a record by span OVERLAP, one-to-one, not by an exact (doc_id, spans) key.** The exact key called every shifted boundary a different mention — "extreme rectal bleed" vs "rectal bleed" — which is what lost 206/240 records their votes on 2026-08-25. `r3.match_votes` assigns each sampled mention to at most one record (best overlap first, deterministic tie-break by list order) and votes are collected per record_id; a single sampled mention spanning two records votes once, for the record it overlaps most. TDD'd, `tests/test_r3_repair.py`.
- 2026-08-26 — **Phase D fix (b): rung 3's sampler draws through rung 0's CONFIGURED path — r0.prepare + r0.extract_document, built from manifest.rungs.0 — never the legacy recall prompt.** The overwrites of 9/32 verified-ACCEPT codes came from voting over a different answer distribution than the one being verified: samples used the recall prompt while the run's codes came from frozen-S2 retrieve-and-pick. r0's per-document body (step dispatch + trimmer) is now factored into `extract_document`, shared by `r0.apply` and `r3.sample_document`, so the two cannot drift; `prepare` builds step validation, few-shot block and trimmer once for both. Billing: a sample is now meta["api_calls"] calls (2 through S2), summed into the DOCUMENT ledger row — one per sample would have reported the repaired rung at half price. TDD'd; test proves the winning vote can only arrive through the retrieved menu.
- 2026-08-26 — **Phase D measurement 1 (`out/phaseD-r3-1.*`, dev, 40 docs, 245 records): the two fixes work — and they exposed a third defect.** not_resampled 206/240 → 39/245 (161 records re-found by all 3 samples); vote spread over seen≥2: 3-0 x97, 2-1 x52, 2-0 x10, 1-1 x14, 1-1-1 x12, i.e. 57.8% unanimous. Verified-ACCEPT overwrites 9/32 → 1/37, and the hallucination class is GONE — every vote now arrives through the S2 menu. The one survivor is the third defect: 'pain', vocabulary-verified 22253000 |Pain|, overwritten by 38433004 |Analgesia| (the ABSENCE of pain) on a 1-0 "majority" from the ONLY sample that re-found the mention — 8 of 31 changes rested on a single re-finding. Protocol: exact-span outcome() with exclusions and the registry, harness first validated by reproducing the 2026-08-25 numbers (206/240; 9/32; 11 correct→incorrect, 0 improvements) from full-ladder-dev-1.records.jsonl. Rung 3 cost: 222 api_calls, 362,759 tokens over 37 documents (2.5x rung 0's 146,878).
- 2026-08-26 — **Phase D fix (c): one counted vote is not a vote — a record re-found by fewer than 2 samples records its verdict but is never changed.** Same argument as the existing k<2 refusal, applied to the votes actually cast; the withheld action is counted (`single_sample` in checks and aggregates) so thin evidence stays visible. Also fixed: documents are now sampled in SORTED order — the old set iteration tied the sampler's draw sequence (and every cache key) to the process hash seed, making a rung 3 result irreproducible from its run id. Both TDD'd (the doc-order test uses 6 documents; with 2 it passed by hash-seed luck on the first try, which is the defect demonstrating itself).

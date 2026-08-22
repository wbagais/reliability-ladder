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

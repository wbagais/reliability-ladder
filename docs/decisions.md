# Decisions & surprises log

Capture decisions, dead ends, and surprises *as they happen*. This is the raw
material for the InfoQ article — it evaporates if you reconstruct it in week 5.

Format: date — decision/surprise — why.

---

- 2026-08-16 — Dataset = SROIE2019 (626 train receipts, fields company/date/address/total) — already downloaded; gold entities included; the system itself is data-agnostic and SROIE is just the first "user" of the pipeline.
- 2026-08-16 — Temperature locked to 0 for EVERY call in EVERY rung — determinism is the headline metric; any sampling noise would confound it.
- 2026-08-16 — Consequence: rung 5 (voting) cannot use sampling diversity at temp 0. It votes across 5 fixed prompt VARIANTS (different framings/orderings of the harness wrapper around the unchanged user prompt) — deterministic diversity.
- 2026-08-16 — Adapter contract revised to v2 — `output_schema` (JSON Schema, nesting allowed) replaces flat `fields`; `gold` = full output object; `trusted_record` optional (absent = pure extraction, new verdict "n_a"). Reason: user's private dataset is nested-JSON extraction with no trusted source; flat verification-only contract wasn't data-agnostic. Flat v1 still accepted.
- 2026-08-16 — Internally, nested outputs are flattened to leaf paths (vendor.name, lines[0].price); each leaf path is a "field" for metrics + Runner. Arrays compared by index (order-insensitive matching = future work).
- 2026-08-16 — Rung 6 has two modes: simulated (gold value + fixed 2 human-min; reproducible, used for the published SROIE curve) and live (app review queue where the user confirms/corrects escalated fields; measured review time replaces the assumed minutes).
- 2026-08-16 — Accuracy scoring for SROIE is purely mechanical (normalize + exact match); LLM-judge-as-scorer stays a hook for semantic fields in future datasets. Rung-4 judge and scorer-judge must never share a prompt.
- 2026-08-16 — SURPRISE (first smoke run, granite4:micro-h, 10 items K=3): determinism = 1.000 at every rung — local greedy decoding at temp 0 is perfectly deterministic, so for local models the determinism axis is free and the curve rides on accuracy/coverage. Hosted APIs (batching nondeterminism) are where the determinism axis should move; measure the same curve on Gemini to compare. Also: local compute is $0, so the cost frontier for local runs is latency + human-minutes, not dollars.
- 2026-08-16 — SURPRISE (smoke run): rungs 1–3 moved accuracy 0.000. Cause, verified per-field: all 3 rung-0 errors were wrong VALUES at self-reported confidence 0.9–1.0 — not format errors (rung 1 inert for accuracy; scorer is normalization-tolerant anyway), nothing under the 0.7 abstention threshold (rung 2 inert; confidence is uncalibrated), and self-review kept all 3 errors and raised confidence on 2 (rung 3 inert). First accuracy gain came at rung 4 — the first layer with an INDEPENDENT signal. Candidate thesis for the article: self-referential layers are cheap but inert when the model is confidently wrong; gains start where independent signal enters (judge / variant-voting / human).
- 2026-08-16 — ANALYSIS (smoke run, replayed from cache): (a) granite's self-reported confidence is nearly binary — 1.000 when correct, 0.933 when wrong — so the 0.7 abstention threshold catches nothing, but a ~0.95 threshold would have screened 6/9 errors at zero coverage cost: abstention isn't broken, its THRESHOLD is miscalibrated per-model. (b) The 5 prompt variants disagreed on only 2/40 fields — but those 2 are exactly the persistently-wrong fields; variant DISPERSION is a well-calibrated error signal even though the majority vote itself picked the wrong value (3-2 for the wrong total). (c) The judge as an error detector: precision 0.25, recall 0.67 — it caught 6 real errors but withdrew 18 correct answers; all 24 rung-6 escalations trace back to it. K (runs/item) is irrelevant to these findings at temp 0; n_items only tightens their CIs.
- 2026-08-17 — INCIDENT + FIX: the app wrote every run to a single results.json, so a 3-item app run silently destroyed the finished 60-item benchmark. Recovered for free by replaying from the call cache (the cache is the real source of truth; results.json is derived). Runs now go to results/<domain>_<n>x<k>_<timestamp>.json and the dashboard lists them all. Lesson worth a line in the article: if your eval harness caches calls, results files are disposable — if it doesn't, one careless rerun costs you the experiment.
- 2026-08-17 — MINED THE FULL RUN (no new model calls; all four analyses replay from cache):
  (a) ERRORS ARE CONCENTRATED: address 100 wrong / 600, total 40, date 10, company 0. One field carries 2/3 of all errors — a per-field fix beats a whole reliability layer here.
  (b) ABSTENTION THRESHOLD FOUND: at tau=0.90 (not the default 0.70) coverage only drops 1.000 -> 0.979 while the error rate on kept answers falls 0.062 -> 0.043 and yield stays 0.938. About a third of the errors are screened at zero cost to correct answers. The default gate sits below almost every confidence this model emits, which is why rung 2 looked inert.
  (c) CORRECTION to the smoke-run claim: vote dispersion does NOT beat self-reported confidence as an abstention signal at scale. Thresholding on vote agreement costs yield fast (tau=0.7 -> yield 0.838) while self-confidence at tau=0.9 costs nothing. The smoke run's n=9 errors was too small to support the earlier claim.
  (d) THE STACK IS WORSE THAN ITS BEST LAYER: voting ALONE yields 0.946 — better than bare (0.938) and the best single layer — but voting inside the cumulative stack yields 0.772 because it inherits the judge's damage. Judge alone yields 0.905, below baseline. Best configuration measured: bare + voting (+ human = 0.988), not the top rung. This is the strongest argument for the composer view.
  (e) THE FLIP IS REAL: optimal rung by cost of a wrong answer — rung 1 up to ~$2, rung 2 at ~$5, rung 6 from ~$10 up. Article beat 5 has its numbers.
- 2026-08-17 — METRIC FIX: the dashboard now leads with YIELD = accuracy_on_answered x coverage (share of ALL fields correct), not accuracy. Reason: accuracy is a ratio over answered fields, so any layer that withholds answers raises it mechanically. On the full run the judge (rung 4) raised accuracy 0.938 -> 0.960 while yield COLLAPSED 0.938 -> 0.772: it deleted far more correct answers than errors. A user reading the accuracy line alone concludes rung 4 is better; it produces fewer correct fields. The app now shows yield first, warns when accuracy rises while yield falls, judges verdicts on yield, and puts the knee on the yield curve.
- 2026-08-17 — FULL RUN (60 items, K=10, granite4:micro-h). Yield by rung: 0.938 / 0.938 / 0.932 / 0.934 / 0.772 / 0.772 / 0.988. Only rung 6 (human) beats the bare model on yield. Rung 2's confidence gap widened with n: mean confidence 0.995 when correct vs 0.879 when wrong — a real signal, but 140/150 errors still sit above the 0.7 gate, so the threshold (not the mechanism) is what's miscalibrated. Confirms the smoke-run findings at scale.
- 2026-08-16 — Models: local-first via Ollama (data never leaves the machine); hosted APIs (Gemini first) are just registry entries behind the same OpenAI-compatible client. All calls disk-cached by (model, messages, temp, sample) → reruns free, runs resumable.

---

## CADEC pharmacovigilance track (`ladder/`) — owner A, 2026-08-22

The v16 plan retargets the ladder from SROIE receipts to CADEC adverse-event
posts. The two tracks coexist: `bench/` is the data-agnostic ladder with SROIE
as its demo dataset; `ladder/` is the CADEC instance, where rung 1 is grounded
in a real clinical vocabulary rather than in a JSON Schema. Only `ladder/` is
in scope below.

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

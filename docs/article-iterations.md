# InfoQ article — the build log

> A typeset version of this document, for reading away from the terminal, is
> `docs/article-build-log.html` (published privately as a Claude artifact).

Raw material for the article, organised the way the piece needs it rather than
the way the work happened. `decisions.md` is the chronological log; this is the
narrative layer on top of it, with the numbers pulled forward and the process
beats — what we tried, what the data contradicted, what we changed — made
explicit, because those are the parts that cannot be reconstructed later.

Two tracks exist. **Track 1** is the data-agnostic ladder with SROIE receipts as
its demo dataset (`bench/`, shipped, full 60×10 run measured). **Track 2** is the
CADEC pharmacovigilance instance (`ladder/`, owner A's half built and measured;
the model-facing rungs are owner B's and outstanding). The article can lead with
either. Section 3 argues for leading with track 2's rung-1 result and using
track 1's yield trap as the second beat.

---

## 1. The thesis, in one paragraph

Every LLM agent is roughly 10% model and 90% harness, and that harness gets
built by intuition: teams stack retries, validators, judges, voting and human
review because each sounds like it should help. The seven layers are known. What
nobody publishes is the **measured trade-off per layer** — what each one buys, in
what currency, and where it stops being worth paying for. That curve is the
contribution. Everything else in the project exists to keep it clean.

---

## 2. The strongest findings, ranked

Numbers you can put in a pull-quote. Everything here is measured in this repo and
reproducible from the commands given.

### 2.1 A validation gate's leniency setting decides whether it protects you or lies to you

**The number: 19.0% vs 0.1%.**

Rung 1 sorts a record into REJECT (provably wrong), ACCEPT (the vocabulary uses
these very words) or BAND (plausible, unverifiable). The ACCEPT/BAND divider is
a lexical comparison between the quoted patient text and SNOMED's terms for the
predicted code, and it has an obvious knob: exact string equality, or token
containment.

Containment is the intuitive choice. Patients write "bit drowsy" where SNOMED
says "Drowsy"; being strict looks pedantic, and being lenient lifts the share of
a *perfect* answer set that rung 1 can settle for free from 43.1% to 54.5%.

Then we planted **near-miss codes** — a real, active clinical finding sharing its
head word with the right one, which is the confusion a normalisation model
actually makes ("Knee pain" where "Leg pain" belongs) — and asked what the gate
did with them:

| lexical setting | near-misses caught | near-misses **put in ACCEPT** | ACCEPT lane size on gold |
|---|---|---|---|
| `contained` | 0.1% | **19.0%** | 54.5% |
| `exact` | 0.1% | **0.1%** | 43.1% |

Neither setting *catches* near-misses — deterministic checks can't, and the plan
said so. But the lenient one actively **vouches for one near-miss in five**. It
does not fail to protect you; it hands you false confidence, because the span
text is a subset of the wrong concept's term.

We changed the default to `exact` and paid eleven points of free settlement for
it. The generalisable rule, and the one worth writing down: **for any validation
gate, measure the permissive setting's false-vouch rate on planted near-misses
before you ship it — the intuition points the wrong way.** "Be lenient with
colloquial input" is a reasonable instinct that, here, converts a gate into an
endorsement machine.

*Reproduce:* `python -m ladder.probe --split all --lexical-mode contained|exact`

### 2.2 Deterministic checks are exact, and blind

Same probe, all six corruption classes, whole corpus, 8,666 records each:

| planted error | rung 1 rejects |
|---|---|
| hallucinated code (in no release) | **1.000** |
| span shifted two characters | **1.000** |
| fabricated quote | **1.000** |
| real code, wrong branch of the hierarchy | **1.000** (reaction records) |
| random plausible clinical finding | 0.000 |
| near-miss clinical finding | 0.001 |

Deterministic checks are not "pretty good" at their job. On the classes they are
designed for they are *exact*, at zero model cost. And on the one class that
matters most — a real, well-typed, wrong code — they are blind by construction,
because the code is not in the source text and nothing mechanical can put it
there.

That reframes the whole ladder, and it is a better frame than "a stack of
improvements": **rung 1 is a free, exact filter for a specific set of failure
modes, and everything above it is a paid resolver for the one class the filter
cannot see.** The interesting economic question is not "does rung 1 help" — it
does, for free — but what the paid rungs charge for the residue.

### 2.3 Over half of a perfect answer set is unverifiable

Zone occupancy when the *gold standard itself* is fed through rung 1:

    ACCEPT   3,926   43.1%
    BAND     5,173   56.8%
    REJECT      12    0.13%

Even with every answer correct, 57% of records land in "plausible, cannot
corroborate". That is the ceiling on how much of a batch a free layer can settle,
and it is the size of the pool the paid rungs have to work through — known before
a single token is spent. Worth stating as a planning tool: **run your
deterministic layer over your answer key first; the BAND fraction is your bill.**

### 2.4 The metric trap (track 1, SROIE)

**Accuracy is a ratio over answered items, so any layer that withholds answers
raises it for free.** On the full SROIE run the judge rung lifted accuracy
0.938 → 0.960 while **yield** — the share of *all* field slots that came out
correct — collapsed 0.938 → 0.772. It deleted far more correct answers than
errors. A team watching accuracy ships a layer that produces ~17% fewer correct
fields and reports it as an improvement.

Yield by rung: 0.938 / 0.938 / 0.932 / 0.934 / 0.772 / 0.772 / 0.988. Only the
human rung beat the bare model.

The dashboard now leads with yield and warns whenever accuracy rises while yield
falls. This is the single most transferable finding in the project: it costs
nothing to adopt and it invalidates a lot of published layer comparisons.

### 2.5 The stack is worse than its best layer (track 1)

Voting *alone* yields 0.946 — above the bare model and above every cumulative
rung except the human one. Voting *inside* the cumulative stack yields 0.772,
because it inherits the judge's damage. Judge alone yields 0.905, below baseline.

Cumulative stacking is the wrong default. Compose deliberately. This is the
argument for the configurator, and it is why the CADEC track keeps `rung_order`
as a manifest list rather than a hard-coded sequence.

### 2.6 Self-referential layers are inert against a confidently wrong model (track 1)

Format checks, self-confidence abstention and self-correction moved accuracy by
0.000 on the smoke run, and barely more at scale. All the rung-0 errors were
wrong *values* at self-reported confidence 0.9–1.0. The first gain came from the
first layer with an **independent** signal.

The CADEC track predicts the same shape for a different reason and will test it:
rung 3 (self-correction) is fired only by a rung 1 failure, so on this corpus it
will see almost nothing — the false-rejection floor is 0.13% and BAND records
give the model no fact to feed back. **Self-correction needs a stated fact, and
a validation gate that is honest about not knowing produces very few of them.**

---

## 3. Suggested structure

Six beats, practitioner voice. The reordering versus the original outline is
deliberate: lead with the finding that is cheapest for a reader to act on.

1. **Every agent is 90% harness, built by vibes.** The hook. Name the seven
   layers in one paragraph each; do not dwell — they are not the contribution.
2. **The metric trap.** §2.4. Short, concrete, immediately actionable, and it
   earns the reader's trust for the harder material. Figure: the yield-vs-accuracy
   divergence at the judge rung.
3. **What a free layer actually buys.** §2.2 and §2.3. Rung 1 is exact on its own
   classes, blind on the interesting one, and leaves 57% of even a perfect answer
   set unverifiable. Reframe: free filter + paid resolvers, not a stack of
   improvements.
4. **The gate that vouches for the error.** §2.1. The strongest single number,
   and a process story: the obvious setting, the measurement, the reversal. This
   is where the article earns its "we measured it" claim.
5. **The flip.** Whether withholding is worth it depends entirely on your cost of
   a wrong answer versus a missing one; the optimal rung moves with your
   economics (rung 1 below ~$2 per error, rung 2 at ~$5, rung 6 from ~$10 on the
   SROIE run).
6. **Decision rules + the tool.** Compose deliberately, not cumulatively.
   Calibrate the abstention gate per model before concluding the layer does not
   work. Run your deterministic layer over your answer key before you trust it.
   Measure the permissive setting's false-vouch rate.

**The process section** — §4 below — is the differentiator. Most measurement
articles present the finished number. The value here is in the corrections, and
six of the entries below are things that were wrong and got fixed.

---

## 4. Implementation iterations — what we changed, and why

This is the section the article should not skip. Ordered by how much it moved the
result.

### 4.1 The plan said negation was a free win. The corpus said it rejects 4.7% of correct answers.

**What the plan said.** Negation gets its own boxed section: a cue list and a
window catch "so far no gastric problems" extracted as a reported reaction, at
zero cost, and it should be logged as its own rejection reason because a system
that gets codes right and polarity wrong is dangerous in a way F1 hides.

**What we found.** Replaying the check over CADEC's own annotations rejected
**427 gold-correct mentions (4.7%)**, from two independent causes.

First: the plan's worked example is post `ARTHROTEC.1`, and CADEC annotates
`gastric problems` in that very sentence as an ADR coded `162076009`. **CADEC
annotates a mention regardless of polarity.** The check is clinically right and
disagrees with the answer key.

Second: NegEx scope rules misfire badly on forum prose. Real fires from the
corpus — "I can't describe the horrible stomach pain", "I can finally clean my
house without pain", "many doctors deny that there is a connection between joint
pain, muscle aching, fatigue etc and Lipitor". Each negates something, and in
none of them is it the mention.

**What we changed.** Negation was demoted from a rejection to an audit flag. The
detector still runs, the rate is still reported, the cue is still logged —
polarity is a real safety class — but under this gold standard it may not reject.
`negation_action: "reject"` reproduces the plan as written, and costs 427 gold
mentions.

**Why it belongs in the article.** It is the cleanest example of a check that is
*correct* and still wrong to enforce, because the ground truth encodes a
different policy. Nobody discovers this from the plan; you discover it by running
your check against the answer key before you run it against a model.

### 4.2 The semantic-type check was rejecting retired concepts, not wrong ones

**What we found.** The check "is this code a descendant of |Clinical finding|?"
rejected **416 gold-correct reaction mentions**, and 413 of them for a reason with
nothing to do with semantics: |Knee pain| (63 mentions), |Weakness of limb| (53),
|Mentally dull| (38), |Bloating symptom| (34) — all clinically right, all
**retired from SNOMED since CADEC was coded in 2015**.

The mechanism: when SNOMED retires a concept it also retires that concept's is-a
relationships. A hierarchy walk over active relationships cannot place a retired
concept anywhere — and "cannot place" was being read as "is in the wrong branch".

**What we changed.** The index now stores the |Clinical finding| descendant set
twice: once over active is-a rows (129,675 concepts) and once over every is-a row
ever published (177,603). `finding_status()` returns `finding` / `not_finding` /
`unknown`, and rung 1 may reject only on a positive `not_finding`. **Absence of
evidence is not evidence of a wrong slot.**

Residual after the fix: 3 rejections in 9,111, and all three are the check
working — |Eruption| (a morphologic abnormality) coded for "Abdominal rash", an
observable entity coded for "abdominal pressure".

### 4.3 "Does the code exist?" is ambiguous, and the two readings differ by 11%

Of the 1,046 distinct SNOMED codes CADEC uses, in the 2026-07 release:

    927   active
    115   present but INACTIVE (11%)
      4   absent entirely

Reading `exists` as "active in the current release" rejects **6.9% of the gold
standard**. `exists()` therefore means present in the release, active or not, and
inactivity is recorded as an audit fact rather than a verdict. `reject_inactive`
is a manifest setting, because it is exactly the kind of choice that silently
moves the headline number.

The general point: **vocabulary drift is a measurement artefact that looks
exactly like a model error.** Any benchmark that normalises to a versioned
terminology and does not pin the release is reporting the terminology's release
notes as its model's performance.

### 4.4 The gate's own error floor: 9.3% → 0.13%

The three fixes above, in aggregate:

| | false rejections on gold |
|---|---|
| rung 1 as the plan specifies it | 845 / 9,111 = **9.3%** |
| after the three fixes | 12 / 9,111 = **0.13%** |

A validation gate with a 9% false-positive rate does not measure a model; it
manufactures errors, and every rung above it inherits them. The residual 12 are
5 codes absent from the release, 4 genuine typos in CADEC's own annotations, and
3 real gold miscodings.

**The method is the transferable part, and it costs nothing:** replay your
deterministic layer over your answer key. Every rejection there is false by
construction, so you get the gate's false-positive rate exactly, before any model
output exists and without spending a token. We would not have found any of the
three causes by inspecting model output — they would have shown up as a
plausible-looking 9% rejection rate and been written up as a finding.

### 4.5 A filtering rung 1 makes every rung above it unattributable

**What we had.** Rung 1 rejected records, and everything above it ran on the
survivors — which is what the plan's flow implies and what almost every
"validation layer" does in practice.

**Why that's a measurement bug.** If rung 1 removes the records it dislikes,
rung 4's judge is graded on a set rung 1 already cleaned. Rung 4's marginal
contribution is then partly rung 1's, and no amount of care further up recovers
it. The same confound runs through rungs 3, 5 and 6.

**What we changed.** Rung 1 now *judges* without *routing*: the verdict is
recorded, counted and reported, the record's zone is untouched, and rungs 3-6 see
the full set rung 0 produced. Every rung becomes a single-rung ablation on
identical input. Rung 2, which runs last, is where a rung 1 verdict is finally
allowed to cost coverage — so the change **defers** rung 1's cost rather than
cancelling it, and a test asserts both modes reach the same end state.
`mode: "gate"` reproduces the original flow in one manifest line.

**Why it belongs in the article.** It is the same lesson as "the stack is worse
than its best layer" (§2.5) arriving from the other direction. Cumulative
stacking is not just a bad *default* for production — it is a bad *experimental
design*, because it destroys attribution. If you want to know what a layer buys,
the layers below it must not be allowed to change its input.

Two mechanical notes worth a line, because they are what made it cheap: the
ledger grew a `verdict` column (append-only, so nothing downstream broke), and
reporting reads verdicts for rung 1 and zones for every other rung. Conflating
the two would have reported an observational rung 1 as having done nothing —
silently dropping the rung-1 rejection rate, which is the project's 2:20
milestone.

### 4.6 A vocabulary made from the answer key scores 1.000 and means nothing

**What happened.** The plan wants MedDRA as a second vocabulary. The only MedDRA
artefact available ships *inside* CADEC and is derived *from* it, so the first
pass left it out as leakage. The derived columns — `occurrences`, `posts`,
`example_mentions` — were then deleted, which looks like it fixes the problem.

**What we measured.** It does not. The table is **666 codes, all 666 of which
appear in CADEC's gold annotations and none of which do not** — the answer key's
code inventory, about 3% of MedDRA's preferred terms. Deleting the columns
removes the *evidence* of derivation, not the derivation.

The two measurements that make it concrete:

| | `meddra_check="flag"` | `meddra_check="reject"` |
|---|---|---|
| false rejections on gold (of 9,111) | 0 | **3** |
| hallucinated MedDRA code caught | 0.002 | **1.000** |

Both numbers are the leak. The check looks *harmless* on gold — three false
rejections — precisely because the table **is** the gold. And it looks
*miraculous* on planted errors — perfect detection — because anything outside
the 666 is rejected by construction. A real MedDRA release would score somewhere
in between, and neither of these numbers predicts where.

**What we changed.** MedDRA is wired in properly — a table, a sixth rung-1 check,
fixture cases, a probe class — and `meddra_check` defaults to `"flag"`: the
verdict is recorded and counted in rung 1's comparison, and is not a rejection
reason. `"reject"` is one manifest line away, and the leakage figure prints
wherever the number appears. Point the manifest at a subscription release and the
caveat goes away with it.

**Why it belongs in the article.** A 1.000 is the most seductive number a
benchmark can produce, and this one is worthless. The general form: *if your
validator's reference data was derived from your evaluation data, your validator
will score perfectly and tell you nothing.* The tell is cheap to check — count
how many entries in your reference list never appear in your answer key. Here
the answer was zero.

### 4.7 The same check, two vocabulary sources, 24% disagreement

Merging the partner's scaffolding put a second implementation of rung 1's
vocabulary questions in the tree: `bench/vocab.py` queries EBI OLS4 over the
network — free, no key, no 5 GB download, which is a genuinely better
onboarding story than ours. Same three questions, interchangeable in principle.

Cross-checking them over all 8,666 CADEC gold mentions that carry a code:

| | | |
|---|---|---|
| 6,593 | 76.1% | active international — both agree |
| 1,420 | 16.4% | active, but AU-extension only — invisible to OLS4 |
| 648 | 7.5% | retired — OLS4 indexes active concepts only |
| 5 | 0.1% | absent from both |

**An OLS4-backed `exists()` calls 23.9% of the answer key hallucinated.** The
local release calls 5 of 8,666 hallucinated. Reactions 5.9% affected, drugs
**100%** — CADEC codes drugs to AMT, the Australian Medicines Terminology, which
is an extension module the international release simply does not contain.

Two things make this worth a paragraph in the article rather than a footnote.

First, **it is not a bug in either implementation.** Both correctly report what
their source knows. The source decides the answer, and a reader who swaps one
free vocabulary API for another gets a completely different rung 1 rejection rate
with no code change and no error message. The version pin in the manifest is not
bureaucracy; it is the difference between 0.06% and 24%.

Second, **it reproduces §4.2 and §4.3 from a third direction.** Retired concepts
again: OLS4 drops them, and an active-only hierarchy walk cannot place them.
Three independent ways to get the same 7% wrong, all of them looking exactly like
model error. If a measurement study has one recurring failure mode, on this
corpus it is *the vocabulary moved and nobody noticed*.

The offline classifier predicted OLS4's answer on 40/40 sampled codes, so the
figure is measured, not estimated: `python -m ladder.vocab_crosscheck --live 40`.

### 4.8 The plan's record shape encoded the claim its own safety constraint forbade

The plan's example record pairs `drug_text` with `reaction_text` in one object.
Its own safety constraint 3 says drug and reaction mentions are extracted
independently and the system never emits "drug X causes Y". CADEC annotates them
independently too.

Pairing them in the record makes every output a causal claim by construction. We
changed the unit to **one record = one mention**, with an `entity_type` of
reaction or drug.

The same reasoning killed a second thing: CADEC labels four clinical entity
types, and the most common is `ADR` — *adverse drug reaction*, which is a causal
attribution made by a human annotator. Asking a model to reproduce that label is
asking for exactly the causal claim the constraint forbids. The four clinical
types collapse to `reaction`; only reaction-vs-drug is asked for or scored.

**Article angle:** safety constraints written as prose get contradicted by the
data model three pages later. The ones that hold are the ones with no way to
express the forbidden thing — a missing interface, not a warning.

### 4.9 Corpus facts the plan got wrong, and what they cost

| plan says | corpus says | consequence |
|---|---|---|
| "~6,754 entity mentions" | **9,111** in v3's `sct/` files | manifest records the real number |
| "CADEC codes reactions, not drugs; no drug codes to score" | **1,657 of 1,800** drug mentions carry codes, mostly AMT products | rung 1 had to learn that a product concept is not a semantic-type error, or it rejects every correct drug code (measured: `finding_scope: "all"` costs 1,423 gold mentions) |
| "strict = exact SCT code equality" | **252 mentions are post-coordinated** (`A + B`, needs both), 3 are disjunctions | the gold rule is undefined for 2.8% of the corpus; rewritten as "the predicted code is IN the gold set", with the affected records flagged |
| the `concept_less` gift | real — **445 mentions** — but the literal is uppercase | grepping for `concept_less` finds nothing; a nice ten-minute trap |
| BioPortal is the critical path | a **local SNOMED RF2 release** removes the dependency entirely | see §4.7 |
| MedDRA as a secondary check | the only MedDRA artefact available ships *inside* CADEC and is derived *from* it | using it as an existence check is precisely the leakage the plan's own §4.1 warns against; MedDRA is parsed, carried, and not scored |

Also worth a line: **1,065 mentions (11.7%) have discontinuous spans**, and 45 of
them quote the segments in reading order rather than offset order ("swelling
feet" for `[feet][swelling]`). A span-grounding check that compares string
concatenations calls the answer key ungrounded. Ours compares token bags.

And: **CADEC's own gold fails span grounding 4 times in 9,111** — `rena  failure`,
`microabrasion` vs `microabrasions`, `pain i stomach`. That 0.04% is the floor the
cheapest check on the ladder can never get below on this corpus. Every benchmark
has one; almost nobody reports it.

### 4.10 Replacing the critical-path dependency instead of mitigating it

The plan names vocabulary lookup as the critical path, puts "no working
vocabulary lookup" at the top of its risk table, and routes it through the
BioPortal API with a fallback chain and a disk cache.

A local RF2 release removes the risk rather than mitigating it: no key, no rate
limit, no network inside the measurement loop, and the version pin is a directory
name rather than a promise. `ladder/registry.py --build` turns the 5 GB release
into a 365 MB SQLite index in about eight seconds; lookups are microseconds, so
the whole-corpus characterisations in §2 are affordable in the first place.

**Article angle:** the highest-value move on a risk register is often to delete
the risk's cause, not to plan around it. The plan's mitigation (cache every
response, never call twice) is good engineering for a dependency that did not
need to exist.

### 4.11 Process choices that paid for themselves

- **The fixture gate caught our own wrong expectation on its first run.** Ten
  hand-made records against one real archived post, several deliberately broken.
  The failure was a case we had asserted should ACCEPT: "little blurred vision"
  coded `246636008`. SNOMED's terms for that concept are Foggy / Hazy / Misty /
  Cloudy vision — it never uses the word "blurred". Correct code, zero lexical
  evidence, correctly BAND. The plan's own §1 example record has this case with
  `zone: BAND, reason: colloquial_no_lexical_match`, and we had still got it
  wrong in the fixture.
- **Every open choice became a manifest setting, not a default argument.** Four
  settings in rung 1 each move the rejection rate by 5–15 points. A number
  produced by a hard-coded opinion is not reproducible even by its author.
- **Splits are by document, not by mention.** Mentions from one post share its
  wording and its annotator; a mention-level split leaks. CADEC is 80% Lipitor,
  so the split is stratified by drug family — an unstratified test split would be
  almost entirely one drug, and the human-agreement ceiling the plan cites was
  measured on the other one.
- **Missing rungs are reported, never faked.** Half a ladder honestly labelled is
  a result. The scorer is injected the same way, so accuracy columns are written
  empty rather than guessed.
- **An earlier incident, worth one line (track 1):** the app wrote every run to a
  single `results.json`, so a 3-item run silently destroyed a finished 60-item
  benchmark. It was recovered for free by replaying from the call cache. Lesson:
  *if your eval harness caches model calls, results files are disposable; if it
  does not, one careless rerun costs you the experiment.*
- **A finding we published to ourselves and then retracted (track 1):** on a
  10-item smoke run, cross-prompt vote dispersion looked like a better abstention
  signal than self-reported confidence. At n=60 it is not — thresholding on vote
  agreement costs yield fast while confidence at τ=0.90 costs none. Nine errors
  was too small a base. Good honest-aside material.

---

## 5. Figures, with captions written now

Discipline from the plan, and it holds: if you cannot write the caption, the
result is not clear yet.

1. **Yield vs accuracy across the seven rungs (track 1).**
   *"At the judge rung accuracy rises and yield falls. The layer improved the
   metric most teams watch and reduced the number of correct fields the user
   actually receives by 17%."*
2. **Rung 1 detection profile — six planted error classes (track 2).**
   *"Deterministic checks are exact on the classes they are built for and blind
   to the one that matters. Rejection rate by planted error type, 8,666 records
   per class, zero model calls."*
3. **The lexical knob (track 2).**
   *"Token containment lifts the free-settlement lane from 43% to 55% of a
   perfect answer set, and puts 19% of near-miss errors into ACCEPT — records the
   gate actively vouches for. Exact matching puts 0.1% there."*
4. **Zone occupancy on the gold standard (track 2).**
   *"Even when every answer is correct, 57% of records are unverifiable by string
   comparison. That fraction is the bill the paid rungs have to work through, and
   it is knowable before the first token is spent."*
5. **The gate's own error floor, before and after (track 2).**
   *"Rung 1 as specified rejected 9.3% of the answer key. Three fixes — negation
   demoted to a flag, retired concepts distinguished from misplaced ones,
   inactive codes distinguished from nonexistent ones — took it to 0.13%."*
6. **Net utility by cost-of-a-wrong-answer (track 1).**
   *"The optimal rung is a function of your economics, not of the model: rung 1
   below ~$2 per error, rung 2 at ~$5, human review from ~$10 up."*

---

## 6. Limitations to state plainly

- **The MedDRA check cannot be trusted as configured.** Its reference table is
  derived from the answer key. It is reported, not scored, and any number from
  it carries the caveat.
- **Track 2 is half a ladder.** Rungs 0, 3, 4, 5 are owner B's and outstanding.
  Everything in §2.1–2.3 is a property of the *gate*, measured against the gold
  standard and against planted errors — not a model result. Say so; it is a
  stronger claim for being narrower.
- **Track 1 is one model on one task** (granite4:micro-h, SROIE). The
  contribution is the method and the shape, not a leaderboard.
- **Determinism was 1.000 at every rung on the local model** — greedy decoding at
  temperature 0 is exactly reproducible, so that axis is free locally and only
  becomes interesting on hosted APIs with batching nondeterminism. The
  cross-model run is not done.
- **Contamination.** CADEC is public and from 2015 and is almost certainly in
  pretraining. It inflates rung 0, which makes the ladder's gains look *smaller* —
  so the conclusion is conservative. The v2/MultiADE slice is the check, and is
  not run yet.
- **Human ceiling.** Strict span agreement between CADEC's own annotators was
  about 68.7 on the diclofenac posts. A system near 0.69 strict span F1 is at the
  noise floor of the answer key, not underperforming.
- **The abstention target is thin** at 60 test documents: 7 `CONCEPT_LESS`
  mentions in 393. Abstention accuracy cannot be separated from noise there.
- **`tau` is 0.0** — the confidence gate is off until a real rung-0 confidence
  distribution exists to calibrate against.
- **Near-miss corruption is synthetic.** The near-miss pool is built from
  concepts sharing a head word, which is a proxy for the confusions a
  normalisation model makes, not a sample of them. The 19% is a property of the
  check under a plausible error model, and should be quoted that way.

---

## 7. Reproduce every number here

```bash
python -m ladder.registry --build --release data/SnomedCT_Release_AU1000036_20260731
python -m ladder.run init
python -m ladder.run gate
python -m ladder.calibrate --split all --sweep --json out/rung1_floor.json
python -m ladder.probe --split all --json out/rung1_detection.json
python -m ladder.probe --split all --lexical-mode contained --json out/rung1_detection_contained.json
python -m ladder.probe --split all --meddra-check reject --json out/rung1_detection_meddra.json
python -m ladder.run ladder --split test --source gold --run-id gold_control
python -m ladder.vocab_crosscheck --live 40
python scripts/preflight.py --history
```

Track 1's numbers are in `docs/decisions.md` and reproduce from the cached run in
`results/`. Neither corpus is redistributable — see `docs/licences.md`.

# InfoQ article — the build log

> A typeset version of this document, for reading away from the terminal, is
> `docs/article-build-log.html` (published privately as a Claude artifact).

Raw material for the article, organised the way the piece needs it rather than
the way the work happened. `decisions.md` is the chronological log; this is the
narrative layer on top of it, with the numbers pulled forward and the process
beats — what we tried, what the data contradicted, what we changed — made
explicit, because those are the parts that cannot be reconstructed later.

Everything here is measured on **CADEC** — patient-reported adverse-event posts,
normalised to SNOMED CT. Owner A's half of the ladder is built and measured; the
model-facing rungs (0, 3, 4, 5) are owner B's and outstanding, so every number
below is a property of the *deterministic* layer, measured against the gold
standard and against planted errors. That is a narrower claim than a full ladder
curve, and a stronger one for being checkable.

An earlier data-agnostic track was retired on 2026-08-22 along with its results;
nothing here is derived from it.

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

---

## 3. Suggested structure

Five beats, practitioner voice. The ladder is not fully measured yet, so the
piece leads with what *is*: a validation gate characterised end to end before a
single model call.

1. **Every agent is 90% harness, built by vibes.** The hook. Name the seven
   layers in a paragraph each and move on — they are not the contribution.
2. **You can measure a layer before you build the layer above it.** §4.4's
   method: replay your deterministic gate over the answer key, where every
   rejection is false by construction. It costs nothing and it caught three
   faults that would otherwise have shipped as a plausible 9.3% rejection rate.
3. **What a free layer actually buys.** §2.2 and §2.3. Rung 1 is exact on its own
   error classes, blind on the interesting one, and leaves 57% of even a perfect
   answer set unverifiable. Reframe: a free, exact filter plus paid resolvers —
   not a stack of improvements.
4. **The gate that vouches for the error.** §2.1. The strongest single number,
   and a process story: the obvious setting, the measurement, the reversal.
5. **Decision rules.** Measure the permissive setting's false-vouch rate before
   shipping it. Pin your vocabulary release — §4.7 shows the same check giving
   23.9% different answers across two sources. Don't let a validation layer
   filter the input to the layers you are trying to measure (§4.5). And check
   whether your reference list came from your answer key (§4.6).

Beats 2–4 are the article. Beat 5 is what a reader takes to work on Monday.

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

**Why it belongs in the article.** Cumulative stacking is not just a
questionable *default* for production — it is a bad *experimental design*,
because it destroys attribution. If you want to know what a layer buys,
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
- **The call cache is architecture, not convenience.** Every model call is keyed
  and written to disk, so a re-run costs nothing, an interrupted run resumes, and
  results files become disposable derivatives rather than the only copy of an
  experiment.

---

## 5. Figures, with captions written now

Discipline from the plan, and it holds: if you cannot write the caption, the
result is not clear yet.

1. **Rung 1's own error floor, before and after (§4.4).**
   *"The gate as specified rejected 9.3% of the answer key. Three fixes —
   negation demoted to a flag, retired concepts distinguished from misplaced
   ones, inactive codes from nonexistent ones — took it to 0.13%."*
2. **Rung 1 detection profile — six planted error classes (§2.2).**
   *"Deterministic checks are exact on the classes they are built for and blind
   to the one that matters. Rejection rate by planted error type, 8,666 records
   per class, zero model calls."*
3. **The lexical knob (§2.1).**
   *"Token containment lifts the free-settlement lane from 43% to 55% of a
   perfect answer set, and puts 19% of near-miss errors into ACCEPT — records the
   gate actively vouches for. Exact matching puts 0.1% there."*
4. **Zone occupancy on the gold standard (§2.3).**
   *"Even when every answer is correct, 57% of records are unverifiable by string
   comparison. That fraction is the bill the paid rungs have to work through, and
   it is knowable before the first token is spent."*
5. **The same check, two vocabulary sources (§4.7).**
   *"An OLS4-backed existence check calls 23.9% of the answer key hallucinated;
   a local release calls 5 of 8,666. Neither implementation is wrong — the source
   decides the answer."*

Still to come, once owner B's rungs land: the marginal cost curve (tokens and
human reviews per prevented error, per rung) — the headline the whole ladder
exists to produce.

## 6. Limitations to state plainly

- **The MedDRA check cannot be trusted as configured.** Its reference table is
  derived from the answer key. It is reported, not scored, and any number from
  it carries the caveat.
- **This is half a ladder.** Rungs 0, 3, 4 and 5 are owner B's and outstanding.
  Everything in §2 is a property of the *gate*, measured against the gold
  standard and against planted errors — not a model result, and not yet a
  cost curve. Say so; it is a stronger claim for being narrower.
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

The corpus is not redistributable and the SNOMED release needs an affiliate
licence — see `docs/licences.md`. Every figure above comes from the commands
here; nothing is quoted from a pipeline that is no longer in the repo.

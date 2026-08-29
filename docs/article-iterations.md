# InfoQ article — the build log

> A typeset version of this document, for reading away from the terminal, is
> `docs/article-build-log.html` (published privately as a Claude artifact).

Raw material for the article, organised the way the piece needs it rather than
the way the work happened. `decisions.md` is the chronological log; this is the
narrative layer on top of it, with the numbers pulled forward and the process
beats — what we tried, what the data contradicted, what we changed — made
explicit, because those are the parts that cannot be reconstructed later.

Everything here is measured on **CADEC** — patient-reported adverse-event posts,
normalised to SNOMED CT. **The ladder is now measured end to end** (2026-08-26):
all seven rungs ran cold, in order, on the 60 held-out test documents, under a
frozen configuration, exactly once — run id `phaseF-test-1` — and nothing was
re-run after the numbers were seen. §2A below is the deterministic gate,
characterised before a model call existed; §2B is the model-facing ladder,
measured through five phases on dev and settled on test. The cost curve §5 once
listed as "still to come" is now the headline.

An earlier data-agnostic track was retired on 2026-08-22 along with its results;
nothing here is derived from it.

**Rung numbering.** Sections written before 2026-08-23 use the old rung ids in
their prose; the mapping is old 3→2, 5→3, 2→5 (0, 1, 4, 6 unmoved). Everything
dated after uses the final numbering: 0 bare LLM, 1 deterministic, 2
self-correction, 3 voting, 4 LLM judge, 5 abstention, 6 human loop.

---

## 1. The thesis, in one paragraph

Every LLM agent is roughly 10% model and 90% harness, and that harness gets
built by intuition: teams stack retries, validators, judges, voting and human
review because each sounds like it should help. The seven layers are known. What
nobody publishes is the **measured trade-off per layer** — what each one buys, in
what currency, and where it stops being worth paying for. That curve is the
contribution. Everything else in the project exists to keep it clean.

Having measured it, the answer is not the one the premise expects. The ladder
made errors **visible**, not fewer. The layers that survive measurement are the
free deterministic check and the person; the paid model rungs, in composition,
moved nothing they could not also have broken — and two of them turned out not
to be wired to anything at all (§2C). That is the finding, and it is a negative
one. A build log that only reported the layers that worked would be the exact
artefact this project exists to argue against.

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

*Findings 2.1–2.3 are the gate, measured before any model call. Findings
2.4–2.9 are the model-facing ladder, measured through Phases A–F
(2026-08-24 → 26). Final rung numbering throughout.*

### 2.4 The ladder, run once on held-out data — what each rung actually bought

**The number: F1 0.204 shipped, 77% of records routed to a person.**

The whole point of the project, in one table. 60 held-out test documents,
frozen configuration, one run (`phaseF-test-1`), nothing re-run after the
numbers were seen. Extractor `gpt-oss:20b` local, judge `granite4:micro-h`
(2B — the caveat is §2.7). Shipped result, exact span / strict code:
**F1 0.204 [0.150–0.260]**, overlap 0.215; detection F1 0.521 exact / 0.808
overlap; coding accuracy on matched spans 0.392 / 0.266. Five outcomes
(exact): 60 correct, 0 outdated, 91 abstained, 2 incorrect, 0 modernised.

Per rung, what the money bought:

| rung | what happened | cost |
|---|---|---|
| 0 bare LLM | 314 records, answered-accuracy 0.370 | 194.5k tokens, p95 57 s/call |
| 1 deterministic | ACCEPT 72 / BAND 226 / REJECT 16 (5.1%, local-rf2) | free, 0.15 s total |
| 2 self-correct | **fired zero times** — every REJECT was `schema_invalid`, which is not a statable fact | 0 |
| 3 voting | re-found 8 unanswered records; **all 8 wrong**; correct count unchanged | 536.5k tokens — 2.8× rung 0 |
| 4 LLM judge | pass 202 / fail 110 | 113.6k tokens |
| 5 abstention | ships 72 records at 0.833 accuracy; errors/100 fall 59.6 → 3.8 | withdraws 242 answers, 45 of them already exactly correct |
| 6 human loop | routes the residue | **242 of 314 records to a person** (77.1/100) |

The curve is not a staircase of improvements. On this run, one paid rung was
net negative (§2.6), one never fired, and the two that clearly work — the free
gate and abstention — work by *refusing*, which is exactly the cost the third
measure exists to count. Test came out above the re-derived dev baseline on
all three layers (dev shipped F1 0.131), with no tuning ever touching test:
generalisation plus split luck, in that order.

### 2.5 Asking a model to recall a nine-digit code is broken, not weak

**The number: F1 0.018 vs 0.171, and the broken step costs MORE tokens.**

Rung 0 is a three-step prompt study with identical scope: S0 asks the model to
state the SNOMED code from memory, S1 asks for names that are resolved against
the vocabulary, S2 retrieves a candidate menu and asks for a pick. On dev
(gpt-oss:20b): S0 scored **0.018**, S1 0.171, S2 0.209 exact — S0 is ten times
worse than S1 for more tokens (44.0k vs 36.1k), and it is the only step that
fails to parse (5 of 40 documents). The one thing a language model cannot do —
recall a nine-digit identifier — is also the most expensive way to ask.

An abstention hatch reduces fabrication but does not remove it: S0 was allowed
to answer null for unknown ids, did so 12.4% of the time, and still emitted a
nonexistent code beside a correct label. And the retrieval that fixes this is
not presentation-neutral: alphabetising S2's candidate menu — changing
*nothing* but the order — cost 10–12 points of coding accuracy at byte-identical
detection. Small models anchor on early slots; the retriever's best-first
ranking is doing real work.

### 2.6 Voting can only shuffle what is below it — and its numbers are samples

**The number: +5 net correct on dev, −0 (8 found, 8 wrong) on test.**

Rung 3 resamples each document k times at temperature and takes majorities.
As first built, it destroyed verified answers: votes matched by exact span key
never aligned across temperature resamples (206 of 240 records got no vote),
and a "majority" of one — the only sample that re-found a mention — overwrote
a vocabulary-verified code with its opposite (|Analgesia| over |Pain|). Three
repairs, each TDD'd: match votes by span overlap one-to-one, draw every sample
through rung 0's own configured path so the votes come from the distribution
being voted on, and require at least two sightings before a change.

After repair, on dev: hallucinated overwrites gone, zero correct codes
destroyed, +5 net correct — for 2.6× rung 0's tokens. On the one test draw:
coverage rose (8 records re-found), correct count did not move, answered
accuracy fell 0.370 → 0.360. **A voting rung's contribution is a sample, not
a property** — cite the run id with every number, and price the draw honestly:
it is the most expensive rung on the ladder.

### 2.7 The judge measured, the better judge rejected, and the signal that lived in an accident

**The number: 167 of 240 records unjudged — by the domain-adapted model.**

The judge must be a different family from the extractor, and the only local
option is 2B judging 20B — the wrong way round, stated with every rung 4
number. The obvious fix, a domain-adapted 7B (BioMistral), was installed,
harness-repaired twice, and rejected on measurement: it answers EOS after `{`
on prompts past ~430 tokens (167/240 unjudged), every verdict it did parse
was "fail" with no correctness separation, and its confidence was a flat 0.0.
**Domain adaptation does not buy instruction-following.**

The sharper finding came from re-judging the incumbent through a repaired
prompt path: an accidental duplication (the post pasted twice) turned out to
be load-bearing — with it, granite's pass/fail correctness split was
28.0%/15.6%; without it, 25.4%/23.6% — no separation. Same lesson as the menu
order in §2.5: **for small models, prompt form is part of the measurement**,
and a signal that lives in an accident is not a signal an article can stand
on. The duplication stayed fixed; rung 4's test-split verdicts carry the
caveat.

### 2.8 Abstention's bill is countable, and a person could pay it down to 0.99

**The number: 242 of 314 routed; the ceiling above them is 0.444, all spans.**

Rung 5 withdraws every answer the stack could not corroborate; rung 6 is what
happens to the queue. Its headline cost is deliberately a COUNT — records
routed to a person — because minutes here are declarable, not measurable
(77.1 per 100 on test; the manifest's 2.0 min/record makes that 484 minutes
*at the declared rate*, a phrase that never becomes "measured").

Two measurements make the queue legible. First, its composition: rung 5
withheld 45 exactly-correct answers on test (86 by overlap) — the price of
taking errors/100 from 59.6 to 3.8. Second, its ceiling, measured on dev with
an oracle desk (gold-derived resolutions, refused on the test split by
design): a perfect reviewer takes shipped F1 from 0.131 to **0.444** and
coding accuracy on matched spans from 0.291 to **0.990** — with detection
unchanged. Read that pair carefully: after a perfect code-picking human, the
entire remaining gap is **span boundaries**, which neither the desk nor any
code-level rung can fix. The next rung worth building is boundary repair, and
this number is how we know.

### 2.9 Retrieval's gain decomposes — and the decomposition inverts with k

**The number: 61.8% → 86.1% recall@20, split +3.3 corpus / +21.0 scoring.**

S2's dense retriever beats the lexical one by 24 points of recall@20 — but
the two also search different corpora (1.8M description rows of every semantic
type vs 228k findings-and-disorders keywords), so the headline confounds two
changes. Running the lexical scorer over the dense corpus separates them: at
k=20 the gain is +3.3 from the corpus and +21.0 from dense scoring. At k=1 it
*inverts* — +29.1 corpus, +15.2 scoring: filtering to the right semantic types
is what clears the top slot, and better scoring is what fills the rest of the
menu. Two retrievers, kept side by side, because a recall number under one is
only interpretable next to the other.

---

## 2C. The audit of rungs 1-6 — ask what reads what

Everything in §2 measures a rung. This section measures the **composition**, and
it is where the strongest negative results are. All of it is dev-side: Phase F
spent the test split on 2026-08-26 and this repo has no held-out data left, so
§2.4's numbers stand exactly as reported and nothing here re-opens them. Where a
Phase F artifact appears below it is a read-only counterfactual, labelled.

### 2C.1 Every deferral in the ladder terminates in a field nothing reads

**The number: three rungs defer to rung 5; rung 5 reads none of them.**

Rungs 2, 3 and 4 each decline to act on their own evidence, on an argument that
is correct and that this project made loudly: a rung which routes confounds
every rung above it, so a rung should record its judgement and let the rung that
owns coverage act. Each names rung 5, in its own docstring:

| rung | writes | says |
|---|---|---|
| 2 self-correction | `checks["r2_declined"]` | "rung 5 owns abstention and reads `checks['r2_declined']`" |
| 3 voting | `checks["r3_unanimous_none"]` | "EVIDENCE for rung 5, not an action here" |
| 4 LLM judge | `checks["r4_verdict"]` | "record ... and let rung 5 act" |

`r5.decide()` reads the zone, `r1_verdict`, `r1_reason` and `rec.confidence`.
Its entire configuration is `{tau, abstain_zones, abstain_on_reject}`. A
repo-wide search finds no consumer for any of the three fields outside the rungs
that write them and one diagnostic script.

So in composition the ladder is one rung. Rung 5 routes on rung 1's free lexical
verdict and on nothing else; rungs 2, 3 and 4 can affect a shipped number only
by mutating `rec.sct` in passing, which only rung 3 does — and that turned out
to be a defect (§2C.4).

The uncomfortable part is that **no test could have caught this, because every
rung does exactly what its own docstring promises.** Each was reviewed, tested
and measured alone. The hole is between them, and it is only visible if you stop
asking "does this rung work" and start asking "what reads this rung's output".
That question has no unit-test shape. For a practitioner the takeaway is
concrete: for every field your pipeline writes, grep for its readers, and treat
a field with no reader as a rung that is not in your pipeline no matter how much
it costs to run.

### 2C.2 A fix three rungs down silently disabled two rungs up

**The number: rung 1's rejection rate went 5.1% → 0.4%, and rung 2's trigger
set went with it.**

Rung 1 rejected 5.1% of records on the held-out test run, every one of them
`schema_invalid` — rung 0 emitting an unlocated `(-1, -1)` span for a quote it
could not find in the post. Rung 2 fires on a rung 1 rejection whose reason
yields a statable fact; `schema_invalid` yields none, so rung 2 fired zero times
in the whole test run.

Then rung 0 got better. A span filter shipped in a later accuracy pass
(`rung0_drop_ungrounded`) drops exactly those unlocated records at rung 0. On
the current baseline rung 1 rejects **1 record of 248**, and rung 2's trigger
set holds **1**.

Nothing is broken. Rung 1 and rung 2 still pass every test they have, still log
every row, still report honestly. Their **input** was removed from underneath
them by a change three rungs below, and no test and no per-rung report could
show it — a rung with nothing to do and a rung doing nothing look identical from
inside. It is only visible by replaying the whole stack against a changed lower
rung. If you tune the bottom of a pipeline, re-measure the top; the layers you
are proudest of are the ones most likely to have quietly become no-ops.

### 2C.3 The check a validation layer was built for can become unreachable

**The number: `code_unknown` fires 0 times in 248 records. `label_verified` is
true 232 times out of 232.**

Rung 1's headline check asks whether the code the model produced exists in
SNOMED CT. It was tuned in 2026-08-22 against a rung 0 that recalled codes from
its weights, where 164 of 176 emitted codes did not exist at all. It is the
reason the rung exists.

It now fires zero times — confirmed through the unmasked reason table, so this
is not the first-failure ordering bias the audit pass was written to expose. The
cause is architectural: rung 0's shipped step picks its code from a
dense-retrieved menu built from a keyword table and resolves names through that
same table, and both contain only real SNOMED codes. **The model can no longer
emit a code that does not exist**, so the check written to catch that cannot
fire.

Two more went with it. `sct_active` is true for all 232 coded records and
`sct_outdated` false for all 235, so the retirement machinery has nothing to act
on. And `label_verified` — "did the model name the concept it coded?", the check
added because `82249009` is real, active, and means |California chicken| — is
true for 232 of 232, because the retrieval menu shows the code and its
vocabulary label *together*. The model's label is the vocabulary's own label by
construction. The check asks a question retrieval already answered.

Three vocabulary lookups per record that cannot vary. A validation layer is
calibrated against a *generator*, and when the generator's failure mode moves,
the layer does not follow it — it just keeps passing.

### 2C.4 The free check separates better than the paid judge

**The numbers: 83.7% vs 35.9% for free; 27.0% vs 21.9% for a call per record.**

One rung 1 check survives: the lexical match between the span text and the
vocabulary's words for the chosen code, which splits the pass state into ACCEPT
("the vocabulary uses these very words") and BAND ("plausible, unverifiable").
It is the only signal rung 5 routes on. Scored against gold — coding accuracy on
matched spans, overlap:

| | n | coding accuracy |
|---|---|---|
| rung 1 ACCEPT — deterministic, zero model calls | 49 | **83.7%** |
| rung 1 BAND | 131 | 35.9% |
| rung 4 judge `pass` — one call per record, dev | 105 | 21.0% |
| rung 4 judge `fail`, dev | 63 | 12.7% |
| rung 4 judge `pass`, held-out test | 163 | 27.0% |
| rung 4 judge `fail`, held-out test | 73 | 21.9% |

A 2.3x separation for free, against 1.65x on dev falling to 1.23x out of
sample — on the only axis a judge is for. The free side survives this
project's own three-draw test, the one that killed the reranker arm: over
three independent draws the ACCEPT lane reads 83.7 / 83.0 / 87.2 and BAND
35.9 / 36.8 / 36.2, a ratio of 2.33 / 2.26 / 2.41, and under a different
rung 0 entirely it is 85.7 vs 30.1. It is conditional on a deterministic
property of the record rather than on the run, which is why it is steadier
than the headline F1 it sits inside. Rung 4's separation is one draw per
split, and carries that caveat. The judge here is a 2B model grading a
20B one, which is the wrong way round and is stated wherever its numbers are;
the domain-adapted 7B brought in to fix that was measured and rejected. But the
comparison that matters is not judge-vs-better-judge. It is that a string
comparison against a controlled vocabulary, costing nothing, out-separates the
LLM judge — and it does so because it is the only checker in the stack that
knows something the extractor does not.

### 2C.5 A rung that asks the model to check itself is a coin flip

**The numbers: fixed 5 broke 0 on dev; fixed 2 broke 2 out of sample.**

Rungs 2, 3 and 4 all run on the extractor's own model, so they inherit its
errors. The rung 0 work measured this directly in a different shape: an LLM
reranker over the retrieved menu promoted gold to rank 0 for 50% of the mentions
the pick already got right, and 16.7% of the ones it got wrong. It ranked well
and converted nothing, because the reranker and the picker were the same model
making the same judgement.

Rung 3 is the same claim at the level of a whole rung. Scoring each record whose
code the vote changed, against gold, before and after:

| | scorable changes | fixed | broke | net |
|---|---|---|---|---|
| dev | 18 | 5 | 0 | **+5** |
| held-out test | 21 | 2 | 2 | **0** |

On dev it looked like a rung that works. Three of those five "fixes" are
`no code` → a correct code — rung 3 filling a gap rather than correcting an
error. Out of sample it destroyed two correct codes (|Severe pain|, and a
correct coding of "chest muscle soreness") while rescuing two others. A 5-0 on
18 trials is what a coin flip looks like sometimes; this is the single-draw
lesson again, in a rung instead of a metric. Rung 3 costs 2.6x rung 0's entire
token budget to move zero correct records out of sample.

Rung 6 is the exception, and the reason is not subtle: **it is a person, so it
is the only rung that adds information.** Its oracle ceiling lifts exact F1 from
0.131 to 0.444 and coding accuracy on matched spans from 0.291 to 0.990.

### 2C.6 The headline metric is blind to the defect the ladder exists to prevent

**The number: the fix moves F1 by 0.0000 and withdraws a false warrant.**

Rung 3 adopted a majority code by overwriting the record's code and stopping
there — but rung 5 routes on rung 1's verdict, which was computed against the
code rung 3 had just replaced. On the two full-ladder runs in the archive, the
vote changed 25 and 30 codes respectively, and **all 55 records carried a
verdict about a superseded code.**

One of them shipped. A record quoting "Chronic pain" was coded |Chronic pain|
and ACCEPTed by rung 1 on an exact lexical match; rung 3 voted 3-0 to replace it
with |Chronic musculoskeletal pain|; the record then shipped to the user marked
VERIFIED — on a lexical match to a code it no longer had. Re-checked, the new
code does not match. The configured rung 1 would have banded it and rung 5 would
have sent it to a person.

Fixing it changes the headline by nothing:

| | exact | overlap | shipped | routed to a person |
|---|---|---|---|---|
| dev, as built | 0.153 | 0.170 | 37 | 208 |
| dev, re-validated | 0.153 | 0.170 | 36 | 209 |
| test, as built *(= the reported run)* | 0.204 | 0.215 | 72 | 242 |
| test, re-validated *(counterfactual)* | 0.204 | 0.218 | 72 | 242 |

Of course it does. A record that was wrong scores the same whether it ships
wrong or is withdrawn — precision and recall cannot see the difference between
an answer that is unwarranted and an answer that is merely incorrect. **The
metric the ladder is optimised against is structurally blind to the failure the
ladder was built to prevent**, which is a reason to be suspicious of any
reliability layer justified on F1, including every layer in this project.

### 2C.7 A dial nobody could have turned

**The number: rung 0's confidence is `{1.0: 204, 0.99: 44}`.**

Rung 5 has a confidence threshold, `tau`, with a risk-coverage sweep written to
tune it, a manifest note recording that it is tuned on dev, and a declared
abstention reason `low_confidence`. `tau` has been 0.0 for the life of the
project.

It had to be. The extractor's self-reported confidence takes two values on the
dev baseline, both at or above 0.99. There is no operating point: any threshold
at or below 0.9 abstains nothing, and any threshold above it abstains 80-98% of
the set on a number the model emits as boilerplate. `low_confidence` — one of
three declared abstention reasons — is unreachable, and the risk-coverage curve
has nothing to sweep. An unelicited "confidence" field from an instruct model is
not a measurement; it is a token the model has learned to end JSON with.

### 2C.8 "Which configuration produced this number" needs one answer, twice over

**The number: `manifest.json` runs a rung 0 that is 5.9 exact points below the
baseline it is compared against.**

This project already learned this lesson once: a model default in code and a
model name in configuration disagreed, so "which model produced this number" had
two answers depending on whether a manifest reached the call, and the fix was to
make the resolver raise rather than fall back (§4.13).

The same failure recurred one layer down. A set of rung 0 accuracy arms —
a coordination splitter, three span filters, a trim threshold — were measured,
accepted, and shipped **as code with their defaults off**, and the manifest was
never appended to. Measured on the same documents from the same cache:

| | exact F1 | overlap F1 | detection F1 |
|---|---|---|---|
| `manifest.json` as shipped | 0.340 | 0.449 | 0.449/0.745 |
| the baseline every recent measurement uses | **0.399** | **0.469** | 0.516/0.785 |

Both are real. Only one is in the manifest, and it is not the one the decision
log quotes. The general form: **"off by default" is a safe policy for a
behaviour and an unsafe one for a measurement**, because the arm you measured
and the arm you ship are then different arms, and nothing in the repository
knows which is which. If you gate changes behind flags, make the flag's value at
measurement time part of the recorded result.

### 2C.9 The whole ladder, run again with the audit's eyes open

**The numbers: rung 3 net negative, rung 4 moves nothing, and rung 1 plus
rung 5 do all of the work.**

All seven rungs, in order, on 40 dev documents, one run id
(`audit-full-dev-1`), with the stale-verdict arm left OFF because this is the
ladder as it ships. Shipped **F1 exact 0.182 [0.124–0.244], overlap 0.187**;
52 records shipped VERIFIED at 0.808 answered-accuracy; **196 of 248 routed to
a person.**

| rung | answered accuracy | what it did | tokens | p95 latency |
|---|---|---|---|---|
| 0 · bare LLM | 0.371 | 248 records | 164,897 | *cache-served* |
| 1 · deterministic | 0.371 | ACCEPT 52 / BAND 195 / REJECT 1 | **0** | **0** |
| 2 · self-correct | 0.371 | fired **once** — one correctable rejection existed | 548 | *cache-served* |
| 3 · voting | **0.367** | 29 changed, 7 withheld, 27 not re-found | **425,355** | **152.2 s** |
| 4 · LLM judge | 0.367 | pass 146 / fail 95 / 7 unjudged — **no downstream effect** | 92,687 | 1.5 s |
| 5 · abstention | ships 0.808 | coverage 1.00 → 0.21; errors/100 **63.3 → 4.03** | 0 | 0 |
| 6 · human loop | — | **196 records to a person** · 79.0 per 100 | 0 | 0 |

Three cost measures, never fused: 683,487 tokens over 618 calls; a 152-second
p95 on the voting rung; 79 reviews per 100 records. Rung 0's and rung 2's
latencies are cache-served and are *not* latency measurements — said rather
than quoted.

Read down the accuracy column. It does not move until rung 5, and then it
moves by refusing. **Rung 3 is net negative on this draw at 2.6x rung 0's
entire token budget; rung 4 cannot move it at all, because nothing reads its
verdict.** Every point of the fall from 63.3 to 4.03 errors per 100 is rung
1's free lexical verdict, acted on by rung 5, paid for in coverage.

The stale-verdict defect also fired again, for the third independent time, and
the new stamp caught it in production: `r3_r1_stale` on all 29 changed
records — 28 already heading to a person, and **one shipped VERIFIED**. This
time it was the span "stamina", ACCEPTed on an exact match to |Stamina| and
then voted 2-1 to |Lack of stamina|, which does not match. Across three full
runs: 25, 30 and 29 stale verdicts, and **exactly one false VERIFIED warrant
in each**. It is not an artefact of a draw; it is what the rung does.

### 2C.10 What this section is evidence for

The ladder's premise is that stacking reliability layers buys reliability. Six
of the seven rungs are now measured, and the honest summary is that **the ladder
made errors visible rather than fewer.** That is worth something — every finding
in §2C exists because the harness records what each rung did — but it is not
what the layers were bought for.

What survives is small and specific: one free deterministic check that
out-separates a paid judge, an abstention mechanism whose bill is a countable
number of records, and a person. The paid model rungs, in composition, moved
nothing they could not also have broken.

---

## 3. Suggested structure

Seven beats, practitioner voice. The ladder is measured end to end now, so the
piece leads with the curve and spends its middle on why each number can be
trusted — the measurement discipline IS the story.

1. **Every agent is 90% harness, built by vibes.** The hook. Name the seven
   layers in a paragraph each and move on — they are not the contribution.
2. **The curve, once, on held-out data.** §2.4's table. One run, frozen
   config, three cost currencies never fused. One paid rung net negative, one
   never fired, the two that work refuse rather than answer. This is the
   figure the reader came for; everything after it explains why it can be
   believed.
3. **You can measure a layer before you build the layer above it.** §4.4's
   method: replay your deterministic gate over the answer key, where every
   rejection is false by construction. It caught three faults that would
   otherwise have shipped as a plausible 9.3% rejection rate — errors every
   paid rung above would have inherited.
4. **What a free layer actually buys.** §2.2 and §2.3. Rung 1 is exact on its
   own error classes, blind on the interesting one, and leaves 57% of even a
   perfect answer set unverifiable. The ladder reframed: a free, exact filter
   plus paid resolvers for the residue.
5. **The paid rungs, honestly.** §2.5–§2.7. Never ask a model to recall an
   identifier (0.018 vs 0.171 for MORE tokens); a voting rung's number is a
   sample, and its first build destroyed verified answers on 1-0 "majorities";
   the judge's separation partly lived in an accidental prompt duplication.
   Running thread: for small models, presentation IS measurement — menu
   order, prompt form, all load-bearing.
6. **Abstention and the person.** §2.8. The bill is a count, not a currency
   conversion; the queue holds 45 answers that were already right; and the
   oracle ceiling proves the residual gap is span boundaries — which tells
   you the next rung to build, which is the real use of a ceiling.
6b. **Then audit the composition, and find that there isn't one.** §2C — the
   turn the piece needs, and the strongest material in it. Three rungs defer
   their action to rung 5; rung 5 reads none of their fields. A rung 0
   accuracy fix silently emptied rung 1's rejection class and with it rung 2's
   trigger. Rung 1's headline check now fires zero times because retrieval
   made hallucinated codes impossible, while the one check that survives
   out-separates the paid judge 2.3x to 1.23x. And the fix for a record that
   shipped VERIFIED on a stale warrant moves F1 by exactly nothing, because
   precision cannot tell an unwarranted answer from an incorrect one. Every
   one of these is invisible to a per-rung test and to a per-rung report.
7. **Decision rules.** Grep for the readers of every field your pipeline
   writes; a field with no reader is a rung you are paying for and not
   running. Re-measure the top of a stack after you tune the bottom of it.
   Measure the permissive setting's false-vouch rate
   before shipping it (§2.1). Pin your vocabulary release — §4.7's 23.9%.
   Don't let a validation layer filter the input to the layers you are
   measuring (§4.5). Check whether your reference list came from your answer
   key (§4.6). Hold presentation fixed or you are measuring two things
   (§2.5, §2.7). Cite the run id on any sampled rung (§2.6). And spend your
   test split once.

Beats 2–6b are the article, and 6b is its turn: everything before it measures
rungs, and it measures whether they add up. Beat 7 is what a reader takes to
work on Monday.

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
  experiment. Two rules learned the hard way: **the cache key must cover every
  generation parameter** (a cache that survives a `max_tokens` change serves a
  stale result and calls it reproducibility), and **a timeout is never cached**
  — it is a property of the run's machine, not of the question.

### 4.12 One runaway document must cost one record, and a cut-off reply is not a parse failure

A dev run once stopped dead for 25 minutes on a 761-character forum post — a
reasoning model generating unboundedly. The fix is a wall-clock budget on
every call, as per-model registry data, that does not raise: it returns an
empty response flagged `timed_out`, so the run loses one record instead of
its afternoon. 90% of calls finish under 3.3k completion tokens; the tail is
what makes a run unbounded, and the budget is what makes "hours, not days" a
property rather than a hope.

Downstream of that, failures carry **three labels, most specific first:
`timed_out` > `truncated` > `json_decode`**. They overlap on purpose. A reply
cut off by the token cap must never be counted as "the model cannot produce
JSON", and a hung machine must never be counted as either — the first is a
budget you set, the second is a capability claim about the model, and the
third is your hardware. Timeouts are filed in the cost column, not the
accuracy one. On the final test run all three counters were zero, which is
itself only a checkable claim because the labels exist.

### 4.13 "Which model produced this number" must have exactly one answer

Midway through the project, the answer had quietly become "two": the manifest
named one extractor while a code-level default silently substituted another
whenever a manifest didn't reach the call site. Every number produced in that
window had an ambiguous provenance. The repair is structural, not procedural:
`manifest.model` is the ONE place a model is named, the resolver RAISES on a
missing entry instead of defaulting, and rungs never name models — they are
bound by role (extractor/judge) through a single resolution function, which is
also where "the judge must be a different family from the extractor" is
enforced rather than remembered.

Same shape as §4.5 and §4.6: the constraints that hold are the ones with no
way to express the forbidden thing. A default argument is a way to express it.

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
6. **The ladder curve — accuracy and three costs per rung, test split (§2.4).**
   *"Seven rungs, one cold run on 60 held-out documents. Errors per 100 fall
   59.6 → 3.8; the price is 845k tokens, minute-scale p95 latencies on a local
   20B, and 77 of every 100 records routed to a person. One paid rung was net
   negative on this draw; one never fired. The three costs are three axes —
   never one currency."*
7. **The prompt-shape cliff (§2.5).**
   *"Same model, same scope, same documents. Asking for the code from memory:
   F1 0.018, and the most tokens. Asking for names: 0.171. Retrieve-and-pick:
   0.209. The step that cannot work is also the most expensive way to ask."*
8. **What abstention withholds, and what a perfect reviewer would recover (§2.8).**
   *"Rung 5's queue on test holds 242 records, 45 of them already exactly
   correct. On dev, an oracle desk lifts shipped F1 0.131 → 0.444 with
   detection unchanged: after a perfect code-picker, the whole remaining gap
   is span boundaries."*

9. **The composition, audited (§2C.1).**
   *"Rung 2 writes `r2_declined` 'for rung 5'. Rung 3 writes
   `r3_unanimous_none` 'for rung 5'. Rung 4 writes `r4_verdict` and says 'let
   rung 5 act'. Rung 5 reads none of them. Three rungs were paid for, ran
   correctly, passed their tests, and were wired to nothing."*
10. **The metric cannot see the bug (§2C.6).**
   *"A record shipped marked VERIFIED on a lexical match to a code it no
   longer had. Fixing that moves exact F1 by 0.0000 — precision cannot
   distinguish an unwarranted answer from a merely incorrect one. Be
   suspicious of any reliability layer justified on F1."*

## 6. Limitations to state plainly

- **Everything in §2C is dev-side and unvalidatable.** The test split was spent
  on 2026-08-26 and this repo has no held-out data left. The audit's numbers
  come from 40 dev documents and from read-only replays of two archived runs;
  where a Phase F artifact is used it is a labelled counterfactual, and §2.4's
  reported numbers are unchanged by anything in §2C.
- **Two of the audit's cleanest results rest on small counts.** Rung 3's
  fix/break tally is 18 and 21 scorable changes; the single record that shipped
  on a stale warrant is one record. They are reported as what they are —
  existence proofs of a mechanism, not rates — and the mechanism is the claim.
- **A single-draw confidence interval that excludes zero is not a result.** Three
  independent draws killed the one rung 0 arm a single draw plus a paired
  bootstrap had called significant (+0.0215 [+0.0000, +0.0433], then -0.0089 on
  the third draw). Dev's real spread across draws is 1.3 points exact and 0.6
  overlap, and the nondeterminism enters at one call, all-or-nothing per run.
  Three draws plus the paired bootstrap, never one alone — and never
  ten-document subsets, which overstate both effect size and variance.
- **Exact F1 above ~0.70 is unreachable here for any system, including a
  perfect one.** The answer key's own span-boundary convention is only ~67%
  deterministic: over 25,002 boundary decisions on the learnable split, 66.9%
  fall at tokens gold treats one way >=95% of the time, 20% lean, and 13% are
  genuinely mixed — "terrible" is kept inside a span 52% of the time, "very"
  70%, "in" 40%. A perfect learner of that convention gets ~0.92 per boundary
  and a span needs two, capping the exact-span rate near 0.85; composed with
  the measured detection and retrieval ceilings that gives **F1 ~0.68 with
  every component at its best**, and a perfect reranker over the top 200 plus
  perfect spans measures 0.667 exact on dev. Exact match scores a boundary
  disagreement as both a false positive and a false negative, so every
  0.70-class claim in this project is stated on **overlap**, with exact
  reported beside it as the stricter, capped number.
- **The MedDRA check cannot be trusted as configured.** Its reference table is
  derived from the answer key. It is reported, not scored, and any number from
  it carries the caveat.
- **The test split was spent exactly once, so its CIs are the claim.** 60
  documents, 290 scorable mentions: F1 0.204 lives in [0.150–0.260]. Nothing
  was tuned on test and nothing re-run — which also means no second draw
  exists to average with. Report the interval, not the point.
- **Test above dev is partly split luck.** Shipped F1 0.131 (dev) vs 0.204
  (test), CIs barely overlapping, with no test tuning anywhere in the
  pipeline. Generalisation is the honest first-order read; the second-order
  read is that 40-document dev was the harder draw. Say both.
- **Rung 3's numbers are samples.** Temperature resamples differ run to run —
  dev gained +5 net correct, the one test draw gained zero — so every voting
  number carries its run id, and the rung's value claim is bounded by the
  spread between draws, which two draws cannot estimate.
- **The judge is 2B judging 20B** — the wrong way round, kept as the measured
  lesser evil after the domain-adapted 7B alternative failed to return
  parseable verdicts at all (§2.7). Every rung 4 number carries this.
- **The oracle desk is a dev-only ceiling.** It is derived from gold, labeled
  on every row, and refused on the test split by construction. No real human
  desk session exists; human minutes appear only "at the declared rate".
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
- **The abstention target is thin** on the test split: 3 `CONCEPT_LESS`
  mentions in 290 scorable. Abstention accuracy against concept-less gold
  cannot be separated from noise there.
- **The confidence gate never earned a threshold.** `tau` stayed 0.0: the 2B
  judge's confidence field is nearly two-valued (a τ=0.95 shelf keeps 5.4%
  coverage at n too thin to gate on), so rung 5 gates on verdicts, not
  confidence. A calibrated confidence distribution remains unbuilt.
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

# The model-facing ladder (preprocessing per CLAUDE.md first; Ollama with
# gpt-oss:20b and granite4:micro-h). Dev runs replay from the call cache;
# the test run below is THE run — it was executed once and is archived,
# with every baseline, in the main checkout's out/archive/.
python -m ladder.keywords --build && python -m ladder.clean --build && python -m ladder.embed --build
python -m ladder.run ladder --split dev  --run-id <your-dev-run>
python -m ladder.run ladder --split test --run-id phaseF-test-1   # the one test run
# Re-score any run's records (exact + overlap, layers, CIs, five outcomes):
#   ladder.score.score_run / bootstrap_ci over <run>.records.jsonl — see
#   docs/decisions.md 2026-08-26 (Phase F) for the protocol and denominators.
```

The corpus is not redistributable and the SNOMED release needs an affiliate
licence — see `docs/licences.md`. Every figure above comes from the commands
here; nothing is quoted from a pipeline that is no longer in the repo.

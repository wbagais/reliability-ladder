# Which answers can you trust?

*Building a system that tells you which of its own outputs to believe — and
measuring, over five months and five open-weight models, how little of what we
built actually did that.*

---

## The problem, and the number that states it

Read a patient's forum post about a drug. Find every adverse reaction the
writer says they had. Assign each one a SNOMED CT code. There is a real answer
key — CADEC, 1,250 posts, 9,111 annotated mentions — and the task is the shape
of a great many production pipelines: pull structured records out of prose,
normalise them against a controlled vocabulary, be prepared to defend each one.

"Be prepared to defend each one" is not the same problem as accuracy, and it is
the harder one. A system that is 80% right and cannot tell you *which* 80% is
unusable anywhere a wrong answer costs something. You do not need a better
average. You need to know, per record, whether this particular answer is one you
can stand behind.

Here is what we ended up with, stated before any of the reasoning that produced
it:

> The system ships **21%** of its answers. On those it makes **4.0 errors per
> 100**, against **62.9** for the bare model and **63.3** for everything the
> paid layers could do to it. It sends the other **196 of every 248 records to
> a person.**

That is not a good result. It is, we think, an honest one, and most of this
article is about the things we built that did not contribute to it.

---

## 1. The ground moves, and it moves further than any of our improvements

Before trying to make a model's output trustworthy, it is worth checking whether
it is even stable. Three draws of one frozen configuration, same 40 documents,
same machine, same hour:

| | draw 0 | draw 1 | draw 2 | spread |
|---|---|---|---|---|
| F1, exact span | 0.395 | 0.408 | 0.401 | **1.3 pt** |
| F1, overlap span | 0.469 | 0.475 | 0.471 | 0.6 pt |

A 1.3-point spread is unremarkable until you notice that **every rung-0
improvement this project ever shipped was smaller than that.** Prompt changes,
span filters, a reranking stage — all of them lived inside the noise band of the
thing producing them.

We tried to suppress it and failed. A system message, three prompt
interventions, a role clause: each moved *where* errors landed without reducing
them, and restating an instruction the model already ignored produced compliance
three times out of three — zero.

Then we ran the same experiment across five open-weight models, and the premise
turned out to be wrong.

| model | distinct outputs over 3 identical draws |
|---|---|
| `llama3.1:8b` | **1** |
| `mistral:7b-instruct` | **1** |
| `qwen3:8b` | **1** |
| `granite4:micro-h` | **1** |
| `gpt-oss:20b` | **3** |

Four of five are **bit-reproducible** — identical output files, byte for byte,
across three independent runs. Only one varies, and it is the only
Mixture-of-Experts model in the set. `qwen3` is a reasoning model and `granite4`
is a Mamba/transformer hybrid, so neither deliberation nor architectural novelty
is the variable. Sparsity is the one property that separates them, which fits
the known mechanism — which experts fire depends on what else is in the batch,
while a dense forward pass at temperature 0 does not.

**Said at its real strength: four dense models against one sparse one.** A
single MoE model cannot establish a mechanism. But the practical consequence
does not depend on the mechanism being right:

> Run-to-run reproducibility is a **model-selection choice with a measurable
> price.** `gpt-oss:20b` buys 6.5 exact points over `llama3.1:8b` and pays a
> 1.3-point run-to-run spread for them — a spread larger than every improvement
> we ever shipped.

Nobody told us that trade existed. We found it by accident, four months in,
because we had only ever run one model.

---

## 2. The significance test that certified noise

One methodological detour, because it nearly cost us a published result.

We built a bootstrap confidence interval properly: resampling **documents**, not
mentions, because mentions inside one post share an author, a topic and a model
call, and resampling mentions would claim roughly six times more independent
observations than exist. That part is right and we still recommend it.

Then we measured a reranking stage and got:

> **+0.0217 overlap F1, paired bootstrap +0.0215 [+0.0000, +0.0433]**

An interval excluding zero. In most write-ups that is where the analysis stops.

We ran it twice more:

| | draw 0 | draw 1 | draw 2 |
|---|---|---|---|
| overlap F1 delta | **+0.0217** | +0.0087 | **−0.0089** |

The sign reverses. The effect is not there.

The bootstrap was not broken — it was answering a different question. **It
resamples the documents of a single run, so it prices the corpus sample and
nothing else.** The run-to-run variance from section 1 is invisible to it,
because every replicate is drawn from one fixed set of model outputs. Given one
draw, it will certify noise, confidently, with a tight interval.

**If your significance test only ever sees one generation per configuration, it
cannot see the dominant noise term.** Three draws minimum, plus the bootstrap.
And not ten-document subsets, which overstate both effect size and variance.

---

## 3. What a free deterministic check can and cannot see

If the output will not hold still, attach something to it that will. The
controlled vocabulary is the obvious candidate: SNOMED CT does not resample.

We measured what six such checks catch by planting each error class into an
otherwise-perfect answer set, 8,666 records at a time:

| planted error | caught |
|---|---|
| code that exists in no release | **1.000** |
| span shifted two characters | **1.000** |
| fabricated quote | **1.000** |
| real code, wrong branch of the hierarchy | **1.000** |
| random plausible clinical finding | **0.000** |
| near-miss finding sharing a head word | **0.001** |

The top half is better than "useful": on the classes they are built for, these
checks are **exact**, at zero cost, with no model call.

The bottom half is why the rest of this article exists. Give the system a real,
active, correctly-typed clinical finding that is simply the *wrong* one and
every check passes it. **The right code is not in the source text, so nothing
mechanical can put it there.** The failure mode that matters most is invisible
to the cheapest layer, permanently.

So the vocabulary cannot tell you an answer is right. What it can do is sort
answers into three states — REJECT (provably wrong), ACCEPT (the vocabulary uses
these very words), BAND (plausible, unverifiable) — and **57% of even a perfect
answer set lands in BAND.** That number is knowable before you spend a token. It
is the fraction free checks will never settle: the bill everything expensive has
to work through.

### The knob that turns a gate into an endorsement machine

The ACCEPT/BAND divider is a string comparison with one obvious setting: exact
equality, or token containment.

Containment is the intuitive choice. Patients write "bit drowsy" where the
vocabulary says "Drowsy"; strictness looks pedantic, and leniency lifts the
share of a perfect answer set settled for free from 43.1% to 54.5%.

Then we planted **near-miss codes** — a real, active finding sharing its head
word with the correct one, which is the confusion this kind of model actually
makes:

| setting | near-misses caught | near-misses placed in **ACCEPT** | free coverage |
|---|---|---|---|
| `contained` | 0.1% | **19.0%** | 54.5% |
| `exact` | 0.1% | **0.1%** | 43.1% |

Neither catches near-misses. But the lenient setting **actively vouches for one
in five of them**, because the patient's phrase is a subset of the wrong
concept's name. It does not fail to protect you; it hands you false confidence,
which is worse, because you act on it. We took the strict setting and paid the
eleven points.

---

## 4. The one thing that worked

The ACCEPT/BAND split is strongly predictive of correctness — and, unlike the
headline number, it barely moves between draws.

Across **five open-weight model families, three draws each, fifteen runs**:

| model | exact F1 | **ACCEPT lane** | BAND lane | ratio |
|---|---|---|---|---|
| `gpt-oss:20b` | 0.401 ±0.007 | **84.6%** | 35.9% | 2.36× |
| `llama3.1:8b` | 0.336 ±0.000 | **80.4%** | 28.8% | 2.79× |
| `mistral:7b-instruct` | 0.206 ±0.000 | **83.3%** | 14.6% | 5.70× |
| `granite4:micro-h` | 0.185 ±0.000 | **89.3%** | 14.6% | 6.12× |
| `qwen3:8b` | 0.141 ±0.000 | **83.3%** | 30.3% | 2.75× |

Headline F1 ranges **0.141 to 0.401** — a factor of 2.8. The ACCEPT lane ranges
**80.4 to 89.3**, and its ordering has no relationship to model quality: the
*worst* model by F1 has the *highest* ACCEPT lane. The BAND lane, meanwhile,
tracks model quality directly.

> The check does not merely correlate with correctness. It identifies a subset
> of answers that are **~85% correct regardless of which model produced them**,
> and it earns **more** the worse the model is.

The reason is structural and it generalises. The quantity is conditional on a
**deterministic property of the record** — "given that the vocabulary uses these
exact words for this code, how often is the code right?" — rather than on the
run. Resampling moves which records land in each lane without much moving what
each lane means.

That is the answer to the question this article opens with. You cannot make the
model repeatable. **You can make your knowledge about it repeatable**, by
conditioning it on something that does not resample.

---

## 5. And here is the corpus where it does not work at all

Everything above is one corpus. So we ported the whole system to a second one:
**FiNER-139** — SEC filings, where the task is to find numeric facts and tag
them with one of 139 US-GAAP XBRL tags. Same code, same rungs, same models. The
port cost sixteen one-line harness edits and zero changes to rung logic.

The result is not a worse score. It is no score:

```
rung 1   ACCEPT 0 / BAND 291 / REJECT 1
         lexical_match  False on every record carrying a tag
         sct_exists     True  on every one of them
rung 5   coverage 1.0 → 0.0
rung 6   292 of 292 records routed to a person
```

**The identical system that ships 21% of its answers on CADEC ships 0% here.**

The vocabulary check works perfectly — every tag exists. It is the *lexical*
check that has nothing to compare. On CADEC it matches `"chronic pain"` against
`|Chronic pain|`. On FiNER it must match `"47.6"` against
`|EffectiveIncomeTaxRateContinuingOperations|`, and a number shares no tokens
with a name by construction. The one signal carrying the entire system has zero
coverage.

So the honest scope of section 4's claim is:

> Deterministic evidence of this kind is available when the vocabulary's words
> and the source's words are drawn from the same language. It is unavailable
> when the span is a bare quantity.

That is the method's **precondition**, not a weakness — but it was invisible for
five phases because the project had one corpus.

The most alarming part is how it fails. `err_per_100` at the abstention step is
**0.0**: a perfect error rate, over an empty output. A system whose safety
property is "abstain unless corroborated" degrades to "abstain always" the
moment corroboration is inapplicable, and it does so **silently, reporting
flawless numbers**. Print coverage beside every error rate, always.

---

## 6. What the four paid resolvers bought

With a free layer that is exact on some classes, blind on the important one, and
leaves 57% unsettled, the obvious move is to spend money on the residue. We
built four resolvers. We expected a staircase.

**Ask the model to fix what the checks caught.** State the failure back as a
fact — "the code 41456009 does not exist in SNOMED CT" — never as a question.
The mechanism is sound and it fired **once in 248 records**, for a reason that
is section 7's subject.

**Ask the model again and take the majority.** This is what people reach for
first against nondeterminism. It cost 2.6× the entire extraction token budget
and a 152-second p95 latency, and scored per changed record against gold:

| | changes scored | fixed | broke | net |
|---|---|---|---|---|
| tuning set | 18 | 5 | 0 | **+5** |
| held-out | 21 | 2 | **2** | **0** |

On the tuning set it looked like a win — until you notice three of the five
"fixes" were *no code → a correct code*, filling a gap rather than correcting an
error. Out of sample it is a coin flip. **The voter and the answerer are the
same model, so the vote carries no information the original answer lacked.** We
measured this directly elsewhere: a reranking stage promoted the right answer
for 50% of the cases the picker already got right, and 16.7% of the ones it got
wrong.

**Ask a different model.** A second family as judge — enforced, not advised: if
judge and extractor match, the code raises. It separates, weakly, and less where
it counts:

| | pass | fail | ratio |
|---|---|---|---|
| tuning set | 21.0% | 12.7% | 1.65× |
| held-out | 27.0% | 21.9% | **1.23×** |

Set that against the free check's 2.36–6.12× across five models. **A string
comparison against a controlled vocabulary out-separates the LLM judge on the
only axis a judge is for**, at zero marginal cost.

There is a caveat that turned into a finding. Our judge is a 3.2B model grading
a 20B one, and on CADEC it engaged with spans and said nothing useful about
codes — which we read as a limit of a small model. On FiNER, with the prompt
corrected, the *same* model adjudicates codes fine (fail 299 / pass 48, both
sub-verdicts splitting genuinely). The difference is that 139 tags fit in its
context and 129,675 SNOMED concepts do not. **A judge cannot adjudicate a
vocabulary it cannot see** — a property of the task, not the model.

**Refuse.** The last resolver resolves nothing. It withdraws every answer the
stack could not corroborate, preserves it rather than deleting it, and routes
the record to a person. Errors per 100 **63.3 → 4.03** — 63.3 being the rate
after every paid layer has had its turn, against 62.9 for the bare model, which
is the more damning pair. Coverage 100% → **21%.** Records to a person:
**196 of 248.**

Every point of that fall is the free check from section 4, acted on, and paid
for entirely in a third currency — human attention. We never collapse cost into
one figure: tokens, latency and human referrals are three axes, and a system
that looks cheap on two can be ruinous on the third.

How much is on the other side of that referral? An oracle desk — gold-derived,
labelled on every row — takes shipped F1 from 0.131 to **0.444** and coding
accuracy from 0.291 to **0.990, with detection unchanged.** After a perfect
human code-picker, the entire remaining gap is span boundaries, which a
code-picking reviewer cannot fix. That is what a ceiling is for: not comfort,
but finding out which layer the headroom is in.

### We removed all three and measured what happened

The per-rung numbers above are an argument. The ablation is the measurement:
run the same corpus through `[0, 1, 5]` — the deterministic spine, with
self-correction, voting and the judge deleted — holding rung 0 **identical** on
both sides.

| stack | F1 exact | overlap | correct | shipped | to a person | tokens |
|---|---|---|---|---|---|---|
| full `[0..6]` | 0.182 | 0.187 | 43 | 52 | 196 | **683,488** |
| spine `[0, 1, 5]` | 0.182 | 0.182 | 42 | 52 | 196 | **164,898** |

Identical exact F1, identical coverage, identical error rate, identical records
routed to a person. **The entire contribution of the three paid model rungs is
one overlap-matched correct answer out of 43, for 518,590 tokens and a
152-second p95 latency.**

On FiNER both stacks ship nothing, and the spine costs 25% of 3.5M tokens.

(One trap worth naming, because it nearly reversed the reading: the spine
configs predated a set of rung 0 improvements, so running them as they stood
would have compared a spine on a *worse* rung 0 against a full stack on a
better one, and charged the difference to the rungs being dropped. An ablation
that does not hold its base fixed is two experiments wearing one name.)

### All of it, end to end

| layer | answered accuracy | tokens | p95 |
|---|---|---|---|
| bare model | 0.371 | 164,897 | *cached* |
| deterministic checks | 0.371 | **0** | **0** |
| self-correction | 0.371 | 548 | *cached* |
| voting | **0.367** | **425,355** | **152.2 s** |
| second-model judge | 0.367 | 92,687 | 1.5 s |
| refusal | ships **0.808** | 0 | 0 |
| person | — | **196 records** | — |

Read down the accuracy column. **It does not move until the refusal step, and
then it moves by declining to answer.** The two paid model resolvers cost
518,042 tokens between them and moved the number backwards.

---

## 7. Three things no single-layer test could see

These are what we found auditing the system as a whole rather than one layer at
a time, and they are what we would most want another team to check for.

**Every deferral terminated in a field nothing read.** Each paid resolver
correctly declined to act on its own evidence — a layer that both judges and
routes contaminates every measurement above it — and each named the refusal step
as the one that would act. Self-correction wrote `r2_declined`, voting wrote
`r3_unanimous_none`, the judge wrote `r4_verdict`. **The refusal step reads none
of the three.** It reads the deterministic verdict and nothing else. Three
layers ran, cost money, passed their tests, and were wired to nothing. No test
could have caught it, because every layer does exactly what its own
documentation promises. The hole is *between* them.

**A fix three layers down silently disabled two layers up.** The checks used to
reject 5.1% of records, nearly all for an unlocatable span. Then extraction
improved: a span filter now drops those at source. The rejection rate fell to
**1 record in 248**, and self-correction's trigger set went with it — which is
why it fired once. Nothing broke. Both layers still pass every test and report
honestly. Their *input* was removed by a change three layers below, and a layer
with nothing to do is indistinguishable from inside from a layer doing nothing.
The same mechanism hollowed out the checks themselves: the existence check now
fires **0 times in 248**, because the model picks from a retrieved menu of real
codes and can no longer invent one.

**The headline metric could not see the bug it exists to prevent.** Voting
overwrote a record's code and never re-validated — but the refusal step routes
on a verdict computed against the *replaced* code. Across three full runs it
changed 25, 30 and 29 codes, and every one carried a stale verdict; exactly one
per run shipped to a user marked *verified*. In the most recent: the span
"stamina", accepted on an exact match to `|Stamina|`, then voted to `|Lack of
stamina|`, which does not match. We fixed it. Effect on the headline: exact F1
**0.204 → 0.204**. Of course — a record that was wrong scores the same whether
it ships wrong or is withdrawn. Precision and recall cannot distinguish an
*unwarranted* answer from an *incorrect* one, which is the entire distinction
the system exists to make.

---

## 8. What open-weight models are actually short of

Everything here ran locally, which was a licence constraint before it was a
research one: CADEC is patient-reported medical text that cannot leave the
machine.

**Instruction-following, not domain knowledge, is the binding constraint.** We
imported **BioMistral-7B**, domain-adapted to medical text, specifically to
improve the judge. It was rejected on measurement: 167 of 240 records unjudged,
end-of-sequence emitted immediately after `{` on prompts past ~430 tokens, every
parsed verdict `fail`, confidence flat 0.0.

We then ran the **un-adapted** `mistral:7b-instruct`, which the original study
never did — and it completes the full 40-document extraction cleanly. That
closes the gap in our own earlier conclusion and sharpens it: the base family
follows instructions here, so **domain adaptation cost instruction-following.**
(Not a matched comparison — different role, prompt and quantization — so what
transfers is the existence proof, not the magnitude.)

**Presentation is part of the measurement.** When we repaired an *accidental*
prompt defect — the source post had been pasted in twice — the incumbent judge's
pass/fail separation collapsed from 28.0/15.6 to 25.4/23.6. Its signal had been
partly living in the duplication. Separately, alphabetising the candidate menu
cost 10–12 points of accuracy at byte-identical detection. For small models,
menu order and prompt form are load-bearing, and a result that survives only
under one of them is not a result.

**Architecture can rescue a model that failed the task.** `granite4:micro-h`
(3.2B) was unusable as an extractor when asked to *recall* codes — it answered
`AFTERPROMPT`. Under retrieve-and-pick, where the answer is a menu selection, it
runs the full corpus and posts the **highest ACCEPT lane of any model tested**
(89.3%). The task got easier, not the model better.

**Report detection and coding separately, or you will rank models wrongly.**
`qwen3:8b` is last by headline F1 (0.141) and **second-best at coding** (0.556,
ahead of llama's 0.530 and mistral's 0.386) — because it emits 57 predictions
against `gpt-oss`'s 232. It answers less and is right more often. A single
number ranks it below two models it beats at the part everyone assumes is hard.
It is also the most expensive by far: roughly two hours per draw against llama's
fifteen minutes, for a quarter of the output.

**And a better model does not fix what you think.** Swapping a frontier hosted
model into extraction (ten documents, one draw, both caveats stated) took
detection recall from 55/62 to **61/62** and produced **31 exactly-correct
answers against the local model's 31 — identical**, with coding accuracy
drifting *down*. Both models pick from the same 20-candidate retrieved menu, and
a better reader cannot beat the menu. Yet across our five local models coding
accuracy spans **21.3 points**. The asymmetry is the finding: **retrieval is a
ceiling, not a floor.** A better reader cannot beat the menu; a worse one can
certainly fail to use it.

---

## 9. A second corpus found bugs that more testing would not have

Three of the defects fixed while writing this had been invisible for five
phases, and all three surfaced within hours of running a second dataset:

- the judge's prompt was never ported, so on FiNER a model grading SEC filings
  was asked whether the span was *"really an adverse reaction the writer says
  they experienced"*
- CADEC's exclusion list — a claim about *one* answer key — was applied to every
  corpus
- models were resolved lazily per rung, so a mistyped judge name burned **133
  minutes** of extraction and voting before failing at the rung that needed it

A fourth came from a new *model* rather than a new corpus: the pick call crashed
the entire run on a bare JSON array, a reply shape the find call had accepted
for weeks. Same file, same rule, one call site missed.

None were subtle once a second thing was tried, and none would have been found
by more tests against the original substrate. **Diversity in what you test
against finds a class of bug that depth of testing does not.**

---

## 10. The ceiling, and why every number here appears twice

One limit shapes every accuracy figure and applies to any span task scored
against human annotation. **The answer key's own boundary convention is ~67%
deterministic.** Over 25,002 boundary decisions, 66.9% fall at tokens the
annotators treat consistently; 13% are genuinely mixed. "terrible" is kept
inside a span 52% of the time. "very", 70%.

A perfect learner of that convention gets ~0.92 per decision, and a span needs
two — capping exact-span rate near 0.85. Composed with measured detection and
retrieval ceilings, **F1 ≈ 0.68 with every component at its best**; a directly
measured oracle lands at 0.667.

So **exact F1 above 0.70 is unreachable on this task by any system, including a
perfect one**, and the binding constraint is the answer key. Exact match scores
a boundary disagreement as both a false positive and a false negative —
punishing twice a difference two humans also disagree about. Every number here
is reported on both layers. If you are benchmarking span extraction against one
number, measure your annotators' agreement first. It is probably your ceiling.

---

## What we would actually tell you

We set out believing that stacking reliability layers buys reliability. Measured
end to end, **the layers made errors visible rather than fewer** — which is
worth a great deal, and is not what they were bought for.

What survived:

1. **Condition your confidence on something that does not resample.** Ours was a
   controlled vocabulary; yours might be a schema, a type check, a database
   lookup, a compiler. It held at ~85% across five model families spanning a
   factor of 2.8 in accuracy.
2. **Know its precondition.** The same check has *zero* coverage on a corpus
   where the span is a number. Check yours applies before you build on it.
3. **Three draws, or you have not measured it.** A single-draw interval
   excluding zero certified an effect whose sign reversed on the third run.
4. **Reproducibility is a model choice.** Four of five models were bit-identical
   across runs. The one that was not bought 6.5 points and cost a spread larger
   than every gain we shipped.
5. **Test your free layer against your answer key first.** Every rejection there
   is false by construction, so you get its false-positive rate exactly, for
   nothing. Ours went from 9.3% to 0.13% — errors every paid layer above would
   have inherited and reported as model error.
6. **Measure the lenient setting's false-vouch rate before shipping it.** 19%
   versus 0.1% is the gap between a gate and an endorsement machine.
7. **A model checking itself adds nothing.** A different family adds a little. A
   fixed external artefact adds a lot more.
8. **Grep for the readers of every field you write.** Three of our layers
   deferred to a fourth that never read them.
9. **Re-measure the top when you change the bottom**, and **print coverage
   beside every error rate** — 4 errors per 100 and 0 errors per 100 mean very
   different things when the second is computed over nothing.
10. **Do not justify a reliability layer on F1.** The metric cannot tell an
    unwarranted answer from an incorrect one.

The system ships about a fifth of its answers, at four errors per hundred
instead of sixty-three, and hands the rest to a person. That is not what we set
out to build. But the machinery that makes the other four-fifths *legible* to
that person turned out to be worth more than any of the layers that tried to
answer them.

---

## Reproducing this

CADEC is not redistributable (CSIRO licence, non-commercial, non-transferable)
and SNOMED needs an affiliate licence. **FiNER-139 is CC-BY-SA-4.0** — that arm
is reproducible from a clean checkout, and we rebuilt it from its own documented
instructions to confirm.

**Limitations.** The held-out split was spent once, so its intervals are the
claim and no second draw exists to average with; everything after is
tuning-side, and labelled. Voting numbers are samples and carry their run id.
The judge is a 3.2B model grading a 20B one. The oracle desk is a gold-derived
ceiling; no real reviewer session was ever timed, so human cost is reported as a
**count** of records routed, never as minutes. The near-miss corruption is
synthetic. The FiNER arm has one dev run and no tuning history, so it stands
next to CADEC as a demonstration and not as a matched comparison. And CADEC is
public and from 2015, so it is almost certainly in pretraining — which inflates
the bare-model baseline and makes every gain here **conservative**.

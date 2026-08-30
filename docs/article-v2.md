# The AI Reliability Ladder, Measured Rung by Rung

**Pushpdeep Mishra · Wejdan Bagais**

*Seven reliability layers around a language model, measured one at a time on a
task with a real answer key — what each one bought, and what it charged.*

![Figure 1](figures/fig0-hero.png)

*Fig. 1: The seven rungs, coloured by what each one bought. Two paid for
themselves, two cost tokens and changed nothing, three had no measured effect.
Source: author-created with Matplotlib.*

---

## Five key takeaways

1. Four of five open-weight models produced byte-identical output across three identical runs, so whether a system is reproducible turns out to be something you choose when you pick the model — and the one model that varied bought 6.5 accuracy points while costing a spread wider than every improvement we shipped.
2. Our bootstrap confidence interval excluded zero on the first draw and the effect's sign reversed by the third, because resampling documents prices the corpus and is blind to the variance between generations.
3. A free string comparison against a controlled vocabulary identified a subset of answers roughly 85% correct across five model families spanning a factor of 2.8 in headline accuracy.
4. That same check has zero coverage on a corpus where the span is a bare number, so it has a precondition you can test in one query before building on it.
5. Two paid layers cost 518,042 tokens for −0.004 accuracy, while the layer that dropped errors from 62.9 to 4.0 per 100 spent nothing and paid instead in a currency no single-figure summary reports: 196 of 248 records referred to a person.

---

## What an AI reliability ladder is for

A language model is not a dependable component. The same input can produce a
different output on the next call, and the model itself will be replaced within a
release cycle or two. Everything else in a production system is deterministic;
this one part is not, and the standard response is to put layers around it until
the whole behaves as though it were.

An AI reliability ladder is that stack, and there is broad agreement on its
shape: check the output against something deterministic, ask the model to correct
itself, sample it several times and take the majority, have a second model judge
the first, withhold what cannot be corroborated, and send the rest to a person.
Six layers, each reasonable, each with published work behind it — and the
assumption underneath all of them is that they stack. Every rung buys reliability,
and somewhere up the ladder is the point where the next stops being worth its
cost.

Nobody, as far as we could find, had measured that end to end on one task with a
real answer key. So we built all seven and measured each one — and found that the
staircase is not there, that the only layer which reliably paid was the free one,
and that the most useful thing we built was not a layer at all but the accounting
underneath them.

## The task, and the result

Read a patient's forum post about a drug. Find every adverse reaction the writer
says they had. Assign each one a SNOMED CT code. There is a real answer key —
CADEC, 1,250 posts, 9,111 annotated mentions — and the task is the shape of a
great many production pipelines: pull structured records out of prose, normalise
them against a controlled vocabulary, be prepared to defend each one.

"Be prepared to defend each one" is not the same problem as accuracy, and it is
the harder one. A system that is 80% right and cannot tell you *which* 80% is
unusable anywhere a wrong answer costs something.

Here is what we ended up with, stated before the reasoning that produced it:

> The system ships **21%** of its answers. On those it makes **4.0 errors per
> 100**, against **62.9** for the bare model and **63.3** for everything the paid
> layers could do to it. It sends the other **196 of every 248 records** to a
> person.

That is not a good result. It is an honest one, and most of this article is about
the things we built that did not contribute to it.

---

## 1. The ground moves more than our improvements do

Before making a model's output trustworthy, check whether it is stable. Three
draws of one frozen configuration, same documents, same machine, same hour:

| | draw 0 | draw 1 | draw 2 | spread |
|---|---|---|---|---|
| F1, exact span | 0.395 | 0.408 | 0.401 | **1.3 pt** |
| F1, overlap span | 0.469 | 0.475 | 0.471 | 0.6 pt |

A 1.3-point spread is unremarkable until you notice that **every extraction
improvement this project shipped was smaller than it.** Prompt changes, span
filters, a reranking stage — all lived inside the noise band of the thing
producing them.

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
Mixture-of-Experts model in the set. `qwen3` is a reasoning model and `granite4` a
Mamba/transformer hybrid, so neither deliberation nor architectural novelty is
the variable; sparsity is what separates them, which fits the known mechanism.
One MoE model cannot establish that, but the consequence does not depend on it:

> Reproducibility is a **model-selection choice with a measurable price.**
> `gpt-oss:20b` buys 6.5 exact points over `llama3.1:8b` and pays a 1.3-point
> run-to-run spread for them.

We found that four months in, because we had only ever run one model.

---

## 2. The significance test that certified noise

We measured a reranking stage with a paired bootstrap over documents, and got
**+0.0217 overlap F1, CI [+0.0000, +0.0433]** — an interval excluding zero. In
most write-ups that is where the analysis stops. We ran it twice more:
**+0.0217, +0.0087, −0.0089.** The sign reverses.

The bootstrap was not broken. It resamples the documents of a single run, so it
prices the corpus sample and nothing else; the run-to-run variance from section 1
is invisible to it, because every replicate is drawn from one fixed set of model
outputs. **A significance test that sees one generation per configuration cannot
see the dominant noise term.**

---

## 3. What a free deterministic check can and cannot see

If the output will not hold still, attach something to it that will. The
controlled vocabulary is the obvious candidate: SNOMED CT does not resample. We
measured what six such checks catch by planting each error class into an
otherwise-perfect answer set, 8,666 records at a time:

| planted error | caught |
|---|---|
| code that exists in no release | **1.000** |
| span shifted two characters | **1.000** |
| fabricated quote | **1.000** |
| real code, wrong branch of the hierarchy | **1.000** |
| random plausible clinical finding | **0.000** |
| near-miss finding sharing a head word | **0.001** |

On the classes they are built for these checks are **exact**, at zero cost, with
no model call. The bottom half is why the rest of this article exists: give the
system a real, active, correctly-typed clinical finding that is simply the *wrong*
one and every check passes it. **The right code is not in the source text, so
nothing mechanical can put it there.**

So the vocabulary cannot tell you an answer is right. It can sort answers into
three states — REJECT, ACCEPT (the vocabulary uses these very words), and BAND
(plausible, unverifiable) — and **57% of even a perfect answer set lands in
BAND**, a number knowable before you spend a token.

One setting is worth naming. The ACCEPT/BAND divider is a string comparison, and
the lenient option lifts free coverage from 43.1% to 54.5%. We then planted
near-miss codes — a real finding sharing its head word with the correct one:

| setting | near-misses caught | near-misses placed in **ACCEPT** |
|---|---|---|
| `contained` | 0.1% | **19.0%** |
| `exact` | 0.1% | **0.1%** |

Neither catches them, but the lenient setting **actively vouches for one in
five** — worse than missing them, because you act on it.

---

## 4. The one thing that worked

The ACCEPT/BAND split predicts correctness, and unlike the headline number it
barely moves between draws. Across **five model families, three draws each,
fifteen runs**:

| model | exact F1 | **ACCEPT lane** | BAND lane | ratio |
|---|---|---|---|---|
| `gpt-oss:20b` | 0.401 ±0.007 | **84.6%** | 35.9% | 2.36× |
| `llama3.1:8b` | 0.336 ±0.000 | **80.4%** | 28.8% | 2.79× |
| `mistral:7b-instruct` | 0.206 ±0.000 | **83.3%** | 14.6% | 5.70× |
| `granite4:micro-h` | 0.185 ±0.000 | **89.3%** | 14.6% | 6.12× |
| `qwen3:8b` | 0.141 ±0.000 | **83.3%** | 30.3% | 2.75× |

Headline F1 ranges **0.141 to 0.401** — a factor of 2.8. The ACCEPT lane ranges
**80.4 to 89.3**, and its ordering has no relationship to model quality: the
*worst* model by F1 has the *highest* ACCEPT lane.

> The check identifies a subset of answers that are **~85% correct regardless of
> which model produced them**, and it earns **more** the worse the model is.

The reason is structural: the quantity is conditional on a **deterministic
property of the record** rather than on the run. You cannot make the model
repeatable. **You can make your knowledge about it repeatable.**

---

## 5. The corpus where none of it works

We ported the whole system to **FiNER-139** — SEC filings, where the task is to
tag numeric facts with one of 139 US-GAAP XBRL tags. Same code, same rungs, same
models; the port cost sixteen one-line harness edits and no changes to rung logic.

The result is not a worse score. It is no score: **ACCEPT 0, BAND 291, REJECT 1**,
coverage 1.0 → 0.0, every record routed to a person. The identical system that
ships 21% of its answers on CADEC ships **0%** here.

Every tag exists, so the vocabulary check works perfectly. It is the *lexical*
check that has nothing to compare. On CADEC it matches `"chronic pain"` against
`|Chronic pain|`; on FiNER it must match `"47.6"` against
`|EffectiveIncomeTaxRateContinuingOperations|`, and a number shares no tokens with
a name by construction.

![Figure 2](figures/fig4-precondition.png)

*Fig. 2: The lexical check compares the extracted span against the code's own
name. On one corpus they are drawn from the same language; on the other they
cannot overlap. Source: author-created with Graphviz.*

> Deterministic evidence of this kind is available when the vocabulary's words and
> the source's words are drawn from the same language. It is unavailable when the
> span is a bare quantity.

That is the method's **precondition**, and it was invisible for five phases
because the project had one corpus.

The most alarming part is how it fails. `err_per_100` at the abstention step is
**0.0** — a perfect error rate over an empty output. A system whose safety
property is "abstain unless corroborated" degrades to "abstain always" the moment
corroboration is inapplicable, and it does so **silently, reporting flawless
numbers.**

The port paid for itself in defects, too. Three that had been invisible for five
phases surfaced within hours: the judge's prompt was never ported, so a model
grading SEC filings was asked whether the span was *"really an adverse
reaction"*; CADEC's exclusion list, a claim about one answer key, was applied to
every corpus; and a mistyped model name burned **133 minutes** of compute before
failing at the rung that needed it. **Diversity in what you test against finds a
class of bug that depth of testing does not.**

---

## 6. What the four paid resolvers bought

We built four resolvers on the residue and expected a staircase.

The first asks the model to fix what the checks caught, stating the failure back
as a fact. The mechanism is sound and it fired **once in 248 records**, for a
reason section 7 explains. The second asks the model again and takes the
majority; it cost 2.6× the extraction token budget and a 152-second p95 latency,
and scored **+5 on the tuning set and 0 out of sample**. The voter and the
answerer are the same model, so the vote carries no information the original
answer lacked. The third asks a different model to judge, which separates weakly
and less where it counts: 1.65× on the tuning set, **1.23×** held out, against
the free check's 2.36–6.12×. **A string comparison against a controlled
vocabulary out-separates the LLM judge on the only axis a judge is for**, at zero
marginal cost.

One caveat became a finding. Our judge is a 3.2B model grading a 20B one, and on
CADEC it said nothing useful about codes, which we read as a limit of a small
model. On FiNER the *same* model adjudicates codes fine — because 139 tags fit in
its context and 129,675 SNOMED concepts do not. **A judge cannot adjudicate a
vocabulary it cannot see.**

The fourth resolver resolves nothing. It withdraws every answer the stack could
not corroborate and routes the record to a person, and it is the only one that
moves the number: errors per 100 fall **62.9 → 4.0** against the bare model, while
coverage falls 100% → **21%.**

Every point of that fall is the free check from section 3, acted on, and paid for
in a third currency — human attention.

![Figure 3](figures/fig2-flat.png)

*Fig. 3: Accuracy on answered records is flat through four layers and falls at
the voting step; it rises only when the system stops answering. Token cost below.
Source: author-created with Matplotlib.*

| layer | answered accuracy | what it bought | tokens | p95 |
|---|---|---|---|---|
| bare model | 0.371 | — | 164,897 | *cached* |
| deterministic checks | 0.371 | +0.000 | **0** | **0** |
| self-correction | 0.371 | +0.000 | 548 | *cached* |
| voting | **0.367** | **−0.004** | **425,355** | **152.2 s** |
| second-model judge | 0.367 | +0.000 | 92,687 | 1.5 s |
| refusal | ships **0.808** | **+0.437**, at 21% coverage | 0 | 0 |
| person | — | — | **196 records** | — |

Read down the two middle columns together. **Accuracy does not move until the
refusal step, and then it moves by declining to answer.** The two paid model
resolvers cost **518,042 tokens between them for −0.004** — which is not a poor
exchange rate so much as an undefined one, since there is no positive quantity to
divide into. The layer that moved the number spent nothing.

The exchange rate that does exist is the one nobody prices: **0.437 accuracy for
196 of 248 records referred to a person.** Whether that is worth paying depends
entirely on what a wrong answer costs you, which is a number only you have — and
which is why we report the three currencies separately and refuse to fuse them.
A layer that is free in tokens and ruinous in human attention will look like a
bargain in any single-figure summary.

---

## 7. What no single-layer test could see

**Every deferral terminated in a field nothing read.** Each paid resolver
correctly declined to act on its own evidence and named the refusal step as the
one that would act. Self-correction wrote `r2_declined`, voting wrote
`r3_unanimous_none`, the judge wrote `r4_verdict`. **The refusal step reads none
of the three.** No test could have caught it, because every layer does exactly
what its own documentation promises. The hole is *between* them.

![Figure 4](figures/fig1-wiring.png)

*Fig. 4: Where each layer's verdict goes. Self-correction, voting and the judge
each write a field; the refusal step reads none of them. Source: author-created
with Graphviz.*

**A fix three layers down silently disabled two layers up.** The checks used to
reject 5.1% of records, nearly all for an unlocatable span, until extraction
improved and a span filter began dropping those at source. The rejection rate fell
to **1 record in 248** and self-correction's trigger set went with it. Nothing
broke; both layers still pass every test and report honestly. **A layer with
nothing to do is indistinguishable from inside from a layer doing nothing.**

A third defect says something about metrics. Voting overwrote codes without
re-validating, so records shipped marked *verified* against a code they no longer
had. Fixing it moved exact F1 from **0.204 to 0.204** — because precision and
recall cannot distinguish an *unwarranted* answer from an *incorrect* one, which
is the entire distinction the system exists to make.

---

## How we found these

None of the layers above announced that it had stopped working. Each ran,
returned, wrote its field and passed its tests. What surfaced them was a loop we
fell into rather than designed, and it is the transferable part of this project.

![Figure 5](figures/fig3-loop.png)

*Fig. 5: The measurement loop. Every dead layer in this article was found on it.
Source: author-created with Graphviz.*

The step that does the work is the third. A layer that has just produced a good
number is the least likely thing in a system to be re-examined, and it is where
every one of our false results lived: a reranking stage with an interval excluding
zero, a judge with a 2:1 separation, a voting layer with five net fixes. All three
evaporated under a second draw, a corrected prompt, or a held-out split.

The fourth step is the one that costs something. When the judge's separation
turned out to be living in an accidental prompt defect, fixing the defect meant
losing a published-looking result — and the fix was still right.

## What we would tell you

We set out believing that stacking reliability layers buys reliability. Measured
end to end, **the layers made errors visible rather than fewer** — worth a great
deal, and not what they were bought for.

Condition your confidence on something that does not resample — a vocabulary, a
schema, a type check, a compiler — and establish its precondition before you
build on it. Test that free layer against your answer key first: every rejection
there is false by construction, so you get its false-positive rate for nothing.
Ours went from 9.3% to 0.13%.

Then treat the accounting as part of the system rather than a report on it. Grep
for the readers of every field you write, re-measure the top when you change the
bottom, and print coverage beside every error rate.

The system ships about a fifth of its answers, at four errors per hundred instead
of sixty-three, and hands the rest to a person. That is not what we set out to
build. But the machinery that makes the other four-fifths *legible* to that person
turned out to be worth more than any of the layers that tried to answer them.

## What we could not settle

Three questions this project raises and does not answer.

The reproducibility mechanism rests on one sparse model against four dense ones.
That is suggestive and it is not a result: it wants a wider set of
Mixture-of-Experts models, and if sparsity is the variable it should hold across
them and fail on a dense model of similar size.

The precondition in section 5 was discovered after the fact, by running the whole
system for hours to learn something a single query would have told us. Each layer
has a property its value depends on — whether the checks ever fire, whether
samples re-find the same spans, whether a judge separates known-good from
known-bad input — and every one is measurable on a development split before the
layer is built. Whether such a preflight actually predicts which layers will pay
is the obvious next experiment, and we have not run it.

And the second corpus is a demonstration, not a matched comparison: one run, no
tuning history, and a task shape different enough that some of what we measured
may belong to numeric spans rather than to the ladder. A third corpus with a
lexical vocabulary would test whether the ~85% ACCEPT lane belongs to controlled
vocabularies in general or to SNOMED in particular.

---

## Limitations

The held-out split was spent once, so its intervals are the claim. The judge is a
3.2B model grading a 20B one. Human cost is a **count** of records routed, never
minutes — no reviewer session was timed. The near-miss corruption is synthetic.
CADEC is public and from 2015, so it is almost certainly in pretraining, which
inflates the bare-model baseline and makes every gain here conservative.
**FiNER-139 is CC-BY-SA-4.0 and that arm is reproducible from a clean checkout**;
CADEC is not redistributable.

Code, the measurement ledger, every decision record, and the source for each
figure in this article: **https://github.com/wbagais/reliability-ladder**

---

*Cuts from the 4,569-word version, for review: the answer-key boundary ceiling
(~0.67 deterministic, capping exact F1 near 0.70); the menu-order and
prompt-duplication findings; `granite4` rescued by retrieve-and-pick;
`qwen3` ranked wrongly by a single metric; the oracle desk ceiling; the bootstrap
methodology detail; and the full "Reproducing this" section, which belongs in the
README.*

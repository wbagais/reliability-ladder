# The AI Reliability Ladder, Measured Rung by Rung

> **No claim is open.** The two that were at risk have both been checked.
> CADEC's boundary convention caps span-exact scores near 0.70 — verified
> against the strongest published system on this corpus, and it held. And
> §9's *"retrieval is a ceiling"* rested on a general-purpose 30M embedder
> where this task's literature uses domain-adapted ones; we swapped in
> SapBERT and measured it. It puts gold on the menu more often across the
> corpus and made the system **worse**, three draws for three. §9 now carries
> that result. Everything here is measured, labelled by split, and cited.

**Pushpdeep Mishra · Wejdan Bagais**

*Seven reliability layers around a language model, measured one at a time on two
tasks with real answer keys — what each one bought, and what it charged.*

![Figure 1](figures/fig0-hero.png)

*Fig. 1: The seven rungs, coloured by what each one bought. The two that mattered
cost nothing. Source: author-created with Matplotlib.*

---

## Five key takeaways

1. **Reproducibility is a model choice.** Four of five open-weight models gave byte-identical output across three identical runs. The one that varied bought 6.5 accuracy points and cost a spread wider than every improvement we shipped.
2. **The model should read the text and nothing else.** Recalling an identifier, building the candidate list, ordering it, checking, judging, and deciding to abstain each measured better when taken away from the model.
3. **A free string comparison beat the LLM judge by 3×** at identifying which answers were correct — and held at ~85% across five model families spanning 2.8× in accuracy.
4. **That check has a precondition you can test in one query.** On a corpus where the span is a bare number it has zero coverage, and the system silently ships nothing.
5. **Deleting the three paid layers changed one answer out of 43 and saved 518,590 tokens** (development split). The layer that cut errors from 62.9 to 4.0 per 100 spent nothing — and charged 196 of 248 records to a person instead.

---

## What an AI reliability ladder is for

A language model is not a dependable component. The standard response is to wrap
it in layers until the whole behaves as if it were: check the output against
something deterministic, ask the model to correct itself, sample it and take the
majority, have a second model judge it, withhold what cannot be corroborated,
send the rest to a person.

Six layers above the model. Each reasonable, each with published work behind it,
and all of them resting on one assumption — that they stack.

Each layer has its own literature and we lean on it below. What we could not find
published is the comparison *between* them: the layers priced against each other,
on the same records, in the same run, with the free one entered as a competitor
rather than as preprocessing. So we built all seven and measured each.

The staircase is not there.

![Figure 2](figures/fig6-spine.png)

*Fig. 2: How to read this article. One question, three sub-questions, one body of
evidence under all three. Source: author-created with Graphviz.*

## The task, and the result

Read a patient's forum post about a drug. Find every adverse reaction. Assign each
a SNOMED CT code. There is a real answer key — CADEC, 1,250 posts, 9,111
annotated mentions — and the task is the shape of many production pipelines: pull
structured records out of prose, normalise against a controlled vocabulary, be
prepared to defend each one.

"Be prepared to defend each one" is the harder problem. A system that is 80% right
and cannot tell you *which* 80% is unusable wherever a wrong answer costs
something.

> **On the held-out split, run once and never re-run:** the system ships **23%**
> of its answers — 72 records of 314. On those it makes **3.8 errors per 100**,
> against **59.6** for the bare model. It sends the other **242** to a person.
> End-to-end F1 is **0.204 [0.150–0.260]** span-exact, **0.215** on overlap.

Not a good result. An honest one — and most of this article is about the things we
built that did not contribute to it.

The held-out split was spent on that single run, so **every other number in this
article is development-side.** They are labelled where they appear. We say which
split a number comes from every time, because the two do not agree and the
difference is not always in our favour.

---

## 1. The two datasets

An answer key is the whole experiment: a corpus where somebody has already written
down the right answer for every record, so that a score means something. We used
two, and they differ on the property that turned out to decide everything.

**CADEC v2** — the CSIRO Adverse Drug Event Corpus — is 1,250 posts from AskaPatient,
a consumer site where people write up their own experience of a medication. All
1,250 concern two drugs, diclofenac and atorvastatin. Annotation ran as two human
passes, mark the mentions and then attach the terminology, reviewed by a clinical
terminologist. Every adverse reaction the writer mentions is marked as a span of
their own words and given a SNOMED CT code. **One record is one span with one
code**, and our system has to produce both halves from the post alone.

**FiNER-139** is filings made to the US Securities and Exchange Commission,
published as `nlpaueb/finer-139` under CC-BY-SA-4.0. Its gold needed no
annotators at all: XBRL is markup the filing companies attach to their own numbers, audited by
professionals, and the dataset keeps the 139 most frequent tags. Every tagged
figure is a span of digits carrying one US-GAAP tag. **One record is one span
with one tag** — and there is no separate identifier, because the tag name *is*
the answer. Only 17.3% of sentences carry any tag, so most documents hold no gold
at all.

Read as a pair they vary one thing, and it is the thing this article turns on:
whether the words in the source and the words in the vocabulary come from the
same language. `"bit drowsy"` shares a word with |Drowsy|. `"47.6"` shares
nothing with |EffectiveIncomeTaxRateContinuingOperations|, and cannot.

### What the model is given, and what it gives back

![Figure 3](figures/fig7-pipelines.png)

*Fig. 3: Both pipelines, side by side. Two model calls; everything else is
deterministic. The corpora differ on one row. Source: author-created with
Graphviz.*

**First call — find.** The model gets the whole post and an instruction asking
for every reaction, quoted as the writer's own exact words, character for
character — including reactions they say they did *not* have, and the same
reaction twice if it is described twice. It is asked for no concept and no code.

We cannot print a real post: CADEC is non-transferable, and annotated spans and
vocabulary labels are all this article can quote from it. This one is ours,
written to exercise those rules. (FiNER is CC-BY-SA-4.0, so section 6 quotes it
directly.)

```
Been on this for arthritis pain for about three months now. The first
week I was a bit drowsy in the afternoons, and I still get drowsy if I
take it late. No stomach trouble at all so far, which is more than I
can say for the last one. Some days I just feel awful and have no stamina.
```

```json
{"mentions":[
  {"span_text":"arthritis pain",  "negated":false},
  {"span_text":"bit drowsy",      "negated":false},
  {"span_text":"drowsy",          "negated":false},
  {"span_text":"stomach trouble", "negated":true },
  {"span_text":"feel awful",      "negated":false},
  {"span_text":"no stamina",      "negated":false}]}
```

Six mentions: the condition the drug was taken for, a reaction described twice
and returned twice, a denied reaction kept rather than dropped, and a vague
state with no specific symptom in it. Every one of those is a rule we wrote
after measuring the corpus.

**Between the calls — retrieval, and there is no model in it.** Each span is
embedded by `granite-embedding:30m` and cosine-matched against 227,554
keyword-to-code rows covering SNOMED's findings and disorders. The twenty
best-scoring distinct concepts become a numbered menu. This is the real one:

```
reaction 1: "bit drowsy"
     [0] drowsy
     [1] dizziness - giddy
     [2] dizziness
     [3] gets drowsiness
     [4] bites self
     ...
     [19] epidemic dropsy
```

Line 0 is right, and several lines under it are the embedder matching on the
letters *b-i-t*. A retrieved menu is not a clean menu.

**Second call — pick.** The model gets that menu and an instruction to answer
with numbers only, never a concept name, with `null` and `no_concept` available
when nothing fits. It returns `{"picks":[{"reaction":1,"choice":0}]}`.

**The menu carries labels only. The model is never shown a SNOMED code, at any
point in the pipeline** — and that `0` is a position in a twenty-line list, not
an identifier. Numbers rather than names because names do not identify: 76.8% of
these menus hold two different concepts carrying an identical label.

**After the calls — resolution, again with no model.** Line 0 is `271782001`,
the concept named |Drowsy|. The code the system ships was looked up from a table,
never generated.

**FiNER runs the same pipeline with the retrieval step removed.** 139 tags fit in
a prompt, so there is nothing to retrieve: the menu is the whole vocabulary,
alphabetical, the same 139 lines for every mention. The right answer is therefore
always on it. Everything else — find, then pick a line number — is identical, and
that is deliberate: a corpus that needed the shape changed would be a different
experiment rather than a second data point.

**The system can fail at either half, so we score them separately.**
*Detection* is whether it found the right words; *coding* is whether it named the
right concept. They fail for different reasons and want different fixes, and one
combined number sends your effort to the wrong half — section 6 catches us doing
exactly that.

**Scoring happens once, at the end.** It is not a step in the pipeline and the
model never sees it: we take the finished records, line them up against the
answer key by span, and count. A span counts as matched two ways and we print
both. *Exact* means the same characters; *overlap* means the two spans intersect.
Exact is the headline and it is harsh — quoting `"extreme rectal bleed"` where
gold says `"rectal bleed"` scores as a false positive *and* a false negative, for
naming the same concept correctly.

### What we removed from the answer key, and why

Before any of this runs, 414 of CADEC's gold mentions are dropped from the
denominator — 6% of the corpus. Three reasons, all recorded per record in
`data/exclusions.csv`:

| reason | mentions | what it is |
|---|---|---|
| **retired code** | 407 | the gold code was withdrawn from SNOMED after CADEC was annotated in 2015 |
| span/offset mismatch | 4 | the annotation's character offsets do not land on its own quoted text |
| invalid code | 3 | the number is not a SNOMED identifier at all |

The last row is the interesting one. Every SNOMED identifier ends in a check
digit, and these fail it — so they were never issued, which means they are typos
rather than retirements. `81680008` is plainly meant to be `81680005` |Neck pain|.
**We did not repair them.** Editing an answer key so the system under test scores
better is how a benchmark stops being evidence. They are dropped, counted, and
reported here.

The retired codes are the bulk, and dropping them matters more than the count
suggests. CADEC was coded against a 2015 release and we score against a current
one; **before this filter 6.3% of coded gold carries a withdrawn code, and after
it 0.5% does.** So the staleness that would otherwise sit inside every coding
number is removed from the denominator rather than absorbed into it — and where
a retired code survives *with* a recorded successor, the scorer names that
outcome separately rather than counting it right or wrong.

**The splits.** 40 documents, 226 mentions, for development — every arm, ablation
and comparison in this article. 60 documents, 290 mentions, held out, run once
and never re-run.

### The two corpora side by side

| | **CADEC** | **FiNER-139** |
|---|---|---|
| Task | find adverse reactions in forum posts, code to SNOMED CT | tag numeric facts in SEC filings with one of 139 XBRL tags |
| A span looks like | `"bit drowsy"` | `"47.6"` |
| Vocabulary | 129,675 concepts — too large to show the model | 139 tag names — the whole thing fits in the prompt |
| We used | 40 dev docs (226 mentions), 60 held out (290) | 40 dev docs (165 mentions), one run |

---

## 2. Rung 0: what it is, what we tried, what it achieves

**Sections 2 and 3 are the extraction step alone** — rung 0, over 40 development
documents on each corpus, `gpt-oss:20b` unless another model is named. No checks,
no refusal: this is what the model proposes, not what the system ships. Section 1
showed the pipeline; this is what came out of building it. Section 4 is where the
ladder proper starts.

### First we tried three shapes for rung 0

Before any of that, a more basic question: how much of the job should the model
do? We built three versions and measured them on the same 40 documents.

| | what the model is asked for | F1 exact | F1 overlap | tokens | replies that would not parse |
|---|---|---|---|---|---|
| **S0** | the span, the concept name, **and the code** | **0.018** | 0.018 | 43,998 | **5 of 40** |
| **S1** | the span and the concept name; the code is looked up | 0.171 | 0.305 | 36,079 | 0 |
| **S2** | the span; then a line number from a retrieved menu | **0.209** | 0.310 | 68,906 | 0 |

**S0 is not weak, it is broken.** Ten times worse than S1, for *more* tokens, and
it is the only version that fails to produce readable output at all. Asking a
model to recall a nine-digit identifier from its weights is the single most
expensive thing in this table and the least successful.

It also fails in the way that matters most. S0 was given an explicit escape —
answer `null` if you do not know the code — and it used it 12.4% of the time. It
still emitted `2714004`, a code that exists in no SNOMED release, next to a
correct concept name. **An abstention hatch reduces fabrication and does not
remove it.**

S1 and S2 are close: half a point apart on overlap, 3.8 on exact, and S2 costs
1.9× the tokens. We froze S2 anyway, because rungs 1 to 6 all have to be measured
against one extraction step and the exact metric is the headline — but the cost
is a declared trade, not a free win.

A fourth design was dropped before it could be measured properly: show the model
one fixed printed list of codes and have it pick. No printable list survives
contact with this task. The obvious candidate is the answer key's own inventory,
which is circular; the best ontology-native alternative covers 48.7% of gold; and
the real keyword table is 227,554 rows. **A list retrieved per mention is S2.**

Everything section 3 measures is a change *within* S2.

### Seventeen changes to the one we picked

Every result below is judged against one number. **Three identical runs of this
system differ by 2.1 points of F1** — the same 40 documents answered 92, 98 and
94 times correctly out of 226, with nothing changed between runs. Section 3 is
about where that number comes from and how nearly it fooled us; here it is just
the bar, and it works out to roughly three correct answers per point. Here is everything we tried on the extraction step, measured
against it — development split throughout, span-exact unless noted, and labelled
by which corpus it was measured on:

| change to rung 0 | corpus | effect | |
|---|---|---|---|
| a worked example in the prompt | CADEC | **+5.7 pt** | shipped — at 1.55× the tokens |
| negation: extract denied reactions, flagged | CADEC | **+6.2 pt** | shipped |
| coordination splitter: one quote → several records | CADEC | **+4.4 pt** | shipped, sign consistent 3/3 |
| span trimmer: cut spans to gold's boundary convention | CADEC | +0.4 pt | shipped |
| the trimmer's threshold, tuned | CADEC | +1.4 pt | shipped, interval contains zero |
| drop spans not found in the post | CADEC | 11 records, **0 gold** | shipped — can only remove errors |
| drop spans with no content word | CADEC | — | shipped |
| drop repeated spans | both | 39 spans, **0 gold** | shipped |
| a worked example, FiNER's own | FiNER | — | shipped |
| drop spans that *are* a date or a clock time | FiNER | 26 false positives, **0 gold** | shipped |
| **reranking the menu** | CADEC | **+0.7 pt, sign flips** | **rejected** |
| three prompt rewrites | CADEC | traded exact for overlap | **rejected** |
| rewriting the query before retrieval | CADEC | recall 87.0% → 86.5% | **rejected** |
| a domain-adapted encoder (SapBERT) | CADEC | **−2.7 pt** | **rejected** |
| alphabetising the menu | CADEC | **−10 to −12 pt** coding | **rejected** |
| ordering the menu by sentence context | FiNER | **−9 pt** coding | **rejected** |
| drop any span with no digit in it | FiNER | 14 errors cut, **7 gold destroyed** | **rejected** |

Seventeen changes, ten shipped. **The pattern worth taking is which ones won.**
The two largest — a worked example, and telling the model to report denied
reactions — are both *the prompt describing the task more exactly*. The next
fixes a structural mismatch: gold marks each reaction separately, and our
extractor returned one quote covering several. Nothing that tried to help the
model *choose better from the menu* ever cleared the bar, and four of those made
it worse.

One qualification we owe that sentence. The most promising menu intervention we
built — a rerank pass driven by the model itself rather than by a free feature —
was measured on **one draw** and dropped on cost before it ever faced three. It
is untested, not rejected. Every other row here survived or failed the full
three-draw test; that one did not take it.

Most rejections are only interpretable because we measured the floor first.
**+0.7 points looks like a result until you know that three identical runs of the
unchanged system differ by 2.1.**

**The two corpora do not run the same rung 0, and that is deliberate.** Four of
CADEC's shipped arms were never ported: two are CADEC-specific by construction —
a splitter learned on clinical phrases, and a trimmer threshold learned from
CADEC's own boundary convention — and two more are generic enough that they would
probably transfer, which is exactly why they were not ported unmeasured. Copying
an arm across would declare as measured something that was never measured on that
corpus. So FiNER runs a leaner extractor, and its numbers in section 6 should be
read as such rather than as the same system pointed at harder text.

### What that leaves: where the answers go

S2 produces one number — F1 around 0.41 — and one number cannot tell you
which stage to work on. Following every gold mention and every proposed span
through the three stages can:

![Figure 4](figures/fig9-funnel.png)

*Fig. 4: Rung 0 on the CADEC development split, draw 0. **The only input is the
40 posts**; 232 spans come out, 219 of them scorable. The answer key is dashed
because it is not part of the pipeline — the system never sees it, and it is
applied only at the comparison. The 219 and the 226 overlap rather than sum: the
126 matched spans are one prediction **and** one gold mention. The other two
draws differ by a few at each node — matched 126 / 133 / 129, code on the menu
114 / 119 / 115, correct 92 / 98 / 94. Source: author-created with Graphviz.*

**Three outcomes, not four.** There is no true negative on this task. A true
negative would be a span the system correctly declined to extract, and the
negative class is every possible span in every post — unbounded, so it cannot be
counted. That is why extraction is scored with precision, recall and F1, none of
which reference TN. FiNER is the exception, and it is a useful one: its
candidates are the numeric tokens in the text, which *are* enumerable, so
"correctly tagged nothing" is measurable there and section 6 uses it.

The three stages lose very different amounts, and the ranking is not the one the
project spent its effort on:

| stage | loses | of what reached it |
|---|---|---|
| **find** — quote the reaction | **100** missed, **93** invented | 44% of gold, 42% of predictions |
| **retrieve** — 20 nearest concepts | 12 | 10% of spans matched |
| **pick** — choose a line | 22 | 19% of menus holding the answer |

**Detection is where almost all of the loss is, on both sides.** It misses 100 of
226 gold mentions and proposes 93 spans that match nothing — nearly as many
inventions as correct answers. Retrieval and the pick together account for 34
mentions.

Notice also that the two middle failures are counted twice. A right span with a
wrong code is a **false positive** — the system asserted something untrue — *and*
a **false negative**, because the gold mention still went unanswered. That is the
double penalty section 1 described, visible in the arithmetic: FP 127 and FN 134
overlap on the same 34 records.

And the effort went to the wrong stage. Of ten shipped changes, the two largest
help the model *read* — a worked example and the negation rule — but six of the
seven rejected arms were attempts to improve the *choosing*, which loses 22
mentions out of 226.

That inverts on the second corpus. On FiNER the whole vocabulary is in the
prompt, so retrieval cannot lose anything and the right answer is always on the
menu; section 6 shows the loss moving almost entirely into the pick. **Same
pipeline, opposite bottleneck** — which is why we report detection and coding
separately everywhere, and why one recall number would have sent the effort to
the wrong stage on at least one of the two corpora.

That is the baseline: 41% of gold answered correctly, most of the loss in
detection, and a set of stages that each fail differently. The obvious next move
is to improve it. Section 3 is what happened when we tried.

> **[PENDING — the same tree for FiNER.]** It cannot be drawn from anything that
> survives: `data/finer` is in no checkout, so the FiNER records cannot be
> re-scored against gold. The stage-by-stage split for FiNER is registered work.

---

### The same pipeline, five different models

Everything above is one model. Running four more families through the identical
frozen configuration says which findings belong to the pipeline and which to
`gpt-oss:20b`:

| model | spans proposed | detection | coding | F1 exact |
|---|---|---|---|---|
| `gpt-oss:20b` | 232 | **0.788** | **0.599** | **0.401** |
| `llama3.1:8b` | 214 | 0.745 | 0.530 | 0.336 |
| `mistral:7b-instruct` | 259 | 0.685 | 0.386 | 0.206 |
| `granite4:micro-h` | 292 | 0.637 | 0.345 | 0.185 |
| `qwen3:8b` | **57** | **0.318** | **0.556** | 0.141 |

Headline F1 spans a factor of **2.8**, and the two halves do not rank the models
the same way. **`qwen3:8b` is last by F1 and second by coding** — ahead of llama
and mistral at choosing the right concept, behind only gpt-oss. It ranks last
because it proposes 57 spans where gpt-oss proposes 232. A single number puts it
below two models it beats at the half everyone assumes is hard.

`granite4:micro-h` fails the opposite way: 292 spans, the most of any model, and
the worst coding accuracy. One over-extracts and codes badly; the other barely
extracts and codes well. **Neither failure is visible in the F1 column.**

Cost does not track quality either. `qwen3` took roughly two hours per run
against llama's fifteen minutes, for a quarter of the output.

---

## 3. How much of this is real?

Two of the numbers above nearly came out differently, for two different reasons.
The first is a mistake anyone can make with a standard tool. The second is why
the tool had nothing to work with.

### What a confidence interval actually prices

**One row of that table nearly went the other way**, and how it did is the
sharpest thing this project learned about measurement.

The reranking stage reorders the twenty-line menu before the model picks from it,
so a good concept sitting at line 14 moves up. It is the most obvious thing to
try once you know the menu usually holds the right answer, and we built it. Then
we asked whether it helped.

The standard way to ask is a **paired bootstrap**. Score every document twice,
with the stage on and off. Resample the documents at random a few thousand times,
and see how often the difference comes out positive. If nearly always, the
improvement is real.

It came out **+0.0217 overlap F1, interval [+0.0000, +0.0433]**. Above zero.
Significant. Most write-ups stop here.

We ran the same comparison twice more:

| draw 0 | draw 1 | draw 2 |
|---|---|---|
| **+0.0217** | +0.0087 | **−0.0089** |

The sign reverses. The three average to +0.007 — a fifth of the noise floor
section 2 measured. **So the reranker does not work, and we did not turn it on.**
The code ships and the arm stays off: nothing here separates from zero across
draws, and a change that cannot be told from noise must not become the
configuration every rung above it is measured against.

The verdict is not the interesting part, though. The interesting part is that a
standard statistical test had already told us the opposite.

**The test was not broken. It answers a narrower question than it appears to.** A
bootstrap over documents asks *would this hold on different documents?* It never
asks *would this hold on a different run?* It resamples the documents of one run,
so run-to-run variance is invisible to it — and here that is the larger term.

> **Three draws minimum, and report all three.**

### And a wrong number that looked right

The helper computing those intervals resampled with `set(random.choices(...))`.
A bootstrap works by drawing duplicates; **the `set()` deleted them**, leaving a
63% subsample.

It ran that way for a month, because the intervals looked fine — right size,
sensible width, plausible bounds. Nothing errored, nothing looked odd, and no
number was implausible enough to make anyone re-derive it. **A wrong number that
looks wrong gets found. A wrong number that looks right becomes evidence.**

**And that helper had measured every rung 0 arm we accepted before we found it.**
Not the reranker alone — the reranker was caught before it shipped, which cost
nothing. The arms already *in* the shipped configuration had been judged the same
way, two of them on a single draw each.

So we re-tested those two with the fixed estimator, at three draws:

| shipped arm | one draw said | three draws said |
|---|---|---|
| coordination splitter | a gain on exact **and** overlap | **exact only** — the overlap effect reverses sign |
| the trimmer's threshold | a gain | consistent, small, inside the noise band on its own layer |

Both survived, and we kept them. But **the splitter's overlap claim did not** —
the single-draw headline had implied a gain there and never established one. That
is the honest shape of this: the method was wrong, the conclusions happened to
hold anyway, and we found out which was which only by redoing the work.

The reranker is the memorable story because it is the one that reversed. The
expensive one is the quieter fact that a shipped configuration had been accepted
on a number nobody had reproduced.

---

### Where the 2.1 points comes from

One thing is still unexplained: why does an identical configuration move at
all? We ran at **temperature 0** — not low-temperature sampling but greedy
decoding, where the model takes its single highest-probability token every time.
The knob everyone reaches for was already turned all the way down.

So we ran five model families over the same 40 documents, three times each. The
result was not what we expected, and it reframes everything above.

One run reads all 40 documents and writes one output file, so three runs give three files — and the question is how
many of those three are **different from each other**. One means the model
repeated itself perfectly; three means no two runs agreed.

| model | architecture | CADEC: different files, of 3 runs | mentions all 3 runs agree on | FiNER: different files, of 3 runs |
|---|---|---|---|---|
| `llama3.1:8b` | dense | **1** | **100%** | not run |
| `mistral:7b-instruct` | dense | **1** | **100%** | not run |
| `granite4:micro-h` | Mamba/transformer hybrid | **1** | **100%** | not run |
| `qwen3:8b` | dense, reasoning | **1** | **100%** | not run |
| `gpt-oss:20b` | **Mixture-of-Experts** | **3** | **62.8%** | 3 or 2, see below |

Read the last row across: on CADEC all three of `gpt-oss`'s runs differed; on
FiNER two of the three came out identical and the third did not.

**The FiNER column is nearly empty and that is a gap, not a finding.** Only the
extractor was run three times there; the other four families were probed on a
single document. Filling that column is registered work — and it would test
whether bit-reproducibility is a property of the model or of the model and the
corpus together, which nothing here establishes.

Four of five are **bit-reproducible**, in the strong sense: three runs, one
SHA-256, every span and every code identical. Not "stable within noise" — the
same file, byte for byte.

So run-to-run variance is **not** a property of language models. It is a property
of *this* language model — and we had assumed otherwise for as long as we had
run only one model, which was most of the project.

Three things this table does not say. `qwen3` also reasons and `granite4` is also
an unusual architecture, so **neither deliberation nor novelty is what separates
them** — sparsity is the one property the odd model out has alone, and one MoE
model cannot establish a mechanism. The figures are **CADEC only**; on FiNER just
`gpt-oss` was run three times. And **repeatable is not the same as right**: a model can return the same
wrong answer three times, which is what `granite4:micro-h` does at F1 0.185.
This section asks only whether the ground holds still. Section 4 onward asks
whether what stands on it is correct.

### Where the fifth model actually moves

It is not a temperature setting. We ran at **temperature 0** — not
low-temperature sampling but greedy decoding, where the model takes its single
highest-probability token every time — same documents, prompts, machine and hour.
The knob everyone reaches for was already turned all the way down, and four other
models under those same settings returned one file three times.

Three draws of the shipped configuration. (Every F1 in this article is
`ladder/score.py`'s span-exact figure with the declared exclusions applied —
worth saying once, because this repo carries three F1 variants that differ from
each other by more than any improvement it ever shipped.) The useful comparison
is not how each one scored against gold — that is section 4's question — but **where the three
runs disagree with each other**, which needs no answer key at all.

Lining the runs up mention by mention, and grouping any spans that overlap into
one mention, gives 298 mentions across the three runs:

| CADEC — across three identical runs | mentions | |
|---|---|---|
| **all three agree — same span, same code** | **187** | **62.8%** |
| same span, different code | 26 | 8.7% |
| same code, different span | 6 | 2.0% |
| both differ | 11 | 3.7% |
| found by only two of the three runs | 35 | 11.7% |
| found by only one of the three runs | 33 | 11.1% |

Three summary numbers fall out, and they are not the same number:

| | |
|---|---|
| **consensus** — all three runs, same span *and* same code | **62.8%** |
| all three runs propose the same span | 71.5% |
| all three agree on the code, where all three found the mention | 83.9% |

**Three runs of one frozen configuration reach full consensus on fewer than two
mentions in three.** The rest splits between the two halves of the job: **22.8%
of mentions are not even found by all three runs**, and **8.7% are found
identically by all three and then coded differently.**

Both failures are worth seeing, because they look nothing alike. The coding one:

> span `"at my wits end"`, quoted identically by all three runs
> run 0 → **CONCEPT_LESS** — no concept fits
> runs 1, 2 → `225444004` |At risk for suicide|

One run declined to code it; two filed a suicide-risk concept. Same model, same
prompt, same menu, same hour. And the detection one, which is milder:

> run 0 → `"very very severe abdonimal pain"`
> runs 1, 2 → `"abdonimal pain"`
> all three → `21522001` |Abdominal pain|

Same concept, different boundary — the disagreement two human annotators also
have, and the one section 1 said exact matching punishes twice.

Note what did *not* prevent any of this: narrowing the question. The pick step
chooses a number from a twenty-line list, about as constrained as a request gets,
and it is where 8.7% of mentions diverge.

### On FiNER the same model was sometimes perfectly stable

We have two three-draw sets on FiNER, and they disagree about whether this model
is reproducible at all.

**In one set, all three runs produced the identical file.** Not similar — the
same SHA-256, and 306 of 306 mentions in full consensus. These were real calls,
not replays: median 56 seconds per document, no cached responses.

| FiNER — across three identical runs | mentions | |
|---|---|---|
| **all three agree — same span, same code** | **306** | **100%** |
| every other category | 0 | 0% |

**In the other set, one run refused a whole document.**

| FiNER, the earlier set | draw 0 | draw 1 | draw 2 |
|---|---|---|---|
| detection recall | **0.679** | 0.691 | 0.691 |
| coding on matched spans | **0.393** | 0.421 | 0.421 |
| F1, exact span | **0.193** | 0.205 | 0.205 |
| output file | — | **identical SHA-256** | **identical SHA-256** |

Draws 1 and 2 are the same file. The whole difference is draw 0, and inside it a
single document, where the extractor answered *"I'm sorry, but I can't provide
that."* and returned nothing. The other runs got 33 mentions from it. That
document held **21 of FiNER's 165 gold mentions — 12.7% of the answer key.**

So the honest statement about this model on this corpus is not "it is
reproducible" or "it is not". It is **sometimes**, and the difference between the
two sets is one document in one run.

> Variance does not always arrive as a wobble across records. It can arrive as
> one whole document, all or nothing — and an average over records hides exactly
> that shape.

That also sharpens the comparison with CADEC. The same model, the same
temperature, the same two-call pipeline: **62.8% consensus on one corpus and
100% on the other.** Whatever makes this model unstable is not a property of the
model alone — the task it is pointed at decides how much room the instability
has, and nothing here tells us why.

**Which answers an objection that usually ends the conversation.** *You cannot
put a language model in a pipeline that has to be auditable, because it will not
give you the same answer twice.* On this evidence that is false as a general
claim: four of five open-weight families gave the same answer three times out of
three, to the byte, and even the one that did not agreed with itself completely
on nearly two mentions in three.

> **Repeatability is available.** `gpt-oss:20b` buys 6.5 exact points over
> `llama3.1:8b` and pays its reproducibility for them. That is a purchase, and
> you can decline it.

Which reframes this whole section. Most of what we could not prove about our own
improvements, we could not prove because of a model we had chosen and never
compared against an alternative — for as long as we had run only one, which was
most of the project.

## 4. Rung 1: what a free deterministic check can and cannot see

**This is the first rung above the model, and the only free one.** If the output
will not hold still, attach something that will: SNOMED CT does not resample. Ask
the vocabulary whether a proposed code can be right — does it exist, is the span
really in the post, is the concept the right kind of thing — and you get an
answer that is identical every time you ask, for zero tokens and no model call.

**Everything in this section is CADEC.** Rung 1 on FiNER is a different animal
and it does not work; section 6 is where that gets its own accounting.

**Rung 1 judges; it does not route.** Its verdicts are recorded and counted, and
the record continues untouched, so every rung above it sees the same unfiltered
set and each one's contribution stays attributable to it. Acting on a rung 1
verdict is rung 5's job, at the top of the ladder. That is a deliberate choice
and it is reversible in configuration; it matters here because a REJECT below is
a *finding*, not a deletion.

Also unlike the rest of this article, none of what follows depends on a model
run. We corrupted a perfect answer set one error class at a time — every gold
record, all 8,666 of them, once per class — and watched what the checks did. No
sampling, no draws, no noise floor.

| planted error | caught |
|---|---|
| code that exists in no release | **1.000** |
| span shifted off its mention | **1.000** |
| quote fabricated, not in the post | **1.000** |
| wrong branch of the hierarchy | **1.000** |
| near-miss finding sharing a head word | **0.001** |

On the classes they are built for, these checks are **not approximately good.
They are exact, at zero cost, with no model call.**

### Three verdicts, and none of them is "correct"

So the vocabulary cannot tell you an answer is right. What it can do is sort
every answer into one of three lanes — and the names are worth being careful
about, because none of them means what it sounds like.

| lane | what it actually claims | what it does **not** claim |
|---|---|---|
| **REJECT** | *provably wrong.* A check failed: the code is in no release, the quoted span is not in the post, or the concept is the wrong **kind** of thing — SNOMED knows whether a concept is a clinical finding, a drug product or an organism, and a reaction coded to an organism is wrong whatever the words say. | — |
| **ACCEPT** | *the vocabulary uses these very words.* The span text matches one of the code's own names — identical strings, under the setting we ship. | that the answer is right |
| **BAND** | *nothing fired.* No check found anything wrong, and no string matched either. | that the answer is wrong |

The order matters, because the checks run as a chain and stop at the first
failure. A record is REJECTed the moment any check fails. If it survives all of
them, one last test decides between the other two: **does the patient's span text
match one of the concept's names, as strings?** Match, and it goes to ACCEPT.
No match, and it goes to BAND.

**And no lane is a decision.** An ACCEPT record is not cleared for shipping and a
BAND record is not held back: rung 1 judges without routing, so every record in
every lane goes on to every rung above. The verdict is a label that rung 5 will
read, five steps later, when something is finally allowed to act on it.

So **BAND is not a negative verdict. It is the absence of one** — the lane for
records nothing could say anything about. Two thirds of everything lands there,
including plenty of correct answers:

> `"extreme rectal bleed"` → `12063002` |Rectorrhagia| — **correct**, and BAND.
> The vocabulary holds twelve names for that code, among them "rectal bleeding"
> and "blood per rectum". None is the phrase the patient used.

Gold's own span for that mention is `"rectal bleed"`, and it lands in BAND too.
**Even quoting the answer key exactly is not enough**, because "bleed" and
"bleeding" are different strings and the test compares characters.

And **ACCEPT is not a correctness claim either.** It says the words line up.
Section 5 is about how far that turns out to go, and it goes further than it has
any right to — but the check itself is only ever making a statement about
spelling.

**57% of even a perfect answer set lands in BAND.** That is the ceiling on how
much of the batch this rung can settle for free, and you can know it before
spending a token.

### What rung 1 receives, and what it does with it

Everything. Rung 1 judges without routing, so the whole of rung 0's output
reaches it — including the 96 records sitting on no gold mention at all. It has
no way to tell those apart, which is the point: it sorts on the vocabulary alone.

![Figure 5](figures/fig10-rung1.png)

*Fig. 5: Rung 1 on the CADEC development split, draw 0. The lanes are assigned
from the vocabulary with no model call and no answer key; the correct / wrong
split inside each lane is scored afterwards. Draws 1 and 2 agree closely —
ACCEPT 85.7% and 85.1%, BAND 29.9% and 31.2%. Source: author-created with
Graphviz.*

**The sort works, and it costs nothing.** An answer in ACCEPT is right **85%** of
the time; an answer in BAND is right **29%** of the time. Rung 1 arrived at that
split without a model, without gold, and identically on every run — which is the
whole argument of section 5.

Two things in that figure are worth more than the headline.

**BAND is where the false positives go.** 94 of its 174 records sit on no gold
mention at all — so the lane that cannot be confirmed is also the lane holding
most of what the model invented. That is a coincidence of construction rather
than intelligence: an invented span has no vocabulary words to match, so it fails
the lexical test the same way a real-but-unmatched span does.

**REJECT is empty, and we emptied it.** Rung 1 used to reject 5.1% of records for
an unlocatable span. Then a rung 0 filter started dropping those at source, and
the class arrived already empty — 0, 2 and 2 records across the three draws. The
check still runs, still passes its tests, and has nothing left to find. Section 8
is about what that did to the rung above it.

### The one decision this rung has

The ACCEPT/BAND divider is a string comparison, and it can be run two ways. You
pick one in the manifest and it applies to every record.

| setting | a match means | `"bit drowsy"` against the names of `271782001` |
|---|---|---|
| **`exact`** | the strings are identical, after lowercasing | none of the eight names *is* "bit drowsy" → **BAND** |
| **`contained`** | identical, **or** one's words are a subset of the other's | "drowsy" is a subset of "bit drowsy" → **ACCEPT** |

`contained` is the looser one. It accepts everything `exact` accepts and more, so
switching to it can only move records **from BAND into ACCEPT**, never back.

**It buys eleven points.** Free coverage goes from **43.1%** of gold to **54.5%**
— an eighth of the batch settled without spending a token, all of it records like
`"bit drowsy"`, where the patient's phrase wraps a word the vocabulary uses.

**We took the strict one anyway**, and here is the measurement that decided it.
We planted near-miss codes into the answer key — real, active, correctly-typed
findings sharing a head word with the right one, which is the mistake a coding
model actually makes — and ran both settings over them:

| setting | near-misses **caught** | near-misses put in **ACCEPT** |
|---|---|---|
| `contained` | 0.1% | **19.0%** |
| `exact` | 0.1% | **0.1%** |

Read the two columns separately, because they say different things.

**The first column is identical, and that is the point of section 4.** Neither
setting catches near-misses. No string comparison ever will — the right code is
not in the source text, so nothing mechanical can put it there.

**The second column is the decision.** It is not about catching them; it is about
what happens to the ones that get through. Under `exact` they sit in BAND, where
nothing is claimed about them. Under `contained`, **one in five is moved into
ACCEPT** — the lane that means *the vocabulary vouches for this*, and the lane
rung 5 will act on.

Eleven points of free coverage is not worth a check that endorses one near-miss
in five. The cost of refusing them is only that more records fall through to the
paid rungs, which is what the rest of the ladder is for.

**What that decision looks like on the records themselves.** Replaying the same
222 records through the same four checks under each setting:

![Figure 6](figures/fig11-lexmode.png)

*Fig. 6: The same records, the same rung, the two settings. Correctness is scored
afterwards and rung 1 never sees it. Source: author-created with Graphviz.*

| setting | ACCEPT | of those, correct | BAND | of those, correct |
|---|---|---|---|---|
| **`exact`** *(shipped)* | 48 | **85.4%** | 174 | 29.3% |
| `contained` | 88 | 63.6% | 134 | 26.9% |
| | **+40** | **−21.8 pts** | −40 | −2.4 pts |

The looser setting **nearly doubles the free lane and takes 22 points off its
accuracy.** Of the 40 records it adds, **15 are correct**; the other 25 are wrong
or sit on no gold mention at all.

And notice what does *not* happen. BAND's accuracy barely moves, 29.3% to 26.9%.
**The setting does not sort better. It moves the line**, and most of what it
moves across is unverifiable either way. That is the difference between a check
that discriminates and a threshold that is simply lower.

**Why the looser setting loses 22 points of lane accuracy is not something we
have investigated, and this article does not answer it.** We measured the effect
and made the decision on it; we did not decompose it. Whether those 25
non-correct additions share a structure — a particular kind of qualifier, a
particular shape of concept name — is future work, and it matters, because a
rule that admitted the 15 correct ones without the other 25 would be worth eleven
points of free coverage.

It also decides the number section 5 is built on. **The ACCEPT lane is ~85%
correct because of this setting** — under the alternative it would be 64%, and
the claim that the free check identifies a reliably-correct subset would not
survive.

**The strict setting reduces that failure by a factor of 190. It does not remove
it.** Here is one of the 0.1%, from the development split, sitting in ACCEPT:

> span `"knee pain"` → `1003722009` |Pain of knee region|
> gold says `30989003` |Gonalgia|

Both concepts carry **"Knee pain"** among their names, so the span matches either
one exactly. The check accepts whichever the model picked and has no way to
prefer the other.

**A lexical match is evidence about the words, never about the claim.** Where two
concepts share a name — and SNOMED has many such pairs — it is not even evidence
about which of them you meant.

One caveat on that example, because it cuts against us. Gold's code there is
retired and SNOMED records no successor for it, while ours is active and means
the same thing to a clinician. Our scorer credits only the code in the answer
key, so a defensible synonym is filed as an error. We have not measured how often
that happens; it is on the list at the end.

---

## 5. The one thing that worked

The ACCEPT/BAND split predicts correctness, and unlike the headline number it
barely moves between draws. Five model families, three draws each:

| model | exact F1 | **ACCEPT lane** | BAND lane | ratio |
|---|---|---|---|---|
| `gpt-oss:20b` | 0.401 | **84.6%** | 35.9% | 2.36× |
| `llama3.1:8b` | 0.336 | **80.4%** | 28.8% | 2.79× |
| `mistral:7b-instruct` | 0.206 | **83.3%** | 14.6% | 5.70× |
| `granite4:micro-h` | 0.185 | **89.3%** | 14.6% | 6.12× |
| `qwen3:8b` | 0.141 | **83.3%** | 30.3% | 2.75× |

Headline F1 spans **2.8×**. The ACCEPT lane spans **80.4 to 89.3**, and its
ordering has no relationship to model quality — the *worst* model by F1 has the
*highest* ACCEPT lane.

These are the same five models section 2 measured, where the F1 column was shown
to rank them badly — `qwen3:8b` is last here and second-best at coding. What
matters now is the column beside it, which does not care.

> The check identifies a subset of answers **~85% correct regardless of which
> model produced them**, and it earns **more** the worse the model is.

The reason is structural. The quantity is conditional on a **deterministic
property of the record**, not on the run. You cannot make the model repeatable.
**You can make your knowledge about it repeatable.**

The cost shows up in single records. This one was withheld, and it was right:

> span `"extreme rectal bleed"` → `12063002` |Rectal hemorrhage| — **correct**,
> and withdrawn, because the patient's words and the vocabulary's words share
> nothing.

That is the 57% BAND bill in one line. The check is not saying this answer is
wrong. It is saying it has no evidence either way.

---

## 6. The corpus where the free check never fired

We ported everything to FiNER-139. Sixteen one-line harness edits, no changes to
rung logic.

The result is not a worse score. It is no score — full stack, 292 records:
**ACCEPT 0, BAND 291, REJECT 1.** Coverage 1.0 → 0.0. Every record routed to a
person. The system that ships 21% of its answers on CADEC ships **0%** here.

**And that zero is a fact about our check, not about the corpus.** It has to be
said that way round, because the alternative reading is the more flattering one
and it is wrong.

Walk rung 1's chain on FiNER and almost nothing is live:

| check | on CADEC | on FiNER |
|---|---|---|
| is the span really in the text? | works | **works** |
| does the code exist? | 129,675 concepts; a fabricated id fails | the menu **is** the vocabulary — always true |
| is it active? | SNOMED withdraws concepts; a model can still name one | *"vacuously true for anything that exists"* |
| is it the right kind of concept? | a drug product is not a finding | no hierarchy — always passes |
| **do the words match?** | 12 synonyms per concept, a real test | **always false** |

One check of five has any power on FiNER, and it is the one a rung 0 filter
already handles. So `ACCEPT 0` does not mean the check ran and found nothing
worth accepting. **It means the check could not fire.** Reporting that as a
property of the corpus would be the same mistake as reporting a perfect error
rate over an empty output — which this section is about to catch us doing one
layer up.

![Figure 7](figures/fig4-precondition.png)

*Fig. 7: On one corpus the span and the code's name are drawn from the same
language; on the other they cannot overlap. Source: author-created with Graphviz.*

**The precondition is real, and narrower than we first stated it.** Our test was
*does the span's text share words with the concept's name?* — and by that test
FiNER has no deterministic evidence at all. But the evidence is there; it is just
not in the span:

> *"The **effective income tax rate** was **47.6** percent…"* →
> `EffectiveIncomeTaxRateContinuingOperations`

The tag's own words are in the sentence. De-camel-case the tag and four of them
appear verbatim within a few characters of the number. **We built a check that
looks only at the span, on a corpus where the span is the one place the evidence
cannot be**, and then reported the result as though the corpus were at fault.

> **Test this before you build:** deterministic evidence of this kind exists when
> the vocabulary's words and *the source's* words come from the same language —
> and check where in the source you are looking. A span-level test on a corpus
> whose spans are bare quantities returns zero whether or not the evidence
> exists.

> **[PENDING — a rung 1 that works on FiNER.]** Two deterministic checks are
> registered and neither is built: matching the tag's own words against the
> sentence around the span rather than the span itself, and a type check (a tag
> ending `Percentage` should carry a span between 0 and 100). Both must be
> measured the way `lexical_mode` was — plant near-miss tags, report the ACCEPT
> coverage **and** the share of near-misses wrongly accepted — because a check
> that lifts coverage while vouching for near-misses is worse than the vacuous
> one it replaces. Until then FiNER has no working rung 1, and every FiNER
> number below is the ladder running with its free rung switched off.

So what the numbers below support is narrower than this section's old title: not
*the corpus where none of it works*, but **the corpus where the check we shipped
could not run** — which is a defect, and ours.

The failure mode is the alarming part. `err_per_100` at the abstention step reads
**0.0** — a perfect error rate over an empty output. A system whose safety
property is "abstain unless corroborated" degrades to "abstain always" the moment
corroboration is inapplicable, and reports flawless numbers while doing it.
**Print coverage beside every error rate.**

**And a ceiling no model work touches.** The label is **not decidable from the
text**: gold tags a number only if the filer chose to tag it *and* that tag made
the top-139 cut. **77% of our false positives are defensible readings of the
sentence.** One of ours:

> *"The Company recognized a net increase in revenues of $ **19.5** million…"*
> — the model tags `19.5 → Revenues`. Gold does not tag it here, though it tags
> that same literal elsewhere in the corpus. Both readings are defensible; only
> one is in the answer key.

### Two things the second corpus told us about the first

FiNER's recall is 0.303, which reads as *the model never proposes 70% of gold*. It
does not. That number is a product — **detection recall × coding accuracy on the
spans it did reach** — and both halves are measurable separately:

| | detection recall | coding accuracy | = recall |
|---|---|---|---|
| full stack, one run | 0.685 | 0.446 | 0.303 |
| extraction alone, three draws | 0.679 / 0.691 / 0.691 | 0.393 / 0.421 / 0.421 | 0.267 / 0.291 / 0.291 |

Either way the shape is the same: the model reaches roughly two thirds of the
spans and mis-codes most of what it reaches. **One recall number for
a pipeline that both finds and classifies sends your effort to the wrong half.**

Decomposing the mis-codes, one tag stopped looking like the others:

> `AccrualForEnvironmentalLossContingencies` is predicted **57 times in 292
> records.** The answer key uses it **twice.**
>
> *(extraction alone, draw 0. The other draws and the full stack agree: 63 of
> 303, 64 of 292 — between 19.5% and 21.9% of all predictions.)*

It is menu slot 0 — our menu is alphabetical and that tag is first. An arm that
re-orders the menu by sentence relevance moves it off slot 0, which makes a clean
natural experiment:

| | alphabetical menu | re-ordered menu |
|---|---|---|
| its median slot | **0** | 92 |
| times predicted | **57** | **3** |
| …taken while sitting at slot 0 | 57 | 3 |

**The model picks it if and only if it is first.** That is roughly **one
prediction in five** on this corpus going to line one of a list. On a real sentence:

> *"…trade accounts receivable are all due in **12 months** or less."*
> → `AccrualForEnvironmentalLossContingencies`

No reading of that sentence brings the tag close. It is the first line of the
menu. Position bias in option
lists is documented and we are rediscovering it; what is ours is the setting — 139
options in a production pipeline, not four in a benchmark.

It also cost us the arm. Re-ordering *killed* the attractor and still made the
system worse — coding accuracy **0.393 → 0.304, 0.421 → 0.263, 0.421 → 0.263**
across three draws of the extraction step — because it *amplified* the positional
prior — moving mass off the
model's own reading and onto the ranker's top slot. **A ranking can carry real
signal, visibly move the model, and still lose to what it displaced.**

The port paid for itself in defects. Three invisible for five phases surfaced
within hours: the judge's prompt was never ported, so a model grading SEC filings
was asked whether the span was *"really an adverse reaction"*; CADEC's exclusion
list was applied to every corpus; a mistyped model name burned **133 minutes**
before failing at the rung that needed it. A fourth was a label — the refusal in
section 2 was filed as a JSON parse failure, i.e. as *a model that cannot emit
JSON*, until we gave it its own name. **Diversity in what you test against finds a
class of bug that depth of testing does not.**

---

## 7. What the four paid resolvers bought

We built four resolvers on the residue and expected a staircase.

**Everything in this section is the development split** — 248 records, 40
documents. The held-out split was spent on one frozen run and cannot arbitrate an
ablation, so the ablation and the judge arm live here and stay labelled.

Each is followed by what it actually did to a real record, from the full-ladder
run behind every development-side CADEC figure in this article.

**Rung 1, the free checks.** Three verdicts, three records:

| verdict | record | |
|---|---|---|
| ACCEPT | `"spotting"` → \|Menstrual spotting\| | the vocabulary uses this very word |
| BAND | `"extreme rectal bleed"` → \|Rectal hemorrhage\| | plausible, no lexical evidence |
| REJECT | `"severe muscle pain in ankles"` | that text is **not in the post** — the model quoted something it invented |

**Rung 2, self-correction.** States the failure back as a fact, never as a
question. It fired **once in 248 records** — on that REJECT — and **declined**:
the fact it was handed was `span_ungrounded`, and a model cannot re-ground a
quote it made up. Sound mechanism, empty trigger set.

**Rung 3, voting.** Asks again and takes the majority: 2.6× the extraction token
budget, 152-second p95, **+5 on the tuning set and 0 out of sample.** The case
that matters:

> `"stamina"` — rung 1 **ACCEPT**ed `248276000` \|Stamina\| on an exact word
> match. Rung 3 voted it to `248277009` \|Lack of stamina\|, **which is the right
> answer** — and the record shipped still carrying rung 1's verdict, computed
> against the code rung 3 had replaced.

Voting improved the answer and invalidated the evidence for it in one step. The
voter and the answerer are the same model, so the vote carries no information the
original answer lacked; it just occasionally lands better.

**Rung 4, the judge.** A different family, enforced in code — a model judging its
own output measures self-consistency, not correctness. It separates 1.65× on
tuning, **1.23×** held out, against the free check's 2.36–6.12×.

**Rung 5, refusal.** Resolves nothing. It withdraws what the stack could not
corroborate and routes the record to a person — and it is the only one that moves
the number. It **withholds, it does not delete**: the proposed answer stays on
the record so a reviewer can see what the system was going to say.

**Rung 6, the person.** Three rows from the queue — what 196 of 248 records
actually look like:

> `"extreme rectal bleed"` → system proposed \|Rectal hemorrhage\| — *correct*
> `"extremely sick"` → system proposed \|Illness\|
> `"might not survive"` → system proposed \|Does not stand\| — *not close*

The first is a right answer the system could not corroborate and threw away. The
third is why it throws them away.

![Figure 8](figures/fig2-flat.png)

*Fig. 8: Accuracy on answered records is flat through four layers and falls at
voting. It rises only when the system stops answering. Source: author-created with
Matplotlib.*

| layer (development split) | answered accuracy | bought | tokens | p95 |
|---|---|---|---|---|
| bare model | 0.371 | — | 164,897 | *cached* |
| deterministic checks | 0.371 | +0.000 | **0** | **0** |
| self-correction | 0.371 | +0.000 | 548 | *cached* |
| voting | **0.367** | **−0.004** | **425,355** | **152.2 s** |
| second-model judge | 0.367 | +0.000 | 92,687 | 1.5 s |
| refusal | ships **0.808** | **+0.437**, at 21% coverage | 0 | 0 |
| person | — | — | **196 records** | — |

**Accuracy does not move until the refusal step, and then it moves by declining to
answer.**

### We deleted all three and re-ran

Per-layer deltas are an argument. The ablation is the measurement — same corpus,
extraction step held **identical** on both sides:

| stack (development split) | F1 exact | overlap | correct | shipped | to a person | tokens |
|---|---|---|---|---|---|---|
| full seven rungs | 0.182 | 0.187 | 43 | 52 | 196 | **683,488** |
| spine only | 0.182 | 0.182 | 42 | 52 | 196 | **164,898** |

Identical F1, coverage, error rate and records routed. **The entire contribution of
the three paid model layers is one overlap-matched answer out of 43, for 518,590
tokens and a 152-second p95.**

One trap nearly reversed this. Our spine config predated a set of extraction
improvements, so running it as it stood would have compared a stripped stack on a
*worse* extractor against a full stack on a better one. **An ablation that does not
hold its base fixed is two experiments wearing one name.**

### Then we gave the judge the one thing it lacked

The judge's verdict had no reader (§8). The obvious objection is that it would
have paid if connected. So we connected it, off by default, and measured three
draws.

| | judge off | judge on |
|---|---|---|
| coverage | 0.210 / 0.202 / 0.215 | 0.153 / 0.149 / 0.156 |
| precision on answered | 0.808 / 0.800 / 0.824 | 0.816 / 0.811 / 0.838 |
| **yield** (correct ÷ all) | 0.169 / 0.161 / 0.177 | **0.125 / 0.121 / 0.131** |
| to a person | 196 / 198 / 186 | 210 / 211 / 200 |

It withdraws 14, 13, 14 shipped answers to remove **3 errors each time** — about
**3.7 correct answers destroyed per error caught.** Three it destroyed, all
three of which gold agrees with:

> `"drowsiness"` → |Drowsy| &nbsp;·&nbsp; `"memory loss"` → |Amnesia|
> &nbsp;·&nbsp; `"pain"` → |Pain| Its withdrawals are 1.11–1.21×
more likely to be wrong than what it keeps; the free check, same records,
separates 3.03–3.15×.

Precision rose, which is the trap: **abstaining always raises precision.** Yield
cannot be fooled that way, and it fell 26%.

The exchange rate nobody prices is the real one: **0.437 accuracy for 196 of 248
records referred to a person.** Whether that is worth paying depends on what a
wrong answer costs you — a number only you have. Which is why we report three
currencies separately and refuse to fuse them. **A layer that is free in tokens
and ruinous in human attention looks like a bargain in any single-figure
summary.**

---

## 8. What no single-layer test could see

**Every deferral terminated in a field nothing read.** Self-correction wrote
`r2_declined`, voting wrote `r3_unanimous_none`, the judge wrote `r4_verdict`. The
refusal step reads none of the three. No test could catch it, because every layer
does exactly what its own documentation promises. The hole is *between* them.

![Figure 9](figures/fig1-wiring.png)

*Fig. 9: Three layers write a verdict; the refusal step reads none of them.
Source: author-created with Graphviz.*

**A fix three layers down silently disabled two layers up.** The checks used to
reject 5.1% of records for an unlocatable span, until extraction improved and a
filter dropped those at source. The rejection rate fell to **1 in 248** and
self-correction's trigger set went with it. Nothing broke; both layers still pass
every test. **A layer with nothing to do is indistinguishable from inside from a
layer doing nothing.**

And one about metrics. Voting overwrote codes without re-validating, so records
shipped marked *verified* against a code they no longer had. Fixing it moved exact
F1 from **0.204 to 0.204** — because precision and recall cannot distinguish an
*unwarranted* answer from an *incorrect* one, which is the entire distinction the
system exists to make.

---

## 9. Did we try making the model better first?

Yes — about twenty arms over five months. Six lessons transfer:

- **Do not ask the model for an identifier.** Recalling a code from weights scored
  F1 **0.018**; retrieving candidates and picking scored **0.209**, for fewer
  tokens. The recall version invented codes and put them beside correct labels.
- **Retrieval is a ceiling, not a floor.** A frontier hosted model produced **31
  exactly-correct answers against the local model's 31** — identical. A better
  reader cannot beat the menu; a worse one can fail to use it.
- **And a better menu did not beat the pick either.** Our retriever was a
  general-purpose 30M embedder where this task's literature uses domain-adapted
  ones, so we swapped in SapBERT — same corpus, same *k*, same answer key, one
  manifest key. Across all 6,595 gold mentions it *is* the better retriever:
  menu recall@20 **87.0% → 88.4%**, recall@1 **63.7% → 66.1%**, both separated
  over 1,144 documents. End to end on three paired draws it **lost**: F1 exact
  **0.413/0.434/0.423 → 0.405/0.394/0.391**, coding accuracy **0.754/0.778/0.758
  → 0.738/0.706/0.702**, at byte-identical detection and identical token cost.
  Two independent tests of the same claim, from opposite ends: a better *reader*
  scored the same, and a better *menu* scored worse.
- **Menu order is load-bearing.** Alphabetising cost 10–12 points at
  byte-identical detection.
- **Menu recall is not menu accuracy.** Retrieving 40 candidates put more gold on
  the menu than 20 and picked *worse*.
- **And the span decides the menu, so a detection error deletes the answer.**
  Retrieval is deterministic: quote `"stamina"` where the writer described the
  lack of it and the menu is `[0] stamina` plus nineteen stoma and foramina
  near-matches, with `248277009` |Lack of stamina| absent at any depth we
  retrieve. Quote `"no stamina"` and the same retriever puts it at line 0. The
  20-line menu holds the right concept 87.0% of the time, and which 13% it
  misses is partly chosen upstream.
- **Ship only the filters with zero false-rejection cost**, priced against the
  answer key first. One that cut 14 false positives at the cost of 7 real ones was
  rejected.
- **Prompt interventions did nothing** — three for three.

The residual is span boundaries, and those belong to the answer key.

**One caveat we owe the reader, because it cuts against us.** "Retrieval is a
ceiling" is a claim about the division of labour, not about the height of the
ceiling — and the height is partly ours. SapBERT reaches 88.4% where our
shipped encoder reaches 87.0%, and an oracle picking the better of the two per
mention reaches **93.6%**. So 87% is this encoder's ceiling, not the task's.
What the arm shows is that raising it is not the same as improving the result.

---

## 10. The division of labour

The part another team can use tomorrow:

| job | whose | evidence |
|---|---|---|
| **Read the prose, propose candidate spans** | **the model** | the one thing it does well — detection 0.69–0.79 |
| Recall an identifier | **not the model** | F1 0.018 vs 0.209, at more tokens |
| Decide the candidate list | **not the model** | a frontier model scored identically on the same menu; a better encoder scored worse |
| Order the candidate list | **not the model** | takes line one 19.5% of the time, iff it is line one |
| Check its own output | **not the model** | self-correction 1 in 248; voting moved accuracy down |
| Judge whether an answer is right | **not the model** | 1.1–1.2× against a string comparison's 3.0–6.1× |
| Decide when to abstain | **not the model** | its confidence was a constant — the threshold was a dead dial |
| Validate existence, format, grounding | **not the model** | deterministic checks are exact on those classes |

> **The model reads. Everything else belongs to something that does not
> resample.**

---

## How we found these

No layer announced that it had stopped working. Each ran, returned, wrote its
field, passed its tests.

![Figure 10](figures/fig3-loop.png)

*Fig. 10: The measurement loop. Every dead layer here was found on it. Source:
author-created with Graphviz.*

The third step does the work. **A layer that has just produced a good number is
the least likely thing in a system to be re-examined**, and that is where all our
false results lived — a reranker with an interval excluding zero, a judge with 2:1
separation, a voting layer with five net fixes. All three evaporated under a
second draw, a corrected prompt, or a held-out split.

---

## Where this sits in the literature

**We mostly agree, and the agreements matter.** Our abstention layer is *selective
prediction*, a formalised field; we compute risk-coverage curves without having
used its vocabulary. Our weak judge is corroborated, not idiosyncratic — published
work documents self-inconsistency in LLM judges and an agreeableness bias with
true-positive rates above 96% against true-negative rates below 25%. Our voting
result is the same story from the other side. And the slot-0 attractor is a
rediscovery: position bias in option lists is documented, and *option-order
randomisation* — the mitigation we arrived at independently — is already the
recommended one.

**Where we differ is what we compared.** That literature treats the judge and
self-consistency voting as standard tooling. We priced both against a free string
comparison, on the same records, in the same run, and the string comparison won by
3×. We have not found that comparison published. It is the narrow claim this
article defends.

**Where we are behind, stated in the right units.** The strongest published system
on this corpus is CONORM (Yazdani et al., medRxiv `10.1101/2023.09.26.23296150`),
which fine-tunes on 875 of CADEC's 1,250 files. Its
evaluation code scores a `(type, span, concept)` tuple under the same two
strategies we use — identical offsets, or overlapping ones — so the metrics line
up even though the vocabularies do not. Matched on both axes:

| | span-exact | overlap / lenient |
|---|---|---|
| CONORM, end-to-end, supervised | ≤ **0.704** | **0.7245** |
| CONORM, **detection only**, supervised | **0.704** | 0.891 |
| ours, end-to-end, zero-shot, held-out | **0.204** [0.150–0.260] | 0.215 |

We are a long way behind on both, and one number would have hidden by how much. The
`≤` is arithmetic, not modesty: end-to-end demands the span *and* the code, so it
cannot exceed detection alone under the same matching, and their published 0.7245
therefore has to be the lenient figure. Their paper reports one end-to-end number
per corpus without labelling its strategy.

**And the ceiling claim survives the check that was meant to break it.** We claimed
CADEC's ~67% boundary determinism caps span-exact scores near 0.70. A fully
supervised tagger, trained on that corpus, scores **0.704 span-exact on detection
alone** — before it assigns a single code. That is the predicted number, reached by
the system with every advantage, doing the easier half of the task.

Three things travel with the comparison. They normalise to **MedDRA preferred
terms**, not the 129,675-concept SNOMED graph we code against. They are supervised,
and their own analysis prices what that buys: stratified by whether the gold
concept was seen in training, precision falls from **85.8% to 47.1%** on concepts
it was not — and a zero-shot system is out-of-distribution on every record by
construction. And their tagger uses a contiguous BIO scheme, so the discontinuous
mentions our extractor cannot express appear to be beyond theirs too.

---

## What we would tell you

We set out believing that stacking reliability layers buys reliability. Measured
end to end, **the layers made errors visible rather than fewer** — worth a great
deal, and not what they were bought for.

- **Condition your confidence on something that does not resample** — a
  vocabulary, a schema, a type check, a compiler.
- **Establish its precondition first.** One query, before you build.
- **Test the free layer against your answer key.** Every rejection there is false
  by construction, so you get its false-positive rate for nothing. Ours went from
  9.3% to 0.13%.
- **Grep for the readers of every field you write** — and when you find an orphan,
  measure it before you adopt it. Ours cost yield when we connected it. This one
  is worth automating: forty lines of regex over our own source names all three
  of the dead layers we had found by hand, and needs no data and no model.
- **Re-measure the top when you change the bottom**, and **print coverage beside
  every error rate.**

The system ships about a quarter of its answers, at four errors per hundred
instead of sixty, and hands the rest to a person. Not what we set out to build. But
the machinery that makes the other four-fifths *legible* to that person turned out
to be worth more than any layer that tried to answer them.

## What we could not settle

- **The reproducibility mechanism rests on one sparse model against four dense
  ones.** Suggestive, not a result. It wants more MoE models, and should fail on a
  dense model of similar size.
- **The precondition was found by accident**, after hours of running, when one
  query would have said it — so we wrote the query down as a tool and checked it
  against our own wreckage. Run against the code as it stood *before* the audit,
  its free wiring check names the three orphaned verdict fields we had found by
  hand and nothing else, leaving 55 diagnostic fields alone. Its ACCEPT-lane
  check refuses the corpus where the ladder shipped 0%, on a property of the
  answer key, before a model runs. **What we have not done is use it in
  anger**: every case above is one we already knew the answer to, and a
  precondition tool validated only backwards is a hypothesis about the next
  project, not a result from this one.
- **We never ran a supervised baseline.** Our distance from a trained system is
  read off someone else's paper rather than measured on our own splits — verified
  line by line against their evaluation code, but still a comparison across two
  vocabularies and two test sets.
- **~~Our retriever is a general-purpose 30M embedding model.~~ CLOSED
  2026-09-01, and the answer has two halves.** SapBERT — domain-adapted, the
  field standard for biomedical entity linking — was run as an off-by-default
  arm on the same dev split, three paired draws. It **is** the better retriever
  corpus-wide (menu recall@20 87.0% → 88.4%, separated over 1,144 documents) and
  it made the system **worse** (F1 exact −0.027 pooled, coding accuracy −0.048,
  sign-consistent three for three at byte-identical detection). So the ceiling
  we attribute to the task *is* partly ours — an oracle over the two encoders
  reaches 93.6% — and moving it did not move the result. **What the arm also
  exposed is a flaw in our own method:** the probe that authorised it measured
  recall over 1,144 documents while the arm ran on 38, and on those 38 the sign
  is negative. A go/no-go probe has to be run on the denominator the arm will be
  scored on.
- **~~We tested a domain-adapted model in one role only.~~ CLOSED 2026-08-31.**
  BioMistral-7B has now been run as the *extractor* on the same dev split and
  frozen config, three draws: 3 predictions against 226 gold, F1 exact 0.0087,
  36 of 40 documents returning `" {"` and end-of-sequence — the identical
  signature to its judge failure, in the role whose prompts are 2-3x longer.
  Raising the temperature to 1.0 escapes the greedy EOS and still lands at F1
  0.017-0.050, a factor of four below the un-adapted `mistral:7b-instruct` on
  the same split. The claim holds in two roles.
- **We assume one code is right, and we have not checked that.** The scorer
  credits only the code in the answer key. But `"knee pain"` coded
  |Pain of knee region| is filed as wrong against a gold |Gonalgia| that is
  retired, has no recorded successor, and carries "Knee pain" as one of its own
  names. Some share of what we report as mis-coding is a defensible synonym, and
  we do not know what share. **The check is straightforward — take every
  incorrect answer, ask whether its code and gold's are the same concept under
  SNOMED's own relationships, and report the residue** — and we have not run it.
  It would move our coding numbers upward, which is why it needs doing carefully
  rather than not at all. Related and unmeasured: gold sometimes carries two
  codes for one mention, so "one right answer" is not always the corpus's own
  assumption either.
- **The second corpus is a demonstration, not a matched comparison.** A third
  corpus with a lexical vocabulary would test whether the ~85% ACCEPT lane belongs
  to controlled vocabularies in general or to SNOMED in particular.

---

## Limitations

The held-out split was spent once, so its intervals are the claim; everything
after — the ablation, the judge arm, the second corpus — is development-side and
labelled. The judge is a 3.2B model grading a 20B one. Human cost is a **count** of
records routed, never minutes. **17.3% of CADEC's gold mentions are discontinuous
spans our extractor cannot express** — gold marks `"loss of"` and `"strength"` as
one mention, and we emit a single segment — so every recall number here carries a
cap we built rather than one the task imposes, and we report it attached rather
than subtracted out. The near-miss corruption is synthetic. CADEC is
public and from 2015, almost certainly in pretraining, which makes every gain here
conservative. Both corpora are public and both arms are reproducible, but not on the
same terms: FiNER-139 is CC-BY-SA-4.0 and comes down with the code, while CADEC
is non-transferable, so a reader has to accept CSIRO's licence and fetch it
themselves. We ship document IDs for the splits, never text.

Code, ledger, decision records, and the source for every figure:
**https://github.com/wbagais/reliability-ladder**

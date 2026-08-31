# Every Reliability Layer We Added Reported Success

## What four wrappers around an LLM measured, and what they missed

---

**Scope, up front.** 40 documents from the CADEC v2 adverse-event corpus, one
~3B parameter model (`granite4:micro-h`) running locally on a single GPU,
SNOMED CT-AU release `AU1000036_20260731`, judged by `llama3.2:3b`. Everything
below was measured on that setup. The instrumentation findings generalise. The
specific accuracy numbers do not, and I will say so again where it matters.

---

## The task, and why it makes a good probe

Pharmacovigilance triage: read a patient's forum post about a medication, pull
out the adverse reactions they describe, and normalise each one to a SNOMED CT
code.

Most work on LLM reliability is done on tasks where the only available grader is
another language model. Summarisation, question answering, code explanation —
you can measure fluency and you can ask a bigger model whether it liked the
answer, but there is no fact of the matter sitting outside the system.

This task has one. Whether `41456009` exists in the release, whether it is
active, and whether it descends from Clinical Finding are three lookups against
a 365 MB SQLite index built from the official distribution. They take
microseconds and they do not have opinions. The corpus ships 9,111 human
annotations, so there is also a ground truth for what the right answer was.

That combination — a decidable floor plus a real answer key — is what makes the
task useful for measuring reliability layers rather than model quality. It means
that when a layer reports an improvement, you can check.

## The ladder

The design is a stack of interventions, each one added on top of the last, each
one measured for what it buys and what it costs.

```mermaid
flowchart TD
    R0["**0 · Extract**<br/>bare model, one call"] --> R1
    R1["**1 · Validate**<br/>deterministic lookup<br/>zero model calls"] --> R2
    R2["**2 · Self-correct**<br/>tell the model its code<br/>failed, ask for another"] --> R3
    R3["**3 · Vote**<br/>k samples, majority<br/>on the normalised code"] --> R4
    R4["**4 · Judge**<br/>second model scores<br/>span and code"] --> R5
    R5["**5 · Abstain**<br/>withdraw what cannot<br/>be verified"] --> R6
    R6["**6 · Triage**<br/>route to a human"]

    style R1 fill:#2d4f2d,color:#fff
    style R5 fill:#2d4f2d,color:#fff
    style R6 stroke-dasharray: 5 5
```

Two design choices matter for what follows.

**Rung order is configuration, not a constant.** Cheap fixes before expensive
sampling, judging after both so the judge grades the best available answer,
abstention last because withdrawing early throws away records the layers above
might have recovered. The order lives in a manifest rather than in code, so it
can be varied and measured rather than asserted.

For most of the project those two things were separate: IDs came from the
original brief and execution order was `[0, 1, 3, 5, 4, 2, 6]`, so abstention
was numbered second and ran last. Holding both mappings at once turned out to
cost more than it bought, and midway through we renumbered so that ID equals
position — self-correction 3→2, voting 5→3, abstention 2→5, the rest unchanged.

That is a small thing, but it is worth saying how it was handled, because the
rest of this article is about exactly this kind of hazard. Every measurement
recorded before the change uses the old IDs. Rather than rewrite the history,
the mapping table went into the manifest and the decisions log beside the
entries that need it, so *"rung 2 abstained on all three"* in an earlier entry
is still readable and still means what it meant. The measurements did not
change; only the labels moved, and the translation is written down where someone
reading the old numbers will find it.

A renumbering with no mapping table is indistinguishable from a silent
denominator shift, and this article has several of those in it.

**Cost is three numbers, never one.** Tokens per record, p95 latency, and
records routed to a person. Fusing them into a single figure hides which
resource a layer actually spends, and the three do not move together — as the
voting results below demonstrate.

The two layers shaded green are deterministic. They make no model calls. Hold
that thought.

## Result one: the model finds half the reactions and codes none of them

Baseline, no wrappers:

| | |
|---|---|
| Mentions emitted | 169 |
| Span precision | 0.683 |
| Span recall | 0.451 |
| Span F1 | **0.543** |
| Correct codes | **0 / 105** |

The span numbers are unremarkable for a small model on noisy patient text. It
finds roughly half the reactions, and about a third of what it finds is not
there.

The code column is the interesting one. Of 105 gradable predictions, zero
matched the gold code. Not a low rate — zero. The model produces SCTID-shaped
strings with confident term labels attached, and none of them are the right
code. Most are not codes at all: 155 of 169 fail an existence check against the
release.

That is the number every subsequent layer is measured against. Each of the four
layers below reported an improvement. The correct-code count stayed at zero
throughout.

## Result two: a tool-access experiment that never tested tool access

The first wrapper was a prompt variant that describes a vocabulary lookup tool
and instructs the model to use it. Call it Mode B.

Mode B halved the validation layer's rejection rate. That looks like a win until
you ask where the halving came from: 59 records where the model returned no code
at all. Rejections fell because the model answered less often, and correct codes
stayed at zero.

Then the arm's own instrumentation gave it away. A flag called `honoured_tool`
is never `True` across the entire split — and `vocab.search` runs *after*
generation, not during it. The model never had the tool. The A/B contrast
measured **prompt wording**, not tool access.

The lesson is not about tools. It is that the label on an experimental arm is a
claim, and it needs the same verification as a result. We came within one commit
of publishing "tool access does not help" from an experiment where no tool was
ever available.

## Result three: self-correction that never corrects

The next layer takes each validation failure and tells the model the fact:
*code 41456009 does not exist in this release*. Then it asks for a replacement,
and — a deliberate departure from the original spec — re-validates whatever
comes back through the same validation function.

| outcome | count |
|---|---|
| offered | 158 |
| **rescued** | **0** |
| still failing | 0 |
| reasserted | 0 |
| declined | **158** |

Told that a code does not exist, the model neither defends it nor proposes
another. It returns null, 158 times out of 158, at a cost of 72,539 tokens.

The spec deviation is the part worth dwelling on. The original design said this
layer should not re-validate — update the record and let the ladder continue.
Under that design, `rescued` would have been an *assertion*: a record marked as
repaired because a repair was attempted, not because it worked. A
spec-conformant implementation would have reported **158 corrections, none of
them checked, all of them empty.** A 100% correction rate for a layer that
corrected nothing.

That is not a hypothetical. It is what the spec said to build, and it was caught
because someone asked what `rescued` would mean if nothing verified it.

## Result four: unanimous agreement, computed over 2% of the input

Voting: sample the extractor k=3 times at temperature 0.7, take the majority on
the normalised code.

| outcome | count | share |
|---|---|---|
| unanimous | 3 | 2% |
| split | 0 | 0% |
| tie | 0 | 0% |
| **not re-found by any sample** | **166** | **98%** |

Cost: 55,704 tokens, 505 seconds.

Ninety-eight percent of the mentions from the greedy pass were not found again
by any of three samples. The voting mechanism had three records to vote on. It
was unanimous on all three, and all three codes were fabricated.

An agreement metric requires a set that persists across samples. Here it does
not. At temperature 0.7 the extractor's span boundaries move enough that
matching between samples fails almost entirely — the consensus figure describes
2% of the input, and the other 98% is not disagreement either.

The implementation happens to have a `not_resampled` outcome, distinct from both
agreement and disagreement. Without that third category — and the first draft
did not have it — those 166 records would have been folded into one bucket or
the other, and voting would have reported near-perfect consensus.

There is a sharper version of this failure. My collaborator found that our
shared model caller was not varying the sample index, which is part of the disk
cache key. All k votes were hitting the same cache entry. Her words from the
decisions log: *unanimity that was never measured, in 0.00s, for free.*

## Result five: two judges, opposite failure modes, neither reading its input

The judge is a second model, from a different family — a model judging its own
output measures self-consistency and reports it as verification, so the
implementation raises if the two model strings match. It answers two questions,
counted separately:

- `span_ok` — is the quoted text really a reported reaction?
- `code_ok` — is this code right for it?

The first report pooled the two into one verdict and concluded the judge always
agreed with the deterministic checker — two checkers paid for twice, a null
result. Splitting the channels showed something else entirely, and splitting
them is what made the rest of this section possible.

### The control

Judging model output alone cannot separate a harsh judge from an accurate one:
those records had already been rejected, so a low pass rate might be correct.
The fix is to mix in ground truth. 226 gold reaction mentions — spans written by
human annotators, codes correct by construction — go in with the 169 model
records, all 395 judged in one pass. The validator splits the set three ways, so
both questions have known answers on each side.

Two judges were run through the identical set: `llama3.2:3b`, and `qwen2.5:7b`
at roughly twice the size and from a different family again.

| | | `llama3.2:3b` | `qwen2.5:7b` |
|---|---|---|---|
| `span_ok` | gold (correct by construction) | 3% | **83%** |
| | model output | 3% | **83%** |
| `code_ok` | gold (correct codes) | 92% | **21%** |
| | model output (0/105 correct) | 86% | **21%** |
| parse failures | | 204 / 395 | **1 / 395** |

Read the rows, not the columns. Within each judge, **gold and model output score
identically** — to the percentage point on three of the four channel pairs. The
small judge fails almost every span and passes almost every code. The large
judge does the reverse. Neither distinguishes a correct answer from a fabricated
one.

The larger model's code channel is the sharper result. Those gold codes are
right — human-annotated, valid, active, correct for the mention. It rejects 79%
of them, at precisely the rate it rejects codes that do not exist in any
release. That is not strictness. A strict judge would reject fabricated codes
*more often* than correct ones.

The breakdown by validation verdict says the same thing a third way: records the
deterministic checker accepted score `code_ok` 29%; records it rejected score
21%. Eight points apart, on a distinction that is a database lookup.

### What did improve with model size

One thing, and it is worth separating out because it is a genuine difference:
**parse failures fell from 204 of 395 to 1.**

The small judge failed to produce usable output on 52% of records — and not at
random, 58% on gold against 43% on model output, so the records it could answer
about were a biased subsample of the records it was given. That is an
availability problem, and it belongs in the cost column rather than the accuracy
discussion. It was a property of that model, not of LLM judging, and a larger
model fixed it completely.

It fixed availability and changed nothing about discrimination. The judge now
answers reliably, and its answers still do not depend on whether the thing being
judged is correct.

### The number that moved 51 points while nothing changed

Because the pooled verdict is near-constant, agreement with the deterministic
checker is mostly a function of that checker's rejection rate on whatever set
you hand it:

| judge | set | validator's REJECT share | reported agreement |
|---|---|---|---|
| llama3.2:3b | 5 documents | 9 / 9 | **100%** |
| llama3.2:3b | 40 documents | 94 / 96 | **98%** |
| llama3.2:3b | mixed control | 94 / 191 | **49%** |
| qwen2.5:7b | mixed control | 165 / 394 | **44%** |

Four configurations, four agreement figures spanning 56 points, and no
relationship between any of them and whether the judge was doing useful work.
The 100% and the 44% are the same finding.

If you take one thing from this article, take that table. A reliability metric
swung across most of its range while the thing it measures did not change, and
nothing in the metric's presentation would have told you.

### Cost

`llama3.2:3b`: 207,529 tokens, 611 seconds for the control.
`qwen2.5:7b`: 209,354 tokens, 5,545 seconds — the larger model did not fit
entirely in 4 GB of VRAM and ran partially on CPU, which is a compute-backend
difference and is recorded as one.

Similar token counts, an order of magnitude apart in wall clock, for two
constants each.

It was not uniformly useless. On one record the small judge returned `span_ok:
false` with the explanation *a fear, not an adverse reaction* — a genuine catch
no deterministic check could make, and exactly the work a judge is for. Another
time it asserted that *SNOMED CT 41456009 represents rectal hemorrhage* at 0.95
confidence, for a code the existence check had already rejected, confabulating a
label for a hallucinated identifier. Both are anecdotes. 83% versus 83% is a
measurement.

## The layer that worked, and what it cost

Abstention is deterministic. It reads the validation verdict and maps it: accept
becomes verified and keeps its code; band or reject becomes abstain and the code
is withdrawn — moved to a `withheld` field rather than deleted, so a human
reviewer can still see what the system was going to say.

On model output: **169 of 169 withdrawn, zero codes published.** Since the
extractor produced zero correct codes, the correct abstention rate was 100%, and
this layer reached it exactly.

On the gold control: 76 kept, 150 withdrawn, no crossover in either direction.

So the one layer that behaved correctly is the one that makes no claim, calls no
model, produces no accuracy metric, and costs milliseconds. The four layers that
generated impressive-looking numbers recovered nothing between them.

Two caveats keep that from being a victory lap.

**Its correctness is entirely inherited.** Abstention is a transfer function
over the validator's verdict. It withdrew 169 of 169 because the validator
rejected 166 and banded 3 — not because it assessed anything. All of the
discrimination lives in the lookup one layer below.

**It withheld 150 of 226 correct gold codes — 66%.** Those are valid, active,
correct annotator codes, banded for lacking a lexical match and therefore
withdrawn. On this data the trade is free, because there were no correct model
answers to lose. On a model that gets codes right, this layer would suppress two
thirds of them. Nobody has measured that.

```mermaid
flowchart LR
    IN["169 records<br/>from extraction"] --> VAL{"Validate<br/>(lookup)"}
    VAL -->|"ACCEPT 0"| VER["VERIFIED<br/>code published"]
    VAL -->|"BAND 3"| ABS["ABSTAIN<br/>code withheld,<br/>not deleted"]
    VAL -->|"REJECT 166"| ABS
    ABS --> TRI["Triage desk<br/>169 records"]
    VER --> OUT["Published: 0"]

    style VAL fill:#2d4f2d,color:#fff
    style TRI stroke-dasharray: 5 5
```

## Where the ladder terminates

The top of the ladder is a triage desk: route what could not be verified to a
human. It was never built as a product, and building one would have been the
wrong response — it would receive 169 withheld records, every one carrying a
wrong answer or none, and a reviewer opening that queue is re-annotating rather
than triaging.

But the rung still has something to contribute, and it is the thing the cost
model was missing. Two of the three cost measures — tokens and latency — had
real numbers. The third, *records routed to a person*, was zero everywhere, not
because review is free but because nobody had timed it. The ladder's full cost
could not be stated.

So rung 6 was built as a timing study rather than a desk. Six records, drawn
blind from a mixture of gold and model output, presented identically, with the
terminology searchable. Decisions and seconds recorded; accuracy deliberately
not scored, because the moment it is an accuracy test it measures the reviewer.
Stratified by whether the vocabulary returned candidates, and reported that way,
because picking from a list and searching a 129,675-concept terminology are
different jobs:

| | n | median | range |
|---|---|---|---|
| with candidates | 3 | 12.5s | 7–19s |
| without | 3 | 27.1s | 21–46s |

Extrapolated — and it is an extrapolation from three records, by a reviewer who
is not a trained safety officer — the 155 records with no valid code represent
roughly **1.2 reviewer-hours**, against 234,727 tokens that produced zero
correct codes.

That is the whole ladder's cost, stated for the first time: a quarter of a
million tokens, an hour of machine time, and an hour or so of human attention.
The human hour is the only part of it that would have produced correct codes.

The ladder terminates before the top not because the top is unfinished, but
because the bottom produces no signal to pass upward. A seven-rung ladder with
seven green checkmarks would have been a less honest artefact than one that
stops — and one that stops while still costing the reviewer an hour is more
useful than either.

## The instrumentation was wrong the whole time

Everything above is about layers. This section is about the measuring apparatus,
and it is the part that transfers to work that has nothing to do with SNOMED.

### Check order determines the reported diagnosis

The validation function returns on first failure. That is correct behaviour for
a gate — you do not need to know every reason something is invalid in order to
reject it.

It is wrong for a report. On the 40-document run, the verdict table said
`span_ungrounded 172, code_unknown 3`. The true failure set was `code_unknown
164`. **172 of 176 failures were hidden by ordering alone.**

The cleanest demonstration is a single-flag ablation. Identical model output,
identical checks, one configuration flag changed:

| | flag off | flag on |
|---|---|---|
| `span_ungrounded` | 162 | **0** |
| `code_unknown` | 4 | **155** |
| total failures | 163 | 163 |

The full failure set is invariant. What moved was which failure got reported.

The fix separates the two jobs: the gate still returns on first failure, and a
separate function runs every check into an audit trail. Both derive from the
same code — there is no second implementation to drift.

```mermaid
flowchart TD
    REC["Record"] --> G["**Gate**<br/>zone(): returns on<br/>first failure"]
    REC --> A["**Diagnosis**<br/>all_reasons(): every<br/>check runs"]
    G --> V["verdict<br/>ACCEPT / BAND / REJECT"]
    A --> AUD["audit trail<br/>every reason +<br/>every unevaluable"]
    V --> LEDGER["Ledger row"]
    AUD --> LEDGER

    style G fill:#2d4f2d,color:#fff
    style A fill:#2d4f2d,color:#fff
```

### The bias was invisible in the regime the validator was developed in

Here is why nobody caught it for weeks.

Run both the first-failure set and the full-failure set over all 9,111 gold
mentions and **they are identical**. Gold spans ground by construction — they
were written by annotators against the text — so the check that masks the others
never fires.

The validator was developed against gold, where its ordering bias cannot appear,
and deployed against model output, where the bias dominates. That is the most
portable lesson here: **develop validators in the regime you will deploy them
in, not the regime where they look correct.**

### A check that cannot run gets reported as one that ran

This pattern appeared eight separate times in one project. Every instance has
the same shape: the absence of a result rendered as a result.

1. A `--live` comparison mode that was comparing a run against itself.
2. A vocabulary backend flag that was inert — set, read, and connected to
   nothing.
3. A missing vocabulary object returning a neutral verdict instead of raising.
   It now raises unless explicitly allowed.
4. An analysis script counting exceptions as disagreements.
5. The judge's agreement metric computed over a constant set.
6. The judge's guard against (5) — it suppressed the figure when the validator
   returned a single verdict, which is correct. At 40 documents, **two** records
   of a different verdict made the set technically non-constant, the guard
   stopped firing, and a meaningless 98% printed. A binary constancy check needs
   to be a minority-class threshold.
7. Three separate layers where the ledger call sat *below* an early return, so
   the records that could not be evaluated were exactly the records that left no
   trace. Self-correction's parse failures, voting's not-re-found records — 98%
   of that layer's input — and the judge's unparseable responses.
8. The per-record cost accounting for all three model-facing layers called a
   ledger method that **did not exist**, with a required argument missing,
   guarded by a condition that was never true. Four independent reasons it could
   not work.

Number 6 is the one I would put in front of a reader. It is the same failure,
occurring inside the fix written for the previous instance of that failure. This
is not a bug list. It is a structural tendency: when a check cannot produce an
answer, the path of least resistance in code is to return early, and an early
return looks identical to a clean pass.

And number 8 came with a coda. The test suite passed 93 tests before the fix,
after the fix, and after every subsequent revision — because no test constructs
a layer with a ledger attached. Green across eight call sites that could never
have executed.

### A pooled ratio can describe neither population in the pool

The corpus has two entity types: drugs and reactions. Almost every headline
figure changes when you split them.

| pooled | drugs | reactions |
|---|---|---|
| 11% of codes inactive | 46.8% | **6.2%** |
| 23.9% backend disagreement | 100% | **5.9%** |
| 43.1% accepted on gold | 76.0% | **35.0%** |

Drug names appear in patient text as printed on the box. Reactions appear in the
reporter's own words — *"no control over urination"*, *"constipitation"*. They
are different problems and the pooled number describes neither.

The headline changes with them: 43% pooled is 35% on reactions, and reactions
are what the task is actually about.

This one produced an unexpected confirmation. Months later and in a completely
different code path, the abstention layer's gold control accepted 76 of 226
reaction mentions — 33.6%, against the 35.0% above. The split predicted a number
in an experiment built for another purpose, which is much stronger evidence than
the original observation.

### Determinism is bounded by the hardware

Same model, same seed, greedy decoding: **176 mentions on CPU, 169 on GPU.**
Three GPU runs byte-identical to each other.

Reproducible within a backend, not across one. Record the compute backend the
way you record the vocabulary release — and note that the inference server
reported "100% GPU" from its own placement estimate while running on CPU at 4.4
tokens per second. Another check reporting a result it could not have had.

### Wall clock is not reproducible across run lengths

Running the layers individually versus end-to-end produced **identical token
counts** and wall clocks 2–4× longer in the pipeline: self-correction 230s →
977s, voting 505s → 2,050s, judging 265s → 504s.

Thermal throttling was the obvious hypothesis, and it does not survive
measurement. Instrumenting per-record latency and comparing each rung's first
quarter of records against its last — same rung, same run, same work — gives:

| rung | first quarter | last quarter | |
|---|---|---|---|
| extract | 4.06s | 6.83s | +68% |
| self-correct | 1.86s | 2.19s | +18% |
| vote | 29.04s | 21.38s | **−26%** |
| judge | 2.20s | 15.35s | **+597%** |

Voting got *faster*, which thermal throttling does not explain. And the judge
did not creep — it cliffed. Reading its per-record latencies in order:

```
   0s     8.85s   parse_failed
  98s     1.36s   judged
 308s     3.46s   parse_failed
 457s   134.63s   parse_failed      <-- model load
 477s    19.39s   parse_failed
 620s    20.39s   judged
 932s    19.26s   parse_failed
```

One record took 134 seconds. Everything before it runs in 1–5s; everything
after runs in 11–33s and never returns. That is a model being loaded, and the
reason is mundane: the judge is a 4.7 GB model on a card with 4 GB of VRAM. It
does not fit. The inference server evicted what was resident, loaded the judge
partially, and every subsequent call ran with layers on the CPU — a sustained
6× penalty for the rest of the rung.

So the +597% is not degradation. It is **one discontinuity and two regimes**,
and a first-quarter-against-last-quarter comparison spanning that boundary
produces a figure describing neither — the same failure as the pooled ratios
three sections ago, this time in the monitor I had built that afternoon to
watch for exactly this kind of thing.

The correct statements are narrower and more useful. Judging slowed 6× because
a model did not fit in memory, which is a fact about the hardware and the model
sizes rather than about judging. Extraction's +68% is unexplained and may be
thermal. Voting's −26% is unexplained. And p95 latency — one of the three cost
measures — is not a stable property of a rung at all: it is a property of a
rung *in a particular position, on a particular machine, with a particular set
of models resident*. Nothing in the run stamp records any of that.

The drift columns above came from a monitor built to watch runs progress. It
found this on its first render, which is its own small lesson about what
instrumentation is for.

### The tooling does not model any of this

Partway through, we went looking for an observability platform — the reasonable
instinct once you have found this many measurement bugs. We evaluated the main
open-source LLM tracing tools, instrumented a ledger exporter against
OpenTelemetry, and got spans rendering in a local trace viewer within an hour.

Then we looked at what the views could show. Every platform in this category
models the same unit: the call. Prompt, response, tokens, latency, p50/p95, and
usually an LLM-judged quality score. All of that we already had.

Not one of them models a denominator. There is no field for *judged 96 of 169
offered*, no way to say that a rate belongs to one subset and not another, and
no representation of a comparison set's composition. The agreement table above —
the strongest finding here — is invisible in every tool we looked at, because
the thing that moved was not a property of any call.

Several also ship LLM-as-judge scoring as their default quality signal. Adopting
one and using it would have put this pipeline's quality gate on the mechanism
that, three sections ago, returned two constants.

The exporter still went in, with two custom span attributes: which named set a
row's rate is computed over, and whether the check produced a pass, a fail, or
could not run at all. Both had to be invented. That is the finding — not that
the tools are bad, but that the industry's instrumentation vocabulary describes
what happened to a request and has almost nothing to say about what a number is
computed over.

## What deterministic checking can and cannot do

The lookups caught everything above. They are also not a scorer, and the
distinction matters.

Three records survived validation on the 40-document run — code exists, code
active, code is a clinical finding, no lexical match. All three are wrong
against gold:

```
LIPITOR.401#3   60551006   'loss of balance'
LIPITOR.935#1   39249009   'constipitation'
LIPITOR.935#2   39249009   'no control over urination'
```

One code assigned to two opposite conditions in a single document. The validator
checks codes in isolation and structurally cannot notice.

A deterministic checker is a floor, not a grader. It tells you what is
impossible, never what is right.

## The vocabulary is a ceiling nobody measured

The rung 6 desk needed to offer a reviewer candidate codes, and for most
records it offered none. That turned out to be a property of the whole system.

The local terminology index does exact-term retrieval: a query is normalised —
lowercased, semantic tag stripped, punctuation squashed — and matched for
equality against SNOMED's description table. Not substring, not fuzzy. The
choice is documented and deliberate: a fuzzy local index has no relevance
ranking, and would quietly stop being comparable with the networked backend it
is meant to be measured against.

The consequence had not been measured. **Of 343 gold reaction spans — the
annotators' own phrases, the ones a human judged codable — 141 return a
candidate and 202 return nothing.** Fifty-nine percent. `low back pain`
resolves; `lower back pain` does not, because no description normalises to
exactly that string.

This is not a defect. It is the measured cost of a design decision, and it puts
a ceiling on every layer that depends on term lookup. The tool-shaped prompt's
post-hoc search returns empty for most mentions, so its tool-fidelity flag is
*undefined* rather than *false* far more often than its own documentation
implies. The triage desk's "no candidates" stratum does not mean "hard to code";
it means "not in the description table".

Worth stating plainly because I got it wrong first: I initially diagnosed this
as substring matching, wrote it up, and pushed it. The evidence against was
already in front of me — a query for `back` returned two results, and substring
matching would have returned hundreds. The correction is in the decisions log
next to the original, which is the only reason anyone reading it later will know
which claim to trust.

## The answer key is not clean either

One gold annotation file has a date — `20070731` — where an SCTID belongs,
inside a multi-code annotation. It has the right shape and the right length. It
survived the corpus's v1 → v2 revision.

It is handled as a documented defect list, never a silent filter. A silent
filter is the same failure as everything in the previous section: a record that
could not be graded, removed without a trace, changing a denominator that nobody
re-derives.

## What this shows, and what it does not

**It shows** that on this task, each of four reliability layers produced a
metric indicating improvement while correct codes stayed at zero, and that in
every case the metric was generated by the layer being evaluated.

**It does not show** that wrappers never help. Forty documents, one small model,
one corpus, one terminology. A larger model may well have the knowledge this one
lacks. The finding is that the wrappers could not tell us either way, and
reported that they could.

**The transferable claim** is narrower and, I think, more useful: a reliability
layer is also a measurement instrument, and it is an instrument built by the
same reasoning that built the layer. It will tend to report the layer working.
The only checks that caught anything here were the ones with no stake in the
outcome — a lookup against a file, and a function that withdraws answers.

## A checklist

- Run every check, always. Gate on the first failure; diagnose on all of them.
- Develop validators in the regime you will deploy them in, not the one where
  they were tuned.
- Make *could not run* a third outcome that raises or records, never a pass and
  never a fail. Then check that the code path recording it is actually
  reachable.
- Split pooled ratios by the populations you pooled, before publishing either.
- Never report an agreement figure without the composition of the set it was
  computed on.
- Test a judge against known-correct input before trusting it on unknown input.
  If it scores both the same, it is not reading them.
- Stamp backend, release, corpus version, temperature, and rung order into every
  run record.
- Verify the label on an experimental arm before reporting the contrast.
- Keep defects listed, never filtered.
- Write one test that constructs each component with its accounting attached. A
  green suite over unreachable code is the cheapest lie in the project.
- If you adopt a tracing platform, check it can express your denominators before
  you trust its dashboards. Most cannot, and a rate over the wrong base renders
  as healthy.

---

*The pipeline, the decisions log, and every figure above are at
`gitlab.com/pushpdeep/ai-reliability-ladder`. The corpus and the terminology
release are not redistributable and are not included.*

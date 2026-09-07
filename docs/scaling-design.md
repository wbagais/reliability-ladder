# Scaling to 100 × 100

*Written 2026-09-07, from the wreckage of a 30-cell run that took twenty hours.*

---

## The problem is not throughput

100 models × 100 datasets is 10,000 cells. A card does one small cell in
minutes, so the compute is a scheduling problem and scheduling is solved.

**The problem is that today's 30-cell matrix contained, at various points:**

| | cells | how it was found |
|---|---|---|
| ran a different model than their name said | 5 | a saved manifest disagreed with a directory name |
| ran with another corpus's prompt | 12 | reading a prompt dump, after five wrong theories |
| a model returning empty content on every call | 6 | noticing a token count with no output |
| a corpus extracting sentence fragments | 4 | reading the records by hand |
| a scorer reading the pre-fix file | all | the numbers were *identical* to the previous run |

**Every one of those produced a complete, well-formed results table.** None
raised. None was found by anything automatic. At 30 cells a person can look at
all of them; at 10,000 nobody looks at any, and a study that cannot detect its
own bad cells produces 10,000 numbers of unknown provenance — which is worse
than 30 good ones, because it looks authoritative.

So the whole design is about **making misconfiguration loud**.

---

## The single biggest lever: smoke every cell before running any

10,000 cells × 2 documents is cheap — an hour or two. 10,000 cells × 40
documents is a week.

So run the matrix **twice**:

**Pass 1, triage.** Every cell, two documents, rungs 0–1. Assert three things
and quarantine on any failure:

- rung 0 produced ≥ 1 record
- the free check produced at least one non-majority verdict
- the extracted spans overlap the document's gold at better than chance

That last one is the important one and it costs nothing: if a model extracts
`'However'` and `'pharmacology'` from a paper about *Borrelia burgdorferi*,
span overlap against gold is near zero and the cell is broken. Today that
would have caught LINNAEUS on three models, TR-News on all four, and every
wrong-prompt cell — in **minutes**, before a single full split ran.

**Pass 2, measurement.** Only cells that passed triage. Full split, full draws.

The quarantine list is not a failure log. It is a **result**: *these
model/corpus pairs cannot be measured with this configuration*, which is a
finding about the pairs and about the harness.

---

## Six invariants, each from a specific failure

### 1 · Nothing inherits. A missing key is an error, not a default.

Nine constants were inherited from CADEC across three ports: few-shot ids,
vocabulary gate codes, split sizes, loader options, a corpus version string, a
model name prefix, a few-shot pool split, a sheet name, and the task prompt
itself. **Every one had a default that was correct for CADEC and wrong here.**

At 100 datasets no default can be right. So the manifest schema marks every
corpus-specific key **required**, and `run.py` refuses to start without it.
A default that is right once and wrong ninety-nine times is not a convenience.

### 2 · A cell declares what it is, and the declaration is checked against the artefact.

Five cells ran the wrong model because two runners shared one scratch filename.
It was caught because the runner copies its config into the output, giving two
records of one fact that could disagree.

At scale this stops being a habit and becomes a gate: **a cell whose saved
configuration does not match its cell id is quarantined, never scored.** And no
shared mutable paths — each cell writes its own config to its own directory,
once.

### 3 · Every cell carries a run stamp, and cells with different stamps never pool.

Model, commit, host, GPU, library versions. Measured today: the same corpus,
model and seed give 23 records on a CPU-split model and 22 on a GPU-resident
one. Floating-point addition is not associative and a near-tie at the sampling
step resolves differently.

So a stamp mismatch is not a warning. Pooling across it is **refused**, the
same way a rate without a denominator is refused.

### 4 · The rendered prompt is an artefact, and it is asserted before it is used.

Twelve cells ran with a prompt asking for adverse drug reactions on corpora
about places, species and diseases. A thirteenth rendered as *"organism the
paper mentions the paper describes"* — a slot holding a clause where a noun
phrase belonged.

Three assertions at startup, none needing a model:

- the rendered prompt contains this corpus's declared entity
- it does not contain another corpus's entity
- no slot rendered a repeated 3-gram

And the rendered text is **written into the run's artefacts**. Today it was not
recoverable after a run, which is why diagnosing one corpus took five wrong
theories.

### 5 · Every cell reports its own attrition, and thin cells are flagged not averaged.

A cell reporting `100% correct` over five scored records is not a fact about
the check. Each cell publishes: records extracted, records with gold, records
scored, records in each lane. **A cell whose scored count falls below a
declared floor is reported as thin, not folded into a mean.**

### 6 · One results file per cell, or the cell is quarantined.

Today's scorer globbed and took `recs[0]`, which sorted to the *pre-fix* file
and reported the previous run's numbers as the new one's. It was caught only
because the numbers were suspiciously identical.

Ambiguity in the output directory is a defect in the run, not a thing for the
scorer to resolve by heuristic.

---

## What does not scale, and should not be pretended otherwise

**The prompt for each corpus.** Today's four blocks were written from measured
span statistics — multi-token share, dotted share, capitalisation, repeat rate
— and then a human decided what those numbers meant. *"An ordinary English word
for a living thing is an organism mention"* is a judgement about what the
corpus does, made after seeing that only 34.3% of its gold is capitalised.

The statistics side automates completely. The wording does not. A reasonable
middle: **generate a draft from the measured statistics, and require a human
signature before the corpus enters the matrix.** 100 datasets is 100 signatures
— a week of work, not a blocker, and it is the week that decides whether the
other 9,900 cells mean anything.

**The vocabulary build.** SNOMED, GeoNames, MeSH and NCBI Taxonomy each needed
their own builder — different formats, different hierarchies, different
name-class conventions. What *is* general is the **gate**: a real code must
resolve and a fake one must not. That already exists and it has caught three
ports.

**Deciding what a corpus's entity type even is.** BC5CDR annotates chemicals
and diseases and this study scores one. PsyTAR annotates four classes. That is
a choice, and a wrong choice produces a clean table measuring the wrong thing.

---

## What the run loop looks like

```
declare        one manifest per corpus, every key required, schema-validated
build          vocabulary index + gate check, refuse on failure
derive         one cell per (corpus, model, draw); config written once, immutably
triage         2 documents per cell; quarantine on empty, inert, or chance-level overlap
measure        surviving cells only, full split, sharded across workers
verify         saved config == cell id, run stamp present, one results file
score          per-cell attrition published; thin cells flagged; no pooling across stamps
report         the table AND the quarantine list, as one artefact
```

**The quarantine list is part of the result.** A study that reports 8,400 cells
and says nothing about the other 1,600 is reporting a rate over an unnamed set —
which is the thing this whole project exists to complain about.

---

## The honest summary

Scaling this is not a compute problem. It is the problem of **detecting, without
looking, that a cell ran the wrong model, the wrong prompt, or on nothing at
all** — because today every one of those produced a table that looked fine.

The cheapest fix by a wide margin is the two-pass structure: **triage everything
on two documents, quarantine loudly, then measure only what survived.** Most of
today's twenty hours were spent producing numbers that had to be thrown away,
and a two-document smoke test would have thrown them away in ten minutes.

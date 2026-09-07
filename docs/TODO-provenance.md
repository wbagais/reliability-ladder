# stagecheck — provenance gaps found while running the matrix

*Both come from a real failure on 2026-09-06. Neither is built. Recorded here
rather than in code because the tool is complete to its current design and the
evidence for changing it is one day old.*

---

## 1 · A stage records what it DID, not what it WAS

**The failure.** Two matrix runners shared a scratch filename for the manifest
each cell was launched with. One overwrote the other mid-cell, and two cells ran
a different model than their directory name claimed:

    directory                          model actually used
    psytar-gpt-oss_20b-d0        ->    ollama/ibm/granite4:micro-h
    linnaeus-mistral_7b-d0       ->    ollama/qwen3:4b

The first of those carried the headline result. It would have been scored,
written up and published as gpt-oss's number.

**Why it was caught.** The runner copies the configuration into the output
directory after each cell finishes. So there were two records of the same fact —
the name the runner *intended*, and the configuration the run *received* — and
they disagreed. Without that copy the directory name would have been the only
record and it would have been wrong.

**The gap.** stagecheck records a stage's rows, denominators and outcomes. It
records **nothing about the configuration those rows were produced under**. A
user could have exactly this failure — a config swapped underneath a running
stage — and the ledger would look perfect.

**What it would take.** A `Ledger` opened with a `run` block, stamped once and
written into every row's provenance:

```python
led = stagecheck.Ledger(run={
    "model": "gpt-oss:20b",
    "commit": "a1b2c3d",
    "host": "ladder-gpu",
})
```

The tool should not *interpret* those fields — it does not know what a model is.
It should carry them, and refuse to merge two ledgers whose `run` blocks differ
without saying so. **Comparing rows from two configurations is the same error as
computing a rate over an unnamed set, one level up.**

---

## 2 · Hardware is part of the configuration, and nothing says so

**The measurement.** The same corpus, model, manifest, split and `sample_index`,
run on two machines:

    laptop (4 GB card, model split CPU/GPU)   23 records · ACCEPT 9 · BAND 14
    rented card (48 GB, entirely on GPU)      22 records · ACCEPT 7 · BAND 15

Not noise between runs — each machine is self-consistent, and three draws on the
rented card were bit-identical. The two machines simply produce different
output.

**Why.** Floating-point addition is not associative, and a model split across
CPU and GPU accumulates in a different order than one held entirely in VRAM. The
differences are in the last bits, and at the sampling step a near-tie between
two tokens resolves differently. One different token changes everything after
it. **Temperature 0 does not help** — it removes sampling randomness, not
arithmetic differences.

**The consequence.** A smoke test on a laptop cannot be compared with a run on a
card. Numbers from two machines are two experiments, and mixing them is
undetectable after the fact.

**What stagecheck should do — and should NOT do.** It should not try to make
runs reproducible across hardware: deterministic kernels and fixed batch sizes
cost speed, still break on a driver update, and are not this tool's business.

It should **carry the hardware in the run stamp and refuse to pool across it**,
the same way it refuses a rate without a denominator. The point is not to
eliminate the variation but to make pooling across it impossible by accident.

---

## What is NOT worth adding from today

The rest of the day's failures are porting problems specific to one study and
would make the tool larger without making it better:

- a model with no entry in a config registry falling back to a default that
  cannot work (`qwen3:4b`, 2,000 tokens for a model that thinks before answering)
- a model returning valid JSON in the wrong shape (`granite4:micro-h` returns
  mentions as strings)
- seven inherited constants across three corpus ports — few-shot ids, vocabulary
  gate codes, split sizes, loader options, a corpus version string
- a sheet named `WD-Mapped ` with a trailing space among eleven named `X_Mapped`

Each cost an hour and each is a fact about one codebase. **A tool that grew a
feature for every one of these would be a tool nobody could read.**

---

## 3 · A stage should assert things about its own configuration, before it runs

**The failures.** Twelve matrix cells ran with a prompt asking for adverse drug
reactions on corpora about places, species and diseases. A thirteenth rendered
as *"organism the paper mentions the paper describes"* — a slot holding a clause
where a noun phrase belonged. Every one produced a complete results table.

**Why `preflight()` does not catch it.** stagecheck's precondition asks whether
a stage has work to do: is there something here for this check to find? On
LINNAEUS the answer was yes — the papers were full of species. The
*instruction* was malformed, and a precondition about the input cannot see a
defect in the configuration.

**The shape.** `declare()` already takes a testable `Precondition` checked
before the stage runs. A config assertion is the same object pointed at the run
stamp instead of the input:

```python
declare(
    stage="extract",
    precondition=...,           # exists
    config_asserts=[...],       # does not
)
```

**And the boundary matters.** stagecheck must not learn what a prompt is.
*"The rendered text must name this corpus's entity"* is a claim about one
study. The tool should carry the run block, let a caller assert arbitrary
predicates over it, and fail loudly — the same way it carries relations without
knowing what SNOMED is.

**Why it belongs here and not in a second tool.** It is the same argument one
level up. A rate over an unnamed set is meaningless; a rate over a misconfigured
stage is meaningless in exactly the same way, and neither announces itself.

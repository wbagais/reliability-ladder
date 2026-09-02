# stagecheck against the field

*Where it sits, what it does that others do not, and — honestly — what they
could absorb tomorrow.*

---

## The one-line difference

Every tool in this space answers **"is my output good?"**

stagecheck answers **"is my layer worth its cost?"**

Those are different questions with different units, and the second one has no
tool. That is the whole positioning, and it is not a marketing distinction: you
can run every eval framework in the world against a pipeline and still not know
that three of its stages are doing nothing.

---

## Side by side

| | ragas · deepeval · promptfoo | **stagecheck** |
|---|---|---|
| **unit** | an output | **a stage** |
| **asks** | is this answer right? | **did this layer pay for itself?** |
| **needs** | a scorer, often an LLM judge | **a declared bet and a denominator** |
| **output** | a score, a pass/fail, a leaderboard | **build / don't, with the alternative** |
| **when** | after generation | **before, during and after** |
| **cost** | judge calls, often per record | **free — no model calls at all** |
| **failure it catches** | the answer is wrong | **the layer is pointless** |
| **failure it misses** | a stage that does nothing | whether any individual answer is right |

They are complementary rather than competing. A team should run both — one
tells you the output is bad, the other tells you which of your five mitigation
layers to delete.

---

## Four things it does that the others do not

### 1 · A rate must name its denominator

None of them model one. A judge's agreement figure in this project moved
**100% → 98% → 49% across three record sets with no change in judge
behaviour** — the number was describing the composition of the comparison set,
not the judge. That movement is invisible in every tool evaluated, because it
is not a property of any call, and calls are what they model.

### 2 · Three outcomes, not two

`pass`, `fail`, and **`could-not-run`**. A check that could not be evaluated is
not a check that passed, and collapsing the two is how a rate ends up over a
set nobody named. Measured here: 514 of 704 records where a check simply had
nothing to say — reported as its own state rather than folded into agreement.

### 3 · The precondition, before the layer is built

The others measure what you built. This measures whether it was worth building,
from gold, with no model calls. Four of seven layers in this project were dead,
and **each was predictable in an afternoon** — the free check's precondition
either holds on your data or it does not, and one query answers it.

### 4 · The relation registry — an alternative, not a verdict

When a check has no signal, the tool does not say "your check is broken." It
says which *other* deterministic relation does have signal on this data —
lexical overlap, type compatibility, semantic class, name uniqueness. On the
corpus where the lexical check is a structural zero, type compatibility reaches
**87.7% coverage**. Nobody else has this taxonomy because nobody else needed
it.

---

## What they could absorb tomorrow — stated plainly

**The denominator field: yes, trivially.** It is one column in a trace schema
and a well-funded team could ship it in a release. That is the real competitive
threat and there is no defence except being first and being right about why it
matters.

**Three outcomes: yes**, and it is the same afternoon's work.

**The relation registry: no** — not without doing the study. The taxonomy came
out of measuring seven layers on three corpora across five model families and
being wrong four times in public. Each relation exists because a specific
measurement demanded it: `type` because a numeral shares no token with a
phrase, `unique` because an ACCEPT lane fired at 39.8% and scored *worse* than
the lane it was meant to beat.

**The calibration record: they would not want it.** A commercial tool does not
ship a file saying *"2 right, 2 partly, 1 wrong, 1 unknown"* about its own
predictions. That is an advantage available only to something with no revenue
to protect, and it is worth more than it looks: a tool that reports its own
misses is trusted differently from one that does not.

---

## Where stagecheck is weaker, and it should say so

- **No output scoring.** If you want to know whether an answer is right, use
  one of the others. This will not tell you.
- **Instrumentation cost.** Stages must be wrapped. ragas runs on a dataframe.
- **Three corpora of calibration** against their years of community usage.
- **One maintainer**, part time.
- **It tells you things you may not want to hear**, which is a genuine adoption
  barrier and not a badge of honour.

---

## The honest summary

stagecheck is not competing with ragas. It occupies a gap they left because
their unit is the output and this one's is the layer.

The gap is real but small, the defensible part is the study rather than the
code, and the thing most worth having — a denominator on every row — is also
the thing most easily copied. **Ship it, keep it small, and let the article do
the arguing.**

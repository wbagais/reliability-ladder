# Early measurements and the build checklist

*Moved out of the README on 2026-09-09. Everything here is superseded by the
consolidated re-run of 2026-09-03 (`runs/archive/consolidated-2026-09-03/`)
and the matrix of 2026-09-07 (`runs/archive/matrix-2026-09-07/`). It is kept
because [decisions.md](decisions.md) refers to it. Current numbers:
[the article](article-infoq-CADEC.md), [FINAL-RESULTS.md](FINAL-RESULTS.md).*

## What rung 1 costs and catches, measured before rung 0 exists

Both halves of a validation gate can be measured against the answer key alone,
with no model calls. Whole corpus, 9,111 gold mentions, SNOMED
AU1000036_20260731.

```bash
python -m ladder.calibrate --split all --sweep
```

```bash
python -m ladder.probe --split all
```

| | |
|---|---|
| false-rejection floor on gold | **12 / 9,111 = 0.13%** — down from 9.3% for the gate as first specified |
| zone occupancy on gold | ACCEPT 43.1% · BAND 56.8% · REJECT 0.13% |
| detection: hallucinated code · span shift · fabricated quote | 1.000 · 1.000 · 1.000 |
| detection: real code in the wrong branch | 1.000 on reaction records |
| detection: random plausible wrong finding | 0.000 caught, 0.000 wrongly accepted |
| detection: **near-miss** code (right head word, wrong concept) | 0.001 caught — and **19% wrongly ACCEPTED** under lenient lexical matching, 0.1% under strict |

Read together: deterministic checks are *exact* on their own error classes and
blind to the interesting one, and a validation gate's leniency setting decides
whether it declines to have an opinion or endorses one near-miss in five.

## The first dev-split ladder figures, 2026-08-20

> **Superseded.** The shipped numbers are on the frozen test split — exact F1
> 0.204, coding accuracy 0.392, rung 5 dropping errors from 59.6 to 3.8 per 100
> at 77.1 reviews per 100 — and the cross-corpus results are in
> [article-v3.md](article-v3.md). **Rung ids below are the OLD numbering**
> (before the 2026-08-23 renumber: 2 = abstention, 3 = self-correction,
> 5 = voting).

Dev split, 40 documents, `granite4:micro-h` extractor, `llama3.2:3b` judge,
SNOMED CT-AU `AU1000036_20260731`, local GPU.

| rung | intervention | cost | outcome |
|---|---|---|---|
| 0 | bare model | 19,354 tok | 169 mentions · span F1 **0.543** · **0/105 correct codes** |
| 1 | validation | none | 166 REJECT / 3 BAND / 0 ACCEPT |
| 3 | self-correction | 72,539 tok | 158 offered · **0 rescued** · 158 declined |
| 5 | voting k=3 @ 0.7 | 55,704 tok | unanimous on 3 · **166/169 not re-found by any sample** |
| 4 | LLM-as-judge | 87,130 tok | 96 judged of 169 · span_ok 3 · code_ok 83 |
| 2 | abstention | none | **169/169 withdrawn**, 0 codes published |
| 6 | triage desk | — | structurally blocked — see below |

**Zero correct codes throughout.** Every layer produced a metric suggesting
improvement; the correct-code count never moved off zero.

**Rung 4's two channels are constants.** Against a gold control (226 annotator
mentions mixed with the 169 model records, judged in one pass): `span_ok` 3% on
gold and 3% on model output; `code_ok` 92% on correct codes and 86% on
fabricated ones. The judge is not reading its input. Its agreement with rung 1
is a property of the comparison set — 100% / 98% / 49% across three sets with
identical judge behaviour.

```bash
PYTHONPATH=. python3 scripts/r4_gold_control.py
```

**Abstention is correct and inherits all of it.** 169/169 withdrawn on model
output, 76 kept / 150 withdrawn on gold, no crossover. It reads rung 1's
verdict and maps it — the discrimination is the lookup's. Coverage cost: **150
of 226 correct gold codes withheld, 66%**, free here only because the model
produced no correct codes to lose.

**Rung 6 was measured, not built.** A triage desk over 169 records that are
all wrong would be re-annotation, not triage. But the third cost measure —
records routed to a person — was zero everywhere, so the ladder's full cost
could not be stated. It was run instead as a blind, stratified timing study: 6
records, gold and model mixed and presented identically, terminology
searchable, decisions and seconds recorded, accuracy deliberately not scored.

| | n | median | range |
|---|---|---|---|
| with candidates | 3 | 12.5s | 7–19s |
| without | 3 | 27.1s | 21–46s |

Extrapolated from n=3, by a reviewer who is not a trained coder: the 155 records
with no valid code are roughly **1.2 reviewer-hours**, against 234,727 tokens
that produced 0 correct codes.

```bash
LADDER_N=8 PYTHONPATH=. python3 scripts/r6_desk.py
```

**The vocabulary is a ceiling.** `Registry.search()` is exact-term retrieval —
the query is normalised and matched for equality against SNOMED's description
table. Deliberate: a fuzzy local index has no relevance ranking and would stop
being comparable with the OLS4 backend. The measured cost had not been taken:
**141 of 343 gold reaction spans return a candidate, 202 return nothing (59%)**.
`low back pain` resolves; `lower back pain` does not. Every rung that depends on
term lookup inherits that ceiling. (Rung 0 has since moved to dense retrieval
over `data/keywords.csv`; see decisions.md, 2026-08-24.)

**No rung interaction.** Run end to end in the specified order, every per-rung
figure reproduced exactly.

```bash
LADDER_N=0 PYTHONPATH=. python3 scripts/ladder_run.py
```

## Build checklist, as it stood on 2026-09-08

Kept verbatim. [CHANGELOG.md](../CHANGELOG.md) is the current record of what
moved.

- [x] Corpus, frozen splits, vocabulary index, ledger, rung 1, rung 5, harness
- [x] Both model-free characterisations of rung 1
- [x] Rungs 0 / 3 / 4 / 5 — the full ladder runs end to end
- [x] All seven rungs measured; gold controls for rungs 2 and 4; end-to-end run
      in the specified order confirming zero rung interaction
- [x] Per-record ledger for every rung, with denominators and a three-valued
      `evaluable`
- [x] InfoQ article — the submission is
      [article-infoq-CADEC.md](article-infoq-CADEC.md), single-corpus,
      with its rules in [INFOQ-SUBMISSION.md](INFOQ-SUBMISSION.md) and
      the Word export beside it; the long two-corpus draft it was cut from is
      [article-v3.md](article-v3.md), and the 2026-08-24 first draft
      is archived as
      [versions/infoq-article-draft-2026-08-24.md](versions/infoq-article-draft-2026-08-24.md)
- [ ] The shared scorer `ladder/score.py` — `run.py` writes the accuracy columns
      empty rather than guessing, and reports a missing rung rather than faking it
- [x] Rung 6 measured as a timing study — 1.2 reviewer-hours extrapolated
- [x] Provenance stamps on every script that produces a figure
- [x] Contract tests — vocabulary Protocol conformance, exact-term search
      pinned, the never-fired guards exercised, rung 0's two entry points
      asserted to agree
- [ ] Rung 0 mode B — measures prompt wording plus a post-hoc lookup, NOT tool
      access. The search runs after generation and the model never sees it;
      worse, exact-term retrieval returns nothing for most mentions, so
      `honoured_tool` is undefined rather than false. Do not publish the current
      framing. A real tool loop is untested and is the obvious next experiment
- [ ] `ladder/rungs/r0.py` has two entry points, `run()` and `apply()`. They now
      agree and a test enforces it, but the duplication is the underlying issue
- [ ] `docs/plan.html` — audited against measured results, six blocking items
      open. See [plan-html-audit.md](plan-html-audit.md)
- [—] Rung 6 — **structurally blocked, not pending.** Nothing below it produces
      records worth reviewing *(as of 2026-08-20; rung 6 landed 2026-08-26)*

**Retired 2026-08-22:** an earlier data-agnostic track (its pipeline, dashboard,
adapters, schemas and tests), together with its results. The CADEC track
imported none of it.

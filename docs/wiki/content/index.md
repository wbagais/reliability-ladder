# Reliability Ladder

Measure what each reliability layer wrapped around an LLM buys, and what it costs, so you stop at the rung your economics justify.

- **Task** — pharmacovigilance triage. Read an archived patient post, find the adverse reactions described, normalise each to a SNOMED CT code.
- **Unit of evaluation** — one mention record, never one document.
- **Safety boundary** — reports *what a document says*. Never asserts a drug caused an effect.
- **Cost** — three measures, never fused: tokens, latency p95, records routed to a person.

> Rungs 0–2 are research artefacts with deliberate failure rates. Not fit for operational use. There is no free-text entry point: the runner takes a split identifier, never a string.

## Start here

- New to the repo → [[getting-started]]
- Want the system design → [[architecture]]
- Want to know what a rung is → [[rungs]]
- Something broke → [[troubleshooting]]
- Unfamiliar term → [[glossary]]
- About to open an MR → [[contributing]]

## Build status

| Rung | Layer | Owner | State |
|---|---|---|---|
| 0 | [[r0]] bare LLM | B | in progress — `stub_llm.py` and `rung0_ab.py` landed, `rungs/r0.py` not yet |
| 1 | [[r1]] deterministic | A | built and measured |
| 2 | [[r2]] abstention | A | built and measured |
| 3 | [[r3]] self-correction | B | not started |
| 4 | [[r4]] LLM-as-judge | B | not started |
| 5 | [[r5]] voting | B | not started |
| 6 | [[r6]] human-in-the-loop | joint | not started |

- Shared scorer `ladder/score.py` — not written. Accuracy columns stay empty until it is.
- `run.py` reports a missing rung rather than faking it.

## Core reference

- [[record]] — the object every rung mutates, and the zones it moves between
- [[ledger]] — one row per (rung, record); the single accounting path
- [[corpus]] — CADEC, the frozen splits, why dev/test/pool
- [[vocabulary]] — SNOMED backends, and why they are not interchangeable
- [[manifest]] — every setting that can move a published number
- [[runner]] — the CLI and its four subcommands
- [[measurement]] — calibrate, probe, vocab_crosscheck
- [[data-licences]] — what may never be committed
- [[testing]] — the suite, the fixture gate, CI

## Headline measurements

Whole corpus, 9,111 gold mentions, SNOMED `AU1000036_20260731`, no model calls.

| | |
|---|---|
| rung 1 false-rejection floor on gold | **12 / 9,111 = 0.13 %** |
| zone occupancy on gold | ACCEPT 43.1 % · BAND 56.8 % · REJECT 0.13 % |
| detection: hallucinated code, span shift, fabricated quote | 1.000 each |
| detection: plausible wrong finding | 0.000 |
| OLS4 vs local index disagreement on gold | 23.9 % |

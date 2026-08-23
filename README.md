# The Reliability Ladder

Measure what each reliability layer wrapped around an LLM actually buys — and
what it costs — so you can stop at the rung your economics justify instead of
stacking layers by intuition.

**Task.** Pharmacovigilance triage: read an archived patient report, identify the
adverse reactions the writer describes, and normalise each to a SNOMED CT code.
The system reports *what a document says*. It never asserts that a drug caused
an effect.

📄 **[Plan, architecture and interactive demo](https://pushpdeep.gitlab.io/ai-reliability-ladder/)**
— `docs/plan.html`, published by CI on every push to `main`.

> Rungs 0–2 are research artefacts with deliberate failure rates, unfit for
> operational use. There is no free-text entry point in the package: the runner
> takes a corpus split identifier, never a string.

## The ladder

| Rung | Layer | Mechanism | Extra cost | Owner |
|---|---|---|---|---|
| 0 | bare LLM | one call, JSON, temp 0; emits a code with or without a lookup tool (`rung0_mode`) | 1 call/item | B |
| 1 | deterministic | schema · span grounding · negation · code exists · semantic type · MedDRA | **none** | A |
| 2 | abstention | decline anything still unresolved, or below τ | none | A |
| 3 | self-correction | one bounded retry, fired **only by a rung 1 failure**, reason stated as fact | +1 call | B |
| 4 | LLM-as-judge | second model, **different family**, scores the record | +1 call | B |
| 5 | voting | k samples, majority on the **normalised code**, never the string | k calls | B |
| 6 | human-in-the-loop | a person settles it — simulated, or timed | human minutes | joint |

Rung ID equals execution position, `[0, 1, 2, 3, 4, 5, 6]` — abstaining before you
have tried correction and voting throws away recoverable records. Order lives in
`manifest.json`, so it is a testable ablation rather than an assertion.

**Rung 1 judges; it does not filter.** `rungs.1.mode` defaults to `"observe"`:
the verdict is recorded, counted and reported, and the record's zone is left
alone, so rungs 3–6 see the full unfiltered set and each rung stays a
single-rung ablation on identical input. Rung 5 (abstention), which runs last, is where a
rung 1 verdict is finally allowed to cost coverage. `"gate"` restores the
filtering flow.

## Cost, in three measures that are never fused

**Tokens per record** · **latency p95** · **records routed to a person**.

No dollar figure: a single `$/100` needs a price table that shifts under you,
and it silently merges three costs that are not interchangeable. Keeping them
apart forces the honest question — *would you rather spend tokens or human
attention?*

## Quick start

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt pytest
```

```bash
python -m ladder.registry --build --release data/SnomedCT_Release_<yours>
```

```bash
python -m ladder.run init
```

`init` verifies the corpus parses, runs the critical-path gate (a real code
resolves, a fake one does not) and writes the frozen splits. Then the fixture
gate — a dozen hand-made records, several deliberately broken:

```bash
python -m ladder.run gate
```

```bash
python -m ladder.run ladder --split test --source gold --run-id gold_control
```

Before every push — scans the working tree **and git history** for corpus text,
API keys and forbidden paths:

```bash
python scripts/preflight.py --history
```

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

The build log — including every place the plan and the corpus disagreed — is
[docs/decisions.md](docs/decisions.md), with the article-shaped version in
[docs/article-iterations.md](docs/article-iterations.md).

## What the full ladder measured

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

**Rung 2 is correct and inherits all of it.** 169/169 withdrawn on model output,
76 kept / 150 withdrawn on gold, no crossover. It reads rung 1's verdict and
maps it — the discrimination is the lookup's. Coverage cost: **150 of 226
correct gold codes withheld, 66%**, free here only because the model produced no
correct codes to lose.

**Rung 6 is blocked, not unfinished.** It would receive 169 withheld records,
every one carrying a wrong answer or none. The ladder terminates before the top
because the bottom produces no signal to pass upward.

**No rung interaction.** Run end to end in the specified order, every per-rung
figure reproduced exactly.

```bash
LADDER_N=0 PYTHONPATH=. python3 scripts/ladder_run.py
```

## The ledger, and what it records that tools do not

One row per record per rung: tokens, calls, latency, outcome — plus two fields
that no LLM observability platform models.

- **`denominator`** — the named set this row's rate is computed over. Rung 4
  judged 96 of 169 offered; rung 5 voted on 3 of 169. A rate over the wrong base
  renders as healthy.
- **`evaluable`** — `pass` · `fail` · **`could_not_run`**. Three values, never a
  boolean. Parse failures, not-re-found mentions and unevaluable checks are none
  of them a pass and none of them a fail.

Optional OpenTelemetry export, off unless `LADDER_OTEL=1`, so no measured figure
depends on it:

```bash
LADDER_OTEL=1 OTEL_EXPORTER_OTLP_ENDPOINT=localhost:4317 \
  LADDER_N=0 PYTHONPATH=. python3 scripts/ladder_run.py
```

## Data — read before you clone

No corpus is in this repository, and none can be.

| Source | Terms | Where it lives |
|---|---|---|
| **CADEC v2** | CSIRO Data Licence — non-commercial, **non-transferable**, no redistribution | [csiro:10948](https://data.csiro.au/collection/csiro:10948). Each team member accepts it individually; the download directory is gitignored |
| **SNOMED CT** | affiliate licence for full releases | a local RF2 release indexed by `ladder/registry.py`, or [EBI OLS4](https://www.ebi.ac.uk/ols4) at run time via `ladder/vocab.py` — free, no key |
| **MedDRA** | subscription (MSSO) | only `data/meddra_codes.example.csv` (10 rows, for tests) is committed |

`data/splits/*.json` holds **document IDs only** — no post text, no annotations.
Anyone with their own licensed copy reproduces the exact splits; nobody obtains
the corpus from here. Full detail: [docs/licences.md](docs/licences.md).

### Two vocabulary backends, and they are not equivalent

`ladder/vocab.py` selects one and records it in the manifest:

| backend | source | `lossy` |
|---|---|---|
| `local-rf2` | a SNOMED RF2 release indexed to SQLite | **False** — sees retired concepts and extension modules |
| `ols4` | EBI OLS4 over the network | **True** — active international SNOMED only |

An OLS4-backed `exists()` reports **23.9%** of CADEC gold as codes that do not
exist: 7.5% retired, 16.4% AU-extension — which is **100% of drug mentions**,
because CADEC codes drugs to AMT. A rung 1 rejection rate is not comparable
across backends.

```bash
python -m ladder.vocab_crosscheck --live 40
```

## The 3 contracts (see `/schemas`)

1. **runner.py** — `apply(records, sources, cfg) -> records`. Every rung
   implements it, which makes execution order a config value and a new rung
   twenty minutes' work.
2. **vocabulary.py** — the global vocabulary resource, injected once per run
   rather than per item. Two backends, and every backend declares whether it is
   `lossy`.
3. **`ladder/schema.py`** — the record: one **mention**, not one document and
   not a drug↔reaction pair. Frozen after the fixture gate.

## Repo map

```
ladder/       schema (the A/B contract) · corpus reader + frozen splits ·
              registry (local SNOMED index) · vocab (backend selection + OLS4) ·
              llm (cached model client) · ledger · otel (optional OTLP export) ·
              negation · run.py · fixture (the gate) · calibrate · probe ·
              vocab_crosscheck
ladder/rungs/ r0 (extract + A/B ablation) · r1 (validate) · r2 (abstain) ·
              r3 (self-correct) · r4 (judge) · r5 (vote)
schemas/      the contracts
data/         meddra_codes.example.csv · splits/ (document IDs only)
docs/         plan.html · decisions.md · cadec-track.md · licences.md ·
              article-iterations.md
scripts/      preflight.py · ladder_run.py (full ladder, specified order) ·
              r4_gold_control.py · full_run.py · dev_sweep.py ·
              split_by_type.py · count_codes.py
tests/        against stubs — no network, no keys, no corpus
manifest.json corpus + vocabulary versions, seed, splits, gold rule, rung order,
              rung parameters, ablations. Reproducibility and honesty are the
              same file.
```

## Status

- [x] Corpus, frozen splits, vocabulary index, ledger, rung 1, rung 5, harness
- [x] Both model-free characterisations of rung 1
- [x] Rungs 0 / 3 / 4 / 5 — the full ladder runs end to end
- [x] All seven rungs measured; gold controls for rungs 2 and 4; end-to-end run
      in the specified order confirming zero rung interaction
- [x] Per-record ledger for every rung, with denominators and a three-valued
      `evaluable`
- [x] InfoQ article — first draft in [docs/infoq-article-draft.md](docs/infoq-article-draft.md)
- [ ] The shared scorer `ladder/score.py` — `run.py` writes the accuracy columns
      empty rather than guessing, and reports a missing rung rather than faking it
- [ ] Rung 0 mode B — currently measures prompt wording, not tool access
      (`honoured_tool` is never true; the lookup runs after generation). Rename
      it or build a real loop; do not publish the current framing either way
- [ ] `docs/plan.html` — audited against measured results, six blocking items
      open. See [docs/plan-html-audit.md](docs/plan-html-audit.md)
- [—] Rung 6 — **structurally blocked, not pending.** Nothing below it produces
      records worth reviewing

**Retired 2026-08-22:** an earlier data-agnostic track (its pipeline, dashboard,
adapters, schemas and tests), together with its results. The CADEC track imported
none of it. Every number in this repo is measured on CADEC v2.

## Licence

Code: MIT (see [LICENSE](LICENSE)). Third-party data keeps its own terms —
CADEC, SNOMED CT and MedDRA are each named explicitly in the carve-out and in
[docs/licences.md](docs/licences.md).

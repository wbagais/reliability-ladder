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

Runtime order is `[0, 1, 3, 5, 4, 2, 6]`, not numeric — abstaining before you
have tried correction and voting throws away recoverable records. Order lives in
`manifest.json`, so it is a testable ablation rather than an assertion.

**Rung 1 judges; it does not filter.** `rungs.1.mode` defaults to `"observe"`:
the verdict is recorded, counted and reported, and the record's zone is left
alone, so rungs 3–6 see the full unfiltered set and each rung stays a
single-rung ablation on identical input. Rung 2, which runs last, is where a
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

## Data — read before you clone

No corpus is in this repository, and none can be.

| Source | Terms | Where it lives |
|---|---|---|
| **CADEC v3** | CSIRO Data Licence — non-commercial, **non-transferable**, no redistribution | [csiro:10948](https://data.csiro.au/collection/csiro:10948). Each team member accepts it individually; the download directory is gitignored |
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
              llm (cached model client) · ledger · negation ·
              rungs/r1 · rungs/r2 · run.py · rung0_ab (the rung-0 ablation) ·
              fixture (the gate) · calibrate · probe · vocab_crosscheck
schemas/      the contracts
data/         meddra_codes.example.csv · splits/ (document IDs only)
docs/         plan.html · decisions.md · cadec-track.md · licences.md ·
              article-iterations.md
scripts/      preflight.py
tests/        against stubs — no network, no keys, no corpus
manifest.json corpus + vocabulary versions, seed, splits, gold rule, rung order,
              rung parameters, ablations. Reproducibility and honesty are the
              same file.
```

## Status

- [x] Corpus, frozen splits, vocabulary index, ledger, rung 1, rung 2, harness
- [x] Both model-free characterisations of rung 1
- [ ] Rungs 0 / 3 / 4 / 5 and the shared scorer (owner B) — `run.py` reports a
      missing rung rather than faking it
- [ ] Rung 6, joint
- [ ] InfoQ article — beats and numbers in `docs/article-iterations.md`

**Retired 2026-08-22:** the data-agnostic SROIE track (`bench/` pipeline,
`app/`, its adapters, schemas and tests). The CADEC track imported none of it.
Its measured results are kept in [docs/decisions.md](docs/decisions.md) and
[docs/article-outline.md](docs/article-outline.md); the code is recoverable from
git history at `e938f8d`.

## Licence

Code: MIT (see [LICENSE](LICENSE)). Third-party data keeps its own terms —
CADEC, SNOMED CT and MedDRA are each named explicitly in the carve-out and in
[docs/licences.md](docs/licences.md).

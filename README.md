<!-- Paste at the very top of README.md, above the existing title. -->
<!-- Requires docs/figures/fig0-hero.png, which is already in the repo. -->

<p align="center">
  <img src="docs/figures/fig0-hero.png" width="820"
       alt="Seven ladder rungs rendered as beads, coloured by what each layer bought: two paid for themselves, two cost tokens and changed nothing, three had no measured effect.">
</p>

<h1 align="center">The AI Reliability Ladder</h1>

<p align="center">
  <i>Seven reliability layers around a language model, measured one at a time
  on a task with a real answer key — what each one bought, and what it charged.</i>
</p>

<p align="center">
  <a href="docs/article-v3.md">the article</a> ·
  <a href="docs/decisions.md">the decision log</a> ·
  <a href="docs/figures/">figure sources</a>
</p>

---
# The Reliability Ladder

Measure what each reliability layer wrapped around an LLM actually buys — and
what it costs — so you can stop at the rung your economics justify instead of
stacking layers by intuition.

**Task.** Pharmacovigilance triage: read an archived patient report, identify the
adverse reactions the writer describes, and normalise each to a SNOMED CT code.
The system reports *what a document says*. It never asserts that a drug caused
an effect.

📄 **[Plan, architecture and interactive demo](https://ai-reliability-ladder-9baac5.gitlab.io/)**
— `docs/plan.html`, published by CI on every push to `main`.

> Rungs 0–2 are research artefacts with deliberate failure rates, unfit for
> operational use. There is no free-text entry point in the package: the runner
> takes a corpus split identifier, never a string.

## The ladder

| Rung | Layer | Mechanism | Extra cost | What it bought |
|---|---|---|---|---|
| 0 | bare LLM | retrieve candidates, then pick a line number — two calls, and neither ever sees a code | 2 calls/item | the input to everything above |
| 1 | deterministic | schema · span grounding · negation · code exists · semantic type · lexical match | **none** | the one layer that paid — 80–89% correct in its ACCEPT lane across five model families |
| 2 | self-correction | one bounded retry, fired **only by a rung 1 rejection**, the reason stated as a fact | +1 call | **nothing.** 0 rescued of 158 on CADEC, 0 of 918 on FiNER |
| 3 | voting | k samples, majority on the **normalised code**, never the string | k calls | +5 on the tuning set, **0 out of sample**, for 425,355 tokens |
| 4 | LLM-as-judge | second model, **different family**, scores the record | +1 call | separates 1.23× held out, against the free check’s 2.36–6.12× |
| 5 | abstention | decline anything rung 1 could not corroborate | none | errors 62.9 → 4.0 per 100, at 79 reviews per 100 |
| 6 | human-in-the-loop | a person settles it — timed, not simulated | human minutes | the only settling authority, and the cost nothing else prices |

Rung ID equals execution position. **This numbering changed on 2026-08-23**, and
decision-log entries before that date use the old order (2=abstention,
3=self-correction, 5=voting) — the mapping is in `docs/decisions.md`.

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

The ledger does carry a `usd` column alongside the three, computed per call
from `ladder/models.yaml`. It is never fused into them and no headline is
reported in it — it exists so a hosted run's bill is recoverable from the
results rather than reconstructed afterwards.

## Three corpora, and only two of them are yours to run

Deliberately different in the one respect that decides whether the free check can
work at all — whether the extracted span and the code’s own name are drawn from
the same language.

| corpus | domain | vocabulary | licence | free check fires |
|---|---|---|---|---|
| **CADEC v2** | patient forum posts | SNOMED CT, 129,675 concepts | **non-transferable** — you need your own copy | 42.4% |
| **FiNER-139** | SEC filings | 139 XBRL tags | CC-BY-SA-4.0, redistributable | **0.0%** |
| **GeoWebNews** | news geography | GeoNames, 13.4M places | GPL-3.0, redistributable | 39.8% |

FiNER’s zero is structural rather than a low score: the spans are numerals
(`47.6`) and the tags are English phrases
(`EffectiveIncomeTaxRateContinuingOperations`), so the two share no token by
construction — on any run, with any model, forever.

## Run it yourself, without a licence

**Start here.** CADEC cannot be redistributed, so that arm is not reproducible
from a clean checkout by anyone but you. The FiNER arm is.

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt pytest
```

```bash
mkdir -p data/finer && cd data/finer
curl -LO https://huggingface.co/datasets/nlpaueb/finer-139/resolve/main/finer139.zip
unzip -q finer139.zip -d extracted && cd ../..
python -m ladder.run init --manifest manifest.finer.json
```

The free half needs no model and takes seconds:

```bash
PYTHONPATH=. python3 scripts/preflight_rungs.py --manifest manifest.finer.json --static
PYTHONPATH=. python3 scripts/relations_report.py --manifest manifest.finer.json
```

That second command is the shortest route to the central finding. It reports
that the lexical check has **no signal at all** here, and that a
type-compatibility check has 87.7% — a layer reported dead means *this check
found no signal*, never *this corpus has none*.

For the model half you need [ollama](https://ollama.com) and ~14 GB of VRAM:

```bash
ollama pull gpt-oss:20b && ollama pull ibm/granite4:micro-h
PYTHONPATH=. python3 -m ladder.run --manifest manifest.finer.json ladder \
    --split test --limit 3 --plain
```

Drop `--limit 3` for the full split — 60 documents, roughly 25 minutes on a
48 GB card, several hours on a laptop.

### Reproduce the article’s findings

Five of them, from gold and source, with no model calls:

```bash
PYTHONPATH=. python3 scripts/reproduce.py
```

### The GeoWebNews arm

```bash
git clone --depth 1 https://github.com/milangritta/Pragmatic-Guide-to-Geoparsing-Evaluation /tmp/gwn
mkdir -p data/gwn && cp -r /tmp/gwn/data/Geocoding data/gwn/
curl -O https://download.geonames.org/export/dump/allCountries.zip && unzip -q allCountries.zip
python3 scripts/build_geo_index.py --dump allCountries.txt --out ladder/cache/geonames.sqlite
PYTHONPATH=. python3 -m ladder.run --manifest manifest.geo.json init
```

The index is 13.4M rows and takes about a minute. **This arm uses lexical
retrieval where CADEC uses dense** — no embedded keyword table exists for a
gazetteer — and on CADEC that substitution cost 21 points of recall@20. No
absolute score from the geo arm is comparable with CADEC’s.

## Quick start

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt pytest
```

**The model is named in `manifest.json` and nowhere else.** `ladder/llm.py`
carries no default and raises if the manifest names none, so a run always
knows which model produced its numbers. Override for a single run with
`--extractor` or `LADDER_MODEL_SPEC`; both are written into the manifest copy
saved beside the results. Per-model request settings — `max_tokens`,
`sampling`, `reasoning_effort` — live in `ladder/models.yaml`, because a rung
must never know which family it is calling.

Five preprocessing steps, in order. Each produces gitignored, licence-bound
data; a fresh clone runs all four before any rung.

```bash
python -m ladder.registry --build --release data/SnomedCT_Release_<yours>
```

```bash
python -m ladder.keywords --build
```

```bash
python -m ladder.clean --build
```

```bash
python -m ladder.run init
```

`registry --build` indexes the RF2 release to SQLite, including the
retired→replacement association refset that lets a stale code score as
*outdated* rather than as wrong. `keywords --build` writes `data/keywords.csv`,
the name→code table rung 0 resolves through — SNOMED-derived only, nothing in
it reads the answer key. `clean --build` writes `data/exclusions.csv`, the gold
mentions that cannot be answered and leave the denominator with a stated
reason.

Optional, for S2's dense retrieval — a few minutes and a local embedding model:

```bash
python -m ladder.embed --build
```

An index built before 2026-08-24 has no association table. Add it in place,
in seconds, rather than rebuilding:

```bash
python -m ladder.registry --associations --release data/SnomedCT_Release_<yours>
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

> **These are the FIRST dev-split figures, from 2026-08-20, and they are
> superseded.** Kept because the decision log refers to them. The shipped numbers
> are on the frozen test split — exact F1 0.204, coding accuracy 0.392, rung 5
> dropping errors from 59.6 to 3.8 per 100 at 77.1 reviews per 100 — and the
> cross-corpus results are in [docs/article-v3.md](docs/article-v3.md).

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

**Rung 6 is measured, not built.** A triage desk over 169 records that are all
wrong would be re-annotation, not triage. But the third cost measure — records
routed to a person — was zero everywhere, so the ladder's full cost could not be
stated. It was run instead as a blind, stratified timing study: 6 records, gold
and model mixed and presented identically, terminology searchable, decisions and
seconds recorded, accuracy deliberately not scored.

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
term lookup inherits that ceiling.

**No rung interaction.** Run end to end in the specified order, every per-rung
figure reproduced exactly.

```bash
LADDER_N=0 PYTHONPATH=. python3 scripts/ladder_run.py
```

## Watching a run

Two views over the same append-only ledger, so they cannot disagree.

```bash
python3 scripts/ladder_top.py            # terminal, follows the ledger
python3 scripts/ladder_top.py --once     # render a finished run
LADDER_N=0 PYTHONPATH=. python3 scripts/ladder_run.py --tui
```

```bash
python3 -m http.server 8000              # from the repo root
# then http://localhost:8000/docs/ladder-monitor.html
```

Both draw each rung over **its own denominator**, never the run total, and both
render `could_not_run` as a hatch rather than a colour — it is the absence of a
measurement and must not read as one.

The terminal view adds two panels that have already earned their place. **Watch**
runs live checks derived from this project's own mistakes: a verdict
distribution whose minority class is under 10% (agreement over such a set
measures its composition, not the checker), a rung losing more than a quarter of
its input to could-not-run, rows with no denominator. **Time** gives per-rung
latency distribution, throughput, ETA and drift — and it found on its first
render that rung 4's apparent 6x degradation was a single 134-second model load
followed by partial GPU offload, not degradation at all.

## Provenance — what actually ran

`ladder/provenance.py` gathers a run stamp from live objects rather than from
the manifest's intentions, because the two diverge. It records requested against
resolved model strings, the vocabulary backend and whether it is the lossy one,
sampling temperature, rung order, git SHA and whether the tree was dirty, and
whether the model fits in VRAM.

```bash
PYTHONPATH=. python3 -m ladder.provenance
```

It warns rather than raises. On its first real run it caught that the pipeline
judges with `llama3.2:3b` while the manifest specifies `qwen2.5:7b` — two models
that produced opposite results, and nothing had recorded which one ran.

## The ledger, and what it records that tools do not

One row per record per rung: tokens, calls, latency, outcome — plus two fields
that no LLM observability platform models.

- **`denominator`** — the named set this row's rate is computed over. Rung 4
  judged 96 of 169 offered; rung 5 voted on 3 of 169. A rate over the wrong base
  renders as healthy.
- **`evaluable`** — `pass` · `fail` · **`could_not_run`**. Three values, never a
  boolean. Parse failures, not-re-found mentions and unevaluable checks are none
  of them a pass and none of them a fail.

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
              llm (cached model client) · ledger ·
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
- [x] InfoQ article — the 2026-08-24 first draft is archived as
      [docs/versions/infoq-article-draft-2026-08-24.md](docs/versions/infoq-article-draft-2026-08-24.md);
      the live draft is [docs/article-v3.md](docs/article-v3.md)
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

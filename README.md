<p align="center">
  <img src="docs/figures/fig0-hero.png" width="820"
       alt="Seven ladder rungs rendered as beads, coloured by what each layer bought: two paid for themselves, two cost tokens and changed nothing, three had no measured effect.">
</p>

<h1 align="center">The AI Reliability Ladder</h1>

<p align="center">
  <i>Seven reliability layers around a language model, measured one at a time
  on a task with a real answer key — what each one bought, and what it charged.</i>
</p>

<table align="center">
<tr>
<td align="center"><a href="docs/article-infoq-CADEC.md"><b>the article</b></a></td>
<td align="center"><a href="docs/decisions.md"><b>the decision log</b></a></td>
<td align="center"><a href="#the-three-checks"><b>the three checks</b></a></td>
<td align="center"><a href="runs/archive/matrix-2026-09-07/"><b>the run archive</b></a></td>
</tr>
<tr>
<td align="center"><sub>the InfoQ submission; the long cross-corpus version is <a href="docs/article-v3.md">article-v3</a></sub></td>
<td align="center"><sub>every finding, dated, beside its corrections</sub></td>
<td align="center"><sub>gatecheck · crosscheck · stagecheck</sub></td>
<td align="center"><sub>~50 cells, re-scoreable from this repo</sub></td>
</tr>
</table>

---

Teams stack reliability layers around an LLM by intuition: validate, retry,
vote, judge, abstain, escalate. This repository measures what each layer
actually buys, and what it costs, so you can stop at the rung your economics
justify.

**The task.** Pharmacovigilance triage: read an archived patient report,
identify the adverse reactions the writer describes, and normalise each to a
SNOMED CT code. The system reports *what a document says*. It never asserts
that a drug caused an effect.

> Rungs 0–2 are research artefacts with deliberate failure rates, unfit for
> operational use. There is no free-text entry point in the package: the runner
> takes a corpus split identifier, never a string.

## What it found

| | |
|---|---|
| **measured** | 7 corpora · 5 model families (4B–20B) · ~50 cells · development and held-out splits |
| **the free check** *(0 tokens)* | endorses a small lane that is **76–100%** right on clinical vocabularies, a large one that is **7–26%** right on gazetteers. The bands do not overlap, and reach runs opposite to accuracy |
| **the paid layers** *(~500k tokens)* | self-correction, sampled voting and a second-model judge routed **zero** records on PsyTAR across three draws — coverage identical to the free layers alone |
| **reproducible** | every cell published as scoreable output, scoring identically from this repository alone |

**The one-line version.** Reliability layers do not make a model more accurate.
They tell you which answers to trust — and the layer that does it best costs
nothing, while the three that cost tokens changed almost no answer.

**What surprised us.** The check that reaches furthest is the one to trust
least, and the split is not about medicine: three ontologies behave alike and
three corpora built on one gazetteer behave alike, in opposite directions. What
the clinical vocabularies share is that the term and the writing are drawn from
overlapping registers — *weight gain* is both what a patient writes and what the
ontology calls it; *Britain* against *United Kingdom of Great Britain and
Northern Ireland* is not.

## The ladder

| Rung | Layer | Mechanism | Extra cost | What it bought |
|---|---|---|---|---|
| 0 | bare LLM | retrieve candidates, then pick a line number — two calls, and neither ever sees a code | 2 calls/item | the input to everything above |
| 1 | deterministic | schema · span grounding · negation · code exists · semantic type · lexical match | **none** | the one layer that paid — 80–89% correct in its ACCEPT lane across five model families |
| 2 | self-correction | one bounded retry, fired **only by a rung 1 rejection**, the reason stated as a fact | +1 call | **nothing.** 0 rescued of 158 on CADEC, 0 of 918 on FiNER |
| 3 | voting | k samples, majority on the **normalised code**, never the string | k calls | +5 on the tuning set, **0 out of sample**, for 425,355 tokens |
| 4 | LLM-as-judge | second model, **different family**, scores the record | +1 call | separates 1.23× held out, against the free check's 2.36–6.12× |
| 5 | abstention | decline anything rung 1 could not corroborate | none | errors 62.9 → 4.0 per 100, at 79 reviews per 100 |
| 6 | human-in-the-loop | a person settles it — timed, not simulated | human minutes | the only settling authority, and the cost nothing else prices |

Rung ID equals execution position, `[0, 1, 2, 3, 4, 5, 6]`, read from
`manifest.json` so the order is a testable ablation rather than an assertion.
Rung 1 **judges but does not filter**: its verdict is recorded and every rung
above it sees the full set, and only rung 5 is allowed to spend coverage on
that verdict. The numbering changed on 2026-08-23; decision-log entries before
that date use the old order, mapped in `docs/decisions.md`.

**Cost is three measures, never fused:** tokens per record, latency p95, and
records routed to a person. A single dollar figure needs a price table that
shifts under you and hides the real question — *would you rather spend tokens
or human attention?*

## Quick start

The FiNER-139 arm is CC-BY-SA-4.0 and runs from a clean checkout. CADEC cannot
be redistributed; its arm and the other corpora are in
[docs/RUNNING.md](docs/RUNNING.md).

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt pytest
```

Two checks before any GPU time, a second each, no model calls. On FiNER,
`gatecheck` reports a **0.0%** ceiling for the free check and refuses to
recommend the arm — a full GPU arm's finding, available before booking one.

```bash
PYTHONPATH=. python3 scripts/gatecheck.py  --manifest manifest.finer.json
PYTHONPATH=. python3 scripts/crosscheck.py --manifest manifest.finer.json
```

Fetch the corpus and freeze the splits:

```bash
mkdir -p data/finer && cd data/finer
curl -LO https://huggingface.co/datasets/nlpaueb/finer-139/resolve/main/finer139.zip
unzip -q finer139.zip -d extracted && cd ../..
python -m ladder.run init --manifest manifest.finer.json
```

The free half needs no model and takes seconds:

```bash
PYTHONPATH=. python3 scripts/relations_report.py --manifest manifest.finer.json
```

The model half needs [ollama](https://ollama.com) and ~14 GB of VRAM. Drop
`--limit 3` for the full split — 60 documents, about 25 minutes on a 48 GB
card, hours on a laptop.

```bash
ollama pull gpt-oss:20b && ollama pull ibm/granite4:micro-h
PYTHONPATH=. python3 -m ladder.run --manifest manifest.finer.json ladder \
    --split test --limit 3 --plain
```

## Reproduce the findings

Every published cell scores from this repository alone, with no corpus
download and no GPU:

```bash
PYTHONPATH=. python3 scripts/score_matrix.py --dir runs/archive/matrix-2026-09-07/matrix
```

Five of the findings, from gold and source, with no model calls:

```bash
PYTHONPATH=. python3 scripts/reproduce.py
```

[docs/REPRODUCE.md](docs/REPRODUCE.md) covers all three layers: re-scoring the
tracked run files, re-deriving every report from the raw run at
`runs/archive/consolidated-2026-09-03/`, and re-running the rungs on your own
data. If a number does not reproduce, [open an issue](CONTRIBUTING.md) — that
is the most useful thing anyone can send us.

## The corpora

Chosen to differ in the one respect that decides whether the free check can
work at all: whether the extracted span and the code's own name are drawn from
the same language.

| corpus | domain | vocabulary | licence | lane fires | of that, correct |
|---|---|---|---|---|---|
| **CADEC v2** | patient forum posts | SNOMED CT | non-transferable | 32% | 76–82% |
| **PsyTAR** | patient drug reviews | SNOMED CT | **CC BY 4.0** | 19–31% | **80–90%** |
| **BC5CDR** | biomedical abstracts | MeSH | free mirror | 7–22% | **93–100%** |
| **GeoWebNews** | news geography | GeoNames | GPL-3.0 | 20–64% | 11–26% |
| **LGL** | local news | GeoNames | GPL-3.0 | 30–74% | 10–22% |
| **TR-News** | news geography | GeoNames | GPL-3.0 | 37–72% | 10–17% |
| **LINNAEUS** | research papers | NCBI Taxonomy | CC-BY | 0–13% | 80% *(n=5)* |
| **FiNER-139** | SEC filings | 139 XBRL tags | CC-BY-SA-4.0 | **0.0%** | — |

Ranges are across `gpt-oss:20b`, `llama3.1:8b`, `mistral:7b-instruct`,
`ibm/granite4:micro-h` and `qwen3:8b`, one draw each on the dev split, rungs
0–1. Three draws were measured byte-identical on three corpora, so a single
draw is a measurement rather than a sample. CADEC's row is a reference, not a
row of the same table: it was produced on different hardware.

FiNER's zero is structural: the spans are numerals (`47.6`) and the tags are
English phrases (`EffectiveIncomeTaxRateContinuingOperations`), so the two
share no token by construction. Clinical vocabularies give a small lane that is
right; gazetteers give a large lane that is wrong. Read as ACCEPT's accuracy
over the accuracy of what the check declined to endorse, the clinical corpora
separate **2.0–3.8×** and TR-News **0.6–0.9×** — there the free check is worse
than not checking.

## The three checks

Measuring seven layers on seven corpora produced one lesson that outlived the
measurements: **a load-bearing fact recorded in one place cannot be checked,
and will eventually be wrong without saying so.** Every defect caught early
here was caught by comparing two independent records of one fact. Three small
tools came out of that.

| tool | the question | when | knows about corpora |
|---|---|---|---|
| [`gatecheck`](scripts/gatecheck.py) | should this corpus be run at all? | before booking a card | yes |
| [`crosscheck`](scripts/crosscheck.py) | is it wired as it is declared? | the first line of every run | yes |
| [`stagecheck`](https://github.com/pushpdeep/stagecheck) | did the run mean anything? | after | **no, deliberately** |

`stagecheck` is a separate, installable package — 43 tests, no dependencies,
MIT. It records the two things a pipeline usually does not: **the bet a stage
makes**, and **the records it could not judge**. A stage that judged 40 of 100
records and reports 95% accuracy has reported a rate over an unnamed set.
`gatecheck` and `crosscheck` live in `ladder/checks/` with thin CLI wrappers;
52 tests between them, each written from a defect that reached a rented card
first. Detail: [docs/three-checks.md](docs/three-checks.md).

## Data and licences

No corpus is in this repository, and none can be. `data/splits/*.json` holds
document IDs only, so anyone with their own licensed copy reproduces the exact
splits and nobody obtains a corpus from here.

| source | terms | where |
|---|---|---|
| **CADEC v2** | CSIRO Data Licence — non-commercial, **non-transferable** | [csiro:10948](https://data.csiro.au/collection/csiro:10948); each team member accepts it individually |
| **SNOMED CT** | affiliate licence for full releases | a local RF2 release indexed by `ladder/registry.py`, or [EBI OLS4](https://www.ebi.ac.uk/ols4) at run time — lossy, and never interchangeable with the local index |
| **MedDRA** | subscription (MSSO) | only a 10-row example file is committed, for tests |

Code is MIT ([LICENSE](LICENSE)). Third-party data keeps its own terms; the
full detail is in [docs/licences.md](docs/licences.md). `scripts/preflight.py`
scans the working tree and git history for corpus text and API keys before
every push.

## Repository layout

```
ladder/         run.py (the runner) · schema.py (the record) · corpus_*.py (one adapter
                per corpus) · registry.py (local SNOMED index) · vocab.py (backend
                selection) · llm.py (cached model client, models.yaml) · ledger.py ·
                score.py · trace.py · analysis.py · provenance.py
ladder/rungs/   r0 … r6, one file per rung; r7 is the type-compatibility check arm
ladder/checks/  gate.py and cross.py, behind scripts/gatecheck.py and scripts/crosscheck.py
schemas/        the runner and vocabulary contracts
manifest*.json  one manifest per corpus; every arm is a pinned one-key diff
runs/archive/   the tracked, corpus-free run files every published number comes from
scripts/        preflight · score_matrix · reproduce · the run and re-run protocols
tests/          against stubs — no network, no keys, no corpus
docs/           the articles, the decision log, REPRODUCE, RUNNING, licences
```

## Documentation

| | |
|---|---|
| [docs/article-infoq-CADEC.md](docs/article-infoq-CADEC.md) | the InfoQ submission; [docs/article-v3.md](docs/article-v3.md) is the long two-corpus version |
| [docs/decisions.md](docs/decisions.md) | the durable record — every finding, dated, with its corrections beside it |
| [docs/REPRODUCE.md](docs/REPRODUCE.md) | re-score, re-derive, re-run |
| [docs/RUNNING.md](docs/RUNNING.md) | the CADEC and geo arms, watching a run, provenance, the ledger, the contracts |
| [docs/FINAL-RESULTS.md](docs/FINAL-RESULTS.md) | the matrix, cell by cell |
| [docs/early-results.md](docs/early-results.md) | the superseded 2026-08-20 figures and the build checklist |
| [CHANGELOG.md](CHANGELOG.md) · [CONTRIBUTING.md](CONTRIBUTING.md) | what moved, when · the quickest way in is to break a number |

## Where this lives

| | |
|---|---|
| **GitLab** *(primary)* | [gitlab.com/pushpdeep/ai-reliability-ladder](https://gitlab.com/pushpdeep/ai-reliability-ladder) — CI publishes the [plan and demo](https://ai-reliability-ladder-9baac5.gitlab.io/) from here |
| **GitHub** *(mirror)* | [github.com/wbagais/reliability-ladder](https://github.com/wbagais/reliability-ladder) — the address the article prints |
| **stagecheck** | [github.com/pushpdeep/stagecheck](https://github.com/pushpdeep/stagecheck) — installable on its own |

The two ladder remotes are the same repository. If they have diverged, the
GitLab one is ahead.

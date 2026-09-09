# Running the ladder — setup, arms, and what a run records

*Moved out of the README on 2026-09-09. The README keeps the FiNER quick start;
everything else an operator needs is here. For re-scoring and re-deriving the
article's numbers see [REPRODUCE.md](REPRODUCE.md).*

## Contents

- [Install](#install)
- [Which model runs](#which-model-runs)
- [The CADEC arm — five preprocessing steps](#the-cadec-arm--five-preprocessing-steps)
- [The FiNER arm](#the-finer-arm)
- [The GeoWebNews arm](#the-geowebnews-arm)
- [Watching a run](#watching-a-run)
- [Provenance — what actually ran](#provenance--what-actually-ran)
- [The ledger](#the-ledger)
- [The three contracts](#the-three-contracts)
- [Two vocabulary backends, and they are not equivalent](#two-vocabulary-backends-and-they-are-not-equivalent)
- [Before you push](#before-you-push)

## Install

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt pytest
```

CI is `python:3.12-slim` with `requirements.txt` and pytest and nothing else —
no numpy, no httpx, no torch, no `git` binary. Run the suite the way CI does
before pushing:

```bash
python -m venv /tmp/civenv
/tmp/civenv/bin/pip install -r requirements.txt pytest
/tmp/civenv/bin/python -m pytest tests/ -q -m "not integration"
```

## Which model runs

**The model is named in `manifest.json` and nowhere else.** `ladder/llm.py`
carries no default and raises if the manifest names none, so a run always
knows which model produced its numbers. Override for a single run with
`--extractor` or `LADDER_MODEL_SPEC`; both are written into the manifest copy
saved beside the results. Per-model request settings — `max_tokens`,
`sampling`, `reasoning_effort`, `timeout_s` — live in `ladder/models.yaml`,
because a rung must never know which family it is calling.

Models are local by default. Rung prompts carry corpus text verbatim, so any
provider marked `local: false` in `models.yaml` is refused without
`LADDER_ALLOW_REMOTE=1`.

The extractor is `ollama/gpt-oss:20b` and the judge `ibm/granite4:micro-h`,
bound by role from `manifest.model` so that rung 4 is always a different
family from rung 0.

```bash
ollama pull gpt-oss:20b && ollama pull ibm/granite4:micro-h
```

## The CADEC arm — five preprocessing steps

CADEC and SNOMED CT are licensed to you individually (see
[licences.md](licences.md)); nothing here downloads them. Five steps, in
order. Each produces gitignored, licence-bound data; a fresh clone runs all of
them before any rung.

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
python -m ladder.embed --build
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
reason. `embed --build` writes the dense keyword index S2 retrieves from — a
few minutes and a local embedding model. `init` verifies the corpus parses,
runs the critical-path gate (a real code resolves, a fake one does not) and
writes the frozen splits.

An index built before 2026-08-24 has no association table. Add it in place,
in seconds, rather than rebuilding:

```bash
python -m ladder.registry --associations --release data/SnomedCT_Release_<yours>
```

Do not `--build --force` where the index is reached through a symlink: the
rebuild replaces the symlink with a private copy and forks the checkouts.

Then the fixture gate — a dozen hand-made records, several deliberately
broken — and a gold control run:

```bash
python -m ladder.run gate
```

```bash
python -m ladder.run ladder --split test --source gold --run-id gold_control
```

A full ladder run on the dev split takes hours, not minutes: the extractor is
a reasoning model and the cost is reported rather than avoided.

## The FiNER arm

FiNER-139 is CC-BY-SA-4.0 and reproducible from a clean checkout. Two checks
first, a second each, no model calls:

```bash
PYTHONPATH=. python3 scripts/gatecheck.py  --manifest manifest.finer.json
PYTHONPATH=. python3 scripts/crosscheck.py --manifest manifest.finer.json
```

`gatecheck` predicts the free check's ceiling from gold alone. On FiNER it
reports **0.0%** and refuses to recommend the arm — the spans are numerals and
the tags are English phrases, so the check cannot fire however good the model
is. `crosscheck` reads every declared fact back from an independent source:
the rendered prompt against the declared entity, the few-shot ids against the
pool split the guard actually reads, the split ids against the corpus the
adapter loads, and each named model against what ollama has.

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
PYTHONPATH=. python3 -m ladder.run --manifest manifest.finer.json ladder \
    --split test --limit 3 --plain
```

Drop `--limit 3` for the full split — 60 documents, roughly 25 minutes on a
48 GB card, several hours on a laptop.

## The GeoWebNews arm

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
absolute score from the geo arm is comparable with CADEC's.

The other corpora (PsyTAR, BC5CDR, LGL, TR-News, LINNAEUS) each have a
`manifest.<corpus>.json` and a `ladder/corpus_<name>.py` adapter; the index
builders are `scripts/build_mesh_index.py` and `scripts/build_taxon_index.py`.

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

The terminal view adds two panels. **Watch** runs live checks derived from
this project's own mistakes: a verdict distribution whose minority class is
under 10% (agreement over such a set measures its composition, not the
checker), a rung losing more than a quarter of its input to could-not-run,
rows with no denominator. **Time** gives per-rung latency distribution,
throughput, ETA and drift — and it found on its first render that rung 4's
apparent 6x degradation was a single 134-second model load followed by partial
GPU offload, not degradation at all.

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
judged with `llama3.2:3b` while the manifest specified `qwen2.5:7b` — two
models that produced opposite results, and nothing had recorded which one ran.

Every run also writes per-rung artifacts beside the ledger (`ladder/trace.py`):
the record set as each rung left it, one state row per record per rung, every
model call with its full prompt and reply, and an aggregates file carrying the
cache directory, git SHA and models. The call traces carry corpus text and
live under the gitignored `out/` only.

## The ledger

One row per record per rung: tokens, calls, latency, outcome — plus two fields
that no LLM observability platform models.

- **`denominator`** — the named set this row's rate is computed over. Rung 4
  judged 96 of 169 offered; rung 5 voted on 3 of 169. A rate over the wrong base
  renders as healthy.
- **`evaluable`** — `pass` · `fail` · **`could_not_run`**. Three values, never a
  boolean. Parse failures, not-re-found mentions and unevaluable checks are none
  of them a pass and none of them a fail.

The ledger also carries a `usd` column, computed per call from
`ladder/models.yaml`. It is never fused into the three cost measures and no
headline is reported in it — it exists so a hosted run's bill is recoverable
from the results rather than reconstructed afterwards.

## The three contracts

See `schemas/`.

1. **`schemas/runner.py`** — `apply(records, sources, cfg) -> records`. Every
   rung implements it, which makes execution order a config value and a new
   rung twenty minutes' work.
2. **`schemas/vocabulary.py`** — the global vocabulary resource, injected once
   per run rather than per item. Two backends, and every backend declares
   whether it is `lossy`.
3. **`ladder/schema.py`** — the record: one **mention**, not one document and
   not a drug↔reaction pair. Append-only; never reorder.

## Two vocabulary backends, and they are not equivalent

`ladder/vocab.py` selects one and records it in the manifest:

| backend | source | `lossy` |
|---|---|---|
| `local-rf2` | a SNOMED RF2 release indexed to SQLite | **False** — sees retired concepts and extension modules |
| `ols4` | EBI OLS4 over the network | **True** — active international SNOMED only |

An OLS4-backed `exists()` reports **23.9%** of CADEC gold as codes that do not
exist: 7.5% retired, 16.4% AU-extension — which is **100% of drug mentions**,
because CADEC codes drugs to AMT. A rung 1 rejection rate is not comparable
across backends, and is never reported without naming the backend. `ols4`
serves rung 1 only; `run.py` refuses it for a full run, because rung 0's
retriever has no OLS4 implementation.

```bash
python -m ladder.vocab_crosscheck --live 40
```

## Before you push

Scans the working tree **and git history** for corpus text, API keys and
forbidden paths. CI runs it too and blocks the pipeline; catching it locally is
cheaper.

```bash
python scripts/preflight.py --history
```

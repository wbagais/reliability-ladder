# The Reliability Ladder

Measure the **quality + determinism + cost** of each reliability layer wrapped
around an LLM — on *your* task, with *your* data — so you can pick the rung
worth stopping at for your economics instead of stacking layers by intuition.

The pipeline is **data-agnostic**: any task with a structured, checkable output
plugs in as one JSON file (nested schemas included). SROIE receipts are just the
bundled demo dataset. With a local model, your data never leaves your machine.

**Two tracks.** [`bench/`](#the-app) is the data-agnostic ladder above.
[`ladder/`](docs/cadec-track.md) is a second instance of the same seven rungs on
CADEC patient adverse-event reports, where rung 1 is grounded in SNOMED CT rather
than in a JSON Schema — which is what makes it possible to measure what a *real*
validation gate catches, and what it cannot. Jump to
[the CADEC track](#the-cadec-track-ladder).

📄 **[Plan, architecture and interactive demo](https://pushpdeep.gitlab.io/ai-reliability-ladder/)**
— `docs/plan.html`, published by CI on every push to `main`.

## The ladder

| Rung | Layer | Mechanism | Extra cost |
|------|-------|-----------|-----------|
| 0 | bare LLM | one call with your prompt, output as-is | 1 call/item |
| 1 | deterministic checks | schema-driven normalization (ISO dates, plain decimals) + mechanical verdicts vs the trusted record | none |
| 2 | abstention | blank any field below the confidence threshold or failing a format check | none |
| 3 | self-correction | model reviews its own draft against the document and revises | +1 call |
| 4 | LLM-as-judge | separate grading prompt passes/fails each field; failures are blanked, never rewritten | +1 call |
| 5 | voting | 5 fixed prompt *variants* at temp 0; per-field majority wins, agreement becomes confidence | 5 calls instead of 1 |
| 6 | human-in-the-loop | escalated fields answered by a person — simulated (gold + fixed minutes) or live review queue in the app | human minutes |

Run **cumulative** (each rung includes everything below it — the main curve) and
as **single-rung ablations** (each layer alone on the bare model — feeds the
composer). Temperature is locked to 0 for every call; rung 5 gets its diversity
from prompt framing, not sampling (see `docs/decisions.md`).

## Architecture

```
your data (one JSON: prompt + output_schema + items[doc, gold, trusted_record?])
   ↓  [adapter contract — schemas/adapter.py]
bench (rungs 0–6 via Runner contract; K runs/item; cached LLM calls)
   ↓  [results.json contract — schemas/results.schema.json]
app (dashboard: rung-by-rung story + curve + your economics → recommended rung)
```

## Quick start

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
# local-only extras (the hosted build must not be able to call a model):
.venv/bin/pip install openai pytest

# before every push — scans the tree AND git history for corpus text and keys
.venv/bin/python scripts/preflight.py --history

# the app: upload/validate data, run the bench, explore the dashboard
.venv/bin/streamlit run app/streamlit_app.py

# or from the CLI —
# 1. check any data file (see docs/data-format.md + data/example_upload.json)
.venv/bin/python -m bench.cli validate data/sroie_v1.json

# 2. run the ladder (all 7 rungs + ablations)
.venv/bin/python -m bench.cli run --data data/sroie_v1.json \
    --model "ollama/ibm/granite4:micro-h" --smoke    # 10 items, K=3 sanity pass
.venv/bin/python -m bench.cli run --data data/sroie_v1.json \
    --model "ollama/ibm/granite4:micro-h" --k 10     # the real curve

# apply a calibrated abstention gate (find yours in the app's Calibration tab)
.venv/bin/python -m bench.cli run --data data/sroie_v1.json \
    --model "ollama/ibm/granite4:micro-h" --k 10 --conf-threshold 0.90

# hosted APIs are registry entries in bench/models.yaml, e.g.:
#   GEMINI_API_KEY=... --model gemini/gemini-2.5-flash

# rebuild the SROIE demo dataset (only if you have data/SROIE2019 raw files)
.venv/bin/python -m bench.adapters.sroie --raw data/SROIE2019 --out data/sroie_v1.json

# tests (fake LLM, no network)
.venv/bin/python -m pytest tests/
```

Every LLM call is disk-cached (`.llm_cache/`), keyed by
(model, messages, temperature, sample index): re-runs are free, interrupted runs
resume, and rungs 1–2 reuse rung 0's calls with zero extra traffic.

## Bring your own data

One JSON file: a `prompt` (or `prompt_file` for long ones), an `output_schema`
(any JSON Schema — nesting, arrays, and file `$ref`s supported), and ~50–100
`items`, each pairing an input `doc` with its `gold` answer object. Add a
`trusted_record` per item for verification tasks; omit it for pure extraction.
Full guide: [docs/data-format.md](docs/data-format.md) · working example:
[data/example_upload.json](data/example_upload.json) · the validator
(`bench.cli validate`, or the app's upload step) explains every problem in
plain language.

Privacy: local (Ollama) models keep documents on your machine; benchmark
outputs, caches, and `data/private*` are gitignored.

## The app

- **Setup & Run** — data-format panel with a downloadable template, upload +
  validation + preview, prompt editing, model picker (local Ollama or hosted
  API with key), quick/full run sizes, live progress, and an optional rung-6
  review queue where *you* are the human and your review time is measured.
- **Dashboard** — reads any `results.json` (`app/results.stub.json` before a
  real run exists):
  - **🪜 Rung by rung** — the explainability view: each rung's mechanism, its
    before→after scores, what it actually changed (fixed / screened / broke /
    withdrew, with concrete examples), rung internals (confidence calibration,
    judge precision/recall, per-variant voting scores, escalation causes), its
    ablation score, and a plain-language verdict.
  - **🔍 Outputs** — every field's value and status (✅ correct / ❌ wrong /
    — no answer) at every rung, side by side, so you can follow one field's
    fate through the ladder. Reads the `*.outputs.jsonl` sidecar written
    alongside results.json (disable with `--no-outputs` for very large runs).
  - **The curve** — yield, accuracy, coverage and determinism per rung with
    bootstrap CIs and the best-yield marker; the cost frontier.
  - **Economics** — sliders for value/cost of correct, wrong, abstain, and
    human minutes → net utility per rung → **recommended rung** (try the
    cheap-errors vs expensive-errors presets to see the flip).
  - **🎚️ Calibration** — where should the abstention gate sit *for your model*?
    Sweeps the threshold over a finished run (no new model calls) and reports
    the highest-yield gate and the **free-lunch gate**: the strictest threshold
    that screens errors without discarding a single correct answer. Prints the
    command to apply it.
  - **Composer** — toggle layers, estimate a custom stack from ablation deltas.
  - **Method** — exactly how every score is computed.
  - **Table** — the raw numbers + results.json export.

Every run is saved to `results/<domain>_<n>x<k>_<timestamp>.json` (plus its
outputs sidecar), so runs never overwrite each other and the sidebar lists them
all for comparison.

## The 4 contracts (see /schemas; revisions logged in docs/decisions.md)

1. **runner.py** — every rung's signature. Two shapes: `Runner` (field-level,
   one document in) for the `bench/` track, `Rung` (`apply(records, sources,
   cfg)`, per v17 §4) for the CADEC ladder. Rungs are interchangeable within a
   track, which is what makes execution order a config value.
2. **results.schema.json** — the benchmark→app handoff; every emitted
   results.json is validated against it.
3. **adapter.py** — how any dataset (including user uploads) plugs in; v2 adds
   nested `output_schema`, gold as a full object, and optional trusted_record.
4. **vocabulary.py** — the global vocabulary resource (SNOMED, MedDRA),
   injected once per run rather than per item. Two backends implement it and
   they are **not** equivalent: an OLS4-backed `exists()` reports 23.9% of CADEC
   gold as nonexistent codes. Every backend declares whether it is `lossy`, and
   a rejection rate is not comparable across them.

## Scores (details in the app's Method tab)

- **Yield — the headline** — `accuracy_on_answered x coverage`: the share of
  **all** field slots that came out correct. Read this one first.
- **Accuracy on answered + coverage** — vs gold after schema-aware
  normalization (numbers numerically, dates parsed, text case-insensitive), so
  formatting never counts as wrong; abstentions lower coverage, not accuracy.
- **Determinism** — each item runs K times (default 10); per field, the share of
  runs matching the modal value; averaged over fields, then items.
- **Cost** — tokens, dollars (prices in `bench/models.yaml`; local = $0),
  latency, human minutes — per single pass (the K repeats are the instrument,
  not the bill).

> **Why yield leads.** Accuracy is a ratio over *answered* fields, so any layer
> that withholds answers raises it mechanically. In the reference run the judge
> rung lifted accuracy 0.938 → 0.960 while yield **fell** 0.938 → 0.772: it
> deleted far more correct answers than errors, and left the user with fewer
> correct fields. The app now warns whenever accuracy rises while yield falls.
> Whether that trade is still worth it is an economics question — priced in the
> Economics tab, not decided by the curve.

## Repo map

```
ladder/       CADEC track — schema (the A/B contract), corpus reader + frozen
              splits, SNOMED registry, ledger, negation, rungs/r1 + r2, run.py,
              fixture (the step-3 gate), calibrate (false-rejection floor),
              probe (detection profile)
bench/        client+cache, normalize, flatten, prompts, rungs pipeline,
              metrics, diagnostics, harness, cli, adapters (user upload + SROIE),
              outputs.py (per-field sidecar), calibration.py (risk–coverage)
app/          streamlit_app.py + review.py + results.stub.json
schemas/      the 3 contracts
data/         sroie_v1.json (demo) + example_upload.json (template)
results/      saved runs, one file per run (gitignored)
docs/         data-format.md · decisions.md (running log — article raw material)
              cadec-track.md · licences.md · article-iterations.md
manifest.json the CADEC run's frozen settings — corpus + vocabulary versions,
              seed, splits, gold rule, rung order, every rung parameter
tests/        55 tests against a fake LLM, no network needed
```

## Reference run (SROIE, 60 items, K=10, ollama/ibm/granite4:micro-h)

| Rung | yield | accuracy (answered) | coverage |
|------|-------|--------------------|----------|
| 0 bare LLM | **0.938** | 0.938 | 1.000 |
| 1 deterministic | 0.938 | 0.938 | 1.000 |
| 2 abstention | 0.932 | 0.940 | 0.992 |
| 3 self-correction | 0.934 | 0.938 | 0.996 |
| 4 LLM-as-judge | **0.772** | 0.960 | 0.804 |
| 5 voting | 0.772 | 0.960 | 0.804 |
| 6 human-in-the-loop | **0.988** | 0.988 | 1.000 (+1.4 human-min/item) |

Only the human rung beats the bare model on yield. Determinism was 1.000 at
every rung — local greedy decoding at temperature 0 is exactly reproducible, so
that axis only becomes interesting on hosted APIs.

Three more results from mining that run (all replayed from cache, no new calls;
detail in [docs/decisions.md](docs/decisions.md)):

- **Errors concentrate in one field** — of 150 wrong slots: address 100,
  total 40, date 10, company 0. Fixing one field's prompt would beat adding a
  layer.
- **The stack is worse than its best layer** — voting *alone* yields 0.946,
  better than bare (0.938) and better than any cumulative rung except the human
  one; inside the stack it drops to 0.772 because it inherits the judge's
  damage. Cumulative stacking is the wrong default; compose deliberately.
- **Calibrating the gate to 0.90** cuts the error rate among shipped answers
  from 0.060 to 0.043 for a 1.7pt coverage cost — it ships fewer wrong answers,
  it does not produce more correct ones (yield 0.9325 → 0.9330).

## Data — read before you clone

No corpus is in this repository, and none can be.

| Source | Terms | Where it lives |
|---|---|---|
| **CADEC v3** | CSIRO Data Licence — non-commercial, **non-transferable**, no redistribution | [csiro:10948](https://data.csiro.au/collection/csiro:10948). Each team member accepts it individually; `data/cadec/` and the download directory are gitignored. |
| **SNOMED CT** | affiliate licence for full releases | either a local RF2 release indexed by `ladder/registry.py`, or [EBI OLS4](https://www.ebi.ac.uk/ols4) at run time via `bench/vocab.py` — free, no key |
| **MedDRA** | subscription (MSSO) | only `data/meddra_codes.example.csv` (10 rows, for tests) is committed. See [docs/licences.md](docs/licences.md) for why the 666-row list that ships inside CADEC is not a usable substitute |
| SROIE | redistributable | `data/sroie_v1.json`, committed |

`scripts/preflight.py` scans the working tree **and git history** for corpus
text, API keys and forbidden paths, and exits 1 on a breach. CI runs it on every
merge request and blocks the pipeline — deleting a file later does not remove it
from history. Full detail: [docs/licences.md](docs/licences.md).

## The CADEC track (`ladder/`)

The same seven rungs on a fixed archived corpus of patient-reported adverse-event
posts, normalising each mention to a SNOMED CT code. Rung 1 stops being a format
check and becomes a real validation gate: span grounding, negation, code
existence, and semantic type against a local SNOMED release. Full guide:
[docs/cadec-track.md](docs/cadec-track.md) · licences (these have teeth):
[docs/licences.md](docs/licences.md).

```bash
python -m ladder.registry --build --release data/SnomedCT_Release_<yours>
python -m ladder.run init          # verify corpus + vocabulary, write frozen splits
python -m ladder.run gate          # ten hand-made records, several deliberately broken
python -m ladder.calibrate --split all --sweep   # the gate's false-rejection floor
python -m ladder.probe --split all               # what the gate can and cannot catch
```

Owner A's half (everything deterministic — ledger, registry, corpus, zones,
abstention, integration) is built and measured. The model-facing rungs 0/3/4/5
and the shared scorer are owner B's; `run.py` reports a missing rung rather than
faking it.

**Measured so far, with zero model calls** (whole corpus, 9,111 gold mentions,
SNOMED AU1000036_20260731):

| | |
|---|---|
| rung 1's false-rejection rate on the gold standard | **0.13%** — down from 9.3% for the gate as originally specified |
| zone occupancy on gold | ACCEPT 43.1% · BAND 56.8% · REJECT 0.13% |
| detection: hallucinated code · span shift · fabricated quote | 1.000 · 1.000 · 1.000 |
| detection: real code in the wrong branch | 1.000 on reaction records |
| detection: near-miss code (right head word, wrong concept) | 0.001 — and with lenient lexical matching, **19% of them are actively ACCEPTED** |

Read together: deterministic checks are *exact* on their own error classes and
blind to the interesting one, and a validation gate's leniency setting decides
whether it declines to have an opinion or endorses one near-miss in five.

**Rung 1 judges, it does not filter.** `manifest.rungs.1.mode` defaults to
`"observe"`: the verdict is recorded, counted and reported, and the record's
zone is untouched, so rungs 3–6 see the full unfiltered set and each rung stays a
single-rung ablation on identical input. Rung 2, which runs last, is where a
rung 1 verdict is allowed to cost coverage. `"gate"` reproduces the plan's flow.

**MedDRA is recorded, not scored.** The only table available is the code list
CADEC ships with the corpus — 666 codes, every one of which appears in the gold
annotations and none of which do not. As an existence check it scores **1.000**
against hallucinated codes by construction and means nothing, so `meddra_check`
defaults to `"flag"`. Point `vocabulary.meddra_csv` at a subscription release and
`"reject"` becomes honest.

The
build log, including every place the plan and the data disagreed, is in
[docs/decisions.md](docs/decisions.md) and
[docs/article-iterations.md](docs/article-iterations.md).

> Rungs 0–2 are research artefacts with deliberate failure rates, unfit for
> operational use. There is no free-text entry point in the package: the runner
> takes a corpus split identifier, never a string.

## Deliverables

- [x] Benchmark + measured ladder (SROIE, full 60-item K=10 run — table above)
- [x] Configurator app (pick your rung / compose your stack / bring your own data)
- [ ] Cross-model comparison (local vs Gemini: determinism under API batching)
- [ ] Private-dataset run (nested extraction schema)
- [x] CADEC track: corpus, vocabulary index, rung 1 + rung 2, harness, and the
      two model-free characterisations of the gate (owner A)
- [ ] CADEC track: rungs 0/3/4/5 + the shared scorer (owner B)
- [ ] InfoQ article (practitioner decision guide — beats and numbers in
      docs/article-iterations.md, earlier outline in docs/article-outline.md)

## Hosting

Three planes, and the separation is what makes this safe to publish (plan §1):

- **Data plane — your machine only.** Corpus text, model calls, caches. Never leaves.
- **Results plane — git.** `results.json`, `manifest.json`, `docs/decisions.md`. Derived numbers, no document text.
- **Presentation plane — public.** Reads the results plane and nothing else.

**GitLab Pages** serves `docs/plan.html` as a static page — no Python, no corpus,
no key. It is *structurally* incapable of leaking anything rather than merely
configured not to. Streamlit Community Cloud is GitHub-only, so the interactive
dashboard runs locally; gate the local-only tabs behind `LADDER_HOSTED=1` if it
is ever deployed.

## Licence

Code: MIT (see [LICENSE](LICENSE)). Third-party data keeps its own terms — CADEC,
SNOMED CT and MedDRA are each named explicitly in the licence carve-out and in
[docs/licences.md](docs/licences.md).

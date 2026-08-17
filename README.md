# The Reliability Ladder

Measure the **determinism + accuracy + cost** of each reliability layer wrapped
around an LLM — on *your* task, with *your* data — so you can pick the rung
worth stopping at for your economics instead of stacking layers by intuition.

The pipeline is **data-agnostic**: any task with a structured, checkable output
plugs in as one JSON file (nested schemas included). SROIE receipts are just the
bundled demo dataset. With a local model, your data never leaves your machine.

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
python3 -m venv .venv && .venv/bin/pip install openai streamlit plotly jsonschema pytest pyyaml

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
  - **The curve** — determinism + accuracy per rung with bootstrap CIs and the
    knee annotation; the cost frontier.
  - **Economics** — sliders for value/cost of correct, wrong, abstain, and
    human minutes → net utility per rung → **recommended rung** (try the
    cheap-errors vs expensive-errors presets to see the flip).
  - **Composer** — toggle layers, estimate a custom stack from ablation deltas.
  - **Method** — exactly how every score is computed.
  - **Table** — the raw numbers + results.json export.

## The 3 contracts (see /schemas; v2 revision logged in docs/decisions.md)

1. **runner.py** — every rung's input/output signature. Rungs are interchangeable.
2. **results.schema.json** — the benchmark→app handoff; every emitted
   results.json is validated against it.
3. **adapter.py** — how any dataset (including user uploads) plugs in; v2 adds
   nested `output_schema`, gold as a full object, and optional trusted_record.

## Scores (details in the app's Method tab)

- **Determinism** — each item runs K times (default 10); per field, the share of
  runs matching the modal value; averaged over fields, then items.
- **Accuracy on answered + coverage** — vs gold after schema-aware
  normalization (numbers numerically, dates parsed, text case-insensitive), so
  formatting never counts as wrong; abstentions lower coverage, not accuracy.
- **Cost** — tokens, dollars (prices in `bench/models.yaml`; local = $0),
  latency, human minutes — per single pass (the K repeats are the instrument,
  not the bill).

## Repo map

```
bench/        client+cache, normalize, flatten, prompts, rungs pipeline,
              metrics, diagnostics, harness, cli, adapters (user upload + SROIE)
app/          streamlit_app.py + results.stub.json
schemas/      the 3 contracts
data/         sroie_v1.json (demo) + example_upload.json (template)
docs/         data-format.md · decisions.md (running log — article raw material)
tests/        37 tests against a fake LLM, no network needed
```

## Deliverables

- [x] Benchmark + measured ladder (SROIE demo; smoke run findings in decisions.md)
- [x] Configurator app (pick your rung / compose your stack / bring your own data)
- [ ] Full 60-item K=10 run → the publishable curve
- [ ] Cross-model comparison (local vs Gemini: determinism under API batching)
- [ ] InfoQ article (practitioner decision guide — outline in docs/article-outline.md)

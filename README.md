# The Reliability Ladder

Measure the **quality + determinism + cost** of each reliability layer wrapped
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

## The 3 contracts (see /schemas; v2 revision logged in docs/decisions.md)

1. **runner.py** — every rung's input/output signature. Rungs are interchangeable.
2. **results.schema.json** — the benchmark→app handoff; every emitted
   results.json is validated against it.
3. **adapter.py** — how any dataset (including user uploads) plugs in; v2 adds
   nested `output_schema`, gold as a full object, and optional trusted_record.

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
bench/        client+cache, normalize, flatten, prompts, rungs pipeline,
              metrics, diagnostics, harness, cli, adapters (user upload + SROIE),
              outputs.py (per-field sidecar), calibration.py (risk–coverage)
app/          streamlit_app.py + review.py + results.stub.json
schemas/      the 3 contracts
data/         sroie_v1.json (demo) + example_upload.json (template)
results/      saved runs, one file per run (gitignored)
docs/         data-format.md · decisions.md (running log — article raw material)
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

## Deliverables

- [x] Benchmark + measured ladder (SROIE, full 60-item K=10 run — table above)
- [x] Configurator app (pick your rung / compose your stack / bring your own data)
- [ ] Cross-model comparison (local vs Gemini: determinism under API batching)
- [ ] Private-dataset run (nested extraction schema)
- [ ] InfoQ article (practitioner decision guide — outline in docs/article-outline.md)

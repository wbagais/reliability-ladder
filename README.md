# The Reliability Ladder

Measure determinism + accuracy + cost of each reliability layer wrapped around
an LLM — so a user can pick the rung worth stopping at. Then let a user pick the rung worth stopping at for *their* economics.

## The ladder

| Rung | Layer | Owner |
|------|-------|-------|
| 0 | bare LLM | A |
| 1 | deterministic checks | A |
| 2 | abstention | A |
| 3 | self-correction | B |
| 4 | LLM-as-judge | B |
| 5 | voting | B |
| 6 | human-in-the-loop | B |

## Architecture

```
data (docs + trusted-source table + gold)
   ↓  [adapter contract]
bench (runs each rung via Runner contract, logs cost + quality)
   ↓  [results.json contract]
app (loads results.json + user economics → recommended rung + composer)
```

## Quick start

```bash
python3 -m venv .venv && .venv/bin/pip install openai streamlit plotly jsonschema pytest pyyaml

# 1. build the SROIE dataset (one-time; needs data/SROIE2019 downloaded)
.venv/bin/python -m bench.adapters.sroie --raw data/SROIE2019 --out data/sroie_v1.json

# 2. check any data file (yours too — see docs/data-format.md)
.venv/bin/python -m bench.cli validate data/sroie_v1.json

# 3. run the ladder (local model, all 7 rungs + ablations)
.venv/bin/python -m bench.cli run --data data/sroie_v1.json \
    --model ollama/gpt-oss:20b --smoke          # 10 items, K=3 sanity pass
.venv/bin/python -m bench.cli run --data data/sroie_v1.json \
    --model ollama/gpt-oss:20b --k 10           # the real curve

# hosted APIs are registry entries in bench/models.yaml, e.g.:
#   GEMINI_API_KEY=... --model gemini/gemini-2.5-flash

# 4. the app (setup form + dashboard; also runs the bench itself)
.venv/bin/streamlit run app/streamlit_app.py
```

Every LLM call is disk-cached (`.llm_cache/`): re-runs are free and interrupted
runs resume. Temperature is locked to 0 everywhere (see docs/decisions.md).
Bring your own data: `docs/data-format.md` + `data/example_upload.json`.

## The 3 contracts (frozen — see /schemas; v2 revision logged in docs/decisions.md)

1. **runner.py** — every rung's input/output signature. Rungs are interchangeable.
2. **results.schema.json** — the benchmark→app handoff. A writes it, B reads it.
3. **adapter.py** — how any dataset (incl. user uploads) plugs in.

`app/results.stub.json` has fake numbers so the app can be built before real
data exists. Swap for real `results.json` at integration.

## Deliverables

- Benchmark + measured ladder across domain(s)
- Configurator app (pick your rung / compose your stack / bring your own data)
- InfoQ article (practitioner decision guide)

## Todo — Person A (data & benchmark)

- [ ] Lock dataset + model/temp (with B)
- [ ] Finalize 3 contracts (with B)
- [ ] Ship stub results.json — done in repo, refine as needed
- [ ] Trusted-source table + conflict injection (~25%)
- [ ] gold schema + annotation guide
- [ ] Eval harness + cost model → results.json
- [ ] Rungs 0–2
- [ ] Article §3 (method) + §4 (numbers)

## Todo — Person B (app & analysis)

- [ ] Lock dataset + model/temp (with A)
- [ ] Finalize 3 contracts (with A)
- [ ] App skeleton against results.stub.json
- [ ] Rungs 3–6
- [ ] Analysis: risk–coverage, Pareto, net-utility
- [ ] Configurator + user-upload flow
- [ ] Article: outline wk1, §5 + §7, submit

## Shared

- [ ] Keep `docs/decisions.md` running from day 1 (article raw material)

## Open scope decision

v1 single-domain (shippable) vs multi-domain (more useful). Decide before building.

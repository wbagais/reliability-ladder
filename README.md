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

## The 3 contracts (freeze Week 1 — see /schemas)

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

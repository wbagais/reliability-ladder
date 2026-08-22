# Testing & CI

## The suite

```bash
python -m pytest -q
```

- **93 tests**, ~1.5 s. No network, fake LLM.
- Files: `test_ladder_schema.py` · `test_ladder_corpus.py` · `test_ladder_ledger_negation.py` · `test_ladder_rungs.py` · `test_vocabulary_contract.py`

## The fixture gate

```bash
python -m ladder.run gate
```

- 13 hand-made records through ledger, registry and [[r1]], several deliberately broken.
- Uses one real archived post so the span offsets are real. The post itself is **not** reproduced in the file.
- **The point is not coverage** — `tests/` does coverage. The point is that both owners watch the same records go through the harness and agree a broken record comes out rejected with the **right reason**, before anybody writes a rung.
- A ledger that is wrong poisons every number above it, and by the time you notice, every rung has to be re-run.

Must end `GATE PASSED`. What it asserts:

- four rejections with exact reasons: `span_ungrounded` · `code_unknown` · `wrong_semantic_type` · `span_out_of_range`
- a drug product code is **not** rejected for not being a clinical finding
- a negated mention is **flagged, not rejected**
- a retired code (`30989003` Knee pain) **survives**
- `CONCEPT_LESS` is a positive answer, not an error and not an abstention
- an unknown MedDRA code is flagged, not rejected
- in observe mode, **every record is still in `NEW`**
- after [[r2]], no abstained record still ships an answer, and each preserved its `withheld`
- the ledger has exactly `2 × len(CASES)` rows

## Preflight

```bash
python scripts/preflight.py --history
```

- Scans tracked files **and all history** for corpus text, key-shaped strings, forbidden paths and unpinned deps.
- Real scan: 41 commits, 94 distinct paths. Must exit 0.
- See [[data-licences]].

## CI

`.gitlab-ci.yml` — runs on every MR and blocks the pipeline.

- preflight + licence scan
- the test suite
- a vocabulary smoke test
- `pages`, on default branch only, publishing `docs/plan.html`

## Before trusting a new rung-1 check

- Replay it over the gold standard first — every rejection there is false by construction.
- `python -m ladder.calibrate --sweep` prices it; `python -m ladder.probe` measures what it catches.
- See [[measurement]] and [[contributing]].

## Related

- [[contributing]] · [[measurement]] · [[data-licences]]

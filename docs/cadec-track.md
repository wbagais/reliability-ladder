# The CADEC track (`ladder/`) — what is built, how to run it, what is next

The v16 plan retargets the ladder from SROIE receipts to pharmacovigilance
triage on CADEC. The two tracks coexist and answer different questions:

| | `bench/` (shipped) | `ladder/` (this) |
|---|---|---|
| task | any structured extraction; SROIE is the demo | one task: CADEC mention normalisation |
| rung 1 | schema-driven normalisation + verdicts | **vocabulary-grounded**: span, negation, SNOMED existence, semantic type |
| gold | a value per field | a SNOMED code per mention, or `CONCEPT_LESS` |
| unit | one field slot | one mention record |
| what it shows | which layers pay on your own data | what a *real* validation gate catches, and what it cannot |

Nothing in `bench/` was changed.

## Safety, by construction rather than by disclaimer

This ships deliberately unreliable pipelines — rungs 0-2 are supposed to fail —
in a drug-safety shape. Five design constraints, not warnings:

1. **No free-text entry point anywhere.** `run.py` takes a split identifier and
   reads documents out of the licensed corpus by ID. There is no box to type
   into, so nobody can point it at their own medication list.
2. **A record without a grounded span is invalid** — enforced in
   `Record.valid()`, so an output that is not a citation into a specific
   archived post cannot exist. It doubles as rung 1's cheapest check.
3. **No causal link is ever asserted.** Drug and reaction mentions are extracted
   independently and the record shape cannot express "drug X caused Y". This is
   also why CADEC's `ADR` label is collapsed into `reaction`: "ADR" *is* a causal
   attribution, and asking a model to reproduce it would be asking for the claim
   the constraint forbids.
4. **Aggregation is out of scope.** Counting reaction frequency across reports
   is what turns annotation into a safety signal. Not built, and named as a
   boundary.
5. **Abstention escalates, never discards.** `r2` withdraws an answer into
   `checks["withheld"]` and hands it on; nothing here has authority to rule
   anything out.

## Ownership

Following plan §8.2 (whose rationale — A owns everything deterministic, B owns
everything that talks to a model — is coherent; plan §8 steps 5-6 contradict it
and were not followed):

| Owner | Files | Mental model |
|---|---|---|
| **A** | `ledger.py` `registry.py` `corpus.py` `negation.py` `calibrate.py` `probe.py` `rungs/r1.py` `rungs/r2.py` `run.py` `fixture.py` | "Records flow through zones and every transition gets logged." No prompts, no model calls. |
| **B** | `score.py` `rungs/r0.py` `r3.py` `r4.py` `r5.py` `prompts/` | "Given records and sources, return better records." No ledger internals, no zone logic. |
| Joint | `schema.py` `rungs/r6.py` `manifest.json` `docs/decisions.md` | Agree out loud before either types. |

`schema.py` is **frozen**. `manifest.json` is append-only and edited only in a
joint block. B registers a rung by adding `ladder/rungs/rN.py`; B never edits
`run.py`.

## First run

```bash
python -m ladder.registry --build --release data/SnomedCT_Release_AU1000036_20260731
```

```bash
python -m ladder.run init
```

`init` verifies the corpus parses, runs the plan's critical-path gate (a real
code resolves, a fake one does not), and writes the frozen splits. Then the
step-3 fixture gate — ten hand-made records, several deliberately broken:

```bash
python -m ladder.run gate
```

## The two model-free measurements

Rung 1 is fully characterised before rung 0 exists, because both halves of its
behaviour can be measured against the gold standard alone.

**Its false-rejection floor** — replay rung 1 over CADEC's own annotations,
where every rejection is wrong by construction:

```bash
python -m ladder.calibrate --split all --sweep --json out/rung1_floor.json
```

**Its detection profile** — corrupt gold records one known way at a time:

```bash
python -m ladder.probe --split all --json out/rung1_detection.json
```

Results as of 2026-08-22, on the whole corpus (9,111 mentions, SNOMED
AU1000036_20260731):

| | |
|---|---|
| false-rejection floor | **12 / 9,111 = 0.13%** (5 codes absent from the release, 4 corpus typos, 3 genuine gold miscodings) |
| zone occupancy on gold | ACCEPT 43.1% · BAND 56.8% · REJECT 0.13% |
| detection: hallucinated code | 1.000 |
| detection: span shift / fabrication | 1.000 / 1.000 |
| detection: wrong semantic type | 1.000 on reactions (0.000 on drugs, by design) |
| detection: random plausible wrong finding | 0.000 caught, 0.000 wrongly accepted |
| detection: **near-miss** finding | 0.001 caught, **0.001 wrongly accepted** at `lexical_mode="exact"` — but **0.190** at `"contained"` |

Read together: deterministic checks are *exact* on their own error classes and
blind to the interesting one, and the ACCEPT lane's leniency setting is the
difference between a gate that declines to have an opinion and a gate that
endorses one near-miss in five.

## Running the ladder

```bash
python -m ladder.run ladder --split test --source gold --run-id gold_control
```

`--source gold` is the control, not a baseline: it feeds the answer key in as if
it were rung-0 output. Once B ships `rungs/r0.py` the same command runs the real
thing, or `--predictions out/r0.jsonl` runs the deterministic rungs over a
prediction file B produced separately.

Missing rungs are reported and skipped, never faked. Without `ladder/score.py`
the accuracy columns in `results.csv` are written empty rather than guessed.

Outputs land in `out/<run_id>.{ledger.jsonl,results.csv,records.jsonl,manifest.json}`.

## What owner B needs from this

- **`rungs/r0.py`** — `apply(records, sources, cfg)`. Rung 0 is the one rung
  handed an *empty* record list: build `Record`s from `sources` and return them.
  One call, one JSON, temp 0, no validation, and do not repair malformed JSON —
  a parse failure is a real reliability cost and must be counted.
- **`ladder/score.py`** — one shared scorer. `reaction_sct_strict(record, gold)`
  where `gold` is `{record_id: GoldMention}`. The gold rule is in
  `manifest.json`: the predicted code is IN the gold code set. Note the shapes —
  252 mentions are post-coordinated and 3 are disjunctions.
  `rungs/r2.sweep()` takes the correctness oracle as an argument, so there is
  still exactly one scorer and A never imports it.
- **Prediction matching**: rung-0 output is a *set* of mentions per document,
  not a fixed slot list, so scoring needs span-overlap alignment to gold before
  code comparison. That belongs in `score.py`.

## Open for iteration 2

1. **The abstention target is thin at n=60 documents** — 7 `CONCEPT_LESS`
   mentions in 393. Abstention accuracy cannot be separated from noise there.
   Raise `n_test_docs` (a document is one rung-0 call) or pool dev+test for
   that one metric and say so.
2. **`tau` is 0.0** — the confidence gate is off until a real rung-0 confidence
   distribution exists to calibrate it against. Sweep on dev, write the value
   into the manifest, then touch test.
3. **Rung-order ablation** — `rung_order` is a manifest list, so re-running with
   `[0,1,2,3,5,4,6]` is one config change and turns "abstention should run last"
   from an assertion into a measurement.
4. **Post-coordinated gold** — 2.8% of mentions need two codes. The gold rule
   gives credit for either; a stricter reading is a defensible alternative and
   the affected records are flagged so both can be reported.
5. **Contamination** — CADEC is public and from 2015, so it is almost certainly
   in pretraining. It inflates rung 0, which makes the ladder's gains look
   *smaller*, so the conclusion is conservative. The CADEC v2 / MultiADE slice
   (`data/.../CADEC.v2.zip`, already downloaded) is the check.

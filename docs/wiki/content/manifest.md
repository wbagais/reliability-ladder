# manifest.json

**The one file that makes a number reproducible.** Append-only, edited jointly.

> If a setting can move a published number, it belongs here rather than in a default argument.

## Sections

| Key | Holds |
|---|---|
| `task`, `seed`, `unit_of_evaluation` | identity of the experiment |
| `gold_rule` | strict = predicted code is **in the gold code set** for that mention |
| `corpus` | version, licence, paths, split sizes, stratification, checksums |
| `vocabulary` | SNOMED release + backend, MedDRA mode, paths |
| `model` | extractor, judge, temperature |
| `rung_order` | `[0,1,2,3,4,5,6]` — ID equals execution position |
| `rung0_mode` | `recall` (default) or `search` |
| `rungs.N` | per-rung settings |
| `ablations` | declared experiments |
| `output.dir` | where runs are written |

- Paths are **relative to the manifest**, resolved at load, so a checkout moves cleanly.
- Every run writes its manifest alongside its results: `out/<run_id>.manifest.json`.

## Settings that change what a number means

| Setting | Default | Effect if changed |
|---|---|---|
| `rungs.1.mode` | `observe` | `gate` makes rung 1 filter, confounding every rung above it |
| `rungs.1.lexical_mode` | `exact` | `contained` accepts 19 % of near-miss codes vs 0.1 % |
| `rungs.1.meddra_check` | `flag` | `reject` lets an answer-key-derived table decide verdicts |
| `rungs.1.reject_inactive` | `false` | `true` rejects 11 % of the gold standard |
| `rungs.1.finding_scope` | `reaction` | `all` rejects every drug mention |
| `rungs.2.tau` | `0.0` | the confidence gate; swept on **dev**, written **before** the first test run |
| `vocabulary.meddra_mode` | `reference` | `answer_space` makes it a different, much easier task — must be declared in the method section |
| `vocabulary.snomed_backend` | `local-rf2` | the two backends disagree on 23.9 % of gold |
| `rung0_mode` | `recall` | `search` gives the model a lookup tool |

## Known gap

> **`vocabulary.snomed_backend` is currently inert.** It appears in no Python file; all eight `Registry(...)` sites take `vocabulary.snomed_db` directly. No published number is wrong — the field happens to describe what runs — but setting it to `ols4` would keep using the local index while labelling the output `ols4`. Recorded in `docs/decisions.md`.

## Declared ablations

| Name | Change | Scope |
|---|---|---|
| rung0 search vs recall | `rung0_mode: search` | R0+R1 |
| rung order | `[0,1,2,3,5,4,6]` | full |
| vocabulary backend | `snomed_backend: ols4` | R0+R1 |

Currently the rung-order ablation is a no-op: with rungs 3–6 absent, both orders collapse to `[1,2]`.

## Rules

- **Append-only.** Never reorder or delete keys.
- Edited **deliberately** — it is the file most likely to be touched from two directions at once, and the likeliest conflict in the repo.
- A `_note` key beside a setting is normal and expected: the reasoning travels with the value.

## Related

- [[architecture]] · [[rungs]] · [[vocabulary]] · [[corpus]] · [[glossary]]

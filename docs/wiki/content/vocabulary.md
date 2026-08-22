# Vocabulary backends

`ladder/registry.py` · `ladder/vocab.py` · `schemas/vocabulary.py` (contract 2).

A **global resource**, not a per-item `trusted_record`.

## Two backends, NOT interchangeable

| Backend | Implementation | Lossy? |
|---|---|---|
| `local-rf2` | RF2 release indexed to SQLite. **Default.** | no |
| `ols4` | EBI OLS4 over the network. Free, no key, no download. | **yes** |

## The measured gap

OLS4 serves **active, international** SNOMED only. CADEC's gold is neither entirely active nor entirely international.

```
CADEC gold mentions carrying an SCT code: 8666

  6593  76.1%  active international — both backends agree
  1420  16.4%  active, extension-module only — not in OLS4's SNOMED
   648   7.5%  retired — OLS4 indexes active concepts only
     5   0.1%  absent from both

  -> OLS4 reports 2073 / 8666 = 23.92% of GOLD as nonexistent.
     The local RF2 index reports 5.

  drug      1657 / 1657 = 100.0% affected
  reaction   416 / 7009 =   5.9% affected
```

- Every drug mention is affected: CADEC codes drugs to **AMT**, the Australian extension, which the international release does not contain at all.
- A property of the **source**, not a bug in either implementation.

> **Never report a rung 1 rejection rate without saying which backend produced it.** To a validation gate, `exists() == False` reads as "hallucinated code" — so on OLS4, correct answers like `aspirin` and `Crestor` are rejected as fabrications.

## The index

```bash
python -m ladder.registry --build --release data/SnomedCT_Release_<yours>
```

- Three tables: `concept`, `description`, `meta`. ~365 MB, ~9 s.
- Sees retired concepts and extension modules, both of which OLS4 cannot.
- Reproducible: a rebuild gives identical stats and lookups.
- Inspect a code: `python -m ladder.registry --check 162031009 30989003`

## Key semantics

- **"Code exists" means present, active OR retired.** 11 % of CADEC's codes are retired. SNOMED retires a concept's is-a rows with the concept, so an active-only hierarchy walk cannot place them — treating "cannot place" as "wrong slot" cost 413 gold mentions.
- The semantic-type check may reject only on a **positive `not_finding`**, never on "unknown".
- `lexical_match` runs over **every** term the concept has, not just the preferred one. `267036007` has preferred term `Dyspnea` and also carries `Shortness of breath`.

## MedDRA

- The only table available is the code list CADEC ships. **666 codes, all 666 appear in the gold annotations, 0 do not.**
- It is the answer key's code inventory (~3 % of MedDRA PT), **not a vocabulary**.
- Hence `meddra_mode: reference` — cross-check only, retrieval refused — and `meddra_check: flag`, never `reject`.
- Removing its `occurrences`/`posts` columns removes the evidence of derivation, not the derivation.

## Crosscheck

```bash
python -m ladder.vocab_crosscheck
```

- Offline by default. Predicts OLS4's answers from the RF2 `active` and `moduleId` columns — no network.
- `--live N` verifies that prediction against the real service. **Validated 40/40**: backends agree 28/40, and all 12 disagreements are retired (9) or AU-extension (3).

## Related

- [[corpus]] · [[r1]] · [[measurement]] · [[manifest]]

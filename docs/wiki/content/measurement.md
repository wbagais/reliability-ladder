# Measurement tools

Both halves of a validation gate can be measured against the answer key alone, **with no model calls**.

> **Provenance.** Every figure on this page: 2026-08-22, CADEC v2, SNOMED `AU1000036_20260731`, backend `local-rf2`. All are pinned in [[manifest]]. The commands below regenerate them.

## calibrate — the cost half

```bash
python -m ladder.calibrate --split all --sweep
```

- Replays [[r1]] over the gold standard, where **every rejection is false by construction**.
- `--sweep` prices each open setting against the manifest default.

| Setting | REJECT | false-rejection |
|---|---|---|
| manifest default | 12 | **0.13 %** |
| `reject_inactive=True` | 660 | 7.24 % |
| `finding_scope=all` | 1,432 | 15.72 % |
| `negation_action=reject` | 439 | 4.82 % |
| `meddra_check=reject` | 15 | 0.16 % |
| `lexical_mode=contained` | 12 | 0.13 % |

- Zone occupancy at the default: ACCEPT 3,926 (43.1 %) · BAND 5,173 (56.8 %) · REJECT 12 (0.13 %).
- This process took the gate's error floor from **9.3 % to 0.13 %**. Do it before trusting any new check.

## probe — the detection half

```bash
python -m ladder.probe --split all
```

Corrupts each gold record one way at a time and reports what rung 1 catches.

| Corruption | caught | wrongly ACCEPTED |
|---|---|---|
| hallucinated code | 1.000 | 0.000 |
| span shift | 1.000 | 0.000 |
| span fabricate | 1.000 | 0.000 |
| wrong-type code | 0.809 (1.000 on reactions) | 0.000 |
| plausible wrong finding | 0.000 | 0.000 |
| near-miss (sibling) | 0.001 | 0.001 — **0.190 under `contained`** |

- `caught` = rejected outright. `shipped` = put in ACCEPT, a wrong answer the gate actively vouched for. The gap is BAND, where rung 1 correctly declines to have an opinion.
- **Read together with calibrate:** deterministic checks are *exact* on their own error classes and blind to the interesting one. A gate's leniency setting decides whether it declines to have an opinion or endorses one near-miss in five.
- `--lexical-mode` and `--meddra-check` override the manifest to price those choices.

## vocab_crosscheck — backend agreement

```bash
python -m ladder.vocab_crosscheck
```

- **Offline by default**, no network. Predicts OLS4's answers from the RF2 `active` and `moduleId` columns.
- `--live N` verifies against the real service. Validated 40/40. See [[vocabulary]].

## rung0_ab — the tool ablation

```bash
python -m ladder.rung0_ab --compare
```

- Mode A (`recall`) vs mode B (`search`). One implementation, one flag.
- Needs `ladder/stub_llm.py` and a running Ollama.

## align — pairing predictions with gold

`bench/align.py`. Without it precision and recall are undefined: a post has an unknown number of reactions, so *which prediction corresponds to which gold* must be decided before anything is scored.

Three decisions, explicit because they move the numbers more than any rung:

- **Bipartite, not greedy.** CADEC golds overlap each other — two can start at the same offset. Greedy matching depends on file order; maximum-weight bipartite matching gives each gold at most one prediction and is order-independent.
- **Character-level IoU over fragment sets.** Discontinuous mentions are ~16 % of ADRs, so a mention is a *set* of character positions, not a range. One formula handles both.
- **Threshold 0.5, and it is reported.** A threshold chosen silently is a thumb on the scale.

Error classes kept separate: `matched_correct` · `matched_wrong_code` (the interesting one) · `spurious` · `missed`.

## What cannot be measured yet

- **Accuracy.** `ladder/score.py` does not exist, so `f1_sct_strict`, `yield` and `err_per_100` are written empty.
- Everything above is model-free and self-consistent — none of it is an accuracy claim, so none can be inflated by leakage.

## Related

- [[r1]] · [[corpus]] · [[vocabulary]] · [[runner]] · [[glossary]] · [[troubleshooting]]

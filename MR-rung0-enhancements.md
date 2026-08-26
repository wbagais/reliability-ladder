# Rung 0 settled at 0.294/0.447; first full-ladder dev run

## What this branch does

Five measured rung-0 arms on the dev split (40 docs, 226 gold mentions), each
committed with its numbers:

| arm | change | F1 exact | F1 overlap |
|---|---|---|---|
| frozen S2 (baseline) | — | 0.209 | 0.310 |
| 1: few-shot flip | synthetic worked example on | 0.266 | 0.363 |
| 3: dev-analysis rules | base-concept pick rule, scope fix, exhaustiveness, runtime pool examples, `no_concept` | 0.289 | 0.430 |
| 4/4b/4d: B/C/D bundle | name-retrieval, k=40, third example | regressed — isolation runs recorded, reverted |
| 5: reasoning_effort | default vs low, re-measured | +1.5pt exact for 2.6× tokens, ~10× wall — **low stays** |
| **final** | arm 3 + `no_concept` line | **0.294** | **0.447** |

Few-shot examples are pool-split documents rendered at runtime from `data/` —
only doc IDs are committed, no corpus text (CADEC is non-transferable;
preflight clean).

## First full-ladder run against the frozen rung 0

- **Rung 1** concentrates correctness for free: ACCEPT 32 records at 75%
  correct vs 28% base rate; REJECT error floor holds (0/10 correct).
- **Rung 2** fired zero times — the only rejects were ungrounded spans, which
  carry no code-fact to state back.
- **Rung 3 is net negative as built**: 206/240 `not_resampled`, and where it
  matched it overwrote 9 of the 32 verified-ACCEPT codes with memory-recalled
  hallucinations (|Fever| for "stiff neck"). Its sampler must go through the
  same retrieve-and-pick path as S2 before it runs again.
- **Rung 4** (2B judging 20B): pass = 33% correct vs fail = 17% — signal, but
  cannot gate.
- **Rung 5**: P 0.567 at R 0.075; the withdrawal of 43 correct answers is now
  a measured bill, not a slogan.

All decisions in `docs/decisions.md`. 488 tests green.

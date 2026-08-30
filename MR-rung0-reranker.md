# Rung 0 reranker: built, measured, not enabled

## What this branch does

Adds `ladder/rerank.py` — a rerank stage between `_step_pick`'s retrieval and
`_decide` — behind `rung0_rerank` (`None` | `"polarity"` | `"llm"`), plus
`rung0_rerank_deep` / `_k` / `_batch` / `_weight`. **`manifest.json` is
byte-unchanged and nothing is turned on.** 23 tests, TDD'd; 649 pass;
preflight clean.

## Why the component was built

Two measurements from the previous session point at exactly one missing piece.
Over 174 matched dev mentions:

| | |
|---|---|
| gold at retrieval rank 0 | 52.3% |
| gold in the top 20 (the menu) | 81.0% |
| gold in the top 200 | 91.4% |
| the pick converts gold **at rank 0** | **94.5%** |
| the pick converts gold **at rank 1-19** | **42.3%** |

Menu recall wants a deep k; the pick degrades with one (k=40, measured
2026-08-24, made picks worse). A rerank stage is the only shape that holds
both ends. Oracle ceiling on it: +0.20 exact.

## The result: it works as a ranker and does not pay

| arm | exact | overlap | extra calls | extra tokens |
|---|---|---|---|---|
| baseline (mean of 3 draws) | 0.401 | 0.472 | — | — |
| `polarity` deep50 keep15 | 0.402 (+0.001) | 0.479 (+0.007) | 0 | 0 |
| `polarity` deep50 keep20 | 0.395 (−0.004) | 0.482 (+0.013) | 0 | 0 |
| `llm` deep50 keep15 | 0.399 (0.000) | 0.477 (+0.008) | **71** | **+172,370** |
| `llm` deep200 keep20 | probe: menu recall +1.2pt | | ~93 | **+576,822** |

The `llm` arm lifts gold to menu rank 0 from **52.3% to 58.6%** and the pick
still ratifies rank 0 at **96.1%** — the ranking change is real and survives
into production. The headline does not move, because the rank-0 bucket's gain
(86/91 → 98/102) is paid for out of the rank-1+ bucket (22/52 → 12/41).

**The diagnosis, measured.** On the 52 baseline mentions where gold sat at
rank 1-19, the reranker promoted it to rank 0 for:

- **50.0%** (11/22) of the mentions the pick **already coded correctly**
- **16.7%** (5/30) of the ones it **got wrong**

Independence would predict one number. Reranker and picker are the same model,
so the stage mostly re-affirms what the pick already believed. That also
explains deep=200: the codes buried at ranks 20-199 are precisely the ones this
model does not recognise, so a pass by the same model does not lift them — and
holding 200 candidates in one judgement raises unparsed replies from 3 to 15.

**The +0.20 oracle prices a reranker with independent knowledge. This repo has
one model family in the extractor role.**

## The methodology finding

The free `polarity` arm scored **+0.0215 overlap on draw 0, paired bootstrap
[+0.0000, +0.0433] — a CI excluding zero**. Draws 1 and 2: **+0.0087** and
**−0.0089**. A bootstrap over documents resamples the corpus of *one* draw; it
prices the corpus sample and says nothing about run-to-run model variance. The
two must be reported together.

Baseline spread over three dev draws: exact 0.395–0.408 (1.3pt), overlap
0.469–0.475 (0.6pt) — and *lumpy*: draws 0 and 1 produced byte-identical
detection, draw 2's FIND step differed outright.

## Also in this branch

- **The shipped baseline is `rung0_cut_rate: 0.06`**, recorded in the handoff
  notes as "left off". Without it `arm-filters-dev` reproduces at 0.385, not
  0.399 — every arm here would have been measured against the wrong reference.
- **`checks.labels_proposed` is empty on all 235 dev records**: `FIND_PROMPT`
  forbids naming a concept, so the label-query arm of `_merged_candidates` has
  never fired in a shipped S2 run. Dead code, not a measured path.
- **Lexical reranking loses** at every weight (rank-0 52.3% → 50.0–52.3%),
  confirming the 2026-08-24 hybrid-retrieval result in the harder framing where
  only the *order* is at stake.
- **A system message does not shrink the noise floor**, and dev was never noisy
  enough to shrink: Jaccard 0.842 without against 0.906 with, both showing two
  of three draws byte-identical, at a consistent −3 points of exact F1. The
  0.55 → 0.93 result came from a ten-document subset that overstates variance.

## Caveat on all of it

The test split was spent in Phase F. Every number here is dev-side, 40
documents, 226 gold mentions. Nothing is validatable on held-out data.

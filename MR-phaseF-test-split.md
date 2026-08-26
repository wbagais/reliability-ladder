# Phase F: the test split, once — the ladder's final numbers

## Why

Every number so far was measured on dev, where five phases of tuning looked
at it. Phase F is the one thing dev cannot give: the 60 held-out documents,
run cold under the frozen configuration, reported as-is. **Nothing was edited
before the run, nothing was re-run after the numbers were seen, and there are
no further phases.**

## The run

`python -m ladder.run ladder --split test --run-id phaseF-test-1`, full order
[0–6], in a fresh worktree at origin/main (includes the rung-6 cost-measure
decision). The freeze held: manifest.json, prompts and models.yaml exactly as
merged — S2 dense retrieval + trimmer, rung 1 `observe`, rung 3 enabled,
rung 6 `simulated`; extractor `ollama/gpt-oss:20b`, judge
`ollama/ibm/granite4:micro-h`. The shared LLM cache holds only dev/pool
prompts, so the run paid full price: **~78 min wall** (rung 0 1165.5 s,
rung 3 3060.3 s, rung 4 417.0 s), 314 records over 60 docs, 290 scorable
gold reaction mentions (32 excluded per `data/exclusions.csv`). Suite green
before launch (592 passed); zero production code changed — this MR carries
only the log, the CLAUDE.md phase-plan update, and this file. Run artifacts
live in the phase-f worktree's `out/` (gitignored, as always).

## Shipped result (post-rung-5 records, `score_run`, exclusions + local-rf2 registry, 1000-doc bootstrap)

| | exact | overlap |
|---|---|---|
| **F1** | **0.204** [0.150–0.260] | **0.215** [0.160–0.274] |
| detection F1 | 0.521 [0.451–0.586] | 0.808 [0.754–0.855] |
| coding accuracy (matched spans) | 0.392 [0.305–0.476] | 0.266 [0.204–0.332] |
| outcomes (correct/outdated/abstained/incorrect/modernised) | 60/0/91/2/0 | 63/0/167/7/0 |

`modernised` — built so the test split could not hide the retired-gold
successor case — did not fire, on test as on dev. The dev baseline,
re-derived by re-scoring `phaseD-r3-2.records.jsonl` with the same harness
(never requoted): exact F1 0.131 [0.088–0.185], detection 0.449, coding
0.291. **Test came out above dev on all three layers** with barely
overlapping CIs; no tuning ever touched test, so read that as
generalisation plus split luck, in that order.

## Rung by rung (stack view, answered-only accuracy)

- **Rungs 0–2**: 0.370 over 284 answered (coverage 0.904).
- **Rung 1** (backend: **local-rf2**): ACCEPT 72 / BAND 226 / REJECT 16 —
  a 5.1% rejection rate, 72% BAND. All 16 rejects were `schema_invalid`,
  which yields no statable fact, so **rung 2 correctly attempted zero
  corrections** (0 calls; the ledger keeps "did not fire" distinguishable
  from "did not run").
- **Rung 3** (voting — SAMPLES, run id `phaseF-test-1`): re-found 8
  previously unanswered records and all 8 were wrong. Coverage 0.904→0.930,
  correct unchanged at 105, answered accuracy 0.370→0.360. The dev gain
  (+5 net correct on `phaseD-r3-2`) **did not transfer to this draw**.
- **Rung 4** (2B judging 20B — the caveat stands): pass 202 / fail 110,
  2 parse_failed.
- **Rung 5**: ships 72 records at 0.833 answered accuracy (60
  exact-correct), withdraws 242; err_per_100 falls 59.6 → 3.8.
- **Rung 6** (`simulated`): **242 of 314 routed to a person —
  reviews_per_100 77.1**, the headline cost (dev: 84.9). 484.0 human
  minutes *at the declared 2.0 min/record* — declared, never measured.
  The queue's withheld answers were already exact-correct 45× /
  overlap-correct 86×; 16 queue records carry unlocated `(-1,-1)` spans a
  span-keyed desk cannot review. **The oracle desk was not generated:
  refused on test by design.**

## Cost — three measures, never fused

- **Tokens**: 844,657 over 758 calls (rung 0 619.6/record; rung 3
  1,708.6/record = 2.76× rung 0; rung 4 361.9/record). `usd` 0.00 carried
  alongside (local models).
- **Latency p95 per call**: 57.2 s (rung 0) / 126.1 s (rung 3) / 1.5 s
  (rung 4).
- **Routed to a person**: 242/314 (reviews_per_100 77.1).

Zero `timed_out`, zero `truncated`, zero `json_decode` across the run.

**These are the ladder's test numbers, final as reported.**

🤖 Generated with [Claude Code](https://claude.com/claude-code)

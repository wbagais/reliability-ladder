# Phase D: rung 3 repaired — votes from the distribution being verified, and re-enabled on measurement

## Why

The 2026-08-25 full-ladder run measured rung 3 net negative as built:
206/240 records `not_resampled`, and 9 of 32 rung-1-verified-ACCEPT codes
overwritten with memory-recalled hallucinations (|Fever| for "stiff neck").
Two causes: votes were matched on an exact `(doc_id, spans)` key that shifts
between samples, and the sampler drew from the legacy recall prompt while the
run's codes came from the frozen S2 retrieve-and-pick path — voting over a
different answer distribution than the one being verified.

## What changed

**Step 1 — disabled first, as a recorded state.** `manifest.rungs.N.enabled:
false` is now generic: `run_ladder` skips the rung before model resolution,
writes a `disabled` ledger row and a `{"disabled": true}` aggregate entry, so
"rung 3 did not run" stays distinguishable from "rung 3 found nothing".

**Four fixes, all TDD'd** (`tests/test_r3_repair.py`, each test seen failing
first):

- **(a) Overlap matching.** `r3.match_votes` assigns each sampled mention to
  at most one record — best span overlap first, deterministic tie-breaks,
  votes collected per record identity. One sampled mention can never count as
  two agreeing votes.
- **(b) The configured path.** Rung 0's per-document body is factored into
  `r0.prepare()` / `r0.extract_document()` — step dispatch, few-shot block,
  trimmer — and both `r0.apply` and rung 3's sampler run through it, so the
  two cannot drift. The document ledger row bills actual `api_calls`
  (2 per S2 sample), not one per sample.
- **(c) One counted vote is not a vote.** A record re-found by fewer than 2
  samples records its verdict (`single_sample`) but is never changed — the
  `k<2` refusal applied to the votes actually cast. Found by measurement 1:
  38433004 |Analgesia| (the *absence* of pain) overwrote verified 22253000
  |Pain| on a 1-0 "majority".
- **(d) Deterministic order.** Documents are sampled sorted; the old set
  iteration tied the draw sequence (and every cache key) to the process hash
  seed. The 6-document test replaced a 2-document version that passed by
  hash-seed luck on its first run.

## The measurement (dev, 40 docs, 245 records)

Analysis harness validated first by reproducing the 2026-08-25 numbers from
`full-ladder-dev-1.records.jsonl` (206/240; 9/32; 11 correct→incorrect, 0
improvements). Final config, `out/phaseD-r3-2.*`:

| | 2026-08-25 (broken) | phaseD-r3-2 (repaired) |
|---|---|---|
| not_resampled | 206/240 | 38/245 |
| verified-ACCEPT overwrites | 9/32, hallucinated | 1/37, genuine 2-1 menu majority |
| correct codes destroyed | 11 | **0** |
| changes for the better | 0 | 5 (3 abstained→correct, 2 incorrect→correct) |
| stack F1 exact at rung 3 | worse than rung 1 | 0.335 → 0.347 |

Unanimity 56.4% over seen≥2; 8 single-sample actions withheld; cost 222
calls / 382,991 tokens over 37 documents (2.6× rung 0) for ~+5 net correct
answers. Rung 3 results are samples — measurement 1 and 2 differ in
individual votes; numbers cite their run id.

`manifest.rungs.3.enabled` is back to `true`, with the round trip recorded
in its note. Suite: 557 passed (6 new tests).

🤖 Generated with [Claude Code](https://claude.com/claude-code)

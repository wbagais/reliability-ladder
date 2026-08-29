# Audit rungs 1-6: two defects fixed, four rungs measured dead

Rung 0 was audited last session. This branch applies the same treatment to the
six rungs above it: reproduce, find the live defects, fix them TDD-first, log
every decision.

**Every finding here was demonstrated on real run artifacts before a line was
changed.** The rung 0 baseline was reproduced exactly first — `{split,
drop_ungrounded, drop_fragments, drop_duplicate_spans, cut_rate 0.06}` over 40
dev docs gives exact 0.399 / overlap 0.469, det 0.516/0.785, coding
0.773/0.597, 92/108 correct, 235 predictions: all seven figures identical to
`out/arm-filters-dev`.

**Hard constraint, restated.** Phase F spent the test split on 2026-08-26 and
no held-out data remains. Everything below is dev-side and not validatable, and
**Phase F's shipped numbers stand exactly as reported** — nothing here re-opens
them. Where a Phase F artifact appears it is a read-only counterfactual,
labelled as one.

## The headline: the ladder's paid rungs do not compose

Rungs 2, 3 and 4 each decline to act on their own evidence, on the correct
argument that a rung which routes confounds every rung above it. Each names
rung 5 as the rung that will act:

| rung | writes | its own docstring |
|---|---|---|
| 2 | `checks["r2_declined"]` | "rung 5 owns abstention and reads `checks['r2_declined']`" |
| 3 | `checks["r3_unanimous_none"]` | "EVIDENCE for rung 5, not an action here" |
| 4 | `checks["r4_verdict"]` | "record ... and let rung 5 act" |

**`r5.decide()` reads none of the three.** It reads the zone, `r1_verdict`,
`r1_reason` and `rec.confidence`; its whole config is `{tau, abstain_zones,
abstain_on_reject}`. A repo-wide search finds no consumer for any of them
outside the rungs that write them and one diagnostic script.

So in composition the ladder is one rung: rung 5 routes on rung 1's free
lexical verdict and on nothing else. Rungs 2, 3 and 4 can only move a number by
mutating `rec.sct` in passing — which only rung 3 does, and which turned out to
be the defect below.

No unit test could have caught this. Every rung does exactly what its docstring
promises. It is only visible by asking, from outside, what reads what.

## Two live defects, both fixed TDD-first

`tests/test_rungs_audit.py`, 6 tests. 655 pass, preflight clean.

### 1. Rung 3 left rung 1's verdict describing a code the record no longer had

`apply()` did `rec.sct = win` and stopped — but rung 5 routes on
`checks["r1_verdict"]`, which was computed against the replaced code.

* `phaseD-r3-2` changed 25 codes, `phaseF-test-1` changed 30. **All 55 carried
  a superseded verdict.**
* `LIPITOR.739#0` is the one that reached a user: "Chronic pain" coded
  82423001 |Chronic pain|, ACCEPTed by rung 1 on an exact lexical match, voted
  3-0 to 762452003 |Chronic musculoskeletal pain|, and **shipped as VERIFIED**.
  Re-checked against the registry, `lexical_match("chronic pain", 762452003,
  exact)` is `False` — the configured rung 1 would have banded it and rung 5
  would have abstained it.

`r3.revalidate()` now owns adoption of the winning code. It **always** records
`checks["r3_r1_stale"]`, so no rung above can mistake a verdict about a
replaced code for a verdict about this one. Under the new arm
`rungs.3.revalidate` (**default false**) it re-judges through `r1.zone` — the
one measured rung 1, under `manifest.rungs.1` — keeping the superseded verdict
in `checks["r3_r1_before"]`.

Off by default because re-banding **moves coverage** to rung 6: a declared
trade to be measured, not a correctness fix switched on quietly.

### 2. Rung 2 re-validated its repair under `r1.DEFAULTS`, not the manifest

`run_ladder` builds each rung's cfg from `manifest.rungs[n]` alone, so rung 2's
cfg carried no rung 1 settings at all; `r1.zone(cand, source, registry, cfg)`
resolved every rung 1 key to its default, and the meddra table was not passed.
A repair could be counted `rescued` under a rule the rung 1 that rejected it
does not use — the test makes the same repair a rescue under the defaults and a
`still_failing` under `label_check: "reject"`.

**No published number moves**: `manifest.rungs.1` currently equals
`r1.DEFAULTS` on every key, and rung 2 attempted 0 corrections in Phase F. This
was a latent divergence that would have bitten on the first rung 1 setting
anyone changed.

*(The handoff listed rung 2's post-sent-TWICE bug as never fixed. It was fixed
2026-08-26; re-verified from the code and re-asserted in the audit's tests.)*

## Four things that are not bugs, and are worse than bugs

Logged in `docs/decisions.md`, not patched.

**A fix three rungs below disabled two rungs above.** Rung 1 rejected 5.1% on
the Phase F test run, all `schema_invalid`. On the current baseline it rejects
**1 record of 248 (0.4%)** — `rung0_drop_ungrounded` now removes the unlocated
`(-1,-1)` spans that *were* that entire rejection class. Rung 2's trigger set
went with it. Nothing is broken in either rung; their input was removed from
underneath them, and no test and no report could have shown it.

**Rung 1's headline check cannot fire.** `code_unknown` fires **0 times** over
248 records, confirmed through `all_reasons` so it is not the first-failure
ordering bias. S2 picks from a dense-retrieved menu of real SNOMED codes and
resolves names through `KeywordTable.resolve` — **the model can no longer emit
a code that does not exist.** Two more are degenerate: `sct_active` is True for
all 232 coded records, `sct_outdated` False for all 235, and `label_verified`
is True for **232 of 232**, because S2's menu shows the code and its vocabulary
label together, so `sct_label` is the vocabulary's own label by construction.
Rung 1 was tuned in 2026-08-22 against a rung 0 that recalled codes from
weights; retrieval moved the failure mode out from under it.

**The free check beats the paid judge.** Rung 1's ACCEPT/BAND split is the one
survivor, and it separates hard — coding accuracy on matched spans, overlap:

| | n | coding accuracy |
|---|---|---|
| rung 1 ACCEPT (free, deterministic) | 49 | **83.7%** |
| rung 1 BAND | 131 | 35.9% |
| rung 4 pass (one granite call per record), dev | 105 | 21.0% |
| rung 4 fail, dev | 63 | 12.7% |
| rung 4 pass, test | 163 | 27.0% |
| rung 4 fail, test | 73 | 21.9% |

2.3x separation for free, against 1.65x falling to 1.23x for a call per record
— on the only axis a judge is for.

**Rung 5's `tau` is a dead dial.** Rung 0's confidence is
`{1.0: 204, 0.99: 44}` on the dev baseline. There is no operating point: any
tau ≤ 0.9 abstains nothing, any tau above it abstains 80-98% on a number the
model emits as boilerplate. `R_LOW_CONFIDENCE`, one of rung 5's three declared
abstention reasons, is unreachable, and `sweep()`'s risk-coverage curve has
nothing to sweep.

## The through-line, confirmed at rung 3

Rungs 2, 3 and 4 run on the same model as rung 0, so they inherit its errors.
The reranker measured this directly last session: it promoted 50% of what the
pick already had right and 16.7% of what it had wrong. Rung 3 shows the same
shape — changed records scored against gold, overlap, before and after:

| | scorable changes | fixed | broke | net |
|---|---|---|---|---|
| dev (`phaseD-r3-2`) | 18 | 5 | 0 | **+5** |
| test (`phaseF-test-1`) | 21 | 2 | 2 | **0** |

On dev, 3 of the 5 "fixes" are `None`/`CONCEPT_LESS -> a correct code` — rung 3
filling a gap, not correcting an error. On test it destroyed |Severe pain|
76948002 and 281245003 while rescuing two others. A 5-0 on 18 trials is what a
coin flip looks like sometimes, which is the single-draw lesson again. Rung 3
costs 2.6x rung 0's tokens for a net of zero correct records out of sample.

Rung 6 remains the only rung that adds information, and it adds it because it
is a person (oracle desk: exact F1 0.131 -> 0.444, coding accuracy 0.291 ->
0.990).

## The revalidate arm, measured

Replayed exactly over two finished runs rather than re-run — legitimate because
the arm changes nothing upstream of the vote, so both arms are computed from
the **same votes** and rung 3's sampling noise leaves the comparison. The
replay reproduces Phase F's shipped numbers exactly at `revalidate=false`
(exact 0.204 / overlap 0.215, 72 shipped, 242/314 routed), which is what
licenses the counterfactual.

| | exact | overlap | shipped | routed to a person |
|---|---|---|---|---|
| dev, off | 0.153 | 0.170 | 37 | 208 |
| dev, on | 0.153 | 0.170 | 36 | 209 |
| test, off *(= Phase F as reported)* | 0.204 | 0.215 | 72 | 242 |
| test, on *(counterfactual)* | 0.204 | 0.218 | 72 | 242 |

**The fix withdraws a false warrant and moves the headline by nothing** — a
record that was wrong scores the same whether it ships wrong or is withdrawn.
The ladder's own headline metric is blind to the defect the ladder exists to
prevent. That is the argument for the arm, and it is not an accuracy argument.

## Flagged for your call, not fixed

**`manifest.json` runs a rung 0 that is 5.9 exact points below the baseline the
last two sessions measured against.** The 2026-08-27/28 arms (coordination
splitter, three span filters, `cut_rate`) shipped as code with `r0.DEFAULTS`
off and were never appended to the manifest.

| | exact | overlap | detection | predictions |
|---|---|---|---|---|
| `manifest.json` as shipped | 0.340 | 0.449 | 0.449/0.745 | 233 |
| the audited baseline | **0.399** | **0.469** | 0.516/0.785 | 235 |

Both are real; only one is in the manifest, and it is not the one the decision
log quotes. This is the failure the `manifest.model` note was written for — a
default in code and a declaration in configuration disagreeing — one layer
down. Not fixed unilaterally: turning the arms on changes every number the
ladder produces, and the manifest is edited jointly.

## Changed

* `ladder/rungs/r3.py` — `revalidate()`, the `revalidate` arm, two agg counters
* `ladder/rungs/r2.py` — `_r1_params()`, meddra threaded into re-validation
* `manifest.json` — appended `rungs.3.revalidate` + note (one line touched)
* `tests/test_rungs_audit.py` — 6 tests
* `docs/decisions.md` — 12 entries
* `out/harness/` — `r1r2reach.py`, `r1signal.py`, `r4r5signal.py`,
  `stalecheck.py`, `revalarm.py`, `r3throughline.py` (untracked scratch)

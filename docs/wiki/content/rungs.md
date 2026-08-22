# The Ladder

Each rung is one reliability layer. The point is the **marginal** contribution of each: what it buys, and what it costs.

## The seven rungs

| Rung | Layer | Mechanism | Extra cost | Owner | State |
|---|---|---|---|---|---|
| 0 | [[r0]] bare LLM | one call, JSON, temp 0 | 1 call/item | B | in progress |
| 1 | [[r1]] deterministic | schema · span · negation · code exists · semantic type · MedDRA | **none** | A | done |
| 2 | [[r2]] abstention | decline what is unresolved, or below τ | none | A | done |
| 3 | [[r3]] self-correction | one bounded retry, fired only by a rung 1 failure | +1 call | B | not started |
| 4 | [[r4]] LLM-as-judge | second model, different family | +1 call | B | not started |
| 5 | [[r5]] voting | k samples, majority on the normalised code | k calls | B | not started |
| 6 | [[r6]] human-in-the-loop | a person settles it | human minutes | joint | not started |

## Execution order

`manifest.rung_order = [0, 1, 3, 5, 4, 2, 6]` — not numeric.

- Abstention runs **last**: abstaining before correction and voting throws away recoverable records.
- Order is configuration, so "is 0-1-3-5-4-2-6 better than 0-1-2-3-4-5-6?" is a one-line ablation, not an assertion.
- Rung IDs are identity and come from the brief. Renumbering breaks comparability with other groups.

## What each rung may do

- Mutate `zone`, `reason`, `provenance`, `checks` on a [[record]]. Nothing else.
- Write one [[ledger]] row per record touched.
- Read `checks["r1_verdict"]` and `checks["r1_reason"]`. **Nothing else from `checks`** — the rest is audit trail, some of it derived from the answer key.

## The three-outcome design

Rung 1 cannot confirm a code is right — nothing deterministic can, because the code is not in the source text.

- `REJECT` — provably wrong, with a reason.
- `ACCEPT` — passed, and the vocabulary uses these very words.
- `BAND` — passed, unverifiable by string comparison.

Two outcomes cannot express BAND. **BAND is 56.8 % of even a perfect answer set** — that fraction is the bill the paid rungs work through, and the reason the ladder exists.

## Cost, in three measures

Never fused into a dollar figure.

- **tokens per record** — from real usage counts, not estimates.
- **latency p95** — taken over the run, not derived from a total.
- **records routed to a person** — human minutes.

A single `$/100` needs a price table that shifts under you and merges three costs that are not interchangeable. Keeping them apart forces the honest question: would you rather spend tokens or human attention?

## Ablations declared in the manifest

- **rung 0 search vs recall** — does a lookup tool remove errors, or move them into `overrode_tool`?
- **rung order** — abstention early vs last.
- **vocabulary backend** — the two backends disagree on 23.9 % of gold. See [[vocabulary]].

Run each rung alone on identical input:

```bash
python -m ladder.run ablate --split test --source gold
```

## Related

- [[architecture]] · [[record]] · [[ledger]] · [[manifest]] · [[runner]] · [[glossary]]

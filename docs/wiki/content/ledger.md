# Ledger & cost

`ladder/ledger.py` · owner A · Wejdan Bagais · append-only JSONL.

**One row per (rung, record).** Nothing in this project is measured anywhere else: the results table, the marginal-cost curve and the rung-1 reason breakdown are all a `GROUP BY` over this file.

> Two accounting paths is how a benchmark ends up with two different numbers for the same run.

## Entry fields

Append-only. New fields go on the end, always.

| Field | Note |
|---|---|
| `run_id`, `rung`, `doc_id`, `record_id` | identity |
| `zone` | where the record **is** |
| `verdict` | what the rung **concluded** — differs from `zone` in observe mode |
| `outcome` | `settled` · `passed` · `judged` · `rejected` · `abstained` · `escalated` · `unchanged` |
| `reason` | a `REJECT_REASONS` value |
| `tokens_in`, `tokens_out`, `api_calls` | token cost |
| `latency_ms` | per call, so p95 is taken over the run |
| `human_minutes` | the third currency |
| `usd` | carried, but **never added to human minutes** |
| `extra` | per-rung audit dict |

- `verdict` and `zone` being separate columns is what lets [[r1]] judge without routing.

## The three currencies

Never fused.

- **tokens per record** — divided by records that **entered** the rung, not the batch. A rung that only touches rejects is cheap precisely because few records reach it; a per-batch average hides that.
- **latency p95** — over the run.
- **human minutes** — surfaced as `reviews_per_100`.

`usd` exists because a hosted run has a real bill, but nothing downstream may add it to human minutes.

## Aggregations

| Method | Returns |
|---|---|
| `cost_by_rung(n_records)` | per-rung cost in all three currencies |
| `reasons(rung)` | the rung-1 headline — the breakdown, not the rate |
| `verdicts(rung)` | what a rung judged, which is not always what it did |
| `zone_counts(rung)` | where records ended up |
| `totals()` | batch totals; per-record figures hide the bill |

## Reading it

```bash
python -c "from ladder.ledger import Ledger; from collections import Counter; rows=Ledger.read('out/demo.ledger.jsonl'); print(Counter((r.rung, r.verdict) for r in rows))"
```

## Marginal cost

- The rungs are cumulative, so a rung's **own** spend is its marginal spend.
- Divided by the errors it prevented, that gives the exchange rate the project is about — in two currencies, never fused: `marginal_tokens_per_error`, `marginal_reviews_per_error`.
- Only meaningful in a cumulative run. `ablate` leaves these columns empty by design.

## Related

- [[record]] · [[runner]] · [[rungs]]

# Phase E: rung 6 — the human loop, as a rung, priced in human minutes

## Why

The ladder's third cost measure — records routed to a person — has been zero
everywhere, not because review is free but because rung 6 did not exist. After
Phases C/D the residue is real: on `phaseD-r3-2` (dev) rung 5 abstains 208 of
245 records and withholds 46 exact-correct answers doing it. Rung 6 is what
happens to that queue, and it stays a RUNG — "tell the model to escalate when
unsure" is rung 5.

## What was built

**`ladder/rungs/r6.py`** — the rung. The queue is rung 5's abstained residue,
each record still carrying `checks.withheld` (abstention withdraws, never
deletes — the person sees what the system was going to say). No model:
`ROLE_BY_RUNG` gives rung 6 no role deliberately; a "simulated desk" that
needed an LLM would be rung 2 in a trench coat.

- **`mode: "simulated"`** (manifest default) routes the queue to ESCALATE and
  prices it at `minutes_per_record` — every ledger row carries
  `human_minutes` with `minutes_source: "simulated"`. No answer is invented,
  so coverage cannot move: it measures the *bill* of stopping at rung 5, not
  the person. Human minutes stay their own currency, never fused with tokens
  or usd.
- **`mode: "desk"`** applies a resolutions file from a review session.
  Decisions are `code | concept_less | uphold | skip`; minutes are MEASURED
  (seconds at the desk, searching included — a `skip` is still charged the
  looking; unreviewed records escalate at 0 minutes, never fabricated ones).
  Resolutions are matched to records **by span key, one-to-one, never by
  record_id** — record_id is a position, the same argument as the scorer and
  rung 3's votes. Applied resolutions feed `ladder/score.py` with no
  translation step: `code` sets `sct` (RESOLVED), `concept_less` sets the
  literal, `uphold` is RESOLVED with no answer.

**`scripts/r6_desk.py`** — rewritten as a thin UI over the rung's functions.
Loads a run's `records.jsonl`, queues the ABSTAIN residue, shows source
context, the withheld answer **with its vocabulary label** (never a bare
SCTID), and the candidate menu the run itself retrieved; `/term` searches
through rung 0's own configured retriever, and the timer covers the
searching. Sessions append and resume. Resolution rows carry ids, offsets,
codes and labels only — **no corpus text** — so the file is shareable where
the corpus is not.

**`--oracle`** writes the resolutions deterministically from gold: the
ceiling, not a measurement. A queued span that is an exact gold mention gets
its gold code (the withheld answer when already in the gold set), CONCEPT_LESS
gold gets CONCEPT_LESS, an unannotated span is upheld — a perfect reviewer
declines to code a non-mention. Every row is stamped `oracle:gold`, every
ledger row says `resolved_oracle`, the aggregate says `oracle: true` with a
stated warning, and oracle rows are **refused on the test split** outright —
Phase F runs test once, and a gold-derived desk would put the answer key
inside it.

All TDD'd: 23 new tests (`tests/test_r6_human_loop.py`,
`tests/test_r6_desk_script.py`), each seen failing first.

## The measurement (dev, the phaseD-r3-2 residue applied directly)

Rung 6 is zero model calls, so it was applied standalone to the saved
records (`ablate --predictions … --rungs 6`) — the inbox is exactly the
residue Phase D measured, with no rung 3 sampling noise between them.

**Simulated** (`out/phaseE-r6-sim.*`): 208 records routed, **416.0 human
minutes** at the declared 2.0 min/record (reviews_per_100 = 84.9), accuracy
and coverage byte-identical to the input.

**Oracle ceiling** (`out/phaseE-r6-oracle.*`): 199 of 208 resolved (code 77,
concept_less 3, uphold 119). Re-scored with `score_run` (exclusions +
registry):

| | shipped stack (r0–5) | + rung 6 oracle |
|---|---|---|
| F1 exact | 0.131 | **0.444** [0.335–0.548] |
| coding accuracy (matched spans) | 0.291 | 0.990 |
| detection F1 exact / overlap | 0.449 / 0.745 | unchanged |
| exact-correct answered | 30 | 102 |
| human minutes | 0 | 398 (simulated rate, labeled) |

Detection unchanged and coding near-perfect means the **entire remaining gap
is span boundaries**, which a code-picking desk cannot fix — boundary repair
is the unbuilt ceiling above this one. The 9 unresolved records are the
schema-invalid residue with unlocated `(-1,-1)` spans: nine records collapse
onto two span keys, and a span-keyed desk refuses to guess — they stay
ESCALATE at 0 minutes. Context: undoing rung 5 entirely (ship everything
withheld) scores 0.331 exact on this harness — the oracle desk beats it
because a reviewer also *fixes* the queue's wrong codes (102 recovered vs 46
merely withheld-correct).

**Every oracle number is a labeled ceiling derived from gold. No real human
desk session has been run yet — the desk is built and waiting, and its first
timed session is future work.**

Suite: 581 passed (23 new). `manifest.rungs.6` gained only a `mode_note`;
its values are unchanged. Phase F (test split, once) remains untouched.

🤖 Generated with [Claude Code](https://claude.com/claude-code)

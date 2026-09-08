# Published run outputs

59 cells, enough for either owner to re-score every one.

## What is here

| file | contents |
|---|---|
| `*.results.csv` | the per-rung table each run printed |
| `*.aggregates.json` | token counts, latencies, per-rung tallies |
| `cell.manifest.json` | the configuration the cell actually ran under |
| `*.records.jsonl` | full records — none |
| `*.records.stripped.jsonl` | records without `text` or `context` — bc5cdr, geo, lgl, linnaeus, psytar, trnews |

## Why some are stripped

Scoring needs `doc_id`, `spans`, `sct` and the rung verdicts. It does not need
the quoted sentence. So a stripped file **scores identically** to a full one —
`scripts/score_matrix.py` reads the same fields from either.

CADEC's CSIRO licence is non-transferable: a copy received through this
repository would not be licensed, whatever the recipient's use. Its records are
therefore published without the quoted text. Every other corpus here permits
redistribution and is published in full.

## What you cannot do with a stripped file

Read what the model wrote. That is diagnosis rather than scoring — the
difference between *"this cell scores 76%"* and *"it scores 76% because it
wrote 'stomach pain' where gold says 'abdominal pain'"*. For that, use the
licensed local copy.

## Never published, for any corpus

`*.calls.jsonl`, `*.ledger.jsonl` and `*.state.jsonl`. They carry the model
quoting the corpus back verbatim, and they are the bulk of a run.

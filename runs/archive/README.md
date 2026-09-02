# runs/archive — restored run outputs

30 run outputs written by `scripts/{ladder_run,full_run,dev_sweep}.py` between
2026-08-22 and 2026-08-24, committed before the `runs/*` ignore rule existed.
29 were removed on 2026-08-31 by the dead-code cleanup (`7201dc5`); the 30th,
`ladder.ledger.jsonl`, went earlier with the TUI commit (`1a3437a`). All were
restored here on 2026-09-02, byte-identical to the versions deleted.

**This folder is not a write directory.** `runs/` is where the runners write and
its contents stay ignored; `runs/archive/` is the one tracked exception, so a
future cleanup cannot sweep these again. Nothing reads them back — `docs/decisions.md`
is still the durable record — they are kept as the raw material behind entries
dated before 2026-08-25.

Contents: ledger rows, provenance and aggregate blocks only. No corpus text —
document IDs, codes, token counts and latencies. `scripts/preflight.py` passes.

| files | what |
|---|---|
| `dev-model-*.json`, `dev-search-*.json`, `dev-B-*.txt` | `dev_sweep.py` model and search sweeps |
| `full-A-*.json` | `full_run.py` A-arm runs |
| `ladder-*.json`, `ladder.ledger.jsonl` | `ladder_run.py` runs and the pre-rule ledger |
| `r{3,4,5}-ledger-smoke.jsonl`, `r6-timing.jsonl` | per-rung smoke and timing rows |
| `otel-smoke.jsonl` | the one hand-made row from the deleted `ladder/otel.py` |

Timestamps in the filenames are the run ids, not dates.

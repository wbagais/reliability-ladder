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

## `consolidated-2026-09-03/` — the run behind every dev-side article number

Added 2026-09-07. The consolidated re-run (plan item 0b, protocol
`scripts/consolidated_rerun.sh`; S0/S1 draws `scripts/rerun_steps.sh`; the
FiNER type-check arm `scripts/rerun_typecheck.sh`; the driver
`scripts/rerun_all.sh`) produced 36 runs on the dev split. The raw run — records,
state rows, call traces — carries corpus text and stays under the gitignored
`out/` (archived with the call traces at the main checkout's
`out/archive/reliability-ladder-b2-menu-f77617/`). What is tracked here is the
corpus-free four per run, plus the reports derived from the full artifacts:

| path | what |
|---|---|
| `rerun-cadec-d{0,1,2}.*` | CADEC base draws, rungs 0–6 |
| `rerun-cadec-d*-{judgemenu,judgeshuffle,lexarm}.*` | the arms, replayed on the draw's cache |
| `rerun-cadec-d*-spine.*` | rungs 5–6 replayed over the r1 snapshot, zero model calls |
| `rerun-cadec-s{0,1}-d*.*` | S0 and S1 re-measured, rung 0 only |
| `finer/rerun-finer-d*[-arm].*` | the same for FiNER-139 (no lexarm) |
| `finer-typecheck/rerun-finer-d*-typecheck.*` | the type-check arm (rung 7, then 2–6) |
| `rerun/cadec.{md,json}` | `scripts/rerun_analysis.py` over the three base draws and arms — the 2026-09-04 regeneration with the gold-lane occupancy section, the version `docs/article-v3-CADEC.md` was audited against |
| `rerun/cadec-probe-{all,dev}-{exact,contained}.json` | `python -m ladder.probe`, the corruption probe |
| `rerun/cadec-s{0,1}.{md,json}`, `rerun/finer.{md,json}` | the S0/S1 and FiNER reports |
| `rerun-*.log` | the drivers' logs: timings, cache paths, per-rung summaries |

Per run: `.aggregates.json` (per-rung aggregate, models, cache dir, git sha and
dirty flag), `.ledger.jsonl` (one row per record per rung: ids, zone, verdict,
reason, tokens, latency, usd, human minutes), `.results.csv` (the per-rung
summary table) and `.manifest.json` (the configuration as run). The `text`
values in `rerun/*.json` are the model's extracted spans — annotated spans and
vocabulary labels, which is the licence rule for examples; never post prose.
`tests/test_runs_archive.py` pins the 36 run ids, refuses records/state/calls
files here, checks every ledger row for text-carrying keys and runs the
preflight scan over the directory.

**Re-deriving the reports needs the raw run and the corpus**; these files let
a reader open every number's source, not recompute it from git alone.

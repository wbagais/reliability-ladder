#!/usr/bin/env python3
"""
cost_estimate.py — how long will this actually take, from a run you already did.

WHY

Every GPU session in this project mis-estimated its own runtime, twice by an
order of magnitude:

    geo arm      estimated 3-4 hours from arithmetic; the first measurement
                 suggested 15; it ran in 7
    type-check   estimated 90 minutes from a 3-document smoke run; correct

The difference is that the second estimate came from a MEASUREMENT rather than
from reasoning about token counts. The smoke test was already being run for a
different reason — to catch crashes — and its timings were being thrown away.

This reads them instead. Same smoke run, one extra command, and renting a card
stops being a guess.

WHAT IT REFUSES TO DO

It does not extrapolate from a single document, and it says so rather than
producing a confident wrong number. Rung 3 samples k times per RECORD, so a
document yielding 4 records and one yielding 40 differ by an order of magnitude
in that rung alone — which is exactly why the geo estimate was wrong.

It also prints the assumption behind each line, because an estimate whose
assumptions are invisible is the thing that produced the 15-hour projection.

    PYTHONPATH=. python3 scripts/cost_estimate.py out/geo-smoke/*.ledger.jsonl --docs 60
    PYTHONPATH=. python3 scripts/cost_estimate.py out/geo-smoke/*.ledger.jsonl --docs 60 --runs 9 --rate 1.57
"""
from __future__ import annotations

import argparse
import collections
import glob
import json
import pathlib
import sys

RUNG_NAMES = {0: "extract", 1: "check", 2: "self-correct", 3: "vote",
              4: "judge", 5: "refuse", 6: "person", 7: "type check"}


def load(pattern: str) -> list[dict]:
    files = sorted(glob.glob(pattern))
    if not files:
        sys.exit(f"no ledger at {pattern}")
    rows = []
    for f in files:
        rows += [json.loads(l) for l in pathlib.Path(f).read_text().splitlines() if l.strip()]
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Project a full run from a smoke run's own timings.")
    ap.add_argument("ledger", help="the smoke run's ledger (glob ok)")
    ap.add_argument("--docs", type=int, required=True,
                    help="documents in the full split")
    ap.add_argument("--smoke-docs", type=int, default=0,
                    help="documents in the smoke run (default: counted from the ledger)")
    ap.add_argument("--runs", type=int, default=1, help="how many full runs")
    ap.add_argument("--rate", type=float, default=0.0, help="$/hour, if renting")
    ap.add_argument("--new-runs", type=int, default=0,
                    help="how many of the runs send calls the cache has never "
                         "seen. A run repeating another's model, prompts and "
                         "sample_index costs NOTHING — measured: of three base "
                         "runs, one cost 1,706s and two cost zero. Defaults to "
                         "--runs, which is the pessimistic reading.")
    a = ap.parse_args()

    rows = load(a.ledger)
    # AN ESTIMATE IS ONLY VALID ON THE HARDWARE IT WAS MEASURED ON, and this
    # tool cannot see which machine produced the ledger. The first version
    # projected a laptop smoke run onto rented-GPU work and returned 51 hours
    # for a job that took 7 — a laptop with the model half on CPU is roughly
    # 18x slower here. The provenance is the user's to supply because only
    # they know it.
    print("\n  ! This projects the timings in THIS ledger onto a larger split.")
    print("    If the ledger came from a different machine than the run will,")
    print("    the total is wrong by whatever those machines differ by —")
    print("    measured here at 18x between a 4GB laptop card and a rented 48GB one.")
    docs = a.smoke_docs or len({r.get("doc_id") for r in rows if r.get("doc_id")})
    if not docs:
        sys.exit("could not count documents in the smoke run — pass --smoke-docs")
    if docs < 3:
        print(f"\n  ! the smoke run covered {docs} document(s). An estimate from")
        print("    fewer than three is arithmetic, not a measurement — the geo arm")
        print("    was projected at 15 hours this way and ran in 7.\n")

    per_rung = collections.defaultdict(lambda: {"ms": 0.0, "rows": 0, "tokens": 0})
    for r in rows:
        k = per_rung[r.get("rung", "?")]
        k["ms"] += r.get("latency_ms", 0.0)
        k["tokens"] += r.get("tokens", 0)
        k["rows"] += 1

    scale = a.docs / docs
    print(f"\n  smoke: {docs} document(s), {len(rows)} ledger rows")
    print(f"  projecting to {a.docs} documents  ({scale:.0f}x)"
          + (f" x {a.runs} runs" if a.runs > 1 else ""))
    print()
    print(f"  {'rung':16} {'smoke':>9} {'rows':>7} {'projected':>11}   assumption")
    print("  " + "-" * 74)

    total_s = 0.0
    total_tok = 0
    for rung in sorted(per_rung, key=lambda x: (x is None, x)):
        k = per_rung[rung]
        s = k["ms"] / 1000
        proj = s * scale
        total_s += proj
        total_tok += int(k["tokens"] * scale)
        name = RUNG_NAMES.get(rung, str(rung))
        # A rung whose rows outnumber the documents scales with RECORDS, not
        # documents, and records per document is the thing that varies most
        # between corpora. Said per line rather than buried.
        per_doc = k["rows"] / docs
        assumption = ("scales with documents" if per_doc <= 1.5
                      else f"scales with records — {per_doc:.0f} per document here")
        print(f"  {str(rung) + ' ' + name:16} {s:8.1f}s {k['rows']:7} "
              f"{proj/60:9.1f} min   {assumption}")

    # Runs after the first do not pay for cached rungs. Ignoring that projected
    # 171 minutes for six runs that took 52 — the arithmetic was right and the
    # MODEL OF HOW THE RUNS WORK was wrong, which is the more expensive kind of
    # error and the one this repository keeps finding.
    # MEASURED, and it is starker than the flag suggests. Three base runs of
    # the type-check arm: run 1 cost 1,706 seconds, runs 2 and 3 cost ZERO —
    # not mostly cached, entirely cached, every rung. The cache key is
    # (model, messages, temperature, sample_index), so a run repeating a
    # previous run's config pays nothing at all.
    #
    # So the question is not which rungs cache. It is HOW MANY RUNS ARE NEW.
    # Modelling it any other way projected 171 minutes for 52 minutes of work.
    new = a.new_runs if a.new_runs else a.runs
    total_min = total_s * new / 60
    print("  " + "-" * 74)
    print(f"  {'total':16} {'':9} {'':7} {total_min:9.0f} min"
          + (f"   ≈ {total_min/60:.1f} h" if total_min > 90 else ""))
    if total_tok:
        print(f"  {'tokens':16} {'':9} {'':7} {total_tok * a.runs:9,}")
    if a.rate:
        print(f"  {'cost':16} {'':9} {'':7} {'':9} "
              f"  ${total_min / 60 * a.rate:.2f} at ${a.rate:.2f}/hour")

    print()
    print("  Read the assumption column before believing the total. A rung that")
    print("  scales with RECORDS moves with records-per-document, which differs")
    print("  three-fold between the corpora in this repository — and mis-reading")
    print("  that is what produced a 15-hour projection for a 7-hour run.")
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

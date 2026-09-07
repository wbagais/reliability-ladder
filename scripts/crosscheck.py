#!/usr/bin/env python3
"""
crosscheck — is this arm wired as it is declared?

    gatecheck    should I run this?          before booking a card
    crosscheck   is it what I declared?      first line of every run
    stagecheck   did the run mean anything?  after

Every load-bearing fact read back from an independent source and compared. The
principle came out of a week where every defect that got through was a fact
recorded ONCE — the prompt declared and never read back, the few-shot ids
written and never checked against the pool the guard reads, the model named in
a manifest and absent from ollama. Everything that WAS caught compared two
records of one fact.

Costs no GPU, no model call, about a second. That is the point: a check cheap
enough to be the first line of every run never gets skipped.

    PYTHONPATH=. python3 scripts/crosscheck.py --manifest manifest.psytar.json
    PYTHONPATH=. python3 scripts/crosscheck.py --manifest 'manifest.*.json' --quiet

Exit code is the number of failures, so `crosscheck ... || exit` gates a run.

The checks themselves are in `ladder/checks/cross.py`, one function each, listed
at the bottom of that file. Adding one means writing a function.
"""
from __future__ import annotations

import argparse
import glob
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from ladder.checks import Arm, report
from ladder.checks import cross


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--manifest", nargs="+", required=True)
    ap.add_argument("--quiet", action="store_true",
                    help="one line per manifest unless something fails")
    a = ap.parse_args()

    paths: list[str] = []
    for pattern in a.manifest:
        paths += sorted(glob.glob(pattern)) or [pattern]

    total = 0
    for path in paths:
        try:
            arm = Arm.load(path)
            total += report(pathlib.Path(path).name, cross.run(arm), a.quiet)
        except Exception as exc:
            print(f"\n  ── {path}\n   ! could not check: {exc}\n")
            total += 1

    print()
    print(f"  {total} check(s) failed. Each is a fact declared in one place and "
          f"contradicted in another." if total else
          "  Every declared fact was confirmed from a second source.")
    print()
    return min(total, 125)


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""
export_evidence.py — publish this study's track record for stagecheck to vendor.

THE DIRECTION OF DEPENDENCY, AND WHY IT MATTERS

The study imports the tool. The tool never imports the study. If stagecheck
depended on this repository it would inherit CADEC's non-transferable licence, a
1.6 GB SNOMED index and three corpus adapters — and anyone installing a
measurement library would acquire a corpora problem.

So nothing flows from here to there except EVIDENCE, and evidence is data:
which predictions this study's checks made, and what happened afterwards.

WHY IT IS VENDORED RATHER THAN FETCHED

A tool that phones home for its calibration is a tool that behaves differently
depending on the network, and this one's whole argument is that a measurement
must state the conditions it was taken under. The exported file carries the
date, the git SHA and the corpora it covers, so a reader can see exactly which
version of the evidence a verdict was printed against.

WHY IT CARRIES AN AGE

The machinery here is durable and the findings are not. "Self-correction rescues
nothing" was measured on 2026 open-weight models; if a later generation corrects
itself reliably, the code still runs and the advice is wrong — and a tool giving
confident stale advice is worse than none, because it is trusted. So the export
stamps a date and stagecheck prints the age beside every verdict.

    PYTHONPATH=. python3 scripts/export_evidence.py
    PYTHONPATH=. python3 scripts/export_evidence.py --out ../stagecheck/src/stagecheck/evidence.json
"""
from __future__ import annotations

import argparse
import json
import pathlib
import subprocess
import sys
from dataclasses import asdict
from datetime import date

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))


def _git(*args: str) -> str:
    try:
        return subprocess.run(("git", *args), capture_output=True, text=True,
                              check=True).stdout.strip()
    except Exception:
        return "unknown"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="../stagecheck/src/stagecheck/evidence.json",
                    help="where stagecheck vendors it")
    a = ap.parse_args()

    from ladder.calibration import PREDICTIONS, ALIASES

    dirty = bool(_git("status", "--porcelain"))
    payload = {
        "_what": "The track record of the checks in stagecheck's relation "
                 "registry, exported from the study that produced them. Data, "
                 "not code — the tool does not depend on the study.",
        "_read_the_dates": "Every finding here was measured on the models and "
                           "corpora named. The machinery that produced them is "
                           "durable; these conclusions are not. A verdict older "
                           "than a model generation should be read as a "
                           "hypothesis, and stagecheck prints the age for that "
                           "reason.",
        "exported": date.today().isoformat(),
        "study": {
            "repo": _git("remote", "get-url", "origin"),
            "sha": _git("rev-parse", "--short", "HEAD"),
            "dirty": dirty,
            "_dirty_note": ("Exported from a dirty tree — the SHA does not "
                            "describe what produced this." if dirty else ""),
        },
        "corpora": ["CADEC v2", "FiNER-139", "GeoWebNews"],
        "models": ["gpt-oss:20b", "llama3.1:8b", "mistral:7b-instruct",
                   "granite4:micro-h", "qwen3:4b"],
        "aliases": ALIASES,
        "predictions": [asdict(p) for p in PREDICTIONS],
    }

    out = pathlib.Path(a.out)
    if not out.parent.is_dir():
        sys.exit(f"{out.parent} does not exist — is stagecheck checked out beside this repo?")
    out.write_text(json.dumps(payload, indent=2) + "\n")

    counts: dict[str, int] = {}
    for p in PREDICTIONS:
        counts[p.outcome] = counts.get(p.outcome, 0) + 1
    print(f"  {out}")
    print(f"  {len(PREDICTIONS)} prediction(s) · " +
          " · ".join(f"{v} {k}" for k, v in sorted(counts.items())))
    print(f"  study {payload['study']['sha']}" + (" (DIRTY)" if dirty else ""))
    if dirty:
        print("\n  ! Exported from a dirty tree. The SHA in this file does not")
        print("    describe the code that produced these numbers. Commit first.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

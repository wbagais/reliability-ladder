#!/usr/bin/env python3
"""
manifest_diff.py — what actually differs between two arms, before either runs.

WHY

An arm is a claim of the form *"one thing changed, and here is what it bought."*
That claim is only true if one thing changed, and nothing in this repository
checks it.

Measured 2026-08-31: the spine ablation's two manifests differed in `rung_order`
— the declared variable — AND in rung 0's configuration, because the spine
manifests predated five rung-0 arms appended earlier the same day. Running them
as they stood would have compared a `[0,1,5]` stack on a rung 0 scoring 0.340
against a `[0..6]` stack on a rung 0 scoring 0.399, and charged that 5.9-point
difference to the rungs being dropped. It was caught by hand, key by key, and
only because someone thought to look.

This is that check, mechanised, and it takes two seconds.

WHAT IT DOES THAT `diff` DOES NOT

    · Ignores keys that are documentation — anything beginning with `_`, plus
      the note fields this repo attaches to almost every setting. A prose note
      differing is not a second variable.
    · Ignores `output.dir` and run ids, which differ by construction.
    · Separates the DECLARED variable from everything else, so the output says
      "you declared rung_order and also changed rung0_shortlist_k" rather than
      listing both as equals.
    · Exits non-zero when an undeclared key differs, so it can gate a run.

    PYTHONPATH=. python3 scripts/manifest_diff.py base.json arm.json
    PYTHONPATH=. python3 scripts/manifest_diff.py base.json arm.json --declared rung_order
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

#: Keys that differ by construction and say nothing about the experiment.
EXPECTED = {
    "output.dir", "output", "run_id", "_arm", "_draw",
}

#: A key is documentation if it starts with an underscore or ends in `_note`.
#: This repo attaches prose to almost every setting — `rung0_retrieval_note` is
#: several hundred words — and a note differing is not a second variable.
def _is_doc(path: str) -> bool:
    tail = path.split(".")[-1]
    return tail.startswith("_") or tail.endswith("_note") or tail.endswith("_notes")


def flatten(obj, prefix="") -> dict:
    out = {}
    if isinstance(obj, dict):
        for k, v in obj.items():
            out.update(flatten(v, f"{prefix}.{k}" if prefix else str(k)))
    elif isinstance(obj, list):
        # A list is compared whole. Element-wise diffing of rung_order would
        # report three changes for one reordering.
        out[prefix] = json.dumps(obj)
    else:
        out[prefix] = obj
    return out


def diff(a: dict, b: dict) -> dict[str, tuple]:
    fa, fb = flatten(a), flatten(b)
    keys = set(fa) | set(fb)
    out = {}
    for k in sorted(keys):
        if _is_doc(k) or k in EXPECTED or k.split(".")[0] in EXPECTED:
            continue
        va, vb = fa.get(k, "<absent>"), fb.get(k, "<absent>")
        if va != vb:
            out[k] = (va, vb)
    return out


def _short(v, width=46) -> str:
    s = str(v)
    return s if len(s) <= width else s[:width - 1] + "…"


def main() -> int:
    ap = argparse.ArgumentParser(
        description="What differs between two manifests, and what you declared.")
    ap.add_argument("base")
    ap.add_argument("arm")
    ap.add_argument("--declared", nargs="*", default=[],
                    help="the key(s) this arm is testing. Everything else that "
                         "differs is a second variable.")
    a = ap.parse_args()

    for p in (a.base, a.arm):
        if not pathlib.Path(p).is_file():
            sys.exit(f"no manifest at {p}")

    base = json.loads(pathlib.Path(a.base).read_text())
    arm = json.loads(pathlib.Path(a.arm).read_text())
    d = diff(base, arm)

    print(f"\n  {a.base}  →  {a.arm}")
    if not d:
        print("\n  Nothing differs outside documentation. If this is meant to be")
        print("  an arm, it is not one.\n")
        return 1

    declared, undeclared = {}, {}
    for k, v in d.items():
        if any(k == n or k.endswith("." + n) or n in k for n in a.declared):
            declared[k] = v
        else:
            undeclared[k] = v

    if declared:
        print(f"\n  DECLARED — what this arm says it is testing\n")
        for k, (x, y) in declared.items():
            print(f"    {k}")
            print(f"      base  {_short(x)}")
            print(f"      arm   {_short(y)}")

    if undeclared:
        print(f"\n  NOT DECLARED — {len(undeclared)} further difference(s)\n")
        for k, (x, y) in undeclared.items():
            print(f"    {k}")
            print(f"      base  {_short(x)}")
            print(f"      arm   {_short(y)}")
        print("\n  Each of these is a second variable. An arm that changes two things")
        print("  cannot attribute its result to either — and the difference will be")
        print("  charged to whichever one you declared.")
        print("\n  The spine ablation (2026-08-31) differed in rung_order AND in rung 0,")
        print("  which would have charged a 5.9-point rung-0 gap to the rungs it")
        print("  removed. That was caught by hand. This is the same check, mechanised.\n")
        return 1

    print("\n  Nothing else differs. The arm changes what it declares and no more.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

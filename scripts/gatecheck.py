#!/usr/bin/env python3
"""
gatecheck — should this corpus be run at all?

    gatecheck    should I run this?          before booking a card
    crosscheck   is it what I declared?      first line of every run
    stagecheck   did the run mean anything?  after

Reads the gold and the vocabulary and reports what rung 1's free check COULD do
here, before any GPU time. On FiNER it predicts 0.0% and says the arm cannot
produce a lane however good the model is — a full arm's finding, available for
nothing. On LINNAEUS it predicts 4.8% and flags it thin; that arm went on to
produce a usable lane on one model of four.

It also drafts the prompt rules, because every rule written by hand for four
corpora turned out to be a threshold applied to a measurement. And it lists
what it will NOT decide, which is the part that needs a person.

    PYTHONPATH=. python3 scripts/gatecheck.py --manifest manifest.psytar.json
    PYTHONPATH=. python3 scripts/gatecheck.py --manifest manifest.foo.json --write

The measurements are in `ladder/checks/gate.py`, with the thresholds declared
at the top of that file rather than buried in the code that applies them.
"""
from __future__ import annotations

import argparse
import glob
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from ladder.checks import Arm
from ladder.checks import gate


def show(a: Arm, write: bool) -> int:
    p = gate.profile(a)
    if not p.get("mentions"):
        print(f"\n  {a.name}: no gold mentions\n")
        return 1

    print(f"\n  ── {a.name} · {p['documents']} documents · {p['mentions']} mentions "
          f"· {p['distinct']} distinct forms\n")
    for k in ("multi_token", "dotted", "capitalised", "leading_article",
              "discontinuous", "repeated"):
        print(f"      {k:18} {p[k]:6.1%}")
    print(f"      {'length med / p95':18} {p['len_median']:3} / {p['len_p95']}")
    print(f"      commonest: " + ", ".join(f"'{t}'" for t in p["commonest"][:8]))

    if "lane_ceiling" not in p:
        # REFUSE rather than continue. The predicted lane is the one section
        # that can stop a card being booked, and a tool that silently omits its
        # headline check when a file is missing is the failure it exists to
        # prevent — the profile above would read as a complete assessment.
        print("\n  REFUSING: no vocabulary. The predicted lane needs one, and "
              "without that number this tool has not assessed anything.\n")
        return 1

    print(f"\n  ── PREDICTED FREE-CHECK LANE, on gold, no model\n")
    for k, v in p["strata"].items():
        print(f"      {k:12} {v:6.1%}")
    print(f"      absent from vocabulary  {p['vocab_absent']:.1%}")
    c = p["lane_ceiling"]
    print(f"\n      CEILING {c:.1%} — the most the free check could endorse here.")
    if c < gate.T["dead_ceiling"]:
        print("      ! This arm CANNOT produce a lane, however good the model is.")
        print("        Either structural — a numeral against an English phrase —")
        print("        or a vocabulary build choice. This tool cannot tell those")
        print("        apart, and the difference decides whether to spend.")
    elif c < gate.T["thin_ceiling"]:
        print("      ! Thin. Expect a small lane and small denominators.")

    entity = a.prompts.get("entity_short") or a.prompts.get("entity") or "MENTION"
    rules = gate.draft_rules(p, entity)
    print(f"\n  ── DRAFT RULES (entity: {entity})\n")
    print("      " + rules.replace("\n", "\n      "))

    print(f"\n  ── REQUIRES A SIGNATURE — this tool will not guess\n")
    for u in gate.unsigned(a, p, rules) or ["nothing — every declaration is present."]:
        print(f"      · {u}")

    patch = gate.sniffable(a)
    print(f"\n  ── SNIFFABLE, ready to write\n")
    for k, v in patch.items():
        print(f"      {k:26} {v}")
    need = patch["corpus.n_dev_docs"] + patch["corpus.n_test_docs"]
    if len(a.docs) <= need:
        print(f"      ! {len(a.docs)} documents cannot support that split and "
              f"leave a pool. LINNAEUS hit this at 95 against 40+60.")

    if write:
        man = a.manifest
        for k, v in patch.items():
            if v is None:
                continue
            node, parts = man, k.split(".")
            for part in parts[:-1]:
                node = node.setdefault(part, {})
            node[parts[-1]] = v
        pathlib.Path(a.path).write_text(json.dumps(man, indent=2) + "\n")
        print("\n  written. The SIGNATURE list above is still unsigned.")
    print()
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--manifest", nargs="+", required=True)
    ap.add_argument("--write", action="store_true",
                    help="write the sniffable declarations into the manifest")
    a = ap.parse_args()

    paths: list[str] = []
    for pattern in a.manifest:
        paths += sorted(glob.glob(pattern)) or [pattern]

    bad = 0
    for path in paths:
        try:
            bad += show(Arm.load(path), a.write)
        except Exception as exc:
            print(f"\n  {path}: FAILED — {exc}\n")
            bad += 1
    print("  A prompt written from these numbers can say what the corpus does.")
    print("  A prompt written from an impression of it cannot.\n")
    return min(bad, 125)


if __name__ == "__main__":
    raise SystemExit(main())

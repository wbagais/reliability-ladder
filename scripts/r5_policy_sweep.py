#!/usr/bin/env python3
"""
r5_policy_sweep.py — what could FiNER ship, and at what error rate?

THE QUESTION

FiNER ships 0% of its answers. The accuracy of those answers is 0.508 on the
matched dev records. A system that is half right and ships nothing is either
correctly cautious or misconfigured, and until now nobody had asked which.

THE CAUSE, found 2026-09-02

`r5.DEFAULTS["abstain_zones"] = [ZONE_BAND]` — rung 5 withholds every record
rung 1 put in BAND. That policy was chosen on CADEC, where BAND records were
35.9% correct against ACCEPT's 84.6%; withholding BAND there is obviously right.

**On FiNER there is no ACCEPT lane at all** — the lexical check is a structural
zero, a numeral shares no token with an English phrase — so everything is BAND
and the policy withholds the entire population. Not by decision, by inheritance.

That is the third CADEC constant found living in corpus-agnostic code, after the
vocabulary gate's hardcoded SNOMED id and the exclusion list applied to every
corpus.

WHAT THIS SCRIPT DOES, AND WHAT IT REFUSES TO DO

It reports the risk-coverage curve so a policy can be CHOSEN rather than
inherited. It does not choose. Picking whichever policy makes FiNER's headline
look better is tuning on the outcome, which is the failure this project
documents in others, and the curve is printed precisely so the choice is made
against a stated exchange rate instead.

The columns, and why each is there:

  coverage       answered / all
  precision      correct among answered — RISES MECHANICALLY as you abstain
                 more, so it must never be read alone
  yield          correct / all — the honest headline, because abstaining cannot
                 improve it
  over-abstention  correct answers withheld. The cost nothing else prices, and
                 the number that started this: 64 on the shipped policy
  reviews/100    the third currency. Never fused with the other two

    PYTHONPATH=. python3 scripts/r5_policy_sweep.py
    PYTHONPATH=. python3 scripts/r5_policy_sweep.py --records out/tc-finer/dev_*.records.jsonl
"""
from __future__ import annotations

import argparse
import glob
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from ladder.rungs.r5 import decide
from ladder.schema import ZONE_ABSTAIN, ZONE_ACCEPT, ZONE_BAND, ZONE_REJECT


class Replay:
    """A finished record, replayable through r5.decide without a run.

    r5.decide is pure by design — "so the sweep can replay it" — which is what
    makes this measurable at all. A rung whose verdict logic lived inside its
    apply loop could not be swept without re-running the model.
    """

    __slots__ = ("checks", "zone", "reason", "confidence", "sct", "key")

    def __init__(self, d: dict):
        self.checks = d.get("checks") or {}
        self.zone = d.get("zone")
        self.reason = d.get("reason")
        self.confidence = d.get("confidence")
        # rung 5 already ran and moved the answer aside; read what the system
        # ANSWERED, not what it shipped, or every policy scores zero.
        code = d.get("sct") or (self.checks.get("withheld") or {}).get("sct")
        if isinstance(code, list):
            code = code[0] if code else None
        self.sct = code
        self.key = (d["doc_id"], d["spans"][0][0]) if d.get("spans") else None


def _adapter(man):
    """The corpus module the manifest names. Same dispatch run.py uses."""
    name = (man.get("corpus") or {}).get("adapter", "cadec")
    if name == "finer":
        from ladder import corpus_finer as mod
    elif name == "geo":
        from ladder import corpus_geo as mod
    else:
        from ladder import corpus as mod
    return mod


def gold_for(manifest: str, split: str) -> dict:
    man = json.loads(pathlib.Path(manifest).read_text())
    load_corpus = _adapter(man).load_corpus
    read_split = _adapter(man).read_split
    sampling = {k: v for k, v in (man["corpus"].get("sampling") or {}).items()
                if not k.startswith("_")}
    root = man["corpus"].get("root") or man["corpus"]["cadec_root"]
    docs = load_corpus(root, **sampling)
    ids = read_split(man["corpus"]["splits_dir"], split)
    return {(m.doc_id, m.spans[0][0]): m.sct[0]
            for d in ids for m in docs[d].mentions if m.sct}


def evaluate(recs, gold, params) -> dict:
    answered = correct = withheld_right = routed = 0
    for r in recs:
        zone, _ = decide(r, params)
        g = gold.get(r.key)
        right = g is not None and r.sct == g
        if zone == ZONE_ABSTAIN:
            routed += 1
            withheld_right += right
        else:
            answered += 1
            correct += right
    n = len(recs)
    return {
        "coverage": answered / n if n else 0.0,
        "precision": correct / answered if answered else 0.0,
        "yield": correct / n if n else 0.0,
        "over_abstention": withheld_right,
        "reviews_per_100": 100 * routed / n if n else 0.0,
        "answered": answered,
        "correct": correct,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", default="manifest.finer.json")
    ap.add_argument("--split", default="dev")
    ap.add_argument("--records", default="out/tc-finer/*.records.jsonl")
    a = ap.parse_args()

    files = sorted(glob.glob(a.records))
    if not files:
        print(f"no records at {a.records}"); return 1
    gold = gold_for(a.manifest, a.split)

    # Pooled over the draws, and the per-draw spread reported, because a policy
    # chosen on one draw is a policy chosen on noise.
    per_draw = []
    for f in files:
        recs = [Replay(json.loads(l)) for l in open(f)]
        recs = [r for r in recs if r.key]
        per_draw.append(recs)

    print(f"\n  FiNER · {a.split} · {len(per_draw)} draws · "
          f"{len(per_draw[0])} records · {len(gold)} gold mentions")
    print("  Precision rises mechanically as coverage falls. Read YIELD.\n")

    policies = [
        ("withhold BAND  (shipped)",   {"abstain_zones": [ZONE_BAND]}),
        ("withhold nothing",           {"abstain_zones": []}),
        ("withhold BAND, tau 0.995",   {"abstain_zones": [ZONE_BAND], "tau": 0.995}),
        ("withhold nothing, tau 0.995", {"abstain_zones": [], "tau": 0.995}),
        ("withhold nothing + judge",   {"abstain_zones": [], "abstain_on_judge_fail": True}),
    ]

    print(f"  {'policy':30} {'cover':>7} {'prec':>7} {'yield':>7} "
          f"{'lost':>6} {'rev/100':>8}")
    print("  " + "-" * 70)
    for name, params in policies:
        rows = [evaluate(recs, gold, params) for recs in per_draw]
        mean = {k: sum(r[k] for r in rows) / len(rows) for k in rows[0]}
        spread = max(r["yield"] for r in rows) - min(r["yield"] for r in rows)
        flag = "  ±%.3f" % spread if spread > 0.005 else ""
        print(f"  {name:30} {mean['coverage']:7.1%} {mean['precision']:7.1%} "
              f"{mean['yield']:7.1%} {mean['over_abstention']:6.0f} "
              f"{mean['reviews_per_100']:8.0f}{flag}")

    print()
    print("  LOST is over-abstention — correct answers thrown away. It is the")
    print("  cost the shipped policy pays and never reports.")
    print()
    print("  This script does not choose. Which row is right depends on what a")
    print("  wrong answer costs relative to a human review, and that exchange")
    print("  rate is the one number only the owner of the pipeline has.")
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""
score_typecheck_arm.py — did rung 7 change anything, and was it right?

TWO QUESTIONS, AND ONLY ONE OF THEM IS ANSWERED BY THE ARM

The six runs measure the EFFECT: base has no rung 7, the arm has it, rung 0 is
identical at each sample_index, three draws each. Any difference in what ships
is rung 7's contribution.

They cannot say whether rung 7 is RIGHT. A rejection is either a correct
withdrawal of a wrong answer or a false rejection of a right one, and an
end-to-end number contains both. That question is answered against GOLD, where
every rejection of a correct record is false by construction — the same way
rung 1's own false-positive rate went from 9.3% to 0.13%.

Reported separately here, and deliberately not combined into one figure. The
reranker arm (2026-08-31) is the cautionary case: an offline probe separated
over 1,144 documents while the arm ran on 38, and the sign flipped on the arm's
own denominator. Two numbers that disagree are informative; one number that
averages them is not.

THE THIRD QUESTION, which is the interesting one

Rung 2 fired on FiNER for the first time in this arm. On CADEC it fired once in
248 records and rescued none. Here it finally has a trigger — so does it do
anything? A "no" is a stronger result than the CADEC one, because the CADEC
"no" could always be explained by the tiny trigger set.

    PYTHONPATH=. python3 scripts/score_typecheck_arm.py
"""
from __future__ import annotations

import argparse
import collections
import glob
import json
import pathlib
import statistics
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

R_TYPE_MISMATCH = "type_mismatch"


def shipped_code(rec: dict):
    """What the system ANSWERED, including an answer rung 5 later withdrew.

    Reading `sct` alone scores the shipping decision rather than the answer,
    and rung 5 abstains on everything here — so `sct` is null on every record
    and a scorer that trusts it reports zero for both arms.
    """
    ch = rec.get("checks") or {}
    code = rec.get("sct") or (ch.get("withheld") or {}).get("sct")
    if isinstance(code, list):
        code = code[0] if code else None
    return code


def load_runs(pattern: str) -> list[list[dict]]:
    return [[json.loads(l) for l in open(f)]
            for f in sorted(glob.glob(pattern))]


def gold_map(man: dict, split: str) -> dict:
    from ladder.corpus_finer import load_corpus, read_split
    sampling = {k: v for k, v in (man["corpus"].get("sampling") or {}).items()
                if not k.startswith("_")}
    docs = load_corpus(man["corpus"]["root"], **sampling)
    ids = read_split(man["corpus"]["splits_dir"], split)
    return {(m.doc_id, m.spans[0][0]): m.sct[0]
            for d in ids for m in docs[d].mentions if m.sct}


def score(rows: list[dict], gold: dict) -> dict:
    matched = correct = 0
    for r in rows:
        if not r.get("spans"):
            continue
        g = gold.get((r["doc_id"], r["spans"][0][0]))
        if g is None:
            continue
        matched += 1
        correct += (shipped_code(r) == g)
    return {"records": len(rows), "matched": matched, "correct": correct,
            "accuracy": correct / matched if matched else 0.0}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", default="manifest.finer.json")
    ap.add_argument("--split", default="dev")
    ap.add_argument("--base", default="out/tc-finer/*.records.jsonl")
    ap.add_argument("--arm", default="out/tc-finer-typecheck/*.records.jsonl")
    a = ap.parse_args()

    man = json.loads(pathlib.Path(a.manifest).read_text())
    gold = gold_map(man, a.split)
    base_runs, arm_runs = load_runs(a.base), load_runs(a.arm)

    if not base_runs or not arm_runs:
        print(f"  no runs found — base {len(base_runs)}, arm {len(arm_runs)}")
        return 1

    print(f"\n  FiNER · {a.split} · {len(gold)} gold mentions · "
          f"{len(base_runs)} base draws, {len(arm_runs)} arm draws\n")

    # ── 1 · the effect ──────────────────────────────────────────────────
    print("  1 · DID IT CHANGE WHAT SHIPS?")
    print(f"      {'draw':6} {'records':>8} {'matched':>8} {'correct':>8} {'accuracy':>9}")
    for name, runs in (("base", base_runs), ("arm ", arm_runs)):
        for i, rows in enumerate(runs):
            s = score(rows, gold)
            print(f"      {name} {i}  {s['records']:8} {s['matched']:8} "
                  f"{s['correct']:8} {s['accuracy']:9.3f}")
    b = [score(r, gold)["accuracy"] for r in base_runs]
    m = [score(r, gold)["accuracy"] for r in arm_runs]
    if len(b) > 1 and len(m) > 1:
        print(f"\n      base mean {statistics.mean(b):.3f}  "
              f"spread {max(b)-min(b):.3f}")
        print(f"      arm  mean {statistics.mean(m):.3f}  "
              f"spread {max(m)-min(m):.3f}")
        d = statistics.mean(m) - statistics.mean(b)
        print(f"      delta     {d:+.3f}")
        if abs(d) < max(max(b) - min(b), max(m) - min(m)):
            print("      — inside the run-to-run spread. Not separated; say so.")

    # ── 2 · was it right ────────────────────────────────────────────────
    print("\n  2 · WAS IT RIGHT? — every rejection of a CORRECT record is false")
    tot = collections.Counter()
    for rows in arm_runs:
        for r in rows:
            if not r.get("spans"):
                continue
            g = gold.get((r["doc_id"], r["spans"][0][0]))
            if g is None:
                continue
            ch = r.get("checks") or {}
            rejected = ch.get("r1_reason") == R_TYPE_MISMATCH
            tot[(rejected, shipped_code(r) == g)] += 1
    tp, fp = tot[(True, False)], tot[(True, True)]
    print(f"      rejected and WAS wrong   {tp:5}   (correct rejections)")
    print(f"      rejected and WAS right   {fp:5}   (FALSE rejections)")
    print(f"      passed   and was wrong   {tot[(False, False)]:5}")
    print(f"      passed   and was right   {tot[(False, True)]:5}")
    if tp + fp:
        print(f"      precision {tp/(tp+fp):.3f} over {tp+fp} rejections, 3 draws pooled")
        print(f"      false-rejection rate on model output: {fp/(tp+fp):.2%}")
        print("      (on gold, measured before the rung was built: 1.22%)")

    # ── 3 · what rung 2 did with its first real trigger ─────────────────
    print("\n  3 · RUNG 2 HAD A TRIGGER FOR THE FIRST TIME ON THIS CORPUS")
    led = sorted(glob.glob(a.arm.replace(".records.", ".ledger.")))
    outcomes = collections.Counter()
    for f in led:
        for line in open(f):
            row = json.loads(line)
            if row.get("rung") == 2:
                outcomes[row.get("outcome")] += 1
    if outcomes:
        for k, v in outcomes.most_common():
            print(f"      {str(k):16} {v:5}")
        print("      On CADEC rung 2 fired once in 248 and rescued none. A 'no'")
        print("      here is the stronger result: the CADEC 'no' could always be")
        print("      explained by the trigger set being one record.")
    else:
        print("      no rung 2 rows — it never fired")

    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

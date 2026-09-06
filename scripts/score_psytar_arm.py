#!/usr/bin/env python3
"""
score_psytar_arm.py — is the ACCEPT lane as PRECISE on PsyTAR as on CADEC?

THE QUESTION, AND THE ONE IT IS NOT

The gold-side run already answered a different question and the two were briefly
run together, which is recorded as a correction in `docs/decisions.md`:

    lane OCCUPANCY     what share of gold REACHES the lane   CADEC 42.4% · PsyTAR 24.7%
    lane CORRECTNESS   what share of the lane IS RIGHT       CADEC 75-82% · this script

Occupancy is free. Correctness needs the model's own answers, which is what
these three draws are for. Section 11 asks about correctness.

WHAT IS REPORTED, AND WHY THE SPREAD IS NOT OPTIONAL

Three draws, and the per-draw figures are printed beside the pooled one. A lane
correctness of 78% ± 3 and one of 78% ± 20 are different claims, and a mean over
three draws that disagree is a way of hiding that they disagree — the same
defect as a rate over an unnamed set, one level up.

Also reported, and not fused with it:

    · the lane's correctness against the BAND lane's, because a lane that is
      no better than the records it could not vouch for has not separated
      anything. That comparison is the whole point of a lane.
    · what the SEMANTIC check costs here. It is known to encode CADEC's
      annotation guide — |Suicide| and |Antibiotic therapy| are not clinical
      findings — and to reject 37 correct gold records for that reason. The
      run keeps it ON, as shipped, and this reports what the lane would be
      without it. The gap is the price of an inherited precondition, and it is
      a number nobody has for any corpus.

    PYTHONPATH=. python3 scripts/score_psytar_arm.py
"""
from __future__ import annotations

import argparse
import glob
import json
import pathlib
import re
import statistics
import sys
from collections import Counter

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

CADEC_OCCUPANCY = 0.424
CADEC_CORRECTNESS = (0.75, 0.82)
PSYTAR_GOLD_OCCUPANCY = 0.247


def shipped_code(rec: dict):
    """What the system ANSWERED, including an answer rung 5 later withdrew.

    Reading `sct` alone scores the shipping decision rather than the answer,
    and rung 5 abstains on most records — a scorer that trusts it reports zero.
    """
    ch = rec.get("checks") or {}
    code = rec.get("sct") or (ch.get("withheld") or {}).get("sct")
    if isinstance(code, (list, tuple)):
        code = code[0] if code else None
    return code


def score_run(rows, gold) -> dict:
    lanes: dict[str, Counter] = {}
    for r in rows:
        if not r.get("spans"):
            continue
        ch = r.get("checks") or {}
        v = ch.get("r1_verdict") or "—"
        g = gold.get((r["doc_id"], r["spans"][0][0]))
        c = lanes.setdefault(v, Counter())
        c["records"] += 1
        if g is None:
            # No gold at this offset: the model found something the annotators
            # did not mark. Not wrong — unscoreable, and outside the
            # denominator rather than counted against the lane.
            c["no_gold"] += 1
            continue
        c["scored"] += 1
        c["correct"] += shipped_code(r) in g
    return lanes


def main() -> int:
    ap = argparse.ArgumentParser()
    # The FINAL records only. `dev_*.records.jsonl` also matches
    # dev_*.r0.records.jsonl and six siblings, so the first version reported 21
    # "draws" that were 3 draws x 7 per-rung snapshots — identical rows and a
    # 0.0% spread, in the script whose docstring says the spread is not
    # optional. A glob is a denominator too.
    ap.add_argument("--runs", default="out/psytar-d*/dev_model_*[0-9].records.jsonl")
    ap.add_argument("--manifest", default="manifest.psytar.json")
    ap.add_argument("--split", default="dev")
    a = ap.parse_args()

    from ladder.corpus_psytar import load_corpus, read_split

    man = json.loads(pathlib.Path(a.manifest).read_text())
    docs = load_corpus(man["corpus"]["root"], entity=man["corpus"].get("entity", "ADR"))
    ids = read_split(man["corpus"]["splits_dir"], a.split)
    ids = set(ids if isinstance(ids, list) else ids.get("doc_ids", []))
    gold = {(m.doc_id, m.spans[0][0]): m.sct
            for d in ids if d in docs for m in docs[d].mentions}

    # Per-rung snapshots share the stem: dev_model_<ts>.r0.records.jsonl and
    # six siblings all match a naive glob, which reported 21 "draws" that were
    # 3 draws x 7 snapshots — identical rows and a 0.0% spread, in the script
    # whose docstring says the spread is not optional. Filtered by shape rather
    # than by a cleverer glob, because the glob is what got it wrong.
    files = [f for f in sorted(glob.glob(a.runs))
             if not re.search(r"\.r\d+\.records\.jsonl$", f)]
    if not files:
        sys.exit(f"no runs at {a.runs}")

    print(f"\n  PsyTAR · {a.split} · {len(ids)} documents · {len(gold)} gold mentions")
    print(f"  {len(files)} draw(s)\n")

    per_draw = []
    for f in files:
        rows = [json.loads(l) for l in open(f)]
        per_draw.append((f.split("/")[-2], score_run(rows, gold)))

    # ── 1 · the lane, per draw, then pooled ─────────────────────────────
    print("  1 · ACCEPT LANE CORRECTNESS — the number section 11 asks for\n")
    print(f"      {'draw':10} {'records':>8} {'scored':>7} {'correct':>8} {'rate':>8}")
    acc_rates, band_rates = [], []
    for name, lanes in per_draw:
        c = lanes.get("ACCEPT", Counter())
        rate = c["correct"] / c["scored"] if c["scored"] else None
        if rate is not None:
            acc_rates.append(rate)
        b = lanes.get("BAND", Counter())
        if b["scored"]:
            band_rates.append(b["correct"] / b["scored"])
        shown = "—" if rate is None else f"{rate:.1%}"
        print(f"      {name:10} {c['records']:8} {c['scored']:7} "
              f"{c['correct']:8} {shown:>8}")

    if acc_rates:
        mean = statistics.mean(acc_rates)
        spread = max(acc_rates) - min(acc_rates)
        print(f"\n      pooled mean {mean:.1%} · spread {spread:.1%} "
              f"across {len(acc_rates)} draw(s)")
        lo, hi = CADEC_CORRECTNESS
        print(f"      CADEC's lane: {lo:.0%}–{hi:.0%}")
        if spread > 0.10:
            print("\n      ! The draws disagree by more than 10 points. The mean above")
            print("        is a summary of numbers that do not agree, and quoting it")
            print("        alone would hide that.")
        elif lo <= mean <= hi:
            print("\n      → IN RANGE. The lane's PRECISION is a property of the")
            print("        vocabulary; only its SIZE moved (42.4% → 24.7% occupancy).")
            print("        The check works wherever it can reach, and its reach")
            print("        varies by corpus. That STRENGTHENS the article's claim.")
        elif mean < lo:
            print("\n      → BELOW. Precision travels less well than occupancy, and")
            print("        section 11's caution was right. The more interesting")
            print("        result and the one that must not be explained away.")
        else:
            print("\n      → ABOVE CADEC's range. Worth checking the denominator")
            print("        before celebrating: a small scored set inflates easily.")

    # ── 2 · against the lane it must beat ───────────────────────────────
    print("\n  2 · AGAINST THE BAND LANE — a lane no better than what it could")
    print("      not vouch for has separated nothing\n")
    if acc_rates and band_rates:
        am, bm = statistics.mean(acc_rates), statistics.mean(band_rates)
        print(f"      ACCEPT {am:.1%}   BAND {bm:.1%}   "
              f"ratio {am/bm:.2f}×" if bm else "      BAND scored nothing")
        if bm and am <= bm:
            print("\n      ! ACCEPT is NOT better than BAND. Measured once before, on")
            print("        GeoWebNews, where the lane fired at 39.8% and scored worse")
            print("        than the records it declined to endorse.")
    else:
        print("      not enough scored records in one of the lanes")

    # ── 3 · what the inherited semantic check costs ─────────────────────
    print("\n  3 · THE SEMANTIC CHECK — inherited from CADEC's annotation guide\n")
    rejected = Counter()
    for f in files:
        for line in open(f):
            r = json.loads(line)
            ch = r.get("checks") or {}
            if ch.get("r1_reason") == "wrong_semantic_type":
                rejected["rejected"] += 1
                if r.get("spans"):
                    g = gold.get((r["doc_id"], r["spans"][0][0]))
                    if g and shipped_code(r) in g:
                        rejected["and was CORRECT"] += 1
    if rejected:
        print(f"      {dict(rejected)}")
        print("      On gold this check contradicts 37 correct records because")
        print("      |Suicide| and |Antibiotic therapy| are not clinical findings.")
        print("      CADEC's annotators restricted reactions to findings; PsyTAR's")
        print("      did not, so the check is a fact about one corpus's guide.")
    else:
        print("      it did not fire on model output in these runs")

    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

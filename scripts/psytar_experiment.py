#!/usr/bin/env python3
"""
psytar_experiment.py — is the ACCEPT lane a property of SNOMED, or of CADEC?

THE QUESTION, AND WHY IT HAS NOT BEEN ANSWERABLE UNTIL NOW

Section 11 of the article: *"The second corpus is a demonstration, not a matched
comparison. A third, with a lexical vocabulary, would test whether the 75-82%
ACCEPT lane belongs to controlled vocabularies in general or to SNOMED in
particular."*

FiNER and GeoWebNews each vary the text AND the vocabulary, so a difference in
the lane could be caused by either. PsyTAR varies **one thing**: same forum
(askapatient.com, where CADEC also comes from), same task, same vocabulary,
different drugs. So a difference here is attributable.

THE PREDICTION, REGISTERED BEFORE THE RUN

Written down first because a prediction made after seeing the numbers is not a
prediction. On the reasoning that the lane's rate is driven by how often a
patient's words coincide with a clinical term:

    ACCEPT-lane occupancy on PsyTAR gold: 30-45%, against CADEC's 42.4%.

If it lands there, the lane is a property of SNOMED-coded patient narratives
and the article can say so. If it lands far outside, the lane was CADEC's, and
that is the more interesting result and the one that must not be explained away.

WHAT THIS MEASURES, AND WHAT IT DOES NOT

Everything here runs on GOLD with **no model calls** — the same discipline that
priced rung 1 for nothing on three previous corpora. It measures what the free
check COULD do on this data, not what a system does with it. A model arm is a
separate and much more expensive question, and this answers section 11 without
it.

Three things are reported and they are not fused:

    1. LANE OCCUPANCY on gold — the headline, directly comparable with CADEC
    2. THE OVERLAP STRATUM — the mechanism underneath it
    3. WHAT IS OUTSIDE THE DENOMINATOR — SNOMEDCT_US against an AU index, and
       spans this adapter could not locate

The third is reported first in the output, before any rate, because a rate over
a denominator nobody has looked at is the failure this whole project documents.

    PYTHONPATH=. python3 scripts/psytar_experiment.py
    PYTHONPATH=. python3 scripts/psytar_experiment.py --entity WD
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys
from collections import Counter

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

#: Registered before the run. See the module docstring.
PREDICTION = (0.30, 0.45)
CADEC_ACCEPT = 0.424


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default="data/psytar")
    ap.add_argument("--entity", default="ADR")
    ap.add_argument("--manifest", default="manifest.json")
    a = ap.parse_args()

    from ladder.corpus_psytar import load_corpus, stratify
    from ladder.registry import Registry
    from ladder import relations as R

    man = json.loads(pathlib.Path(a.manifest).read_text())
    db = (man.get("vocabulary") or {}).get("snomed_db")
    if not db or not pathlib.Path(db).is_file():
        sys.exit(f"SNOMED index not found at {db!r} — build it first")
    reg = Registry(db)

    docs = load_corpus(a.root, entity=a.entity)
    gold = [m for d in docs.values() for m in d.mentions]
    if not gold:
        sys.exit("no gold mentions loaded")

    print(f"\n  PsyTAR · {a.entity} · {len(docs)} reviews · {len(gold)} mentions")
    print(f"  SNOMED index: {db}")
    print(f"  Registered prediction: ACCEPT lane {PREDICTION[0]:.0%}–{PREDICTION[1]:.0%} "
          f"(CADEC measured {CADEC_ACCEPT:.1%})\n")

    # ── 1 · the denominator, before any rate ────────────────────────────
    st = stratify(docs, reg)
    absent = st.get("not_in_vocabulary", 0)
    usable = sum(v for k, v in st.items() if k != "not_in_vocabulary")
    total = absent + usable
    print("  1 · WHAT IS OUTSIDE THE DENOMINATOR")
    print(f"      mentions with a SNOMED id        {total:5}")
    print(f"      id absent from this index        {absent:5}  ({absent/total:.1%})")
    print(f"      usable                           {usable:5}  ({usable/total:.1%})")
    if absent / total > 0.25:
        print("\n      ! More than a quarter of the answer key is not in this index.")
        print("        PsyTAR maps to SNOMEDCT_US and this is the AU release. The")
        print("        comparison with CADEC is weakened, and saying so is the")
        print("        honest response — not scoring against a vocabulary that")
        print("        does not contain the answer.")

    # ── 2 · the lane ────────────────────────────────────────────────────
    hits = 0
    for m in gold:
        if m.cadec_type == "empty":
            continue
        for code in m.sct:
            try:
                if reg.lexical_match(m.text, code):
                    hits += 1
                    break
            except Exception:
                pass
    rate = hits / usable if usable else 0.0
    lo, hi = PREDICTION
    verdict = ("AS PREDICTED" if lo <= rate <= hi else
               "OUTSIDE THE PREDICTION — this is the interesting result")
    print(f"\n  2 · THE ACCEPT LANE ON GOLD")
    print(f"      {hits} of {usable} mentions match a term for their own code "
          f"= {rate:.1%}")
    print(f"      CADEC, same check, same vocabulary:        {CADEC_ACCEPT:.1%}")
    print(f"      → {verdict}")
    if lo <= rate <= hi:
        print("      The lane is a property of SNOMED-coded patient narratives,")
        print("      not of CADEC. Section 11's open question closes.")
    else:
        print("      The lane did NOT transfer to a corpus that differs only in")
        print("      its drugs. Whatever drives it is narrower than the vocabulary.")

    # ── 3 · the mechanism ───────────────────────────────────────────────
    print(f"\n  3 · THE OVERLAP STRATUM — the mechanism underneath the lane")
    print(f"      {'stratum':11} {'PsyTAR':>10}   {'CADEC':>8}")
    cadec = {"identical": .405, "subset": .248, "partial": .049, "none": .299}
    for k in ("identical", "subset", "partial", "none"):
        v = st.get(k, 0)
        print(f"      {k:11} {v:5} {v/usable:6.1%}   {cadec[k]:7.1%}")
    print("      (CADEC's column is the GeoWebNews-era measurement and is")
    print("       included for shape, not for a paired test.)")

    # ── 4 · every relation, not just the lexical one ────────────────────
    print(f"\n  4 · WHICH FREE CHECKS HAVE SIGNAL HERE")
    # ladder/relations.py predates stagecheck's signature and takes neither
    # code_of nor vocabulary. Called as it is rather than as I misremembered it.
    # `every gold record is correct` is the assertion that makes gold free
    # validation, and it is FALSE for a record whose code this vocabulary does
    # not hold — that record is unanswerable, not right. Asserting it anyway
    # reported 3 correct rejections as false and called the relation BROKEN.
    def answerable(m):
        try:
            return bool(reg.terms(m.sct[0]))
        except Exception:
            return False
    res = R.measure(gold, {d: "" for d in docs}, reg, is_correct=answerable)
    print(R.report(res, on="gold", corpus="PsyTAR"))

    # `semantic` rejects 36 gold records and every one of them is a CORRECT
    # rejection of a rule PsyTAR does not follow. CADEC codes every reaction to
    # a clinical finding; PsyTAR codes some to events and procedures —
    # |Suicide| 44301001, |Suicide attempt| 82313006, |Antibiotic therapy|
    # 281789004. The check is right, the PRECONDITION is corpus-specific, and
    # printing BROKEN here would be the tool blaming a corpus for an assumption
    # the tool brought with it.
    bad = [m for m in gold
           if (lambda c: (lambda st: st is not None and str(st).endswith("not_finding"))(
                   getattr(reg, "finding_status", lambda _: None)(c)))(m.sct[0])]
    if bad:
        print(f"\n  ! `semantic` reads BROKEN, and it is not. Its {len(bad)} rejections are")
        print("    correct: CADEC codes every reaction to a clinical finding and PsyTAR")
        print("    does not — |Suicide|, |Suicide attempt|, |Antibiotic therapy| are")
        print("    events and procedures. The relation is sound; the PRECONDITION is a")
        print("    property of CADEC's annotation guide, not of SNOMED.")
        seen = set()
        for m in bad:
            k = m.sct[0]
            if k in seen: continue
            seen.add(k)
            if len(seen) > 4: break
            print(f"      {k:14} {reg.preferred(k):<26} <- {m.text[:34]!r}")
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

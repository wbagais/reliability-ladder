#!/usr/bin/env python3
"""
psytar_locate_audit.py — what the 573 unlocated spans actually are.

WHY THIS RUNS BEFORE ANY GPU TIME

PsyTAR ships spans as TEXT, not offsets. `corpus_psytar.load_corpus` finds each
one in its sentence with a literal string search, and 573 of 4,687 do not match.

For the gold-side result that is attrition: 12% of records leave the
denominator with a stated reason, and the ACCEPT-lane figure is over what
remains.

**For a model arm it is worse than attrition.** Rung 0 extracts spans and the
scorer compares them against gold spans — so if this module is PLACING the gold
spans, part of the answer key is our construction, and a span-F1 measured
against it partly measures the locator. That is the same defect as scoring the
geo arm against invented ids, which cost a day and produced a number that had
to be thrown away.

So: find out what the 573 are before spending anything. Three outcomes and they
lead to different decisions.

    WHITESPACE OR CASE      fixable, and the fix is safe
    A DIFFERENT SENTENCE    the annotation points at the wrong index; findable
    GENUINELY ABSENT        the span text does not occur in the review at all,
                            and no locator can place it

If most are the first, the arm is viable. If most are the third, PsyTAR can
carry a gold-side finding and must not carry a span-F1 number, and saying so is
the result.

    PYTHONPATH=. python3 scripts/psytar_locate_audit.py
"""
from __future__ import annotations

import argparse
import pathlib
import re
import sys
from collections import Counter, defaultdict

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))


def norm(s: str) -> str:
    """Whitespace-collapsed, lowercased. The loosest comparison worth trying."""
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default="data/psytar")
    ap.add_argument("--entity", default="ADR")
    ap.add_argument("--examples", type=int, default=8)
    a = ap.parse_args()

    import openpyxl
    from ladder.corpus_psytar import SHEETS, _rows

    ident_sheet, _, _ = SHEETS[a.entity]
    wb = openpyxl.load_workbook(pathlib.Path(a.root) / "PsyTAR_dataset.xlsx",
                                read_only=True, data_only=True)

    sentences: dict[str, dict[int, str]] = defaultdict(dict)
    for r in _rows(wb["Sentence_Labeling"]):
        drug = str(r.get("drug_id") or "").strip()
        try:
            idx = int(str(r.get("sentence_index")).strip())
        except (TypeError, ValueError):
            continue
        sentences[drug][idx] = str(r.get("sentences") or "")

    cols = [f"{a.entity}{i}" for i in range(1, 11)]
    why = Counter()
    examples: dict[str, list] = defaultdict(list)
    total = 0

    for r in _rows(wb[ident_sheet]):
        drug = str(r.get("drug_id") or "").strip()
        try:
            idx = int(str(r.get("sentence_index")).strip())
        except (TypeError, ValueError):
            continue
        sent = sentences.get(drug, {}).get(idx)
        if sent is None:
            continue
        review = "\n".join(sentences[drug][k] for k in sorted(sentences[drug]))
        for c in cols:
            txt = str(r.get(c) or "").strip()
            if not txt:
                continue
            total += 1
            if txt in sent:
                why["located exactly"] += 1
                continue
            # 1 · whitespace or case only
            if norm(txt) in norm(sent):
                why["differs by whitespace or case"] += 1
                examples["differs by whitespace or case"].append((txt, sent))
                continue
            # 2 · right review, wrong sentence index
            if txt in review:
                why["in the review, not that sentence"] += 1
                examples["in the review, not that sentence"].append((txt, sent))
                continue
            if norm(txt) in norm(review):
                why["in the review after normalising"] += 1
                examples["in the review after normalising"].append((txt, sent))
                continue
            # 3 · genuinely absent
            why["ABSENT from the review"] += 1
            examples["ABSENT from the review"].append((txt, sent))

    print(f"\n  PsyTAR · {a.entity} · {total} annotated spans\n")
    for k, v in why.most_common():
        mark = " !" if k.startswith("ABSENT") else "  "
        print(f"  {mark} {k:34} {v:5}  {v/total:6.1%}")

    unloc = total - why["located exactly"]
    print(f"\n  {unloc} do not match exactly ({unloc/total:.1%}).")
    fixable = (why["differs by whitespace or case"]
               + why["in the review, not that sentence"]
               + why["in the review after normalising"])
    absent = why["ABSENT from the review"]
    if unloc:
        print(f"  Of those, {fixable} are locatable with a better search "
              f"({fixable/unloc:.0%}) and {absent} are not ({absent/unloc:.0%}).")

    print()
    if absent / max(total, 1) < 0.02:
        print("  → A model arm is viable. Fewer than 2% of gold spans cannot be")
        print("    placed at all, which is comparable to the offset defects found")
        print("    in GeoWebNews and TR-News and can be dropped with a reason.")
    else:
        print("  → A model arm on this corpus would score partly against OUR")
        print("    locator. PsyTAR can carry the gold-side lane finding and must")
        print("    NOT carry a span-F1 number. That is a result, not a blocker.")

    for k in ("differs by whitespace or case", "in the review, not that sentence",
              "ABSENT from the review"):
        if not examples[k]:
            continue
        print(f"\n  {k}:")
        for txt, sent in examples[k][:a.examples]:
            print(f"    span {txt!r}")
            print(f"    sent {sent[:96]!r}")
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

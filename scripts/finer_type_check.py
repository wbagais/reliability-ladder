#!/usr/bin/env python3
"""
finer_type_check.py — a free check for the corpus where the free check cannot fire.

THE PROBLEM THIS ADDRESSES

Rung 1's lexical check asks whether the extracted span's words appear in the
code's own name. On FiNER-139 that is a STRUCTURAL zero, not a low score: the
spans are numerals ("47.6") and the tags are English phrases
("EffectiveIncomeTaxRateContinuingOperations"), so the two are drawn from
disjoint token vocabularies and the intersection is empty for every possible
run. Measured: ACCEPT 0 of 704, and rung 1 rejected 1 record in 704, which left
rung 2 with nothing to correct and rung 5 with nothing to act on. Four rungs
went quiet at once because one check had no signal.

A better model does not fix this. A better prompt does not fix this. A number
cannot share a word with a name.

THE SIGNAL THAT IS AVAILABLE INSTEAD

Both sides carry TYPE information, and neither side's type is a word the other
side happens to contain:

    the tag name        ...Percentage, ...Rate, ...Amount, ...Shares, ...Date
    the span's context  "1.50 %"  "$ 19.4 million"  "1,350,000 shares"
                        "January 9 , 2023"  "6.8 years"

A percentage tag on a span followed by "shares" is PROVABLY wrong, in the same
way a retired SNOMED code is provably wrong — deterministically, at zero model
cost, without knowing the right answer. That is exactly what rung 1 is for.

WHAT THIS SCRIPT MEASURES, and in which order

The discipline is rung 1's own, and the order matters:

  1. FALSE-REJECTION RATE ON GOLD, first and before anything else. Every
     disagreement between a gold span's type and its gold tag's type is a FALSE
     rejection by construction, because gold is right by definition. A check
     that rejects a perfect answer set is worse than no check — CADEC's went
     from 9.3% to 0.13% by being measured this way, and the rate is free.

  2. COVERAGE. A check that fires on 3% of records is not worth wiring in, no
     matter how precise. How many mentions can be typed at all?

  3. DISCRIMINATING POWER. The point is not only to reject: a type narrows the
     139-tag menu. If "rate" admits 12 tags, the pick step chooses from 12
     rather than 139, and that is a retrieval improvement obtained for free.

Nothing here calls a model. Run it, read the false-rejection rate, and only
then decide whether the check is worth building.

    PYTHONPATH=. python3 scripts/finer_type_check.py
"""
from __future__ import annotations

import argparse
import collections
import json
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from ladder.corpus_finer import load_corpus, read_split

#: A span's type, read from the span itself and the few characters around it.
#: Ordered: the first rule that matches wins, so the specific ones come first.
SPAN_RULES = [
    ("date",     r"^(january|february|march|april|may|june|july|august|september"
                 r"|october|november|december)\b|^\d{4}$"),
    ("duration", None),      # handled by context below
    ("percent",  None),
    ("money",    None),
    ("count",    None),
]

#: The type a TAG claims, from the words in its name. Checked in order, so a tag
#: naming both a rate and an amount is read as whichever appears here first.
#: ORDER IS LOAD-BEARING. A tag naming both a quantity and a currency word is
#: read as whichever appears first here, and several do: the antidilutive tags
#: contain both "Securities" and "Amount". Counts before money for that reason.
TAG_TYPE = [
    ("percent",  r"Percentage|Rate(?!d)|BasisSpread|Ratio"),
    ("date",     r"Date\b|MaturityDate|ExpirationDate"),
    ("duration", r"Term\b|Life\b|Period\b|RemainingLease|WeightedAverageRemaining"),
    ("count",    r"Shares|NumberOf|Securities|Units\b|Segments|Employees|Stores"),
    ("money",    r"Amount|Value|Expense|Cost|Proceeds|Income|Loss|Payment|Debt"
                 r"|Goodwill|Assets|Liability|Liabilities|Revenue|Charges|Cash"
                 r"|Capacity|Investment|Consideration|Impairment|Compensation"),
]


def tag_type(tag: str) -> str | None:
    for name, pat in TAG_TYPE:
        if re.search(pat, tag):
            return name
    return None


def span_type(text: str, before: str, after: str) -> str | None:
    """Type the span from its own shape and the characters either side.

    Deliberately conservative: it returns None rather than guessing. An
    unconfident check that abstains is usable; one that guesses is a source of
    false rejections, which is the failure mode this whole exercise exists to
    avoid.
    """
    t = text.strip()
    a = after[:24].lower()
    b = before[-28:].lower()

    if re.match(r"^(january|february|march|april|may|june|july|august|"
                r"september|october|november|december)\b", t.lower()):
        return "date"
    if re.match(r"^(19|20)\d{2}$", t):
        return "date"
    if re.match(r"^\s*%", after) or "percent" in a[:12]:
        return "percent"
    if re.search(r"\byears?\b|\bmonths?\b|\bdays?\b", a[:14]):
        return "duration"
    # "per share" is a UNIT, not a count — "$ 90.07 per share" is a price.
    # Checked before the count rule because the count rule would claim it.
    # A currency symbol immediately before the span outranks anything after it.
    # "$ 6.1 billion in share repurchases" is money; the word "share" three
    # tokens later does not make it a count.
    if re.search(r"\$\s*$", before[-4:]):
        return "money"
    if re.search(r"\bper\s+(share|unit)\b", a[:18]):
        return "money"
    if re.search(r"\bshares?\b|\bunits?\b|\bsecurities\b|\bemployees\b"
                 r"|\bsegments\b|\bstores\b|\bproperties\b", a[:22]):
        return "count"
    if "$" in b[-6:] or re.search(r"\b(million|billion|thousand)\b", a[:16]):
        return "money"
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", default="manifest.finer.json")
    ap.add_argument("--split", default="test")
    ap.add_argument("--examples", type=int, default=8)
    a = ap.parse_args()

    man = json.loads(pathlib.Path(a.manifest).read_text())
    sampling = {k: v for k, v in (man["corpus"].get("sampling") or {}).items()
                if not k.startswith("_")}
    docs = load_corpus(man["corpus"]["root"], **sampling)
    ids = read_split(man["corpus"]["splits_dir"], a.split)
    gold = [(m, docs[m.doc_id].text) for d in ids for m in docs[d].mentions]

    print(f"\n  FiNER-139 · {a.split} split · {len(gold)} gold mentions")
    print(f"  Every disagreement below is a FALSE rejection by construction.\n")

    typed = agree = disagree = untyped_span = untyped_tag = 0
    by_type = collections.Counter()
    mismatches = []

    for m, text in gold:
        i, j = m.spans[0]
        st = span_type(m.text, text[max(0, i - 40):i], text[j:j + 40])
        tt = tag_type(m.sct[0]) if m.sct else None
        if st is None:
            untyped_span += 1
            continue
        if tt is None:
            untyped_tag += 1
            continue
        typed += 1
        by_type[st] += 1
        if st == tt:
            agree += 1
        else:
            disagree += 1
            mismatches.append((m.text, st, m.sct[0], tt,
                               text[max(0, i - 40):j + 24].replace("\n", " ")))

    n = len(gold)
    print("  1 · FALSE-REJECTION RATE — the number that decides everything")
    if typed:
        print(f"      {disagree} of {typed} typed mentions disagree with their own gold tag "
              f"= {disagree/typed:.2%}")
        verdict = ("USABLE — comparable to rung 1's 0.13% on CADEC" if disagree/typed < 0.02
                   else "MARGINAL — above CADEC's 0.13%, tighten the rules first"
                   if disagree/typed < 0.05
                   else "NOT USABLE — it rejects a perfect answer set too often")
        print(f"      {verdict}")
    else:
        print("      nothing could be typed — the check has no signal here")

    print(f"\n  2 · COVERAGE — how much of the corpus the check can speak about")
    print(f"      typed on both sides   {typed:4} of {n}  ({typed/n:.1%})")
    print(f"      span not typeable     {untyped_span:4}  ({untyped_span/n:.1%})")
    print(f"      tag not typeable      {untyped_tag:4}  ({untyped_tag/n:.1%})")
    print(f"      by span type: {dict(by_type)}")

    print(f"\n  3 · DISCRIMINATING POWER — how far a type narrows the 139-tag menu")
    from ladder.vocab_finer import load
    v = load(man["corpus"]["root"])
    tags = sorted(v.all_codes())
    buckets = collections.Counter(tag_type(t) or "untyped" for t in tags)
    for t, c in buckets.most_common():
        share = c / len(tags)
        note = "" if t == "untyped" else f"  → menu of {c} instead of {len(tags)}"
        print(f"      {t:9} {c:4} tags  ({share:5.1%}){note}")

    if mismatches:
        print(f"\n  the {min(a.examples, len(mismatches))} disagreements to read before trusting any of the above")
        for txt, st, tag, tt, ctx in mismatches[:a.examples]:
            print(f"      {txt!r:16} typed {st:9} but {tag[:44]:44} is {tt}")
            print(f"          ...{ctx}")

    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

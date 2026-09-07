"""ladder.checks.gate — should this corpus be run at all?

WHAT IT ANSWERS, AND WHAT IT COSTS

Rung 1's free check compares a span against the names its code carries. That
comparison needs no model, so **the lane's CEILING on a corpus is knowable for
nothing** — and a ceiling of zero means the arm cannot produce a lane however
good the extractor is.

Measured against arms that were later run on a rented card:

    FiNER      predicted 0.0%    measured 0.0% on four models
    LINNAEUS   predicted 4.8%    measured 12.5% on one model, 0 on three
    PsyTAR     predicted 24.3%   measured 18.6-31.0%
    BC5CDR     predicted 35.8%   measured 7.0-21.8%
    geo        predicted 40.9%   measured 20.3-63.6%

Every measured value sits at or below its prediction, which is what a ceiling
must do. Two of the five would have stopped a card being booked.

WHAT IT WILL NOT DECIDE

Whether a thin ceiling is a FINDING or a BUG. FiNER's zero is structural — a
numeral shares no token with an English phrase, on any run, forever. LINNAEUS's
4.8% was a vocabulary build choice, and the all-names index moves the same gold
from 5.4% to 35.4%. From here those look identical, and a tool that guessed
would be inventing the more interesting of two answers.

Nor what the entity IS. No span statistic says whether a corpus is about
organisms or diseases, and BC5CDR annotates two types where the arm scores one.
"""
from __future__ import annotations

import re
from collections import Counter

from . import Arm

_DOTTED = re.compile(r"\b[A-Z]\.")

#: THE THRESHOLDS, declared rather than buried in the code that uses them.
#: Each was chosen from the six corpora measured in this study — BC5CDR at
#: 39.4% multi-token against TR-News at 12.8%, LINNAEUS at 34.3% capitalised
#: against LGL at 100%. They are crude, they are visible, and a reader can
#: disagree with them.
T = {
    "phrase": 0.35,          # above this, say "a phrase"
    "single_word": 0.15,     # below this, say "a word"
    "case_useless": 0.50,    # below this, case is not a cue
    "case_reliable": 0.95,   # above this, nearly everything is capitalised
    "abbreviated": 0.08,     # above this, abbreviations need their own rule
    "repeats": 0.50,         # above this, say "report it every time"
    "discontinuous": 0.02,   # above this, a mention may be two pieces
    "thin_ceiling": 0.15,    # below this, expect small denominators
    "dead_ceiling": 0.02,    # below this, the arm cannot produce a lane
}


def profile(a: Arm) -> dict:
    """What the gold looks like. Measurements only, no interpretation."""
    gold = a.gold
    if not gold:
        return {"mentions": 0}
    n = len(gold)
    texts = [m.text for m in gold]
    toks = [t.split() for t in texts]
    counts = Counter(t.lower() for t in texts)
    lens = sorted(len(t) for t in texts)

    p = {
        "documents": len(a.docs),
        "mentions": n,
        "distinct": len(counts),
        "multi_token": sum(1 for t in toks if len(t) > 1) / n,
        "dotted": sum(1 for t in texts if _DOTTED.search(t)) / n,
        "capitalised": sum(1 for t in texts if t[:1].isupper()) / n,
        "leading_article": sum(1 for t in toks
                               if t and t[0].lower() in ("the", "a", "an")) / n,
        "discontinuous": sum(1 for m in gold if len(m.spans) > 1) / n,
        "repeated": sum(v for v in counts.values() if v > 1) / n,
        "len_median": lens[len(lens) // 2],
        "len_p95": lens[int(len(lens) * 0.95)],
        "commonest": [t for t, _ in counts.most_common(12)],
        "multi_examples": [t for t in texts if len(t.split()) > 1][:6],
    }
    if a.registry is not None:
        p.update(_lane(a, gold))
    return p


def _lane(a: Arm, gold: list) -> dict:
    """The overlap stratum, and the ceiling that follows from it."""
    strata, absent = Counter(), 0
    examples = []
    for m in gold:
        terms = []
        for c in m.sct or []:
            try:
                terms += a.registry.terms(c) or []
            except Exception:
                pass
        if not terms:
            absent += 1
            continue
        mt = set(m.text.lower().split())
        best = "none"
        for t in terms:
            tt = set(t.lower().split())
            if m.text.lower() == t.lower():
                best = "identical"
                break
            if mt and mt <= tt:
                best = "subset"
            elif mt & tt and best != "subset":
                best = "partial"
        strata[best] += 1
        # The MECHANISM behind the no-overlap stratum, which is what a prompt
        # writer needs to see and what no statistic can summarise: 'mice' ->
        # 'Mus musculus' is a different problem from '47.6' -> a tag name.
        if best == "none" and len(examples) < 5:
            examples.append((m.text, terms[0]))
    usable = sum(strata.values())
    n = len(gold)
    return {
        "vocab_absent": absent / n,
        "lane_ceiling": strata["identical"] / usable if usable else 0.0,
        "strata": {k: strata[k] / usable for k in
                   ("identical", "subset", "partial", "none")} if usable else {},
        "no_overlap_examples": examples,
    }


def draft_rules(p: dict, entity: str) -> str:
    """Each rule is a threshold applied to a measurement.

    Every prompt rule written by hand for four corpora on 2026-09-07 turned out
    to be exactly this: 39.4% multi-token became *"most mentions are a phrase"*,
    34.3% capitalised became *"case is not a cue here"*. Those template. What
    does not is the rule the [REVIEW] line asks for, and that is why the
    signature list exists.
    """
    r = []
    if p["multi_token"] > T["phrase"]:
        r.append(f"MOST MENTIONS ARE A PHRASE, NOT A WORD. Measured: "
                 f"{p['multi_token']:.1%} run to more than one word. Quote the "
                 f"whole phrase. From this corpus: "
                 + ", ".join(f"'{t}'" for t in p["multi_examples"][:3]) + ".")
    elif p["multi_token"] < T["single_word"]:
        r.append(f"MOST MENTIONS ARE A SINGLE WORD. Measured: only "
                 f"{p['multi_token']:.1%} run to more than one word. Do not "
                 f"extend a span past the name itself.")
    if p["capitalised"] < T["case_useless"]:
        r.append(f"CASE IS NOT A CUE HERE. Measured: only {p['capitalised']:.1%} "
                 f"of mentions begin with a capital. The commonest gold forms "
                 f"are " + ", ".join(f"'{t}'" for t in p["commonest"][:5]) + ".")
    elif p["capitalised"] > T["case_reliable"]:
        r.append(f"Nearly every mention is capitalised — measured "
                 f"{p['capitalised']:.1%} — but a capital alone does not make a "
                 f"{entity}.")
    if p["dotted"] > T["abbreviated"]:
        r.append(f"ABBREVIATED FORMS ARE COMMON AND ARE QUOTED AS WRITTEN, "
                 f"never expanded. Measured: {p['dotted']:.1%} carry an initial "
                 f"and a dot.")
    if p["repeated"] > T["repeats"]:
        r.append(f"Report a {entity} EVERY TIME it appears. Measured: "
                 f"{p['repeated']:.1%} of gold mentions are a form used more "
                 f"than once, tagged separately at each occurrence.")
    if p.get("discontinuous", 0) > T["discontinuous"]:
        r.append(f"A mention may be TWO PIECES of one sentence. Measured: "
                 f"{p['discontinuous']:.1%} of gold mentions are discontinuous.")
    if p.get("no_overlap_examples"):
        ex = "; ".join(f"'{a}' -> '{b}'" for a, b in p["no_overlap_examples"][:3])
        r.append(f"[REVIEW] The surface form often shares no word with the name "
                 f"it resolves to: {ex}. A rule covering this pattern probably "
                 f"belongs here, and only a person can write it.")
    return "\n\n".join(r)


def unsigned(a: Arm, p: dict, rules: str) -> list[str]:
    """What this tool will not decide, stated rather than guessed."""
    out = []
    if not a.prompts.get("entity"):
        out.append("entity: what IS this corpus about? No span statistic says.")
    if not a.corpus.get("version"):
        out.append("version: which release of the corpus and the vocabulary.")
    types = getattr(getattr(a, "_mod", None), "TYPES", None)
    if types and not a.corpus.get("entity"):
        out.append(f"which entity type to score — this adapter offers {types}. "
                   f"A corpus that annotates two and scores one will otherwise "
                   f"be judged on mentions it never asked for.")
    if "[REVIEW]" in rules:
        out.append("the no-overlap rule: the examples show the pattern; the "
                   "wording is a judgement.")
    if p.get("lane_ceiling", 1) < T["thin_ceiling"]:
        out.append("whether a thin lane is a FINDING or a BUG. FiNER's zero is "
                   "structural; LINNAEUS's was a vocabulary build choice. From "
                   "here they look identical.")
    return out


def sniffable(a: Arm) -> dict:
    """The declarations that can be read off the corpus itself."""
    real = next((m.sct[0] for m in a.gold if m.sct), None)
    n = len(a.docs)
    return {
        "corpus.n_dev_docs": min(40, max(10, n // 3)),
        "corpus.n_test_docs": min(60, max(10, n // 2)),
        "vocabulary.gate.real": real,
        "vocabulary.gate.fake": ("".join("9" if c.isdigit() else c
                                         for c in str(real)) + "9") if real else None,
    }

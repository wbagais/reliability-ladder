#!/usr/bin/env python3
"""
gatecheck.py — should this corpus be run at all?

One of three checks, each at a different moment:

    gatecheck    should I run this?              before booking a card
    crosscheck   is it what I declared?          first line of every run
    stagecheck   did the run mean anything?      after

gatecheck and crosscheck know what a corpus is. stagecheck does not, and
should not.

WHAT THIS REPLACES

Adding a corpus to this study has cost roughly a day each time, and the cost was
never the code. It was nine things that had to be declared and had no list:
adapter registration, a vocabulary index, gate codes, split sizes, loader
options, a version string, few-shot ids from the right pool, prompt slots, and
an entity-type decision. Miss any one and **the run succeeds and the numbers are
meaningless** — twelve cells of the 2026-09-06 matrix were produced by a model
asked to find adverse drug reactions in papers about species.

This reads the corpus and the vocabulary and produces:

    1. a measured PROFILE            — what the gold actually looks like
    2. a PREDICTED LANE              — what rung 1 could do here, before any spend
    3. a DRAFT prompt block          — templated from the measurements
    4. a DRAFT manifest patch        — gate codes, split sizes, few-shot ids
    5. a SIGNATURE list              — what it will not decide

THE BOUNDARY, STATED

Every prompt rule written by hand for the four corpora on 2026-09-07 turned out
to be a threshold applied to a measurement: 39.4% multi-token became *"most
mentions are a phrase"*, 34.3% capitalised became *"case is not a cue here"*,
18.0% dotted became the abbreviation rule. Those template.

What does not template is **what the entity is**. No amount of span statistics
says whether a corpus is about organisms or diseases, and BC5CDR annotates two
types where the arm must score one. The tool asks; it does not guess.

It also will not decide whether a low predicted lane is a **finding** or a
**bug**. FiNER's 0% is structural and correct; LINNAEUS's 5.4% was a vocabulary
build choice. Both look identical from here.

    PYTHONPATH=. python3 scripts/prep_corpus.py --manifest manifest.foo.json
    PYTHONPATH=. python3 scripts/prep_corpus.py --manifest manifest.foo.json --write
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys
from collections import Counter

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

_DOTTED = re.compile(r"\b[A-Z]\.")


# ── the measurements ──────────────────────────────────────────────────
def profile(docs, registry=None) -> dict:
    gold = [m for d in docs.values() for m in d.mentions]
    if not gold:
        return {"mentions": 0}
    n = len(gold)
    texts = [m.text for m in gold]
    toks = [t.split() for t in texts]
    counts = Counter(t.lower() for t in texts)
    lens = sorted(len(t) for t in texts)

    p = {
        "documents": len(docs),
        "mentions": n,
        "distinct": len(counts),
        "multi_token": sum(1 for t in toks if len(t) > 1) / n,
        "dotted": sum(1 for t in texts if _DOTTED.search(t)) / n,
        "capitalised": sum(1 for t in texts if t[:1].isupper()) / n,
        "leading_article": sum(1 for t in toks if t and t[0].lower() in
                               ("the", "a", "an")) / n,
        "discontinuous": sum(1 for m in gold if len(m.spans) > 1) / n,
        "repeated": sum(v for v in counts.values() if v > 1) / n,
        "len_median": lens[len(lens) // 2],
        "len_p95": lens[int(len(lens) * 0.95)],
        "commonest": [t for t, _ in counts.most_common(12)],
        "multi_examples": [t for t in texts if len(t.split()) > 1][:6],
    }

    # ── THE PREDICTED LANE, and it is the whole reason to run this early ──
    # Rung 1's free check compares the surface form against the names its code
    # carries. That comparison needs no model, so the lane's CEILING on this
    # corpus is knowable for nothing — and a 0% ceiling means the arm cannot
    # produce a lane however good the model is. FiNER's zero was structural;
    # LINNAEUS's 5.4% was a vocabulary build choice. Knowing which BEFORE
    # spending is the difference between a finding and a wasted card.
    if registry is not None:
        strata = Counter()
        absent = 0
        for m in gold:
            terms = []
            for c in m.sct or []:
                try:
                    terms += registry.terms(c) or []
                except Exception:
                    pass
            if not terms:
                absent += 1
                continue
            best = "none"
            mt = set(m.text.lower().split())
            for t in terms:
                tt = set(t.lower().split())
                if m.text.lower() == t.lower():
                    best = "identical"; break
                if mt and mt <= tt:
                    best = "subset"
                elif mt & tt and best not in ("subset",):
                    best = "partial"
            strata[best] += 1
        usable = sum(strata.values())
        p["vocab_absent"] = absent / n
        p["lane_ceiling"] = strata["identical"] / usable if usable else 0.0
        p["strata"] = {k: strata[k] / usable for k in
                       ("identical", "subset", "partial", "none")} if usable else {}
        # The mechanism behind the no-overlap stratum, which is what a prompt
        # writer needs to see. Printed, never interpreted.
        p["no_overlap_examples"] = []
        for m in gold:
            if len(p["no_overlap_examples"]) >= 5:
                break
            for c in m.sct or []:
                try:
                    t = (registry.terms(c) or [None])[0]
                except Exception:
                    t = None
                if t and not (set(m.text.lower().split()) & set(t.lower().split())):
                    p["no_overlap_examples"].append((m.text, t))
                    break
    return p


# ── the draft prompt, templated from thresholds ───────────────────────
#: THE THRESHOLDS, declared rather than buried. Each was chosen from the six
#: corpora measured in this study — BC5CDR at 39.4% multi-token against
#: TR-News at 12.8%, LINNAEUS at 34.3% capitalised against LGL at 100%. They
#: are crude, they are visible, and a reader can disagree with them.
T = {"phrase": 0.35, "single_word": 0.15, "case_useless": 0.50,
     "case_reliable": 0.95, "abbreviated": 0.08, "repeats": 0.50,
     "discontinuous": 0.02}


def draft_rules(p: dict, entity: str) -> str:
    """Each rule is a threshold applied to a measurement. Nothing here is a
    judgement about the corpus — which is exactly why it needs a signature."""
    r = []
    if p["multi_token"] > T["phrase"]:
        r.append(f"MOST MENTIONS ARE A PHRASE, NOT A WORD. Measured: "
                 f"{p['multi_token']:.1%} run to more than one word. "
                 f"Quote the whole phrase. Examples from this corpus: "
                 + ", ".join(f"'{t}'" for t in p["multi_examples"][:3]) + ".")
    elif p["multi_token"] < T["single_word"]:
        r.append(f"MOST MENTIONS ARE A SINGLE WORD. Measured: only "
                 f"{p['multi_token']:.1%} run to more than one word. Do not "
                 f"extend a span past the name itself.")
    if p["capitalised"] < T["case_useless"]:
        r.append(f"CASE IS NOT A CUE HERE. Measured: only "
                 f"{p['capitalised']:.1%} of mentions begin with a capital. "
                 f"The commonest gold forms are "
                 + ", ".join(f"'{t}'" for t in p["commonest"][:5]) + ".")
    elif p["capitalised"] > T["case_reliable"]:
        r.append(f"Nearly every mention is capitalised — measured "
                 f"{p['capitalised']:.1%} — but a capital alone does not make "
                 f"a {entity}.")
    if p["dotted"] > T["abbreviated"]:
        r.append(f"ABBREVIATED FORMS ARE COMMON AND ARE QUOTED AS WRITTEN, "
                 f"never expanded. Measured: {p['dotted']:.1%} of mentions "
                 f"carry an initial and a dot.")
    if p["repeated"] > T["case_useless"]:
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


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--write", action="store_true",
                    help="write the draft patch into the manifest")
    a = ap.parse_args()

    from ladder.run import _corpus_for, _corpus_opts, _corpus_root, _vocab_for

    man = json.loads(pathlib.Path(a.manifest).read_text())
    mod = _corpus_for(man)
    docs = mod.load_corpus(_corpus_root(man), **_corpus_opts(man))
    try:
        reg = _vocab_for(man)
    except Exception as exc:
        print(f"  no vocabulary: {exc}")
        reg = None
    p = profile(docs, reg)
    name = (man.get("corpus") or {}).get("name", "?")

    print(f"\n  ── {name} · {p['documents']} documents · {p['mentions']} mentions\n")
    for k in ("multi_token", "dotted", "capitalised", "leading_article",
              "discontinuous", "repeated"):
        print(f"      {k:18} {p[k]:6.1%}")
    print(f"      {'length med / p95':18} {p['len_median']:3} / {p['len_p95']}")
    print(f"      commonest: " + ", ".join(f"'{t}'" for t in p["commonest"][:8]))

    if "lane_ceiling" in p:
        print(f"\n  ── PREDICTED FREE-CHECK LANE, on gold, no model\n")
        for k, v in p["strata"].items():
            print(f"      {k:12} {v:6.1%}")
        print(f"      absent from vocabulary  {p['vocab_absent']:.1%}")
        c = p["lane_ceiling"]
        print(f"\n      CEILING {c:.1%} — the most the free check could endorse here.")
        if c < T["discontinuous"]:
            print("      ! Under 2%. This arm CANNOT produce a lane, however good")
            print("        the model is. That is either structural (a numeral against")
            print("        an English phrase) or a vocabulary build choice — and this")
            print("        tool cannot tell those apart. Decide before spending.")
        elif c < T["single_word"]:
            print("      ! Thin. Expect a small lane and small denominators.")

    entity = (man.get("corpus") or {}).get("prompts", {}).get("entity_short", "MENTION")
    print(f"\n  ── DRAFT RULES (entity: {entity})\n")
    print("      " + draft_rules(p, entity).replace("\n", "\n      "))

    # ── what it will not decide ──────────────────────────────────────
    print(f"\n  ── REQUIRES A SIGNATURE — this tool will not guess\n")
    unsigned = []
    c = (man.get("corpus") or {})
    if not c.get("prompts", {}).get("entity"):
        unsigned.append("entity: what IS this corpus about? No span statistic says.")
    if not c.get("version"):
        unsigned.append("version: which release of the corpus and vocabulary.")
    if not c.get("entity") and hasattr(mod, "TYPES"):
        unsigned.append(f"which entity type to score — this adapter offers "
                        f"{getattr(mod, 'TYPES')}. A corpus that annotates two "
                        f"and scores one will otherwise be judged on mentions "
                        f"it never asked for.")
    if "[REVIEW]" in draft_rules(p, entity):
        unsigned.append("the no-overlap rule: the examples above show the "
                        "pattern; the wording is a judgement.")
    if "lane_ceiling" in p and p["lane_ceiling"] < T["single_word"]:
        unsigned.append("whether a thin lane is a FINDING or a BUG.")
    for u in unsigned or ["nothing — every declaration is present."]:
        print(f"      · {u}")

    # ── the sniffable patch ──────────────────────────────────────────
    gold = [m for d in docs.values() for m in d.mentions]
    real = next((m.sct[0] for m in gold if m.sct), None)
    patch = {
        "corpus.n_dev_docs": min(40, max(10, len(docs) // 3)),
        "corpus.n_test_docs": min(60, max(10, len(docs) // 2)),
        "vocabulary.gate.real": real,
        "vocabulary.gate.fake": (re.sub(r"\d", "9", str(real)) + "9") if real else None,
    }
    print(f"\n  ── SNIFFABLE, ready to write\n")
    for k, v in patch.items():
        print(f"      {k:26} {v}")
    if len(docs) < patch["corpus.n_dev_docs"] + patch["corpus.n_test_docs"]:
        print(f"      ! {len(docs)} documents cannot support that split and leave "
              f"a pool. LINNAEUS hit this at 95 documents against 40+60.")
    print()

    if a.write:
        for k, v in patch.items():
            if v is None:
                continue
            node, leaf = man, k.split(".")
            for part in leaf[:-1]:
                node = node.setdefault(part, {})
            node[leaf[-1]] = v
        pathlib.Path(a.manifest).write_text(json.dumps(man, indent=2) + "\n")
        print("  written. The SIGNATURE list above is still unsigned.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

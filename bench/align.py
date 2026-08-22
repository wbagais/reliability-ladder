"""
bench/align.py — pair predicted mentions with gold mentions.

Without this, precision and recall are not defined: a post has an unknown number
of reactions, so "which prediction corresponds to which gold" has to be decided
before anything can be scored.

THREE DECISIONS, made explicit because they move the numbers more than any rung:

  1. MATCHING IS BIPARTITE, NOT GREEDY.
     CADEC golds overlap each other — T5 and T7 both start at 161 189
     ("severe osteoarthritis in the knees" / "...in the hands"). Greedy matching
     pairs whichever it sees first and the result depends on file order.
     Maximum-weight bipartite matching gives each gold at most one prediction
     and is order-independent.

  2. OVERLAP IS CHARACTER-LEVEL IoU OVER FRAGMENT SETS.
     Discontinuous mentions are ~16% of ADRs, so a mention is a SET of character
     positions, not a range. IoU handles both cases with one formula.

  3. THRESHOLD DEFAULT 0.5, AND IT IS REPORTED.
     Below it, a pair is not a match. Sweep it once and put the curve in the
     appendix — a threshold chosen silently is a thumb on the scale.

Error classes, kept separate because they mean different things:
     matched_correct    right span, right code
     matched_wrong_code right span, wrong code   ← the interesting one
     spurious           prediction matching no gold (false positive)
     missed             gold matching no prediction (false negative)
"""
from __future__ import annotations
from dataclasses import dataclass, field

try:
    from scipy.optimize import linear_sum_assignment
    _SCIPY = True
except ImportError:                       # tiny fallback, no hard dependency
    _SCIPY = False

Frag = tuple[int, int]


def charset(fragments: list[Frag]) -> set[int]:
    s: set[int] = set()
    for a, b in fragments:
        s.update(range(a, b))
    return s


def iou(a: list[Frag], b: list[Frag]) -> float:
    """Character-level intersection over union. Works for discontinuous spans."""
    A, B = charset(a), charset(b)
    if not A or not B:
        return 0.0
    return len(A & B) / len(A | B)


def _hungarian(cost: list[list[float]]) -> list[tuple[int, int]]:
    if _SCIPY:
        import numpy as np
        r, c = linear_sum_assignment(np.array(cost))
        return list(zip(r.tolist(), c.tolist()))
    # fallback: greedy over globally sorted scores — order-independent, and
    # optimal whenever no two golds compete for the same prediction.
    n, m = len(cost), len(cost[0]) if cost else 0
    pairs = sorted(((cost[i][j], i, j) for i in range(n) for j in range(m)))
    used_r, used_c, out = set(), set(), []
    for _, i, j in pairs:
        if i not in used_r and j not in used_c:
            used_r.add(i); used_c.add(j); out.append((i, j))
    return out


@dataclass
class Alignment:
    pairs: list[tuple[int, int, float]] = field(default_factory=list)  # pred, gold, iou
    spurious: list[int] = field(default_factory=list)
    missed: list[int] = field(default_factory=list)
    threshold: float = 0.5
    matcher: str = "hungarian"

    def counts(self) -> dict:
        return {"matched": len(self.pairs), "spurious": len(self.spurious),
                "missed": len(self.missed), "threshold": self.threshold,
                "matcher": self.matcher}


def align(pred: list[dict], gold: list[dict], threshold: float = 0.5) -> Alignment:
    """
    pred/gold items need a 'fragments' key: [[start,end], ...].
    A contiguous mention is simply a one-fragment list.
    """
    if not pred or not gold:
        return Alignment(spurious=list(range(len(pred))),
                         missed=list(range(len(gold))), threshold=threshold,
                         matcher="hungarian" if _SCIPY else "greedy-fallback")

    P = [[tuple(f) for f in p["fragments"]] for p in pred]
    G = [[tuple(f) for f in g["fragments"]] for g in gold]
    sim = [[iou(p, g) for g in G] for p in P]
    # Cells below threshold are zeroed BEFORE matching. Left in, a junk pair can
    # raise the total and pull a prediction off the gold it actually belongs to;
    # the pair is then dropped by the threshold and both ends are lost.
    cost = [[-(s if s >= threshold else 0.0) for s in row] for row in sim]

    a = Alignment(threshold=threshold,
                  matcher="hungarian" if _SCIPY else "greedy-fallback")
    taken_p, taken_g = set(), set()
    for i, j in _hungarian(cost):
        if i < len(P) and j < len(G) and sim[i][j] >= threshold:
            a.pairs.append((i, j, round(sim[i][j], 3)))
            taken_p.add(i); taken_g.add(j)
    a.spurious = [i for i in range(len(P)) if i not in taken_p]
    a.missed = [j for j in range(len(G)) if j not in taken_g]
    return a


GRADABLE_KINDS = {"single", "all_of", "any_of"}


def score(pred: list[dict], gold: list[dict], threshold: float = 0.5) -> dict:
    """
    TWO SCORINGS, REPORTED SEPARATELY AND NEVER FUSED.

    445 of CADEC's 9,111 mentions (4.9%) are gold_kind 'concept_less': a real
    reaction the annotators could not code. They are findable but not gradable.
    A single F1 must either drop them — handing the model a lane where wrong
    codes cost nothing — or grade them, penalising it for an answer that does
    not exist. Neither is a measurement.

      span_*  every gold, including concept_less. Did the model find it?
      code_*  gradable golds only.                Did it code it correctly?

    Gold 'sct' is a LIST: CADEC records 'or' alternatives (gold_kind 'any_of',
    3 mentions) and matching ANY counts as correct.
    """
    a = align(pred, gold, threshold)

    n_gold_gradable = sum(
        1 for g in gold
        if (g.get("gold_kind") or "single") in GRADABLE_KINDS and (g.get("sct") or [])
    )

    correct = wrong = ungradable = 0
    for i, j, _ in a.pairs:
        g = gold[j]
        kind = g.get("gold_kind") or "single"
        codes = {str(c) for c in (g.get("sct") or [])}
        if kind not in GRADABLE_KINDS or not codes:
            ungradable += 1
            continue
        correct += 1 if str(pred[i].get("code") or "") in codes else 0
        wrong += 0 if str(pred[i].get("code") or "") in codes else 1

    n_matched = len(a.pairs)
    span_p = n_matched / len(pred) if pred else 0.0
    span_r = n_matched / len(gold) if gold else 0.0
    graded = correct + wrong
    return {
        # --- span: did it find the mention? all golds count -----------------
        "span_matched": n_matched,
        "spurious": len(a.spurious),
        "missed": len(a.missed),
        "span_precision": round(span_p, 4),
        "span_recall": round(span_r, 4),
        "span_f1": round(2 * span_p * span_r / (span_p + span_r), 4)
        if span_p + span_r else 0.0,
        # --- code: only where a gold code exists ---------------------------
        "code_correct": correct,
        "code_wrong": wrong,
        "code_accuracy": round(correct / graded, 4) if graded else None,
        "code_recall": round(correct / n_gold_gradable, 4) if n_gold_gradable else None,
        "matched_ungradable": ungradable,
        "gold_gradable": n_gold_gradable,
        # --- provenance ----------------------------------------------------
        "threshold": threshold,
        "matcher": a.matcher,
    }


def sweep(pred, gold, lo=0.1, hi=0.9, step=0.1) -> list[dict]:
    """Run once and put the curve in the appendix."""
    out, t = [], lo
    while t <= hi + 1e-9:
        out.append(score(pred, gold, round(t, 2)))
        t += step
    return out


# ───────────────────────────────────────────────────────── self-test
if __name__ == "__main__":
    print("matcher:", "hungarian" if _SCIPY else "GREEDY FALLBACK — scipy missing")

    # Case 1 — the real CADEC shape: two golds sharing their first fragment,
    # predictions supplied in reversed order.
    gold = [
        {"fragments": [[161, 189], [190, 195]], "sct": ["396275006"]},   # ...knees
        {"fragments": [[161, 189], [200, 205]], "sct": ["396275006"]},   # ...hands
        {"fragments": [[9, 19]],                "sct": ["271782001"]},   # bit drowsy
        {"fragments": [[260, 265]], "sct": ["102498003", "76948002"]},   # 'or' case
    ]
    pred = [
        {"fragments": [[161, 189], [200, 205]], "code": "396275006"},
        {"fragments": [[161, 189], [190, 195]], "code": "396275006"},
        {"fragments": [[9, 19]],                "code": "999999999"},
        {"fragments": [[260, 265]],             "code": "76948002"},
        {"fragments": [[400, 410]],             "code": "111111111"},
    ]
    a = align(pred, gold)
    assert (0, 1) in [(i, j) for i, j, _ in a.pairs], "reversed order broke pairing"
    print("case 1 pairs:", a.pairs)
    print("case 1 score:", score(pred, gold))

    # Case 2 — PARTIAL overlap, so the threshold is actually exercised.
    # pred trims 12 of 33 characters: iou = 21/33 = 0.636.
    g2 = [{"fragments": [[100, 133]], "sct": ["1"]}]
    p2 = [{"fragments": [[100, 121]], "code": "1"}]
    print("\ncase 2 iou:", round(iou([(100, 121)], [(100, 133)]), 3))
    for t in (0.5, 0.6, 0.7):
        r = score(p2, g2, t)
        print(f"   t={t}  matched={r['span_matched']} "
              f"spurious={r['spurious']} missed={r['missed']}")
    assert score(p2, g2, 0.6)["code_correct"] == 1
    assert score(p2, g2, 0.7)["missed"] == 1, "threshold not applied"

    # Case 3 — a sub-threshold cell must not steer the assignment.
    g3 = [{"fragments": [[0, 100]], "sct": ["A"]},
          {"fragments": [[60, 160]], "sct": ["B"]}]
    p3 = [{"fragments": [[0, 100]], "code": "A"},
          {"fragments": [[60, 160]], "code": "B"}]
    a3 = align(p3, g3)
    assert [(i, j) for i, j, _ in a3.pairs] == [(0, 0), (1, 1)], a3.pairs
    print("\ncase 3 pairs:", a3.pairs, "— overlapping golds not swapped")

    print("\nthreshold sweep (case 2):")
    for r in sweep(p2, g2, 0.3, 0.9, 0.2):
        print(f"   t={r['threshold']:.1f}  span_F1={r['span_f1']:.2f} "
              f"code_acc={r['code_accuracy']}")
    # Case 4 — concept_less: findable, not gradable.
    g4 = [{"fragments": [[0, 10]], "sct": [], "gold_kind": "concept_less"},
          {"fragments": [[20, 30]], "sct": ["271782001"], "gold_kind": "single"}]
    p4 = [{"fragments": [[0, 10]], "code": "999999999"},
          {"fragments": [[20, 30]], "code": "271782001"}]
    r4 = score(p4, g4)
    print("\ncase 4 (concept_less):")
    print(f"   span_recall  {r4['span_recall']}  (both golds found)")
    print(f"   code_accuracy {r4['code_accuracy']}  over {r4['gold_gradable']} gradable")
    print(f"   ungradable    {r4['matched_ungradable']}")
    assert r4["span_recall"] == 1.0, "concept_less must count as findable"
    assert r4["code_accuracy"] == 1.0, "concept_less must not be graded on code"
    assert r4["gold_gradable"] == 1

    print("\nall assertions passed")

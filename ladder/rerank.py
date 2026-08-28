"""The rung 0 RERANK stage — between the retrieval and the pick.

WHY IT EXISTS, measured on dev 2026-08-28 over 174 matched mentions:

    gold's rank in the retrieved pool     the pick's conversion at that rank
      rank 0            52.3%               94.5%   (86 of 91)
      top-20            81.0%               42.3%   (22 of 52, ranks 1-19)
      top-200           91.4%                  --   (never on the menu)

Two facts that do not fit together. Menu RECALL wants a deep k; the PICK
degrades with one — k=40 was measured 2026-08-24 and made picks worse
(pick-past-gold 34 -> 47), which is what the k=20 setting stands on. A rerank
stage is the only shape that holds both: retrieve deep, reorder, hand the pick
a short menu.

AND THE TARGET IS RANK 0, not the menu. The conversion table above is a
transfer function — moving a gold code from rank 7 to rank 1 is worth about a
fifth of moving it to rank 0, because the pick largely ratifies the top slot
(the same anchoring Phase B(e) measured when alphabetising the menu cost
10-12 points of coding accuracy at identical detection).

WHAT DOES NOT WORK, both measured before this file was written:

  - Retrieving deeper and NOT reranking. Sorting a k=200 pool by the cosine
    and keeping 15 returns the cosine's top 15, by construction. Depth is
    inert until something re-scores it.
  - Lexical overlap as the re-scoring signal. Best-synonym containment over
    the whole keyword table, at every weight from 0.02 to 0.20, LOWERS the
    rank-0 rate (52.3% -> 50.0-52.3%) and recall@15 with it. That is the
    2026-08-24 hybrid-retrieval result again, in the harder form: lexical
    similarity does not help even when the dense corpus filter is kept and
    only the ORDER is at stake.

Two rerankers are provided and they are not the same kind of thing:

  "polarity"  free, deterministic, no call. Repairs ONE failure class the
              cosine is blind to — antonym inversion. Worth +2.9 points of
              rank-0 rate offline, which is inside the dev noise floor.
  "llm"       a call. Asks the extractor for a plausibility SHORTLIST over a
              deep menu, best first, and takes that order. It COSTS CALLS AND
              TOKENS and they go to the ledger like every other measure.

Both are ARMS. `rung0_rerank` defaults to None, so `manifest.json` is
byte-unchanged and no shipped number moves.
"""

from __future__ import annotations

import re
from typing import Any

RERANKERS = ("polarity", "llm")

#: Offline best (2026-08-28): 0.02 gives rank-0 55.2%, and every larger weight
#: is worse — 0.05 is 54.6%, 0.20 costs recall@15 as well. A cue this coarse
#: earns a tie-break, not a veto; the median cosine gap between rank 0 and a
#: misranked gold code is 0.044, so 0.02 flips a near-tie and nothing else.
DEFAULT_WEIGHT = 0.02

#: The span says the reporter did NOT do / could not do something. Deliberately
#: cue-based and deliberately narrow: it fires on evidence or not at all.
_NEG_SPAN = re.compile(
    r"\b(no|not|never|cannot|cant|can'?t|could'?n'?t|couldnt|wo'?n'?t|did'?n'?t|"
    r"do'?n'?t|does'?n'?t|unable|lack|loss|lost|without|barely|hardly|trouble|"
    r"difficulty|difficult|diffuculty|less|poor|reduced|impaired|inability|"
    r"intolerance|intolerant|struggle|struggling)\b")

#: `able` is a substring of `unable`, so the negative pattern is tested FIRST
#: and a label matching it is never read as positive. That ordering is the
#: whole feature: "unable to concentrate" is the answer for "could'nt
#: concentrate" and "able to concentrate" is its opposite.
_NEG_LABEL = re.compile(
    r"\b(unable|inability|impaired|intolerant|intolerance|poor|difficulty|loss|"
    r"lack|absent|absence|decreased|reduced|not|no|insufficient|deficient)\b")
_POS_LABEL = re.compile(
    r"\b(able|ability|tolerant|tolerance|normal|adequate|enough|increased)\b")


def polarity(span: str, label: str) -> float:
    """+1 the concept agrees with the span's polarity, -1 it inverts it, 0 no
    evidence either way.

    The dominant inspectable rank-0 failure on dev is the embedder returning
    the ANTONYM: "can't sleep" -> |able to sleep| (gold: insomnia), "could'nt
    walk" -> |able to walk| (gold: impaired walking), "sever heat intolerance"
    -> |tolerant of heat|. Cosine treats a negation as a small perturbation of
    the sentence it negates.

    Asymmetric on purpose. A span with NO negation cue scores 0 against
    everything: pushing an unnegated span toward negative concepts would be
    the same error mirrored, and there is no evidence for it.
    """
    if not _NEG_SPAN.search((span or "").lower()):
        return 0.0
    text = (label or "").lower()
    if _NEG_LABEL.search(text):
        return 1.0
    if _POS_LABEL.search(text):
        return -1.0
    return 0.0


def _renumber(cands: list[dict]) -> list[dict]:
    """Menu position is the answer key the pick replies with. A reordered menu
    carrying its retrieval numbers would assign one concept's number to
    another — the defect `_decide`'s batching already had to avoid."""
    return [{**c, "i": n} for n, c in enumerate(cands)]


def rerank_menu(span: str, cands: list[dict], cfg: dict[str, Any],
                meta: dict, denied: bool = False) -> tuple[list[dict], dict]:
    """One mention's menu, reordered by the declared reranker and truncated.

    Returns (menu, record_meta). `record_meta` is empty when no reranker is
    configured — the arm off is the arm absent, not the arm recording zeros.

    The LLM reranker is NOT reachable here: it batches several mentions into
    one call and lives in `rerank_llm`. This is the free path.
    """
    which = cfg.get("rung0_rerank")
    if which is None:
        return cands, {}
    if which not in RERANKERS:
        raise ValueError(
            f"rung0_rerank={which!r} is not one of {RERANKERS}. A reranker "
            "nobody defined would report a run under a label the article "
            "cannot explain."
        )
    keep = cfg.get("rung0_rerank_k", 15)
    before = [c["code"] for c in cands]
    if which == "polarity":
        # `denied` is NOT folded into the span text. The pick is told about a
        # denial with a "[denied]" marker and the reranker is too, but a
        # marker inside the string the cue reads would invert the concept the
        # pick is being asked to code.
        # None means "the frozen weight", so a manifest can carry the key
        # without pinning the number the sweep chose.
        w = cfg.get("rung0_rerank_weight")
        w = DEFAULT_WEIGHT if w is None else w
        scored = sorted(
            enumerate(cands),
            key=lambda p: (-(p[1].get("score", 0.0)
                             + w * polarity(span, p[1].get("fsn")
                                            or p[1].get("label") or "")),
                           p[0]),
        )
        cands = [c for _, c in scored]
    out = _renumber(cands[:keep])
    return out, {
        "rung0_rerank": which,
        # Same posture as `span_untrimmed` and `split_from`: the transformation
        # is auditable and the un-reranked number recomputable from the run.
        "candidates_preranked": before,
        "rerank_moved": [c["code"] for c in out] != before[:len(out)],
    }


RERANK_PROMPT = """For each reaction below, choose the concepts from its list that
could plausibly name that reaction, and return them BEST FIRST.

This is a SHORTLIST, not a choice. Return up to {keep} numbers per reaction, the
most plausible first. Include a concept if it names the same thing the reporter
described, even loosely; leave out concepts about a different body part, a
different symptom, or the OPPOSITE of what was described.

Each reaction has a number after the word "reaction". Each concept has a number
in [square brackets]. Answer with numbers only, never with a concept name.

A reaction marked [denied] is one the writer says they did NOT have. Shortlist
the concepts for the reaction being denied, exactly as if they had had it.

Return JSON: {{"shortlists":[{{"reaction":0,"concepts":[3,17,1]}}]}}

{blocks}"""


def _blocks(chunk) -> str:
    out = []
    for idx, item in enumerate(chunk):
        text, cands = item[0], item[1]
        denied = " [denied]" if (len(item) > 2 and item[2]) else ""
        menu = "\n".join(f'     [{n}] {c.get("fsn") or c.get("label")}'
                         for n, c in enumerate(cands))
        out.append(f'reaction {idx}:{denied} "{text}"\n{menu}')
    return "\n\n".join(out) + "\n"


def rerank_llm(pairs, source: str, llm, cfg: dict[str, Any],
               meta: dict) -> tuple[list[list[dict]], dict]:
    """Ask the extractor to shortlist each deep menu, best first.

    `pairs` is (span_text, candidates) or (span_text, candidates, denied).

    It asks for a SHORTLIST, not a choice, and that is the difference from the
    pick rather than a rewording of it: recall over a deep menu is an easier
    question than precision over a short one, and the pick still runs
    afterwards on the result. Nothing here decides a code.

    A concept the shortlist omits is kept BEHIND it in retrieval order — the
    reranker reorders, it never drops a candidate the retriever paid for.
    Truncation to `rung0_rerank_k` is what drops candidates, visibly and by
    a declared number.

    Batched like `_decide`, and for the same reason: the reaction number is
    scoped to the call it appears in, so each batch renumbers from 0.
    """
    from ladder.rungs.r0 import _parse

    keep = cfg.get("rung0_rerank_k", 15)
    size = cfg.get("rung0_rerank_batch") or len(pairs) or 1
    out: list[list[dict]] = []
    for start in range(0, len(pairs), size):
        chunk = pairs[start:start + size]
        raw, usage = llm(
            RERANK_PROMPT.format(keep=keep, blocks=_blocks(chunk)), source, "S2")
        # The bill. Cost is three separate measures and this stage spends
        # calls and tokens; an arm that bought accuracy with calls nobody
        # counted would be a free lunch on paper only.
        meta["tokens_in"] = meta.get("tokens_in", 0) + usage["in"]
        meta["tokens_out"] = meta.get("tokens_out", 0) + usage["out"]
        meta["usd"] = meta.get("usd", 0.0) + usage.get("usd", 0.0)
        meta["api_calls"] = meta.get("api_calls", 0) + 1
        meta["rerank_calls"] = meta.get("rerank_calls", 0) + 1
        meta["truncated"] = meta.get("truncated", False) or bool(usage.get("truncated"))
        meta["timed_out"] = meta.get("timed_out", False) or bool(usage.get("timed_out"))

        parsed = _parse(raw, {})
        if parsed is None:
            # A transport failure is not a reranking. The menus pass through
            # in retrieval order and the failure goes to the cost column, the
            # same rule `timed_out` and `truncated` follow.
            meta["rerank_parse_failed"] = True
            out.extend(_renumber(item[1][:keep]) for item in chunk)
            continue
        got: dict[int, list[int]] = {}
        for p in parsed.get("shortlists", []):
            try:
                ref = int(p.get("reaction", p.get("i")))
            except (TypeError, ValueError):
                continue
            nums = []
            for x in (p.get("concepts") or []):
                try:
                    nums.append(int(x))
                except (TypeError, ValueError):
                    continue
            got[ref] = nums
        for idx, item in enumerate(chunk):
            cands = item[1]
            picked, seen = [], set()
            for n in got.get(idx, []):
                if not 0 <= n < len(cands):
                    # Never clamped: an out-of-range index is the model failing
                    # to use the menu, and clamping it would report that as a
                    # ranking judgement.
                    meta["rerank_bad_index"] = meta.get("rerank_bad_index", 0) + 1
                    continue
                if n in seen:
                    continue
                seen.add(n)
                picked.append(cands[n])
            rest = [c for n, c in enumerate(cands) if n not in seen]
            out.append(_renumber((picked + rest)[:keep]))
    return out, meta

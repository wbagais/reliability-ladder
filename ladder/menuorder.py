"""Ordering S2's candidate menu by the words AROUND the mention.

Added 2026-08-30 for the FiNER recall work, and off by default everywhere.

The problem it exists for. FiNER's menu is `rung0_retrieval: "full"` — the
whole 139-tag vocabulary, in whatever order the vocabulary enumerates itself.
That choice is right about the thing it was made for: a bare number carries no
terms to rank on, so ranking the menu by the SPAN produced an empty menu and a
null code for every record. But two measured facts sit against the ORDER it
leaves behind:

  * alphabetising the CADEC pick menu cost 10-12 points of coding accuracy at
    byte-identical detection (2026-08-27) — the pick anchors on early slots, so
    a menu's order is load-bearing and a meaningless order is a real cost;
  * k=40 picked WORSE than k=20 on CADEC (2026-08-24) — "menu recall is not
    menu accuracy" — and FiNER's menu is 139 long.

The span carries no query. The sentence does: "conversion price of $ 11.16 per
share" is exactly the evidence a person uses to reach
|DebtInstrumentConvertibleConversionPrice1|.

What this deliberately does NOT do is truncate. Nothing is dropped, so menu
recall stays 1.000 by construction and the arm tests one thing only: whether
best-first order is worth anything when the query is context rather than span.
The offline probe that justified building it (out/harness/finerctx.py, 165 dev
gold mentions) put the correct tag at median rank 7 of 139 — real signal, and
nowhere near enough to justify keeping only the top 20.
"""

from __future__ import annotations

import re
from typing import Any, Callable, Sequence

_CAMEL = re.compile(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])|(?<=[A-Za-z])(?=\d)")


def tag_words(code: str) -> str:
    """`us-gaap:DebtInstrumentInterestRateStatedPercentage` -> the English in it.

    The embedder has never seen a camel-cased XBRL identifier and has seen a
    great deal of "debt instrument interest rate". Splitting is the whole
    reason a general-purpose embedding model has anything to say here.
    """
    body = str(code).split(":")[-1]
    return _CAMEL.sub(" ", body).replace("_", " ").lower().strip()


def context_ranked(
    cands: list[dict[str, Any]],
    context: str | None,
    embed: Callable[[Sequence[str]], Sequence[Sequence[float]]],
) -> list[dict[str, Any]]:
    """`cands`, reordered best-first against `context` and renumbered.

    Returns the input unchanged — same objects, same order — when there is no
    context, no menu, or the embedder fails. An ordering that cannot be
    computed must cost the ORDER and never the document: rung 0 already has a
    counter-metric for documents it loses, and losing one to a ranking
    nicety would be charged to the model.

    Ties keep their incoming order (Python's sort is stable), so a run
    reproduces from its inputs.
    """
    if not cands or not context or not str(context).strip():
        return cands
    try:
        vecs = embed([str(context)] + [tag_words(c.get("code", "")) for c in cands])
        q, rest = vecs[0], vecs[1:]
        if len(rest) != len(cands):
            return cands
        qn = sum(x * x for x in q) ** 0.5 or 1.0
        scored = []
        for c, v in zip(cands, rest):
            vn = sum(x * x for x in v) ** 0.5 or 1.0
            scored.append(sum(a * b for a, b in zip(q, v)) / (qn * vn))
    except Exception:
        return cands
    order = sorted(range(len(cands)), key=lambda n: -scored[n])
    return [{**cands[n], "i": pos, "context_rank": pos} for pos, n in enumerate(order)]


# --- B4: breaking the position prior instead of feeding it -------------------
#
# The context ranker above was built to give the menu a MEANINGFUL order. It
# worked as a ranker and lost as a system, and the diagnostic that explained
# why named the real defect: the model takes menu line one because it is line
# one. `AccrualForEnvironmentalLossContingencies` is alphabetically first, sits
# at slot 0 in every FiNER record, and is predicted 57 times in 292 against 2
# in gold. Under the context arm its median slot is 92 and it is predicted 3
# times — all 3 while it happened to be first.
#
# So the next intervention is not a better ranker. It is to stop any single tag
# owning slot 0. A per-mention permutation does exactly that and NOTHING else:
# the answer set is untouched, menu recall stays 1.000, and no option is added
# that is not a valid answer. It is also the option-order-bias literature's own
# mitigation.

import hashlib
import random


def permuted(cands: list[dict[str, Any]], key: str | None,
             seed: int = 0) -> list[dict[str, Any]]:
    """`cands` in a per-mention pseudo-random order, renumbered.

    The permutation is a pure function of `(seed, key)` through blake2b —
    NOT through `hash()`, which is salted per process, and which would make two
    runs of the same configuration incomparable and every paired draw a
    different experiment.

    Returns the input unchanged when there is no menu or no key, for the same
    reason `context_ranked` does: an ordering that cannot be computed must cost
    the ORDER and never the document.

    Each candidate carries `shuffled_from`, its slot before the permutation, so
    a run's artifacts can be checked for the thing an ablation cannot see —
    that the arm moved anything at all. A held-fixed layer and a dead arm both
    print a delta of zero.
    """
    if not cands or key is None or not str(key).strip():
        return cands
    digest = hashlib.blake2b(f"{int(seed)}|{key}".encode("utf-8"),
                             digest_size=8).digest()
    rng = random.Random(int.from_bytes(digest, "big"))
    order = list(range(len(cands)))
    rng.shuffle(order)
    return [{**cands[n], "i": pos, "shuffled_from": n}
            for pos, n in enumerate(order)]

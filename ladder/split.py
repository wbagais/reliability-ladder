"""Coordination splitting — one quoted phrase into the mentions gold keeps.

CADEC annotates a coordination as SEVERAL mentions with DISCONTINUOUS spans,
sharing the head:

    "Terrible muscle and joint pain"  ->  ['muscle' ... 'pain']
                                          ['joint'  ... 'pain']
    "swelling of face, wrists"        ->  ['swelling' ... 'face']
                                          ['swelling' ... 'wrists']

Rung 0 cannot express that. `_mention_record` builds `spans=[(start, end)]` —
one tuple — so the model's single contiguous quote covers the whole phrase and
loses every mention inside it. Measured on the dev split 2026-08-27: 39 of 226
scorable gold reaction mentions (17.3%) are discontinuous, they account for 24
of 68 boundary errors and 15 of 55 false negatives, and **0 of 233 predictions
carried more than one span**. Perfect boundaries on contiguous gold alone caps
exact F1 at 0.383; including the discontinuous ones it is 0.423.

TWO SHAPES ONLY, both structural — no lexicon, no model call:

    head-final     <item> (and|or|,) <item> <HEAD>     "muscle and joint pain"
    head-initial   <HEAD> (in|of|on) <item>, <item>    "pain in hips and legs"

Anything else is left alone. The conservatism is deliberate: a split that
guesses wrong turns one imperfect record into several false positives, and the
whole prize here is 4 points of exact F1.

The split runs BEFORE retrieval, not after. Gold gives the two halves of
"muscle and joint pain" DIFFERENT codes (68962001 and 57676002), so each piece
has to get its own menu and its own pick — splitting after the pick would copy
one code onto both.
"""

from __future__ import annotations

import re

#: Same token class the trimmer and the negation scanner use.
_TOKEN = re.compile(r"[\w']+|[^\w\s]")

COORD = {"and", "or", "&", "+", ","}
#: Prepositions that introduce the list in the head-initial shape.
PREP = {"in", "of", "on", "to", "around", "throughout"}
#: Words that may sit inside a list item without ending it.
FILLER = {"my", "the", "both", "all", "a", "an", "her", "his", "their", "our"}


def _tokens(text: str):
    return [(m.group(0), m.group(0).lower(), m.start(), m.end())
            for m in _TOKEN.finditer(text)]


def _runs(toks, lo, hi):
    """Split toks[lo:hi] on coordinators into runs of (start, end) indices."""
    runs, cur = [], []
    for i in range(lo, hi):
        if toks[i][1] in COORD:
            if cur:
                runs.append(cur)
            cur = []
        else:
            cur.append(i)
    if cur:
        runs.append(cur)
    return [r for r in runs if any(toks[i][1] not in FILLER for i in r)]


def _seg(toks, idxs):
    return (toks[idxs[0]][2], toks[idxs[-1]][3])


def split_coordination(text: str, span: tuple[int, int]) -> list[list[tuple[int, int]]]:
    """Segment lists for the mentions inside one quoted phrase.

    Returns one entry per mention, each a list of (start, end) offsets in the
    SAME coordinate space as `span` — so a two-segment result is a
    discontinuous mention. Returns `[]` when the phrase is not a coordination
    this recognises, which is the common case and means "leave it alone".
    """
    start = span[0]
    toks = _tokens(text)
    if len(toks) < 3:
        return []
    coords = [i for i, t in enumerate(toks) if t[1] in COORD]
    if not coords:
        return []

    def out(groups, head):
        got = []
        for g in groups:
            segs = sorted([_seg(toks, g), head])
            got.append([(start + a, start + b) for a, b in segs])
        return got

    # head-initial: HEAD <prep> item, item and item
    preps = [i for i, t in enumerate(toks) if t[1] in PREP]
    for p in preps:
        if p == 0 or p > coords[-1]:
            continue
        if not any(c > p for c in coords):
            continue
        # The preposition belongs to the HEAD — pool gold keeps it there
        # ("ulceration of" + "the osophragus", "severe osteoarthritis in the"
        # + "knees"). Dropping it would leave a bare noun as the shared part.
        head_idx = [i for i in range(0, p + 1) if toks[i][1] not in COORD]
        runs = _runs(toks, p + 1, len(toks))
        if len(runs) >= 2 and head_idx:
            return out(runs, _seg(toks, head_idx))

    # head-final: item and item HEAD  — the last run carries the shared head
    runs = _runs(toks, 0, len(toks))
    if len(runs) >= 2:
        last = runs[-1]
        content = [i for i in last if toks[i][1] not in FILLER]
        if len(content) >= 2:
            head = _seg(toks, content[-1:])
            groups = runs[:-1] + [content[:-1]]
            if all(g for g in groups):
                return out(groups, head)
    return []

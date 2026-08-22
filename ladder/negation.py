"""Negation detection — rung 1 check 3. A cue list and a window, no vocabulary.

From an actual CADEC post:

    "I feel a bit drowsy & have a little blurred vision, so far no gastric
     problems."

A model will happily extract "gastric problems" as a reported reaction. It is
explicitly denied. Catching that needs no model and no vocabulary, and a system
that gets codes right but polarity wrong is dangerous in a way an F1 hides — so
`negated` is logged as its own rejection reason, never folded into a total.

This is NegEx reduced to what a patient forum actually needs: a cue list, a
token window, and a termination set that stops the scope at a clause boundary.

The trap, and why the cue must sit OUTSIDE the mention
------------------------------------------------------
Patients report absences as symptoms: "no energy", "no appetite", "couldn't
sleep". CADEC annotates the cue as part of the mention in those cases, so a
naive backward scan flags the corpus's own gold as negated. A cue that falls
inside the mention's own span is part of the complaint, not a denial of it.
"""

from __future__ import annotations

import re

#: Denial cues. Multi-word cues are matched as phrases.
CUES = (
    "no",
    "not",
    "none",
    "never",
    "nor",
    "without",
    "denies",
    "denied",
    "deny",
    "negative for",
    "free of",
    "free from",
    "ruled out",
    "no sign of",
    "no signs of",
    "no evidence of",
    "no more",
    "n't",
)

#: Cues whose scope runs FORWARD from the cue to the mention.
FORWARD_ONLY = ("denies", "denied", "deny", "negative for", "ruled out", "without")

#: Words that end a negation's scope before it reaches the mention.
TERMINATORS = (
    "but",
    "however",
    "although",
    "though",
    "except",
    "yet",
    "still",
    "unless",
    "aside",
    "besides",
)

#: Phrases that look like a denial and are not one.
PSEUDO = (
    "no doubt",
    "not only",
    "not just",
    "no wonder",
    "not sure",
    "no idea",
    "not to mention",
)

_TOKEN = re.compile(r"[\w']+|[.;:!?,]")
_SENT_END = frozenset(".;!?")


def _tokens(text: str) -> list[tuple[str, int, int]]:
    return [(m.group(0).lower(), m.start(), m.end()) for m in _TOKEN.finditer(text)]


def is_negated(source: str, spans: list[tuple[int, int]], window: int = 6) -> tuple[bool, str | None]:
    """Is the mention at `spans` explicitly denied in `source`?

    Returns (negated, the cue that fired). `window` is in tokens, counted
    backwards from the start of the mention (or forwards for FORWARD_ONLY
    cues), stopping at a sentence boundary or a terminator.
    """
    if not spans:
        return False, None
    start = min(a for a, _ in spans)
    end = max(b for _, b in spans)
    low = source.lower()
    for phrase in PSEUDO:
        idx = low.rfind(phrase, max(0, start - 60), start)
        if idx != -1 and start - idx <= 40:
            return False, None

    toks = _tokens(source)
    before = [t for t in toks if t[2] <= start]
    after = [t for t in toks if t[1] >= end]

    # Backward scan: "... so far NO gastric problems"
    seen = 0
    for word, w_start, _ in reversed(before):
        if word in _SENT_END:
            break
        if word in TERMINATORS:
            break
        seen += 1
        if seen > window:
            break
        if w_start >= start:  # cue lies inside the mention — part of the complaint
            continue
        if word in CUES and word not in FORWARD_ONLY:
            return True, word
        if word.endswith("n't"):
            return True, "n't"

    # Forward scan for cues that govern what follows them at a distance, e.g.
    # "denies nausea, vomiting and DIZZINESS" — the cue is far to the left of
    # the mention but still its head.
    seen = 0
    for word, w_start, _ in reversed(before):
        if word in _SENT_END:
            break
        seen += 1
        if seen > window * 3:
            break
        if word in FORWARD_ONLY and w_start < start:
            return True, word

    # Trailing denial: "gastric problems? none at all"
    seen = 0
    for word, _, _ in after:
        if word in _SENT_END:
            break
        seen += 1
        if seen > 3:
            break
        if word in ("none", "never"):
            return True, word
    return False, None

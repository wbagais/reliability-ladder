"""Span trimming to the answer key's boundary convention — Phase B(d).

Measured on the enhanced S2 dev run (2026-08-25): detection F1 0.429 exact
against 0.765 overlap. The model FINDS the mention — overlap says so — and
then quotes more of the sentence than gold keeps, so a third of the exact
headline is boundary convention, not extraction failure.

The convention is LEARNED, not legislated. A hand-written trim rule was
already tried and rejected: gold keeps a leading intensifier 3x more often
than it drops one, so "strip the intensifier" breaks the majority case to
fix the minority. What the corpus does state unambiguously is per-token: for
every token, count how often gold leaves it immediately OUTSIDE a span
boundary versus keeps it AT the boundary (first or last token of a span).
"my" sits outside 1,344 times and opens a span almost never; "severe" opens
spans routinely. A token is trimmable only when the outside fraction clears
`outside_ratio` over at least `min_evidence` sightings.

POOL ONLY, same wall as rung0_fewshot_docs and for the same reason: trim
rules learned from dev or test gold would tune the measurement on itself.
Pool is disjoint from both by construction and never scored.

Applied to rung 0's records AFTER locate(): the model's quote and the
located offsets are trimmed together, and the original text is kept on the
record (`span_untrimmed`) so the trim is auditable and reversible.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass

#: Words and single punctuation marks, with positions. The same token class
#: the negation cue scanner uses — boundaries fall between these.
_TOKEN = re.compile(r"[\w']+|[^\w\s]")

DEFAULT_MIN_EVIDENCE = 20
DEFAULT_OUTSIDE_RATIO = 0.95

#: The interior cut's thresholds. Deliberately tight: measured on the
#: baseline dev records (2026-08-25), rate ≤ 0.02 over ≥ 50 sightings lifted
#: exact F1 with overlap untouched, while looser points (0.05/30, 0.10/20)
#: bought exact by cutting into spans until they lost their overlap match —
#: rejected on that measurement.
DEFAULT_CUT_MIN_TOTAL = 50
DEFAULT_CUT_MAX_RATE = 0.02


def boundary_counts(docs) -> dict[str, Counter]:
    """How gold treats each token at span boundaries.

    `docs` is (text, [(start, end), ...]) — one entry per document, spans are
    the gold mention segments. Returns four counters over lowercased tokens:

        before  the token immediately outside a span's LEFT boundary
        first   the token a span STARTS with
        after   the token immediately outside a span's RIGHT boundary
        last    the token a span ENDS with

    before-vs-first is the left convention, after-vs-last the right one.
    """
    counts = {k: Counter() for k in ("before", "first", "after", "last")}
    for text, spans in docs:
        toks = [(m.group(0).lower(), m.start(), m.end())
                for m in _TOKEN.finditer(text)]
        for start, end in spans:
            inside = [t for t in toks if t[1] >= start and t[2] <= end]
            left = [t for t in toks if t[2] <= start]
            right = [t for t in toks if t[1] >= end]
            if inside:
                counts["first"][inside[0][0]] += 1
                counts["last"][inside[-1][0]] += 1
            if left:
                counts["before"][left[-1][0]] += 1
            if right:
                counts["after"][right[0][0]] += 1
    return counts


def interior_counts(docs) -> tuple[Counter, Counter]:
    """(inside, total) occurrences per lowercased token.

    `inside` counts occurrences fully within a gold span; `total` counts every
    occurrence in the documents. inside/total is a token's inside_rate: how
    much of the corpus's use of this token gold considers span material.
    "pain" is high; "that", drug names and dosages are near zero.
    """
    inside, total = Counter(), Counter()
    for text, spans in docs:
        for m in _TOKEN.finditer(text):
            w = m.group(0).lower()
            total[w] += 1
            if any(a <= m.start() and m.end() <= b for a, b in spans):
                inside[w] += 1
    return inside, total


@dataclass(frozen=True)
class SpanTrimmer:
    lead_drop: frozenset
    trail_drop: frozenset
    #: Interior clause cut: the span is truncated before the FIRST occurrence
    #: of one of these (never at position 0). Empty = edge trimming only.
    cut_drop: frozenset = frozenset()

    @classmethod
    def learn(
        cls,
        docs,
        min_evidence: int = DEFAULT_MIN_EVIDENCE,
        outside_ratio: float = DEFAULT_OUTSIDE_RATIO,
        cut_min_total: int = DEFAULT_CUT_MIN_TOTAL,
        cut_max_rate: float = DEFAULT_CUT_MAX_RATE,
    ) -> "SpanTrimmer":
        """Trim rules from gold boundary behaviour. See boundary_counts.

        A token is trimmable on a side when gold has been seen at that side's
        boundary at least `min_evidence` times and left the token OUTSIDE at
        least `outside_ratio` of them. Both thresholds exist to keep the
        anecdote out: one sighting is not a convention.

        A token is a CUT token when it occurs at least `cut_min_total` times
        in the learning documents and its inside_rate (interior_counts) is at
        most `cut_max_rate` — gold effectively never keeps it inside a span,
        so a predicted span running past it has run into the clause gold
        drops ("pain that wakes me up" stops at "that").
        """
        c = boundary_counts(docs)

        def side(outside: Counter, kept: Counter) -> frozenset:
            out = set()
            for w in outside:
                n = outside[w] + kept.get(w, 0)
                if n >= min_evidence and outside[w] / n >= outside_ratio:
                    out.add(w)
            return frozenset(out)

        inside, total = interior_counts(docs)
        return cls(
            lead_drop=side(c["before"], c["first"]),
            trail_drop=side(c["after"], c["last"]),
            cut_drop=frozenset(
                w for w in total
                if total[w] >= cut_min_total
                and inside[w] / total[w] <= cut_max_rate
            ),
        )

    def trim(self, text: str, span: tuple[int, int]) -> tuple[str, tuple[int, int]]:
        """(text, span) with learned-outside tokens stripped from both edges.

        The trim that would empty the span is not made at all — the original
        comes back untouched, because an empty mention is not a boundary
        correction. Offsets move with the text so the record stays grounded.
        """
        toks = [(m.group(0).lower(), m.start(), m.end())
                for m in _TOKEN.finditer(text)]
        if not toks:
            return text, span
        whole = (toks[0][1], toks[-1][2])
        # Interior cut first, never at the first token: a span STARTING with
        # a cut token is not a clause tail.
        for idx in range(1, len(toks)):
            if toks[idx][0] in self.cut_drop:
                toks = toks[:idx]
                break
        i, j = 0, len(toks) - 1
        while i <= j and toks[i][0] in self.lead_drop:
            i += 1
        while j >= i and toks[j][0] in self.trail_drop:
            j -= 1
        if i > j:
            return text, span
        a, b = toks[i][1], toks[j][2]
        if (a, b) == whole:
            return text, span
        start = span[0]
        return text[a:b], (start + a, start + b)


def pool_trimmer(man: dict, split: str = "pool", loader=None) -> SpanTrimmer:
    """A SpanTrimmer learned from the POOL split's gold, read from data/ at
    runtime — the corpus is non-transferable, so the rules are derived on the
    licensed machine and never tracked.

    Any split but pool is REFUSED: dev and test are the measurement.
    """
    if split != "pool":
        raise ValueError(
            f"trim rules must be learned from the pool split, not {split!r}. "
            "Rules learned from a scored split tune the measurement on itself."
        )
    from ladder import clean
    from ladder import corpus as corpus_mod
    from ladder.schema import REACTION

    _c = man.get("corpus") or {}
    docs = (loader or corpus_mod.load_corpus)(_c.get("root") or _c["cadec_root"])
    ids = corpus_mod.read_split(man["corpus"]["splits_dir"], split)
    excluded = clean.load_exclusions()
    data = []
    for d in ids:
        doc = docs[d]
        spans = [
            seg
            for m in doc.mentions
            if m.entity_type == REACTION and m.record_id not in excluded
            for seg in m.spans
        ]
        data.append((doc.text, spans))
    return SpanTrimmer.learn(data)

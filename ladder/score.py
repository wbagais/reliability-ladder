"""The shared scorer. One implementation, injected into every rung's report.

`run.py` finds it through `load_scorer`, which looks for exactly
`ladder.score:reaction_sct_strict`. Until this module existed the accuracy
columns were written empty rather than guessed — see docs/decisions.md.

GOLD IS KEYED BY SPAN, NEVER BY POSITION. Measured: under index-based array
comparison a *perfect* extraction listed in another order scores 0.216, and
dropping a single mention scores 0.081. Span-keyed, the reordered case scores
1.000. Rung 0 emits mentions in whatever order the model wrote them, so a
position-keyed scorer measures the model's writing order and calls it accuracy.

THE GOLD RULE, from manifest.json:

    strict = the predicted SNOMED CT code is IN the gold code set for that
    mention; CONCEPT_LESS is correct only against CONCEPT_LESS gold.

CADEC gold is not always one code. 252 mentions are post-coordinated (A + B)
and 3 are disjunctions (A or B). "In the gold set" gives credit for either half
of a post-coordinated pair, which is generous; 2.8% of mentions are affected,
so `score_run` reports them as their own bucket rather than burying them.

SPAN MATCHING is a declared choice, not a detail:

    exact    the predicted span set equals the gold span set
    overlap  any character overlap, each gold mention claimed at most once

`exact` is the headline. `overlap` exists because rung 3 cannot currently vote
for precisely this reason — it matches on `(doc_id, spans)` and temperature-0.7
resamples pick different phrasings, so keys never align and every record comes
back `not_resampled`. A number is not comparable across modes, so the mode is
returned alongside it.

FOUR OUTCOMES, NOT TWO
----------------------
    correct     the code is in the gold set for that mention
    outdated    the code is a RETIRED concept whose successor is the gold code
    abstained   the model gave no code — CONCEPT_LESS, or nothing at all
    incorrect   everything else

`outdated` exists because SNOMED retires concepts and CADEC was coded in 2015
against a release the model may well have learned. A model that emits
162076009 for a mention now coded 12063002 named a real concept and lacked
eleven years of releases; a model that emits 999999999 invented a number. Those
are different failures and a scorer that calls both "wrong" cannot tell an
article's reader which one it is looking at.

It is NEVER folded into `correct`. The answer is still stale, and a
pharmacovigilance system that files a retired code has filed a retired code —
precision, recall and F1 all count only `correct`. Successors come from
`Registry.replacements`, which follows SAME AS and REPLACED BY and nothing
else; with no vocabulary passed, `outdated` degrades to `incorrect` rather
than to `correct`, so a missing index can never inflate a score.

`abstained` covers CONCEPT_LESS against a coded mention AND `sct is None`. The
two are not the same act — CONCEPT_LESS asserts that no concept fits, None is
the absence of an answer — but neither produced a code, and separating
over-abstention from wrong-code is what makes rung 5's cost readable.
"""

from __future__ import annotations

from typing import Any, Iterable

from ladder.corpus import GOLD_NONE, GoldMention
from ladder.schema import CONCEPT_LESS, REACTION, Record

SPAN_MATCH_MODES = ("exact", "overlap")

CORRECT = "correct"
OUTDATED = "outdated"
ABSTAINED = "abstained"
INCORRECT = "incorrect"

#: Report order, not alphabetical: best answer first, so a table of them reads
#: as a decline. Append new outcomes at the end.
OUTCOMES = (CORRECT, OUTDATED, ABSTAINED, INCORRECT)


# --- one record against one gold mention ------------------------------------


def _find_gold(record: Record, gold: Any) -> GoldMention | None:
    """Locate the gold mention for a record inside a collection, BY SPAN.

    `run.py` builds gold as `{record_id: GoldMention}`, and record_id is
    f"{doc_id}#{index}" — a POSITION. Rung 0 numbers its records by the order
    the model happened to emit them; the annotation file numbers gold by the
    order it was annotated. Those agree only by luck, so looking a record up by
    its own id would grade most mentions against somebody else's answer.
    """
    mentions = gold.values() if isinstance(gold, dict) else gold
    key = _span_key(record.doc_id, record.spans)
    for m in mentions:
        if _span_key(m.doc_id, m.spans) == key:
            return m
    return None


def outcome(record: Record, gold: Any, vocab: Any = None) -> str:
    """One of `OUTCOMES` for this record against this gold mention.

    `gold` is either one `GoldMention` or the collection `run.py` passes — a
    dict of them, or a list. A record whose span matches no gold mention is a
    false positive: INCORRECT, never a free pass.

    `vocab` is anything with `replacements(code)` and `is_active(code)` —
    `Registry` in the pipeline, a stub in the tests. Optional, because the
    365 MB index is absent in CI; when it is missing a retired code reads as
    INCORRECT, which is the conservative direction.
    """
    if not isinstance(gold, GoldMention):
        found = _find_gold(record, gold)
        if found is None:
            return INCORRECT
        gold = found

    predicted = record.sct
    gold_codes = {str(c) for c in (gold.sct or [])}

    # CONCEPT_LESS is symmetric: right only against CONCEPT_LESS gold, and
    # wrong when the vocabulary did have a concept. Over-abstention is an
    # error, not a free pass — that is the cost rung 5 has to earn back.
    if not gold_codes or gold.gold_kind == GOLD_NONE:
        if predicted == CONCEPT_LESS:
            return CORRECT
        # `None` is not CONCEPT_LESS. The model that said nothing did abstain,
        # but it never made the claim the answer key is testing, so it is not
        # credited with it either.
        return ABSTAINED if predicted is None else INCORRECT

    if predicted is None or predicted == CONCEPT_LESS:
        return ABSTAINED
    if str(predicted) in gold_codes:
        return CORRECT
    if vocab is not None and gold_codes & set(vocab.replacements(predicted)):
        return OUTDATED
    return INCORRECT


def reaction_sct_strict(record: Record, gold: Any) -> bool:
    """Is this record's SNOMED answer correct?

    The signature `run.py:load_scorer` expects, and deliberately a BOOLEAN
    over `outcome() == CORRECT` — outdated is not correct, so this answer does
    not move now that there are four outcomes rather than two.

    Says nothing about how the span was matched: this is exact-span. Use
    `score_run` for the overlap mode and for the aggregate numbers.
    """
    return outcome(record, gold) == CORRECT


# --- pairing predictions to gold --------------------------------------------


def _span_key(doc_id: str, spans: Iterable[tuple[int, int]]) -> tuple:
    """Document plus the span SET. Segment order carries no meaning.

    45 of CADEC's own gold mentions quote discontinuous segments in reading
    order rather than offset order, so a scorer that respected order would
    disagree with the answer key.
    """
    return (doc_id, frozenset((int(a), int(b)) for a, b in spans))


def _overlaps(a: Iterable[tuple[int, int]], b: Iterable[tuple[int, int]]) -> bool:
    return any(x < q and p < y for x, y in a for p, q in b)


def _pair(
    records: list[Record], golds: list[GoldMention], span_match: str
) -> list[tuple[Record, GoldMention | None]]:
    """Attach each prediction to at most one gold mention, and vice versa."""
    if span_match == "exact":
        index: dict[tuple, list[GoldMention]] = {}
        for g in golds:
            index.setdefault(_span_key(g.doc_id, g.spans), []).append(g)
        out = []
        for r in records:
            bucket = index.get(_span_key(r.doc_id, r.spans))
            out.append((r, bucket.pop(0) if bucket else None))
        return out

    # overlap: greedy, in prediction order. Each gold mention is claimable
    # once, so two predictions over one mention are one hit and one error
    # rather than two hits.
    remaining = list(golds)
    out = []
    for r in records:
        found = None
        for g in remaining:
            if g.doc_id == r.doc_id and _overlaps(r.spans, g.spans):
                found = g
                break
        if found is not None:
            remaining.remove(found)
        out.append((r, found))
    return out


# --- the run ----------------------------------------------------------------


def _bucket() -> dict[str, int]:
    return {"n_gold": 0, "n_pred": 0, **{o: 0 for o in OUTCOMES}}


def score_run(
    records: list[Record],
    golds: list[GoldMention],
    span_match: str = "exact",
    exclude: set[str] | None = None,
    vocab: Any = None,
) -> dict[str, Any]:
    """Precision, recall and F1 over reaction mentions, plus the sub-buckets.

    Only REACTION records are scored: the manifest's unit of evaluation is one
    reaction mention, and a drug mention is not a wrong answer to a question
    nobody asked.

    A prediction with no gold mention at that span is a false positive. A gold
    mention no prediction reached is a false negative. A paired prediction is
    correct only if `outcome()` says CORRECT, so a right span with a wrong
    code counts against precision AND recall — which is the honest reading:
    the mention was not correctly coded.

    `vocab` (a `Registry`, or anything with `replacements`/`is_active`) turns
    on the OUTDATED outcome. Without it the counts still add up; retired codes
    simply land in `incorrect`. Precision, recall and F1 count CORRECT only in
    both cases, so passing a vocabulary can never raise the headline number —
    it only splits the errors into two named piles.
    """
    if span_match not in SPAN_MATCH_MODES:
        raise ValueError(
            f"span_match={span_match!r} is not one of {SPAN_MATCH_MODES}. "
            "A scorer that silently accepted an unknown mode would report a "
            "number nobody could reproduce."
        )

    # Declared exclusions leave the denominator entirely — see ladder/clean.py.
    # A prediction sitting on an excluded mention is neither credited nor
    # blamed: the mention is unanswerable, so the model's answer to it carries
    # no information either way.
    exclude = exclude or set()
    gold_mentions = [
        g for g in golds if g.entity_type == REACTION and g.record_id not in exclude
    ]
    dropped = [g for g in golds if g.entity_type == REACTION and g.record_id in exclude]
    dropped_keys = {_span_key(g.doc_id, g.spans) for g in dropped}
    preds = [
        r for r in records
        if r.entity_type == REACTION and _span_key(r.doc_id, r.spans) not in dropped_keys
    ]

    buckets = {"single_code": _bucket(), "multi_code": _bucket(), "concept_less": _bucket()}

    def which(g: GoldMention) -> str:
        if not g.sct or g.gold_kind == GOLD_NONE:
            return "concept_less"
        return "multi_code" if len(g.sct) > 1 else "single_code"

    for g in gold_mentions:
        buckets[which(g)]["n_gold"] += 1

    tally = {o: 0 for o in OUTCOMES}
    for record, gold in _pair(preds, gold_mentions, span_match):
        if gold is None:
            # A prediction on no gold mention is a false positive. It is
            # counted in n_pred (so it costs precision) but it has no gold
            # answer to be outdated or abstained WITH, so it stays out of the
            # outcome tally rather than being filed under `incorrect` — the
            # four outcomes are about PAIRED predictions.
            continue
        b = buckets[which(gold)]
        b["n_pred"] += 1
        got = outcome(record, gold, vocab)
        tally[got] += 1
        b[got] += 1

    n_pred, n_gold = len(preds), len(gold_mentions)
    correct = tally[CORRECT]
    precision = correct / n_pred if n_pred else 0.0
    recall = correct / n_gold if n_gold else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0

    return {
        "span_match": span_match,
        "excluded": len(dropped),
        "n_pred": n_pred,
        "n_gold": n_gold,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        **tally,
        **buckets,
    }

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

import random
from typing import Any, Iterable

from ladder.corpus import GOLD_NONE, GoldMention
from ladder.schema import CONCEPT_LESS, REACTION, Record

SPAN_MATCH_MODES = ("exact", "overlap")

CORRECT = "correct"
OUTDATED = "outdated"
ABSTAINED = "abstained"
INCORRECT = "incorrect"
#: Appended 2026-08-26 — the MIRROR of `outdated`. The prediction is the
#: SNOMED-recorded successor of a RETIRED GOLD code: the model answered the
#: current concept for a mention the 2015 annotations filed under an id the
#: release has since replaced. 407 of CADEC's retired gold reaction mentions
#: exist; 111 (27.3%) have such a successor, so this outcome is bounded to
#: them. Same treatment as `outdated`, for the same reason: NEVER folded into
#: `correct` — the gold rule and every headline denominator stay exactly
#: where they were, so no earlier number moves — and with no vocabulary it
#: degrades to `incorrect`, never to `correct`. Decided 2026-08-26 (the
#: parked "111 retired-gold successors" question).
MODERNISED = "modernised"

#: Report order, not alphabetical: best answer first, so a table of them reads
#: as a decline. Append new outcomes at the end.
OUTCOMES = (CORRECT, OUTDATED, ABSTAINED, INCORRECT, MODERNISED)


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
    # The mirror direction: the GOLD code is the retired one and the model
    # answered its recorded successor. `Registry.replacements` returns [] for
    # an active code, so this can only fire on retired gold.
    if vocab is not None and any(
        str(predicted) in set(vocab.replacements(g)) for g in gold_codes
    ):
        return MODERNISED
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
    # A prediction TOUCHING an excluded mention leaves with it, not only one
    # whose span-key equals it. Exclusion says the mention is unanswerable, so
    # any answer over those characters carries no information — but only where
    # it does not also touch a scorable mention, which must still be graded.
    # Measured before this widened (arm-2 dev run): 10 of 38 false positives
    # sat overlapping excluded gold, blamed for answering retired questions.
    def _on_excluded(r: Record) -> bool:
        return any(
            g.doc_id == r.doc_id and _overlaps(r.spans, g.spans) for g in dropped
        ) and not any(
            g.doc_id == r.doc_id and _overlaps(r.spans, g.spans)
            for g in gold_mentions
        )

    preds = [
        r for r in records if r.entity_type == REACTION and not _on_excluded(r)
    ]

    buckets = {"single_code": _bucket(), "multi_code": _bucket(), "concept_less": _bucket()}

    def which(g: GoldMention) -> str:
        if not g.sct or g.gold_kind == GOLD_NONE:
            return "concept_less"
        return "multi_code" if len(g.sct) > 1 else "single_code"

    for g in gold_mentions:
        buckets[which(g)]["n_gold"] += 1

    tally = {o: 0 for o in OUTCOMES}
    n_matched = 0
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
        n_matched += 1
        got = outcome(record, gold, vocab)
        tally[got] += 1
        b[got] += 1

    n_pred, n_gold = len(preds), len(gold_mentions)
    correct = tally[CORRECT]
    precision = correct / n_pred if n_pred else 0.0
    recall = correct / n_gold if n_gold else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0

    # THE TWO LAYERS (2026-08-25). The headline conflates two questions —
    # did the system FIND the mention, and given a found mention is the CODE
    # right — and S0/S1/S2 differ by design only on the second. detection
    # ignores codes entirely; coding is conditional on a match, so
    # recall == detection.recall x coding.accuracy by construction.
    det_p = n_matched / n_pred if n_pred else 0.0
    det_r = n_matched / n_gold if n_gold else 0.0
    det_f1 = 2 * det_p * det_r / (det_p + det_r) if (det_p + det_r) else 0.0

    return {
        "span_match": span_match,
        "excluded": len(dropped),
        "n_pred": n_pred,
        "n_gold": n_gold,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "detection": {
            "n_matched": n_matched,
            "precision": det_p,
            "recall": det_r,
            "f1": det_f1,
        },
        "coding": {
            "n": n_matched,
            "accuracy": correct / n_matched if n_matched else 0.0,
            **tally,
        },
        **tally,
        **buckets,
    }


# --- uncertainty -------------------------------------------------------------


def bootstrap_ci(
    records: list[Record],
    golds: list["GoldMention"],
    span_match: str = "exact",
    exclude: set[str] | None = None,
    vocab: Any = None,
    n_boot: int = 1000,
    seed: int = 0,
    alpha: float = 0.05,
) -> dict[str, Any]:
    """Percentile bootstrap over DOCUMENTS for the headline and layer numbers.

    Exists because "S2 beat S1 by half a point" is not a finding on 226
    mentions unless half a point clears the noise, and until now the noise
    band was a hand-wave. Documents are the resampling unit — mentions within
    a post share a model call, a topic and an author, so resampling mentions
    would pretend 226 independent draws and report a band too tight.

    Pairing is within-document by construction (span keys carry doc_id), so
    each document's counts are computed ONCE and the resamples sum them —
    1000 draws cost arithmetic, not 1000 scoring passes.

    Returns {"f1": {lo, hi}, "detection_f1": {...}, "coding_accuracy": {...},
    "n_boot": ..., "seed": ...}. Deterministic under a seed.
    """
    doc_ids = sorted({r.doc_id for r in records} | {g.doc_id for g in golds})
    per_doc = {}
    for d in doc_ids:
        s = score_run(
            [r for r in records if r.doc_id == d],
            [g for g in golds if g.doc_id == d],
            span_match=span_match,
            exclude=exclude,
            vocab=vocab,
        )
        per_doc[d] = (
            s["n_pred"], s["n_gold"], s["correct"], s["detection"]["n_matched"]
        )

    rng = random.Random(seed)
    draws: dict[str, list[float]] = {"f1": [], "detection_f1": [], "coding_accuracy": []}
    for _ in range(n_boot):
        n_pred = n_gold = correct = matched = 0
        for d in rng.choices(doc_ids, k=len(doc_ids)):
            p, g, c, m = per_doc[d]
            n_pred += p; n_gold += g; correct += c; matched += m
        prec = correct / n_pred if n_pred else 0.0
        rec_ = correct / n_gold if n_gold else 0.0
        draws["f1"].append(2 * prec * rec_ / (prec + rec_) if prec + rec_ else 0.0)
        dp = matched / n_pred if n_pred else 0.0
        dr = matched / n_gold if n_gold else 0.0
        draws["detection_f1"].append(2 * dp * dr / (dp + dr) if dp + dr else 0.0)
        draws["coding_accuracy"].append(correct / matched if matched else 0.0)

    def pct(xs: list[float], q: float) -> float:
        xs = sorted(xs)
        i = min(int(q * len(xs)), len(xs) - 1)
        return xs[i]

    out: dict[str, Any] = {"n_boot": n_boot, "seed": seed, "span_match": span_match}
    for k, xs in draws.items():
        out[k] = {"lo": pct(xs, alpha / 2), "hi": pct(xs, 1 - alpha / 2)}
    return out

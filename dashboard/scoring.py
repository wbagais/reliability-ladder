"""Scores come ONLY from `ladder.score.score_run` / `bootstrap_ci` (governing
rule). This module assembles their inputs from the pipeline's own loaders and
attaches per-record outcomes for drill-downs — pairing reuses the scorer's own
`_pair`, so the dashboard cannot disagree with the headline it links from.
"""
from __future__ import annotations

from typing import Any

from ladder.corpus import gold_records
from ladder.score import _pair, bootstrap_ci, outcome, score_run

from dashboard.runsindex import RunInfo, run_doc_ids
from dashboard.state import AppState


def golds_for_run(state: AppState, info: RunInfo):
    """Gold mentions for the run's SPLIT, or None sans corpus.

    The split's full document list, not the documents that produced records —
    a document the extractor answered nothing for still owes its gold
    mentions to the denominator (they are false negatives, not absentees).
    Only when no split matches does the run's own document set stand in."""
    corpus = state.corpus()
    if corpus is None:
        return None
    split = state.run_split(info)
    doc_ids = (state.splits() or {}).get(split) or sorted(run_doc_ids(info))
    return gold_records(corpus, [d for d in doc_ids if d in corpus])


def score_payload(state: AppState, info: RunInfo, span_match: str,
                  n_boot: int = 1000, seed: int = 0) -> dict[str, Any] | None:
    golds = golds_for_run(state, info)
    if golds is None:
        return None
    records = state.records(info)
    exclude = state.exclusions()
    vocab = state.registry()
    score = score_run(records, golds, span_match=span_match,
                      exclude=exclude, vocab=vocab)
    ci = bootstrap_ci(records, golds, span_match=span_match, exclude=exclude,
                      vocab=vocab, n_boot=n_boot, seed=seed)
    return {"score": score, "ci": ci, "vocab_available": vocab is not None}


def annotate_records(state: AppState, info: RunInfo,
                     span_match: str) -> list[dict] | None:
    """One annotation per record (aligned with state.records): the five-way
    outcome under the given span mode, the matched gold mention's codes, and
    the outcome the WITHHELD answer would have had (rung 5's bill).

    Pairing is the scorer's own `_pair`; excluded gold mentions are dropped
    from the gold side exactly as `score_run` drops them, so an excluded
    mention renders as unmatched/excluded, never as an error."""
    golds = golds_for_run(state, info)
    if golds is None:
        return None
    records = state.records(info)
    exclude = state.exclusions()
    vocab = state.registry()
    reaction_golds = [g for g in golds if g.entity_type == "reaction"
                      and g.record_id not in exclude]
    excluded_golds = [g for g in golds if g.entity_type == "reaction"
                      and g.record_id in exclude]
    reaction_records = [r for r in records if r.entity_type == "reaction"]
    paired = dict(
        (id(r), g) for r, g in _pair(reaction_records, reaction_golds, span_match))

    from ladder.score import _overlaps

    out: list[dict] = []
    for rec in records:
        if rec.entity_type != "reaction":
            out.append({"outcome": None, "matched": False})
            continue
        gold = paired.get(id(rec))
        on_excluded = any(
            g.doc_id == rec.doc_id and _overlaps(rec.spans, g.spans)
            for g in excluded_golds) if gold is None else False
        ann: dict[str, Any] = {
            "matched": gold is not None,
            "excluded": on_excluded,
            "outcome": None,
            "gold_sct": list(gold.sct) if gold is not None else None,
            "gold_kind": gold.gold_kind if gold is not None else None,
        }
        if gold is not None:
            ann["outcome"] = outcome(rec, gold, vocab)
            withheld = (rec.checks or {}).get("withheld") or {}
            if withheld.get("sct") is not None:
                ghost = rec.copy(sct=withheld.get("sct"))
                ann["withheld_outcome"] = outcome(ghost, gold, vocab)
        elif on_excluded:
            ann["outcome"] = "excluded"
        else:
            ann["outcome"] = "unmatched"  # false positive at this span
        out.append(ann)
    return out

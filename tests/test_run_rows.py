"""The results row — where every measured number is actually written.

`ladder/run.py` had no test coverage over `snapshot_row`, which is the function
that turns a record set into the CSV the article quotes. That is the same gap
that let a NameError in scripts/full_run.py survive the renumber.

These build record sets by hand: no corpus, no vocabulary, no model.
"""

import pytest

from ladder.corpus import GOLD_NONE, GOLD_SINGLE, GoldMention
from ladder.run import CSV_COLUMNS, snapshot_row
from ladder.schema import CONCEPT_LESS, REACTION, Record, ZONE_ACCEPT


def gold(**kw):
    base = dict(
        doc_id="D1", index=0, entity_type=REACTION, cadec_type="ADR",
        text="bit drowsy", spans=[(9, 19)], sct=["271782001"], gold_kind=GOLD_SINGLE,
    )
    base.update(kw)
    return GoldMention(**base)


def rec(**kw):
    base = dict(
        doc_id="D1", entity_type=REACTION, text="bit drowsy",
        spans=[(9, 19)], sct="271782001", zone=ZONE_ACCEPT,
    )
    base.update(kw)
    return Record(**base)


class FakeVocab:
    """162076009 retired, replaced by 271782001. A fixture, not a release fact."""

    def replacements(self, code):
        return ["271782001"] if str(code) == "162076009" else []

    def is_active(self, code):
        return str(code) != "162076009"


def row_for(records, golds, **kw):
    from collections import Counter

    from ladder.score import outcome, reaction_sct_strict

    g = {m.record_id: m for m in golds}
    row, _ = snapshot_row(
        0, "bare LLM", records, Counter(r.zone for r in records), {},
        is_correct=reaction_sct_strict, gold=g, outcome_fn=outcome, **kw
    )
    return row


# --- the columns exist and are declared --------------------------------------


def test_outdated_and_abstained_are_declared_columns():
    """A number written into a row nobody declared never reaches the CSV —
    write_results uses a DictWriter over CSV_COLUMNS and drops the rest."""
    assert "sct_outdated" in CSV_COLUMNS
    assert "sct_abstained" in CSV_COLUMNS


# --- what the columns count --------------------------------------------------


def test_a_retired_code_is_counted_outdated_not_correct():
    r = row_for([rec(sct="162076009")], [gold()], vocab=FakeVocab())
    assert r["sct_outdated"] == 1
    assert r["f1_sct_strict"] == 0.0, "outdated is an error, not a hit"
    assert r["corrupted"] == 1


def test_without_a_vocabulary_outdated_is_zero_and_the_error_remains():
    """No index must never move the headline. It only stops splitting errors."""
    r = row_for([rec(sct="162076009")], [gold()])
    assert r["sct_outdated"] == 0
    assert r["corrupted"] == 1
    assert r["f1_sct_strict"] == 0.0


def test_concept_less_on_a_coded_mention_is_counted_abstained():
    r = row_for([rec(sct=CONCEPT_LESS)], [gold()], vocab=FakeVocab())
    assert r["sct_abstained"] == 1
    assert r["corrupted"] == 1


def test_a_correct_record_counts_in_neither_column():
    r = row_for([rec()], [gold()], vocab=FakeVocab())
    assert (r["sct_outdated"], r["sct_abstained"]) == (0, 0)
    assert r["f1_sct_strict"] == 1.0


def test_outdated_and_abstained_never_exceed_the_errors():
    records = [
        rec(spans=[(9, 19)], sct="271782001"),      # correct
        rec(spans=[(30, 44)], sct="162076009"),     # outdated
        rec(spans=[(50, 60)], sct=CONCEPT_LESS),    # abstained
        rec(spans=[(70, 80)], sct="246636008"),     # incorrect
    ]
    golds = [
        gold(index=0, spans=[(9, 19)]),
        gold(index=1, spans=[(30, 44)]),
        gold(index=2, spans=[(50, 60)]),
        gold(index=3, spans=[(70, 80)]),
    ]
    r = row_for(records, golds, vocab=FakeVocab())
    assert r["corrupted"] == 3
    assert r["sct_outdated"] + r["sct_abstained"] == 2


def test_no_scorer_leaves_every_accuracy_column_empty():
    """The documented behaviour: empty, never guessed."""
    from collections import Counter

    row, errors = snapshot_row(
        0, "bare LLM", [rec()], Counter(), {}, is_correct=None, gold=None
    )
    assert errors is None
    assert row["sct_outdated"] == ""
    assert row["f1_sct_strict"] == ""

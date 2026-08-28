"""Gold that contradicts itself cannot grade a model.

The rule (user's, 2026-08-28): for every annotated span text occurring more
than once — across documents or repeated within one — compare the code sets
assigned at each location. A SUPERSET is not a disagreement (the scorer already
credits any code in the gold set, and 'joint pain' is 57676002 seventy-eight
times and 57676002+68962001 once); occurrences sharing NO code are. Every
document carrying such an annotation leaves the evaluation.

Measured over CADEC: 16 span texts, 109 mentions, 93 of 1250 documents —
pool 89, dev 2, test 2.
"""

from types import SimpleNamespace

from ladder import clean


def m(rid, doc, text, codes, entity_type="reaction"):
    return SimpleNamespace(record_id=rid, doc_id=doc, text=text,
                           spans=[(0, len(text))], sct=list(codes),
                           entity_type=entity_type)


def test_the_same_text_coded_two_different_ways_excludes_both_documents():
    rows = clean.inconsistent_gold([
        m("A#0", "A", "tendonitis", ["34840004"]),
        m("B#0", "B", "tendonitis", ["21545007"]),
    ])
    assert {r["doc_id"] for r in rows} == {"A", "B"}
    assert all(r["reason"] == clean.EXCLUDE_INCONSISTENT_GOLD for r in rows)
    assert "tendonitis" in rows[0]["detail"]


def test_a_superset_is_not_a_disagreement():
    """'joint pain' is 57676002 x78 and 57676002+68962001 x1. They share the
    code, the scorer credits either, and excluding 79 documents over one
    added post-coordination would cost 40% of dev's gold for nothing."""
    assert clean.inconsistent_gold([
        m("A#0", "A", "joint pain", ["57676002"]),
        m("B#0", "B", "joint pain", ["57676002", "68962001"]),
    ]) == []


def test_a_text_that_occurs_once_is_never_inconsistent():
    assert clean.inconsistent_gold([m("A#0", "A", "gout", ["90560007"])]) == []


def test_repeats_inside_one_document_count_too():
    """The rule is about the annotation, not about file boundaries."""
    rows = clean.inconsistent_gold([
        m("A#0", "A", "sore", ["22253000"]),
        m("A#1", "A", "sore", ["68962001"]),
    ])
    assert {r["doc_id"] for r in rows} == {"A"}


def test_whitespace_and_case_do_not_make_two_keywords():
    assert clean.inconsistent_gold([
        m("A#0", "A", "Leg  Cramps", ["449917004"]),
        m("B#0", "B", "leg cramps", ["449918009"]),
    ])


def test_concept_less_gold_is_left_alone():
    """No codes is an ANSWER, not a contradiction — same posture as the
    invalid-code rule, which skips CONCEPT_LESS deliberately."""
    assert clean.inconsistent_gold([
        m("A#0", "A", "felt odd", []),
        m("B#0", "B", "felt odd", []),
    ]) == []


def test_every_mention_in_the_document_is_excluded_not_just_the_keyword():
    """The unit is the DOCUMENT: an annotator who coded one span two ways is
    not trustworthy on the rest of that file either."""
    rows = clean.inconsistent_gold([
        m("A#0", "A", "sore", ["22253000"]),
        m("A#1", "A", "nausea", ["422587007"]),
        m("B#0", "B", "sore", ["68962001"]),
    ])
    assert {r["record_id"] for r in rows} == {"A#0", "A#1", "B#0"}


def test_drug_mentions_are_not_considered():
    assert clean.inconsistent_gold([
        m("A#0", "A", "lipitor", ["1"], entity_type="drug"),
        m("B#0", "B", "lipitor", ["2"], entity_type="drug"),
    ]) == []

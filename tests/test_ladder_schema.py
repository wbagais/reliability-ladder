"""Record + span grounding — the A/B contract.

No corpus and no vocabulary: these run anywhere, including on a checkout where
the licensed CADEC download is absent.
"""

import pytest

from ladder.schema import (
    CONCEPT_LESS,
    DRUG,
    R_SCHEMA_INVALID,
    R_SPAN_OUT_OF_RANGE,
    R_SPAN_UNGROUNDED,
    REACTION,
    Record,
    ZONE_ACCEPT,
    ZONE_NEW,
    loads,
    dumps,
)

SOURCE = "I feel a bit drowsy & have a little blurred vision, so far no gastric problems."


def rec(**kw):
    base = dict(doc_id="D1", entity_type=REACTION, text="bit drowsy", spans=[(9, 19)])
    base.update(kw)
    return Record(**base)


def test_grounded_span_passes():
    assert rec().valid(SOURCE) == (True, None)


def test_shifted_span_is_ungrounded():
    ok, reason = rec(spans=[(11, 21)]).valid(SOURCE)
    assert (ok, reason) == (False, R_SPAN_UNGROUNDED)


def test_span_past_end_of_document():
    ok, reason = rec(spans=[(900, 910)]).valid(SOURCE)
    assert (ok, reason) == (False, R_SPAN_OUT_OF_RANGE)


def test_discontinuous_span_in_offset_order():
    r = rec(text="feel drowsy", spans=[(2, 6), (13, 19)])
    assert r.valid(SOURCE)[0]


def test_discontinuous_span_quoted_in_reading_order():
    """45 of CADEC's own gold mentions quote segments out of offset order.

    "swelling feet" for spans [feet][swelling]. Requiring concatenation order
    would call the answer key ungrounded, so the comparison is a token bag.
    """
    r = rec(text="drowsy feel", spans=[(2, 6), (13, 19)])
    assert r.valid(SOURCE)[0]


def test_case_and_whitespace_are_not_fabrication():
    assert rec(text="  Bit   Drowsy ").valid(SOURCE)[0]


@pytest.mark.parametrize(
    "kw",
    [
        dict(spans=[]),
        dict(text="   "),
        dict(spans=[(19, 9)]),
        dict(spans=[(-1, 5)]),
        dict(entity_type="ADR"),  # collapsed away at the adapter, invalid here
    ],
)
def test_malformed_records_are_schema_invalid(kw):
    ok, reason = rec(**kw).valid(SOURCE)
    assert not ok and reason in (R_SCHEMA_INVALID, R_SPAN_OUT_OF_RANGE)


def test_mark_appends_provenance_and_never_rewrites():
    r = rec()
    assert r.zone == ZONE_NEW
    r.mark(1, ZONE_ACCEPT)
    r.mark(2, "VERIFIED")
    assert [p["rung"] for p in r.provenance] == [1, 2]
    assert r.provenance[0]["from"] == ZONE_NEW and r.provenance[0]["to"] == ZONE_ACCEPT
    assert r.zone == "VERIFIED"


def test_mark_rejects_an_unknown_zone():
    with pytest.raises(ValueError):
        rec().mark(1, "SOMEWHERE_ELSE")


def test_roundtrip_through_jsonl():
    rs = [rec(sct="271782001"), rec(entity_type=DRUG, sct=CONCEPT_LESS, spans=[(9, 19), (20, 25)])]
    back = loads(dumps(rs))
    assert [r.to_dict() for r in back] == [r.to_dict() for r in rs]
    assert back[1].spans == [(9, 19), (20, 25)]

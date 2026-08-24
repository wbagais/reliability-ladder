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


# --- sct_label: the model's own claim about what its code means -------------
#
# A bare code is an unverifiable assertion. A code PLUS the label the model
# believes it carries is checkable against the vocabulary for free, with no
# extra model call — which is what turns confabulation into a deterministic
# rung 1 check rather than something only a judge rung could catch.


def test_record_has_an_sct_label_defaulting_to_none():
    assert rec().sct_label is None


def test_sct_label_survives_a_round_trip():
    from ladder.schema import loads as _loads

    r = rec(sct="12063002", sct_label="Rectal hemorrhage")
    back = Record.from_dict(r.to_dict())
    assert back.sct_label == "Rectal hemorrhage"


def test_sct_label_is_absent_from_older_records():
    """schemas are APPEND-ONLY: a record written before this field must load."""
    d = rec().to_dict()
    d.pop("sct_label")
    assert Record.from_dict(d).sct_label is None


def test_label_mismatch_is_a_known_reject_reason():
    from ladder.schema import R_LABEL_MISMATCH, REJECT_REASONS

    assert R_LABEL_MISMATCH in REJECT_REASONS


def test_appended_reasons_go_at_the_end():
    """Reasons are append-only — reordering renumbers every earlier report."""
    from ladder.schema import R_LABEL_MISMATCH, R_SCHEMA_INVALID, REJECT_REASONS

    assert REJECT_REASONS[0] == R_SCHEMA_INVALID
    assert REJECT_REASONS[-1] == R_LABEL_MISMATCH

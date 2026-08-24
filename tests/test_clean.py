"""Gold cleaning — the exclusion list, produced before any rung runs.

EXCLUDE, NEVER CORRECT. Rewriting a gold code so our numbers improve is how a
benchmark stops being evidence. A mention that cannot be answered is dropped
from the denominator and COUNTED, so the shortfall is stated rather than hidden
inside an unexplained ceiling.

What qualifies, measured 2026-08-24 over CADEC's 7,311 gold reaction mentions:

    3  every gold code is invalid — 20070731 is a DATE (2007-07-31 in RF2's
       effectiveTime format), 21499005 and 81680008 fail the Verhoeff check
       digit that terminates every SNOMED identifier, so neither was ever
       issued and neither can be a retired concept
    4  the quoted text does not sit at the quoted offsets

A mention with an invalid code that ALSO carries a valid one (post-coordinated)
stays: it is still answerable.
"""

import pytest

from ladder.clean import (
    EXCLUDE_INVALID_CODE,
    EXCLUDE_SPAN_MISMATCH,
    build_exclusions,
    load_exclusions,
    verhoeff_ok,
)


# --- the check digit --------------------------------------------------------


@pytest.mark.parametrize("code", ["12063002", "213257006", "24199005", "81680005"])
def test_real_snomed_ids_pass_the_check_digit(code):
    assert verhoeff_ok(code) is True


@pytest.mark.parametrize("code", ["20070731", "21499005", "81680008", "21290011000036100"])
def test_the_four_gold_oddities_fail_the_check_digit(code):
    """Not retired concepts — never issued. That is what makes them corruption
    rather than a vocabulary gap."""
    assert verhoeff_ok(code) is False


def test_a_non_numeric_string_is_not_a_valid_id():
    assert verhoeff_ok("CONCEPT_LESS") is False
    assert verhoeff_ok("") is False


# --- building the list ------------------------------------------------------


class FakeMention:
    def __init__(self, doc_id, index, text, spans, sct, entity_type="reaction"):
        self.doc_id, self.index, self.text = doc_id, index, text
        self.spans, self.sct, self.entity_type = spans, sct, entity_type

    @property
    def record_id(self):
        return f"{self.doc_id}#{self.index}"


SOURCE = "I feel a bit drowsy and have blurred vision today."
DOCS = {"D1": SOURCE}


def test_a_mention_whose_only_code_is_invalid_is_excluded():
    m = FakeMention("D1", 0, "bit drowsy", [(9, 19)], ["21499005"])
    rows = build_exclusions([m], DOCS)
    assert rows[0]["record_id"] == "D1#0"
    assert rows[0]["reason"] == EXCLUDE_INVALID_CODE


def test_a_post_coordinated_mention_with_one_valid_code_is_kept():
    """['67849003', '20070731'] — |Excruciating pain| plus a stray date. Still
    answerable, so it stays in the denominator."""
    m = FakeMention("D1", 0, "bit drowsy", [(9, 19)], ["67849003", "20070731"])
    assert build_exclusions([m], DOCS) == []


def test_a_valid_mention_is_kept():
    m = FakeMention("D1", 0, "bit drowsy", [(9, 19)], ["271782001"])
    assert build_exclusions([m], DOCS) == []


def test_concept_less_is_kept():
    """No code is the ANSWER, not corruption."""
    m = FakeMention("D1", 0, "bit drowsy", [(9, 19)], [])
    assert build_exclusions([m], DOCS) == []


def test_a_span_that_does_not_match_its_offsets_is_excluded():
    m = FakeMention("D1", 0, "purple monkey", [(9, 19)], ["271782001"])
    rows = build_exclusions([m], DOCS)
    assert rows[0]["reason"] == EXCLUDE_SPAN_MISMATCH


def test_segment_order_does_not_count_as_a_mismatch():
    """45 gold mentions quote discontinuous segments in reading order rather
    than offset order. The comparison is a token bag, as it is in Record."""
    m = FakeMention("D1", 0, "drowsy feel", [(2, 6), (13, 19)], ["271782001"])
    assert build_exclusions([m], DOCS) == []


def test_the_reason_is_recorded_for_every_row():
    ms = [
        FakeMention("D1", 0, "bit drowsy", [(9, 19)], ["21499005"]),
        FakeMention("D1", 1, "purple monkey", [(9, 19)], ["271782001"]),
    ]
    rows = build_exclusions(ms, DOCS)
    assert {r["reason"] for r in rows} == {EXCLUDE_INVALID_CODE, EXCLUDE_SPAN_MISMATCH}
    assert all(r.get("detail") for r in rows)


# --- the file ---------------------------------------------------------------


def test_the_list_round_trips_through_csv(tmp_path):
    from ladder.clean import write_exclusions

    ms = [FakeMention("D1", 0, "bit drowsy", [(9, 19)], ["21499005"])]
    path = tmp_path / "ex.csv"
    write_exclusions(build_exclusions(ms, DOCS), path)
    assert load_exclusions(path) == {"D1#0"}


def test_a_missing_file_means_nothing_is_excluded(tmp_path):
    """A run without the file must score EVERYTHING rather than silently
    dropping nothing-in-particular."""
    assert load_exclusions(tmp_path / "absent.csv") == set()


# --- retired gold codes -----------------------------------------------------
#
# The keyword table holds ACTIVE concepts only: retired ones are duplicates
# superseded by a live concept, and keeping them made 23,334 keywords ambiguous
# against 103 without them. A mention whose every gold code is retired is
# therefore unanswerable through the table, so it leaves the denominator too —
# 410 mentions, 5.6%. Excluded and counted, never rewritten to the live code.


class FakeVocab:
    RETIRED = {"30989003", "162076009"}

    def is_active(self, code):
        return code not in self.RETIRED


def test_a_mention_whose_only_code_is_retired_is_excluded():
    from ladder.clean import EXCLUDE_RETIRED_CODE

    m = FakeMention("D1", 0, "bit drowsy", [(9, 19)], ["30989003"])
    rows = build_exclusions([m], DOCS, vocab=FakeVocab())
    assert rows[0]["reason"] == EXCLUDE_RETIRED_CODE


def test_a_mention_with_one_active_code_is_kept():
    m = FakeMention("D1", 0, "bit drowsy", [(9, 19)], ["30989003", "271782001"])
    assert build_exclusions([m], DOCS, vocab=FakeVocab()) == []


def test_without_a_vocabulary_nothing_is_excluded_for_retirement():
    """No vocabulary, no claim: better to score everything than to drop an
    unknown set."""
    m = FakeMention("D1", 0, "bit drowsy", [(9, 19)], ["30989003"])
    assert build_exclusions([m], DOCS) == []

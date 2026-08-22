"""Contract 4 — both vocabulary backends, and the one MedDRA table.

The point of a contract is that two implementations are substitutable. These
tests assert the substitutable part and pin the part that is NOT: the OLS4
backend cannot see retired concepts or extension modules, and that difference
decides the rung 1 rejection rate.

No network: the OLS4 backend is exercised through a stubbed transport.
"""

import pytest

import bench.vocab as vocab
from ladder.registry import MeddraTable
from schemas.vocabulary import FINDING, NOT_FINDING, UNKNOWN, conforms


# --- the contract -----------------------------------------------------------


def test_the_ols4_backend_satisfies_the_contract():
    assert conforms(vocab.Ols4Vocabulary()) == []


def test_a_backend_missing_a_method_is_rejected_by_select(monkeypatch):
    """A half-implemented backend must fail at selection, not at the first call
    deep inside a run."""

    class Broken:
        name = "broken"

        def exists(self, code):
            return True

    monkeypatch.setattr(vocab, "_SELECTED", None)
    monkeypatch.setattr(vocab, "Ols4Vocabulary", Broken)
    with pytest.raises(TypeError, match="Vocabulary contract"):
        vocab.select(prefer="ols4", quiet=True)


def test_the_backend_declares_whether_it_is_lossy():
    """A number is not comparable across backends, so the run has to record which."""
    assert vocab.Ols4Vocabulary().lossy is True
    assert vocab.Ols4Vocabulary().name == "ols4"


# --- the OLS4 backend, without a network ------------------------------------


@pytest.fixture
def ols(monkeypatch, tmp_path):
    """OLS4 with a scripted transport: it knows one active international code."""
    ACTIVE = "60862001"

    def fake_get(url, key):
        if key.startswith(("exists_", "search_")):
            code = key.split("_", 1)[1].split("_")[0]
            if code == ACTIVE or code == "Tinnitus":
                return {"response": {"docs": [{"obo_id": f"SNOMED:{ACTIVE}", "label": "Tinnitus"}]}}
            return {"response": {"docs": []}}
        if key.startswith("anc_"):
            return {"_embedded": {"terms": [{"obo_id": "SNOMED:404684003"}]}}
        return {}

    monkeypatch.setattr(vocab, "_get", fake_get)
    monkeypatch.setattr(vocab, "CACHE", tmp_path)
    return vocab.Ols4Vocabulary()


def test_ols4_answers_for_an_active_international_code(ols):
    assert ols.exists("60862001")
    assert ols.finding_status("60862001") == FINDING
    assert ols.preferred("60862001") == "Tinnitus"
    assert ols.lexical_match("tinnitus", "60862001")


def test_ols4_reports_an_invented_code_as_absent(ols):
    assert not ols.exists("999999999")


def test_ols4_cannot_distinguish_retired_from_invented(ols):
    """The finding behind the 23.9%: to OLS4 a retired code and a hallucinated
    one are the same answer. |Knee pain| 30989003 is real, retired, and
    clinically correct — and this backend calls it nonexistent."""
    assert not ols.exists("30989003")
    assert ols.finding_status("30989003") == UNKNOWN, "must be UNKNOWN, never NOT_FINDING"


def test_finding_status_is_never_not_finding_for_a_code_the_backend_cannot_see(ols):
    """UNKNOWN and NOT_FINDING are different claims, and only one may reject."""
    for code in ("30989003", "999999999", "4031011000036106"):
        assert ols.finding_status(code) != NOT_FINDING


# --- the module-level surface delegates -------------------------------------


def test_the_public_functions_use_the_selected_backend(monkeypatch):
    class Fake:
        name, release, lossy = "fake", "r", False
        def exists(self, c): return c == "1"
        def is_active(self, c): return True
        def finding_status(self, c): return FINDING if c == "1" else UNKNOWN
        def is_finding(self, c): return c == "1"
        def terms(self, c): return ["Fake term"]
        def preferred(self, c): return "Fake term"
        def lexical_match(self, t, c, mode="exact"): return True
        def search(self, t, rows=5): return [{"code": "1", "label": "Fake term"}]

    monkeypatch.setattr(vocab, "_SELECTED", Fake())
    assert vocab.exists("1") and not vocab.exists("2")
    assert vocab.is_finding("1") and not vocab.is_finding("2")
    assert vocab.label("1") == vocab.preferred("1") == "Fake term"
    assert vocab.search("x")[0]["code"] == "1"


# --- the vocabulary-free checks ---------------------------------------------

SRC = "I feel a bit drowsy & have a little blurred vision, so far no gastric problems."


def test_grounded_tolerates_case_and_spacing():
    """Exact substring comparison false-rejects 8% of CADEC gold; this does not."""
    assert vocab.grounded(SRC, (9, 19), "bit drowsy")
    assert vocab.grounded(SRC, (9, 19), "  Bit   Drowsy ")
    assert not vocab.grounded(SRC, (11, 21), "bit drowsy")


def test_negated_fires_on_the_plans_worked_example():
    i = SRC.find("gastric problems")
    assert vocab.negated(SRC, (i, i + 16))


def test_negated_does_not_fire_on_an_asserted_mention():
    assert not vocab.negated(SRC, (9, 19))


def test_negated_ignores_a_cue_that_is_part_of_the_mention():
    t = "Since starting it I have no energy at all."
    i = t.find("no energy")
    assert not vocab.negated(t, (i, i + 9))


# --- MedDRA: one implementation -------------------------------------------

CSV = "data/meddra_codes.example.csv"


def test_meddra_is_one_class_under_two_names():
    assert vocab.MedDRA is MeddraTable


def test_reference_mode_refuses_to_retrieve():
    """The safeguard: a list derived from the answer key makes retrieval
    trivially correct, so searching it has to be a declared choice."""
    t = MeddraTable(CSV, mode="reference")
    with pytest.raises(RuntimeError, match="answer_space"):
        t.search("pain")


def test_answer_space_mode_retrieves():
    t = MeddraTable(CSV, mode="answer_space")
    assert t.search("muscle cramp", 3)[0]["code"] == "10028294"


def test_an_unknown_mode_is_rejected_at_construction():
    with pytest.raises(ValueError):
        MeddraTable(CSV, mode="whatever")


def test_leakage_reports_a_derived_table_as_derived():
    t = MeddraTable(CSV)
    gold = set(t.terms_by_code)
    leak = t.leakage(gold)
    assert leak["derived_from_gold"] is True
    assert leak["n_independent_of_gold"] == 0
    assert leak["caveat"]


def test_leakage_reports_an_independent_table_as_independent():
    t = MeddraTable(CSV)
    leak = t.leakage({"10033371"})
    assert leak["derived_from_gold"] is False
    assert leak["n_independent_of_gold"] == len(t) - 1
    assert leak["caveat"] == ""


def test_cross_vocabulary_agreement_needs_no_mapping_table():
    """Unlike an existence check, this compares two PREDICTIONS — no leakage."""
    class Snomed:
        def preferred(self, code): return {"22253000": "Pain"}.get(code)

    t = MeddraTable(CSV)
    assert t.agrees_with_sct("10033371", "22253000", Snomed()) is True
    assert t.agrees_with_sct("10016256", "22253000", Snomed()) is False
    assert t.agrees_with_sct("10033371", "999", Snomed()) is None

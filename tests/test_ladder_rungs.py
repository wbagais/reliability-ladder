"""Rungs 1 and 2 against a stub vocabulary.

The real registry is a 365 MB index built from a licensed SNOMED release, which
no CI box will have. Everything rung 1 asks a vocabulary is three predicates and
a term list, so the tests use a hand-written stand-in — which also means the
expected zone for each case is legible in the test rather than buried in a
snapshot of a 700k-concept hierarchy.
"""

from ladder.ledger import Ledger
from ladder.rungs import r1, r2
from ladder.schema import (
    CONCEPT_LESS,
    R_MEDDRA_UNKNOWN,
    ZONE_NEW,
    DRUG,
    R_CODE_INACTIVE,
    R_CODE_UNKNOWN,
    R_NEGATED,
    R_SPAN_UNGROUNDED,
    R_UNRESOLVED,
    R_WRONG_SEMANTIC_TYPE,
    REACTION,
    Record,
    ZONE_ABSTAIN,
    ZONE_ACCEPT,
    ZONE_BAND,
    ZONE_REJECT,
    ZONE_VERIFIED,
)

SOURCE = "I feel a bit drowsy & have a little blurred vision, so far no gastric problems."


class StubVocab:
    """Four concepts: an active finding, a retired finding, a procedure, a product."""

    CONCEPTS = {
        "271782001": ("finding", True, ["Drowsy", "Somnolence", "Sleepiness"]),
        "30989003": ("finding", False, ["Knee pain"]),  # retired, still a finding
        "71388002": ("not_finding", True, ["Procedure"]),
        "3384011000036100": ("not_finding", True, ["Arthrotec"]),
        "419723007": ("unknown", False, ["Mentally dull"]),  # retired, unplaceable
    }

    def exists(self, code):
        return code in self.CONCEPTS

    def is_active(self, code):
        return self.CONCEPTS.get(code, (None, False, None))[1]

    def finding_status(self, code):
        return self.CONCEPTS.get(code, ("unknown", False, None))[0]

    def is_finding(self, code):
        return self.finding_status(code) == "finding"

    def terms(self, code):
        return self.CONCEPTS.get(code, (None, None, []))[2]

    def lexical_match(self, text, code, mode="exact"):
        want = " ".join(text.lower().split())
        toks = set(want.split())
        for term in self.terms(code):
            got = term.lower()
            if got == want:
                return True
            if mode == "contained":
                other = set(got.split())
                if other and (toks <= other or other <= toks):
                    return True
        return False


def rec(**kw):
    base = dict(doc_id="D1", entity_type=REACTION, text="bit drowsy", spans=[(9, 19)])
    base.update(kw)
    return Record(**base)


def z(record, **cfg):
    return r1.zone(record, SOURCE, StubVocab(), cfg)


# --- the five checks --------------------------------------------------------


def test_vocabulary_words_accept():
    zone, reason, checks = z(rec(text="drowsy", spans=[(13, 19)], sct="271782001"))
    assert (zone, reason) == (ZONE_ACCEPT, None)
    assert checks["lexical_match"] is True


def test_colloquial_wording_bands_rather_than_rejects():
    """Rung 1 may never claim a code is right, so a lexical miss is BAND."""
    r = rec(text="little blurred vision", spans=[(29, 50)], sct="271782001")
    zone, reason, checks = z(r)
    assert (zone, reason) == (ZONE_BAND, None)
    assert checks["reason_band"] == "colloquial_no_lexical_match"


def test_lexical_mode_moves_the_accept_band_divider_and_nothing_else():
    """The two modes must never disagree about REJECT — only about ACCEPT."""
    r = rec(text="a bit drowsy", spans=[(7, 19)], sct="271782001")
    assert z(r, lexical_mode="contained")[0] == ZONE_ACCEPT  # "Drowsy" is a subset
    assert z(r, lexical_mode="exact")[0] == ZONE_BAND
    bad = rec(text="a bit drowsy", spans=[(7, 19)], sct="999999999")
    assert z(bad, lexical_mode="contained")[0] == z(bad, lexical_mode="exact")[0] == ZONE_REJECT


def test_hallucinated_code_rejects():
    assert z(rec(sct="999999999"))[:2] == (ZONE_REJECT, R_CODE_UNKNOWN)


def test_wrong_semantic_type_rejects():
    assert z(rec(sct="71388002"))[:2] == (ZONE_REJECT, R_WRONG_SEMANTIC_TYPE)


def test_ungrounded_span_rejects_before_any_lookup():
    """Span grounding is free, so it must fire on a record whose code is fine."""
    assert z(rec(spans=[(11, 21)], sct="271782001"))[:2] == (ZONE_REJECT, R_SPAN_UNGROUNDED)


def test_drug_product_code_is_not_a_semantic_type_error():
    r = rec(entity_type=DRUG, text="drowsy", spans=[(13, 19)], sct="3384011000036100")
    assert z(r)[0] != ZONE_REJECT


def test_finding_scope_all_would_reject_the_drug():
    r = rec(entity_type=DRUG, text="drowsy", spans=[(13, 19)], sct="3384011000036100")
    assert z(r, finding_scope="all")[:2] == (ZONE_REJECT, R_WRONG_SEMANTIC_TYPE)


# --- the three judgement calls ---------------------------------------------


def test_retired_code_survives_by_default():
    """115 of CADEC's 1,046 codes are retired; rejecting them rejects the gold."""
    zone, reason, checks = z(rec(sct="30989003"))
    assert zone != ZONE_REJECT
    assert checks["sct_active"] is False


def test_retired_code_rejects_when_the_manifest_says_so():
    assert z(rec(sct="30989003"), reject_inactive=True)[:2] == (ZONE_REJECT, R_CODE_INACTIVE)


def test_unplaceable_retired_code_is_not_a_semantic_type_error():
    """"Cannot place in the hierarchy" is not "is in the wrong branch"."""
    zone, _, checks = z(rec(sct="419723007"))
    assert zone != ZONE_REJECT
    assert checks["sct_finding_status"] == "unknown"


def test_negation_flags_but_does_not_reject_by_default():
    r = rec(text="gastric problems", spans=[(62, 78)], sct="271782001")
    zone, reason, checks = z(r)
    assert zone != ZONE_REJECT
    assert checks["negated"] is True and checks["negation_cue"] == "no"


def test_negation_rejects_when_the_manifest_says_so():
    r = rec(text="gastric problems", spans=[(62, 78)], sct="271782001")
    assert z(r, negation_action="reject")[:2] == (ZONE_REJECT, R_NEGATED)


def test_concept_less_is_an_answer_not_an_error():
    zone, reason, checks = z(rec(sct=CONCEPT_LESS))
    assert (zone, reason) == (ZONE_BAND, None)
    assert checks["concept_less"] is True


def test_without_a_vocabulary_nothing_is_rejected_for_its_code():
    zone, _, checks = r1.zone(rec(sct="999999999"), SOURCE, None, {})
    assert zone == ZONE_BAND and checks["vocab"] == "unavailable"


# --- rung 2 -----------------------------------------------------------------


def test_abstention_withdraws_the_answer_but_keeps_it(tmp_path):
    r = rec(sct="271782001", confidence=0.4)
    r.mark(1, ZONE_BAND)
    ledger = Ledger(tmp_path / "l.jsonl", run_id="t")
    r2.apply([r], {"D1": SOURCE}, {"ledger": ledger, **r2.DEFAULTS})
    ledger.close()
    assert r.zone == ZONE_ABSTAIN and r.reason == R_UNRESOLVED
    assert r.sct is None, "an abstained record must not still ship an answer"
    assert r.checks["withheld"]["sct"] == "271782001", "abstention escalates, never discards"


def test_accepted_records_are_verified_not_abstained(tmp_path):
    r = rec(sct="271782001")
    r.mark(1, ZONE_ACCEPT)
    ledger = Ledger(tmp_path / "l.jsonl", run_id="t")
    r2.apply([r], {"D1": SOURCE}, {"ledger": ledger, **r2.DEFAULTS})
    ledger.close()
    assert r.zone == ZONE_VERIFIED and r.sct == "271782001"


def test_tau_gate_is_off_at_zero():
    r = rec(sct="271782001", confidence=0.01)
    r.mark(1, ZONE_ACCEPT)
    assert r2.decide(r, {"tau": 0.0})[0] == ZONE_VERIFIED
    assert r2.decide(r, {"tau": 0.5})[0] == ZONE_ABSTAIN


def test_sweep_is_monotone_in_coverage_and_finds_the_free_lunch():
    records = []
    for i in range(10):
        r = rec(sct="271782001", confidence=0.9 if i < 7 else 0.3)
        r.mark(1, ZONE_ACCEPT)
        r.record_id = f"D1#{i}"
        records.append(r)
    wrong = {"D1#7", "D1#8", "D1#9"}  # exactly the low-confidence ones

    curve = r2.sweep(records, is_correct=lambda r: r.record_id not in wrong)
    coverages = [p["coverage"] for p in curve]
    assert coverages == sorted(coverages, reverse=True)
    assert curve[0]["coverage"] == 1.0 and curve[0]["selective_precision"] == 0.7

    lunch = r2.free_lunch(curve)
    assert lunch is not None
    assert lunch["over_abstention"] == 0 and lunch["selective_precision"] == 1.0
    assert 0.3 < lunch["tau"] <= 0.9
    assert r2.aurc(curve) >= 0.0


def test_sweep_never_touches_the_records_it_scores():
    r = rec(sct="271782001", confidence=0.1)
    r.mark(1, ZONE_ACCEPT)
    r2.sweep([r], is_correct=lambda _r: True)
    assert r.zone == ZONE_ACCEPT and r.sct == "271782001"


# --- rung 1 judges; whether it routes is a setting ---------------------------


class StubMeddra:
    """Two codes, standing in for the CADEC-derived table."""

    TERMS = {"10013649": "Drowsiness", "10033371": "Pain"}

    def exists(self, code):
        return str(code) in self.TERMS

    def term(self, code):
        return self.TERMS.get(str(code))

    def lexical_match(self, text, code, mode="exact"):
        t = self.term(code)
        return bool(t) and t.lower() == " ".join(text.lower().split())


def _run_r1(records, tmp_path, **cfg):
    ledger = Ledger(tmp_path / "l.jsonl", run_id="t")
    r1.apply(records, {"D1": SOURCE}, {"registry": StubVocab(), "ledger": ledger, **cfg})
    ledger.close()
    return ledger


def test_observe_mode_judges_without_touching_the_record(tmp_path):
    """Rungs 3-6 must see the set rung 0 produced, not the set rung 1 approved."""
    bad = rec(sct="999999999")
    good = rec(text="drowsy", spans=[(13, 19)], sct="271782001")
    _run_r1([bad, good], tmp_path, mode="observe")

    assert bad.zone == ZONE_NEW and good.zone == ZONE_NEW
    assert bad.provenance == [] and good.provenance == []
    assert bad.sct == "999999999", "observe mode must not withdraw an answer"
    # ...but the verdict is on the record, for rung 2 and rung 3 to read.
    assert bad.checks["r1_verdict"] == ZONE_REJECT
    assert bad.checks["r1_reason"] == R_CODE_UNKNOWN
    assert good.checks["r1_verdict"] == ZONE_ACCEPT


def test_gate_mode_routes(tmp_path):
    bad = rec(sct="999999999")
    _run_r1([bad], tmp_path, mode="gate")
    assert bad.zone == ZONE_REJECT and bad.reason == R_CODE_UNKNOWN
    assert [p["rung"] for p in bad.provenance] == [1]


def test_the_verdict_is_identical_in_both_modes(tmp_path):
    """Only the routing differs — otherwise the comparison is not a comparison."""
    for mode in ("observe", "gate"):
        recs = [
            rec(sct="999999999"),
            rec(sct="71388002"),
            rec(text="drowsy", spans=[(13, 19)], sct="271782001"),
            rec(spans=[(11, 21)], sct="271782001"),
        ]
        _run_r1(recs, tmp_path, mode=mode)
        got = [r.checks["r1_verdict"] for r in recs]
        assert got == [ZONE_REJECT, ZONE_REJECT, ZONE_ACCEPT, ZONE_REJECT], mode


def test_the_ledger_carries_the_verdict_so_the_rate_survives_observe_mode(tmp_path):
    """The rung 1 rejection rate is the milestone; it must not depend on routing."""
    recs = [rec(sct="999999999"), rec(text="drowsy", spans=[(13, 19)], sct="271782001")]
    ledger = _run_r1(recs, tmp_path, mode="observe")
    assert dict(ledger.verdicts(1)) == {ZONE_REJECT: 1, ZONE_ACCEPT: 1}
    assert dict(ledger.reasons(1)) == {R_CODE_UNKNOWN: 1}
    assert dict(ledger.zone_counts(1)) == {ZONE_NEW: 2}


def test_rung_2_abstains_on_the_verdict_when_rung_1_did_not_route(tmp_path):
    bad = rec(sct="999999999")
    band = rec(text="a bit drowsy", spans=[(7, 19)], sct="271782001")
    good = rec(text="drowsy", spans=[(13, 19)], sct="271782001")
    _run_r1([bad, band, good], tmp_path, mode="observe")

    ledger = Ledger(tmp_path / "l2.jsonl", run_id="t")
    r2.apply([bad, band, good], {"D1": SOURCE}, {"ledger": ledger, **r2.DEFAULTS})
    ledger.close()
    assert bad.zone == ZONE_ABSTAIN and bad.reason == R_CODE_UNKNOWN
    assert band.zone == ZONE_ABSTAIN and band.reason == R_UNRESOLVED
    assert good.zone == ZONE_VERIFIED and good.sct == "271782001"


def test_rung_2_reaches_the_same_end_state_in_either_mode(tmp_path):
    """Observe mode defers rung 1's cost to rung 2; it does not cancel it."""
    ends = {}
    for mode in ("observe", "gate"):
        recs = [rec(sct="999999999"), rec(text="drowsy", spans=[(13, 19)], sct="271782001")]
        _run_r1(recs, tmp_path, mode=mode)
        ledger = Ledger(tmp_path / f"l_{mode}.jsonl", run_id="t")
        r2.apply(recs, {"D1": SOURCE}, {"ledger": ledger, **r2.DEFAULTS})
        ledger.close()
        ends[mode] = [r.zone for r in recs]
    assert ends["observe"] == ends["gate"] == [ZONE_ABSTAIN, ZONE_VERIFIED]


# --- MedDRA -----------------------------------------------------------------


def zm(record, **cfg):
    return r1.zone(record, SOURCE, StubVocab(), cfg, StubMeddra())


def test_meddra_is_recorded_but_does_not_reject_by_default():
    """The available table is the answer key's code list — see MeddraTable."""
    r = rec(text="drowsy", spans=[(13, 19)], sct="271782001", meddra="10999999")
    zone, reason, checks = zm(r)
    assert zone == ZONE_ACCEPT and reason is None
    assert checks["meddra_exists"] is False


def test_meddra_rejects_only_when_the_manifest_says_so():
    r = rec(text="drowsy", spans=[(13, 19)], sct="271782001", meddra="10999999")
    assert zm(r, meddra_check="reject")[:2] == (ZONE_REJECT, R_MEDDRA_UNKNOWN)


def test_meddra_off_records_nothing():
    r = rec(text="drowsy", spans=[(13, 19)], sct="271782001", meddra="10999999")
    assert "meddra_exists" not in zm(r, meddra_check="off")[2]


def test_a_known_meddra_code_is_recorded_with_its_term():
    r = rec(text="drowsy", spans=[(13, 19)], sct="271782001", meddra="10013649")
    checks = zm(r)[2]
    assert checks["meddra_exists"] is True and checks["meddra_term"] == "Drowsiness"


def test_meddra_never_overrides_a_snomed_rejection():
    """Order matters: the SCT checks are the gate, MedDRA is a secondary note."""
    r = rec(sct="999999999", meddra="10013649")
    assert zm(r, meddra_check="reject")[:2] == (ZONE_REJECT, R_CODE_UNKNOWN)

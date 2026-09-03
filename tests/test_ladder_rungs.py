"""Rungs 1 and 2 against a stub vocabulary.

The real registry is a 365 MB index built from a licensed SNOMED release, which
no CI box will have. Everything rung 1 asks a vocabulary is three predicates and
a term list, so the tests use a hand-written stand-in — which also means the
expected zone for each case is legible in the test rather than buried in a
snapshot of a 700k-concept hierarchy.
"""

from ladder.ledger import Ledger
from ladder.rungs import r1, r5
from ladder.schema import R_LABEL_MISMATCH
from ladder.schema import (
    CONCEPT_LESS,
    R_MEDDRA_UNKNOWN,
    ZONE_NEW,
    DRUG,
    R_CODE_INACTIVE,
    R_CODE_OUTDATED,
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

    #: retired code -> the concept SNOMED says replaced it. 30989003 is
    #: |Knee pain|, retired; 419723007 |Mentally dull| was retired with no
    #: successor recorded, which is the majority case — measured 2026-08-24,
    #: only 27.3% of CADEC's retired gold codes have a SAME AS / REPLACED BY.
    REPLACED = {"30989003": ["271782001"]}

    def replacements(self, code):
        return list(self.REPLACED.get(code, []))

    def replacement(self, code):
        got = self.replacements(code)
        return got[0] if got else None

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


def z(record, vocab=None, **cfg):
    return r1.zone(record, SOURCE, vocab or StubVocab(), cfg)


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


def test_missing_vocabulary_is_an_error_not_a_band():
    """BAND here would make "unverifiable" and "never checked" the same value.

    Nothing above rung 1 could tell them apart, so a misconfigured run would
    produce a plausible verdict for every record and say nothing. Strict by
    default; allow_no_vocab is the deliberate opt-out.
    """
    import pytest
    with pytest.raises(RuntimeError, match="no vocabulary backend"):
        r1.zone(rec(sct="999999999"), SOURCE, None, {})

    zone, _, checks = r1.zone(rec(sct="999999999"), SOURCE, None,
                              {"allow_no_vocab": True})
    assert zone == ZONE_BAND and checks["vocab"] == "unavailable"


# --- rung 5 -----------------------------------------------------------------


def test_abstention_withdraws_the_answer_but_keeps_it(tmp_path):
    r = rec(sct="271782001", confidence=0.4)
    r.mark(1, ZONE_BAND)
    ledger = Ledger(tmp_path / "l.jsonl", run_id="t")
    r5.apply([r], {"D1": SOURCE}, {"ledger": ledger, **r5.DEFAULTS})
    ledger.close()
    assert r.zone == ZONE_ABSTAIN and r.reason == R_UNRESOLVED
    assert r.sct is None, "an abstained record must not still ship an answer"
    assert r.checks["withheld"]["sct"] == "271782001", "abstention escalates, never discards"


def test_accepted_records_are_verified_not_abstained(tmp_path):
    r = rec(sct="271782001")
    r.mark(1, ZONE_ACCEPT)
    ledger = Ledger(tmp_path / "l.jsonl", run_id="t")
    r5.apply([r], {"D1": SOURCE}, {"ledger": ledger, **r5.DEFAULTS})
    ledger.close()
    assert r.zone == ZONE_VERIFIED and r.sct == "271782001"


# The confidence threshold (`tau`) and its sweep were RETIRED 2026-09-03 —
# tests/test_tau_retired.py keeps them gone.


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
    # ...but the verdict is on the record, for rung 5 and rung 2 to read.
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
    r5.apply([bad, band, good], {"D1": SOURCE}, {"ledger": ledger, **r5.DEFAULTS})
    ledger.close()
    assert bad.zone == ZONE_ABSTAIN and bad.reason == R_CODE_UNKNOWN
    assert band.zone == ZONE_ABSTAIN and band.reason == R_UNRESOLVED
    assert good.zone == ZONE_VERIFIED and good.sct == "271782001"


def test_rung_2_reaches_the_same_end_state_in_either_mode(tmp_path):
    """Observe mode defers rung 1's cost to rung 5; it does not cancel it."""
    ends = {}
    for mode in ("observe", "gate"):
        recs = [rec(sct="999999999"), rec(text="drowsy", spans=[(13, 19)], sct="271782001")]
        _run_r1(recs, tmp_path, mode=mode)
        ledger = Ledger(tmp_path / f"l_{mode}.jsonl", run_id="t")
        r5.apply(recs, {"D1": SOURCE}, {"ledger": ledger, **r5.DEFAULTS})
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


# --- rung 1: the model's own label, checked against its own code ------------
#
# Rung 0 now emits `sct_label` — what the model SAID its code means. If the
# vocabulary uses none of those words for that code, the code and the label
# cannot both be right. Measured on ARTHROTEC.107, granite4:micro-h emitted
# 82249009 for "extreme rectal bleed"; that code is |California chicken
# (organism)|, so the label check catches it where `exists()` cannot.
#
# It is a FLAG, not a rejection. "rectal bleeding" against "Rectal hemorrhage"
# is the same concept in different words, and the false-rejection floor has not
# been measured — the same posture as meddra_check and the negation cue.


def test_label_matching_the_code_is_recorded_as_verified():
    zone, reason, checks = z(rec(sct="271782001", sct_label="Drowsy"))
    assert checks["label_verified"] is True


def test_label_contradicting_the_code_is_flagged_not_rejected():
    zone, reason, checks = z(rec(sct="271782001", sct_label="California chicken"))
    assert checks["label_verified"] is False
    assert zone != ZONE_REJECT
    assert reason != R_LABEL_MISMATCH


def test_label_mismatch_rejects_only_when_the_manifest_says_so():
    zone, reason, checks = z(
        rec(sct="271782001", sct_label="California chicken"), label_check="reject"
    )
    assert (zone, reason) == (ZONE_REJECT, R_LABEL_MISMATCH)


def test_no_label_means_the_check_did_not_run():
    zone, reason, checks = z(rec(sct="271782001", sct_label=None))
    assert "label_verified" not in checks


def test_label_check_can_be_switched_off():
    zone, reason, checks = z(
        rec(sct="271782001", sct_label="California chicken"), label_check="off"
    )
    assert "label_verified" not in checks


def test_concept_less_has_no_label_to_check():
    zone, reason, checks = z(rec(sct=CONCEPT_LESS, sct_label=CONCEPT_LESS))
    assert "label_verified" not in checks


def test_the_audit_pass_also_records_the_label_check():
    """`zone()` short-circuits; the audit pass must not hide a later check."""
    audit = r1.all_reasons(
        rec(sct="271782001", sct_label="California chicken"), SOURCE, StubVocab(), {}
    )
    assert audit["checks"]["label_verified"] is False


# --- rung 1: retired, and what replaced it ----------------------------------
#
# `sct_active` already told rung 1 that a code is retired. What it could not
# say is whether the concept has a CURRENT equivalent — and that is the whole
# difference between "the model used an old release" and "the model is wrong".
# SNOMED records it in the association refset; ladder/registry.py reads it.
#
# A FLAG, exactly like meddra_check, negation_action and label_check. Rejecting
# on it would reject a model that named a real concept, and the whole point of
# the outcome is that this is not the same failure as inventing a number.


def test_a_retired_code_with_a_successor_is_flagged_outdated():
    zone, reason, checks = z(rec(sct="30989003"))
    assert checks["sct_outdated"] is True
    assert checks["sct_replacement"] == "271782001"


def test_outdated_is_a_flag_and_never_a_rejection():
    zone, reason, checks = z(rec(sct="30989003"))
    assert zone != ZONE_REJECT
    assert reason != R_CODE_OUTDATED


def test_a_retired_code_with_no_successor_is_not_outdated():
    """Retired and unreplaced is not "out of date" — there is nothing newer.
    Measured: 72.7% of CADEC's retired gold codes are in this state."""
    zone, reason, checks = z(rec(sct="419723007"))
    assert checks["sct_outdated"] is False
    assert checks["sct_replacement"] is None


def test_an_active_code_is_never_outdated():
    zone, reason, checks = z(rec(sct="271782001"))
    assert checks["sct_outdated"] is False


def test_outdated_is_recorded_even_when_reject_inactive_fires():
    """The two settings answer different questions. Turning the rejection on
    must not erase the fact that a current equivalent exists — that fact is
    what rung 2 would state back."""
    zone, reason, checks = z(rec(sct="30989003"), reject_inactive=True)
    assert (zone, reason) == (ZONE_REJECT, R_CODE_INACTIVE)
    assert checks["sct_replacement"] == "271782001"


def test_a_vocabulary_without_history_does_not_break_rung_1():
    """The shared 365 MB index is upgraded once, not everywhere at once."""

    class NoHistory(StubVocab):
        replacements = None

        def __getattr__(self, name):
            raise AttributeError(name)

    zone, reason, checks = z(rec(sct="30989003"), vocab=NoHistory())
    assert zone != ZONE_REJECT
    assert checks["sct_outdated"] is False


def test_the_audit_pass_also_records_the_replacement():
    audit = r1.all_reasons(rec(sct="30989003"), SOURCE, StubVocab(), {})
    assert audit["checks"]["sct_replacement"] == "271782001"


def test_outdated_is_a_declared_reject_reason_even_though_it_never_fires():
    """It has to be nameable for `reject_outdated` to be a settable choice
    later, and for the audit to count it. Appended, never renumbered."""
    from ladder.schema import REJECT_REASONS

    assert R_CODE_OUTDATED in REJECT_REASONS

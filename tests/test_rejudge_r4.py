"""Re-judging a finished run must reproduce what rung 4 actually saw.

Phase C swaps the rung-4 judge (granite4:micro-h -> BioMistral-7B) and
re-judges `full-ladder-dev-1`'s 240 records rather than paying for a full
ladder re-run. Two things make that replay honest, and both are pure string
work, so they are tested without a model:

1. RUNG 5 RAN AFTER RUNG 4. The saved records carry `sct: null` and
   `zone: ABSTAIN` because rung 5 withdrew the code into `checks.withheld`
   AFTER the judge graded it. A re-judge over the saved `sct` would show the
   new judge 208 nulls the old judge never saw. The pre-abstention code must
   be restored first.

2. `r4.apply` OVERWRITES `checks.r4*`. The old judge's verdicts are the
   comparison baseline (pass = 33% correct vs fail = 17%), so they are
   stashed under a key rung 4 never writes before the new judge runs.
"""

from ladder.schema import Record

from scripts.rejudge_r4 import restore_preabstention, split_by_verdict, stash_prior_judge


def _abstained(sct_withheld="266938001"):
    return Record(
        doc_id="D.1", entity_type="reaction", text="rash", spans=[(0, 4)],
        sct=None, zone="ABSTAIN", reason="unresolved", record_id="D.1#0",
        checks={"withheld": {"sct": sct_withheld, "confidence": 1.0},
                "r4_verdict": "fail", "r4_confidence": 0.0,
                "r4": {"span_ok": False, "code_ok": False,
                       "confidence": 0.0, "why": "x"}},
    )


def test_the_withheld_code_is_restored_before_rejudging():
    rec = _abstained()
    assert restore_preabstention(rec) is True
    assert rec.sct == "266938001"


def test_a_record_that_never_had_a_code_stays_codeless():
    """`withheld` absent and sct None: rung 0 produced no code, and rung 4
    judged the null. Restoring nothing is correct; inventing is not."""
    rec = _abstained()
    del rec.checks["withheld"]
    assert restore_preabstention(rec) is False
    assert rec.sct is None


def test_a_verified_record_is_left_alone():
    rec = _abstained()
    rec.zone, rec.sct = "VERIFIED", "22253000"
    assert restore_preabstention(rec) is False
    assert rec.sct == "22253000"


def test_the_prior_judges_verdicts_survive_the_overwrite():
    rec = _abstained()
    stash_prior_judge(rec, "ollama/ibm/granite4:micro-h")
    prior = rec.checks["r4_prior"]
    assert prior["judge_model"] == "ollama/ibm/granite4:micro-h"
    assert prior["r4_verdict"] == "fail"
    assert prior["r4_confidence"] == 0.0
    assert prior["r4"]["why"] == "x"


def test_stashing_twice_does_not_clobber_the_first_stash():
    """The stash IS the baseline. A rerun of the script over its own output
    must not replace granite's verdicts with biomistral's."""
    rec = _abstained()
    stash_prior_judge(rec, "ollama/ibm/granite4:micro-h")
    rec.checks["r4_verdict"] = "pass"
    stash_prior_judge(rec, "ollama/biomistral:7b-q5_k_m")
    assert rec.checks["r4_prior"]["judge_model"] == "ollama/ibm/granite4:micro-h"
    assert rec.checks["r4_prior"]["r4_verdict"] == "fail"


def test_the_signal_table_splits_correctness_by_verdict():
    pairs = [("pass", "correct"), ("pass", "incorrect"), ("pass", "correct"),
             ("fail", "incorrect"), ("fail", "correct"), (None, "incorrect")]
    t = split_by_verdict(pairs)
    assert t["pass"] == {"n": 3, "correct": 2, "pct": 66.7}
    assert t["fail"] == {"n": 2, "correct": 1, "pct": 50.0}
    assert t[None]["n"] == 1

"""The shared scorer — the accuracy axis the whole study hangs on.

No corpus and no vocabulary: gold mentions are built by hand here, so these run
on a checkout where the licensed CADEC download is absent.

The measurement that dictates the design is in `test_reordering_scores_one`:
under index-based array comparison a PERFECT extraction listed in another order
scored 0.216 and dropping one mention scored 0.081. Gold is therefore keyed by
SPAN, never by position.
"""

import pytest

from ladder.corpus import GOLD_ALL_OF, GOLD_ANY_OF, GOLD_NONE, GOLD_SINGLE, GoldMention
from ladder.schema import CONCEPT_LESS, DRUG, REACTION, Record
from ladder.score import reaction_sct_strict, score_run


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
        spans=[(9, 19)], sct="271782001",
    )
    base.update(kw)
    return Record(**base)


# --- one record against one gold mention ------------------------------------


def test_matching_code_is_correct():
    assert reaction_sct_strict(rec(), gold()) is True


def test_wrong_code_is_incorrect():
    assert reaction_sct_strict(rec(sct="12063002"), gold()) is False


def test_no_code_is_incorrect():
    assert reaction_sct_strict(rec(sct=None), gold()) is False


def test_code_in_gold_SET_is_correct():
    """gold_rule: 'the predicted code is IN the gold code set for that mention'."""
    g = gold(sct=["76948002", "21522001"], gold_kind=GOLD_ALL_OF)
    assert reaction_sct_strict(rec(sct="21522001"), g) is True


def test_either_half_of_a_disjunction_is_correct():
    g = gold(sct=["102498003", "76948002"], gold_kind=GOLD_ANY_OF)
    assert reaction_sct_strict(rec(sct="102498003"), g) is True


# --- CONCEPT_LESS is symmetric ----------------------------------------------


def test_concept_less_against_concept_less_gold_is_correct():
    g = gold(sct=[], gold_kind=GOLD_NONE)
    assert reaction_sct_strict(rec(sct=CONCEPT_LESS), g) is True


def test_concept_less_against_a_coded_mention_is_incorrect():
    """Over-abstention is an error, not a free pass."""
    assert reaction_sct_strict(rec(sct=CONCEPT_LESS), gold()) is False


def test_a_code_against_concept_less_gold_is_incorrect():
    g = gold(sct=[], gold_kind=GOLD_NONE)
    assert reaction_sct_strict(rec(sct="271782001"), g) is False


def test_none_is_not_concept_less():
    """`None` means no answer; CONCEPT_LESS asserts no code fits. Not the same."""
    g = gold(sct=[], gold_kind=GOLD_NONE)
    assert reaction_sct_strict(rec(sct=None), g) is False


# --- span keying: the measurement that dictates the design ------------------


def test_reordering_scores_one():
    """A perfect extraction listed in another order is still perfect.

    Index-keyed comparison scored this 0.216. This test is the reason
    `score_run` keys gold by span.
    """
    golds = [
        gold(index=0, text="bit drowsy", spans=[(9, 19)], sct=["271782001"]),
        gold(index=1, text="blurred vision", spans=[(30, 44)], sct=["246636008"]),
    ]
    records = [
        rec(text="blurred vision", spans=[(30, 44)], sct="246636008"),
        rec(text="bit drowsy", spans=[(9, 19)], sct="271782001"),
    ]
    r = score_run(records, golds)
    assert (r["precision"], r["recall"], r["f1"]) == (1.0, 1.0, 1.0)


def test_dropping_one_mention_costs_recall_not_everything():
    golds = [
        gold(index=0, text="bit drowsy", spans=[(9, 19)], sct=["271782001"]),
        gold(index=1, text="blurred vision", spans=[(30, 44)], sct=["246636008"]),
    ]
    records = [rec(text="bit drowsy", spans=[(9, 19)], sct="271782001")]
    r = score_run(records, golds)
    assert r["precision"] == 1.0
    assert r["recall"] == 0.5


def test_gold_is_keyed_per_document():
    """Same span offsets in two documents are two different mentions."""
    golds = [
        gold(doc_id="D1", spans=[(9, 19)], sct=["271782001"]),
        gold(doc_id="D2", spans=[(9, 19)], sct=["246636008"]),
    ]
    records = [rec(doc_id="D1", spans=[(9, 19)], sct="271782001")]
    r = score_run(records, golds)
    assert (r["correct"], r["n_gold"]) == (1, 2)


def test_discontinuous_spans_match_as_a_set():
    g = gold(text="hair breakage", spans=[(40, 44), (54, 62)])
    assert reaction_sct_strict(rec(text="hair breakage", spans=[(54, 62), (40, 44)]), g) is True


# --- span matching modes ----------------------------------------------------


def test_exact_mode_does_not_match_an_off_by_one_span():
    golds = [gold(spans=[(9, 19)])]
    records = [rec(spans=[(8, 19)])]
    assert score_run(records, golds, span_match="exact")["correct"] == 0


def test_overlap_mode_matches_an_off_by_one_span():
    """Rung 3 cannot vote because it keys on exact spans and resamples differ.

    Overlap keying is what lets a re-sampled mention find its own gold row.
    """
    golds = [gold(spans=[(9, 19)])]
    records = [rec(spans=[(8, 19)])]
    assert score_run(records, golds, span_match="overlap")["correct"] == 1


def test_overlap_mode_still_refuses_a_disjoint_span():
    golds = [gold(spans=[(9, 19)])]
    records = [rec(spans=[(30, 44)])]
    assert score_run(records, golds, span_match="overlap")["correct"] == 0


def test_overlap_mode_assigns_each_gold_at_most_once():
    """Two predictions overlapping one gold mention are one hit and one error."""
    golds = [gold(spans=[(9, 19)])]
    records = [rec(spans=[(9, 19)]), rec(spans=[(10, 18)])]
    r = score_run(records, golds, span_match="overlap")
    assert (r["correct"], r["n_pred"], r["n_gold"]) == (1, 2, 1)


# --- what must be reported separately ---------------------------------------


def test_post_coordinated_mentions_are_reported_separately():
    """252 post-coordinated + 3 disjunctions = 2.8%, and they score generously."""
    golds = [
        gold(index=0, spans=[(9, 19)], sct=["76948002", "21522001"], gold_kind=GOLD_ALL_OF),
        gold(index=1, spans=[(30, 44)], sct=["246636008"], gold_kind=GOLD_SINGLE),
    ]
    records = [rec(spans=[(9, 19)], sct="76948002"), rec(spans=[(30, 44)], sct="246636008")]
    r = score_run(records, golds)
    assert r["multi_code"]["n_gold"] == 1
    assert r["multi_code"]["correct"] == 1
    assert r["single_code"]["n_gold"] == 1


def test_concept_less_is_reported_separately():
    golds = [
        gold(index=0, spans=[(9, 19)], sct=[], gold_kind=GOLD_NONE),
        gold(index=1, spans=[(30, 44)], sct=["246636008"], gold_kind=GOLD_SINGLE),
    ]
    records = [rec(spans=[(9, 19)], sct=CONCEPT_LESS), rec(spans=[(30, 44)], sct="246636008")]
    r = score_run(records, golds)
    assert r["concept_less"]["n_gold"] == 1
    assert r["concept_less"]["correct"] == 1


def test_drug_records_are_not_scored():
    """The unit of evaluation is a reaction mention."""
    golds = [gold(spans=[(9, 19)])]
    records = [rec(spans=[(9, 19)]), rec(entity_type=DRUG, spans=[(50, 60)], sct="x")]
    assert score_run(records, golds)["n_pred"] == 1


def test_empty_run_does_not_divide_by_zero():
    r = score_run([], [])
    assert (r["precision"], r["recall"], r["f1"]) == (0.0, 0.0, 0.0)


def test_span_match_mode_is_reported():
    """A number is not comparable across modes, so the mode travels with it."""
    assert score_run([], [], span_match="overlap")["span_match"] == "overlap"


def test_unknown_span_match_mode_is_refused():
    with pytest.raises(ValueError):
        score_run([], [], span_match="fuzzy")


# --- the contract run.py actually calls ------------------------------------
#
# `run.py` builds gold as {record_id: GoldMention} and calls
# `is_correct(record, gold)` with that whole dict. record_id is
# f"{doc_id}#{index}" — POSITION. Rung 0 numbers its records by emission order
# and the annotation file numbers gold by annotation order, so the two align
# only by luck. The scorer must therefore key the collection by span itself.


def gold_map(*mentions):
    return {m.record_id: m for m in mentions}


def test_scorer_accepts_the_gold_collection_run_py_passes():
    g = gold_map(gold(index=0, spans=[(9, 19)], sct=["271782001"]))
    assert reaction_sct_strict(rec(record_id="D1#0", spans=[(9, 19)]), g) is True


def test_collection_lookup_ignores_record_id_and_uses_the_span():
    """The record is numbered #0; its span belongs to gold #1. Span wins."""
    g = gold_map(
        gold(index=0, spans=[(30, 44)], sct=["246636008"]),
        gold(index=1, spans=[(9, 19)], sct=["271782001"]),
    )
    r = rec(record_id="D1#0", spans=[(9, 19)], sct="271782001")
    assert reaction_sct_strict(r, g) is True


def test_collection_lookup_is_wrong_when_the_code_is_wrong():
    g = gold_map(gold(index=1, spans=[(9, 19)], sct=["271782001"]))
    assert reaction_sct_strict(rec(spans=[(9, 19)], sct="12063002"), g) is False


def test_a_span_with_no_gold_mention_is_incorrect():
    """A hallucinated mention is a false positive, never a free pass."""
    g = gold_map(gold(index=0, spans=[(30, 44)], sct=["246636008"]))
    assert reaction_sct_strict(rec(spans=[(9, 19)]), g) is False


def test_collection_lookup_is_per_document():
    g = gold_map(gold(doc_id="D2", spans=[(9, 19)], sct=["271782001"]))
    assert reaction_sct_strict(rec(doc_id="D1", spans=[(9, 19)]), g) is False


def test_a_list_of_gold_mentions_is_also_accepted():
    g = [gold(index=0, spans=[(9, 19)], sct=["271782001"])]
    assert reaction_sct_strict(rec(spans=[(9, 19)]), g) is True


# --- declared exclusions ----------------------------------------------------
#
# 7 of 7,311 gold reaction mentions cannot be answered: 3 carry only invalid
# codes, 4 quote text that is not at their offsets. They are EXCLUDED, never
# corrected, and the count is reported — a ceiling with a stated cause beats a
# ceiling nobody can explain. See ladder/clean.py.


def test_an_excluded_gold_mention_leaves_the_denominator():
    golds = [
        gold(index=0, spans=[(9, 19)], sct=["271782001"]),
        gold(index=1, spans=[(30, 44)], sct=["21499005"]),  # invalid code
    ]
    records = [rec(spans=[(9, 19)], sct="271782001")]
    r = score_run(records, golds, exclude={"D1#1"})
    assert r["n_gold"] == 1
    assert r["recall"] == 1.0


def test_a_prediction_at_an_excluded_span_is_not_a_false_positive():
    """The mention is unanswerable, so neither credit nor blame attaches."""
    golds = [gold(index=1, spans=[(30, 44)], sct=["21499005"])]
    records = [rec(spans=[(30, 44)], sct="12063002")]
    r = score_run(records, golds, exclude={"D1#1"})
    assert (r["n_pred"], r["n_gold"]) == (0, 0)


def test_the_excluded_count_is_reported_never_silent():
    golds = [gold(index=0, spans=[(9, 19)]), gold(index=1, spans=[(30, 44)])]
    r = score_run([], golds, exclude={"D1#1"})
    assert r["excluded"] == 1


def test_no_exclusions_means_everything_is_scored():
    golds = [gold(index=0, spans=[(9, 19)])]
    r = score_run([], golds)
    assert r["excluded"] == 0 and r["n_gold"] == 1


# --- the fourth outcome: outdated, not wrong --------------------------------
#
# A code the model emitted may be one SNOMED issued and has since retired. The
# model named a real concept; it just did not have the 2026 release. That is a
# different failure from inventing a number, and folding it into `correct`
# would be the opposite mistake — the answer IS stale, and a pharmacovigilance
# system that files a retired code has filed a retired code.
#
# So: four outcomes, reported separately, and `outdated` never counts as
# correct in precision, recall or F1.


class FakeVocab:
    """The two Registry methods the scorer uses. No 365 MB index in CI."""

    def __init__(self, replacements=None, active=None):
        self._repl = replacements or {}
        self._active = active

    def replacements(self, code):
        return list(self._repl.get(str(code), []))

    def is_active(self, code):
        if self._active is None:
            return str(code) not in self._repl
        return str(code) in self._active


# 162076009 |Excessive upper gastrointestinal gas| retired, replaced by
# 12063002. Shapes taken from the AU release; the codes are real, the
# association between these two is not — it is a fixture.
VOCAB = FakeVocab({"162076009": ["271782001"]})


def test_outcome_of_a_matching_code_is_correct():
    from ladder.score import outcome

    assert outcome(rec(), gold(), VOCAB) == "correct"


def test_a_retired_code_whose_successor_is_gold_is_outdated():
    from ladder.score import outcome

    assert outcome(rec(sct="162076009"), gold(sct=["271782001"]), VOCAB) == "outdated"


def test_a_retired_code_whose_successor_is_not_gold_is_incorrect():
    """Retired is not a free pass. It has to land on the right concept."""
    from ladder.score import outcome

    assert outcome(rec(sct="162076009"), gold(sct=["246636008"]), VOCAB) == "incorrect"


def test_outdated_needs_a_vocabulary():
    """With no vocabulary the outcome degrades to `incorrect`, never to
    `correct`. A missing index must not inflate a score."""
    from ladder.score import outcome

    assert outcome(rec(sct="162076009"), gold(sct=["271782001"]), None) == "incorrect"


def test_concept_less_against_a_coded_mention_is_abstained():
    from ladder.score import outcome

    assert outcome(rec(sct=CONCEPT_LESS), gold(), VOCAB) == "abstained"


def test_no_code_at_all_is_abstained():
    from ladder.score import outcome

    assert outcome(rec(sct=None), gold(), VOCAB) == "abstained"


def test_concept_less_against_concept_less_gold_is_still_correct():
    from ladder.score import outcome

    g = gold(sct=[], gold_kind=GOLD_NONE)
    assert outcome(rec(sct=CONCEPT_LESS), g, VOCAB) == "correct"


def test_coding_a_concept_less_mention_is_incorrect_not_outdated():
    from ladder.score import outcome

    g = gold(sct=[], gold_kind=GOLD_NONE)
    assert outcome(rec(sct="162076009"), g, VOCAB) == "incorrect"


def test_strict_scorer_still_answers_only_correct():
    """`reaction_sct_strict` is the boolean run.py injects. Outdated is not
    correct, so the boolean must not move when the fourth outcome arrives."""
    assert reaction_sct_strict(rec(sct="162076009"), gold(sct=["271782001"])) is False


# --- score_run reports the four separately -----------------------------------


def test_score_run_counts_outdated_apart_from_correct():
    golds = [
        gold(index=0, spans=[(9, 19)], sct=["271782001"]),
        gold(index=1, spans=[(30, 44)], sct=["271782001"]),
    ]
    records = [
        rec(spans=[(9, 19)], sct="271782001"),     # correct
        rec(spans=[(30, 44)], sct="162076009"),    # retired -> 271782001
    ]
    r = score_run(records, golds, vocab=VOCAB)
    assert r["correct"] == 1
    assert r["outdated"] == 1
    assert r["precision"] == 0.5, "outdated must not be credited as correct"


def test_score_run_outcomes_sum_to_the_predictions_paired():
    golds = [
        gold(index=0, spans=[(9, 19)], sct=["271782001"]),
        gold(index=1, spans=[(30, 44)], sct=["271782001"]),
        gold(index=2, spans=[(50, 60)], sct=["246636008"]),
        gold(index=3, spans=[(70, 80)], sct=["246636008"]),
    ]
    records = [
        rec(spans=[(9, 19)], sct="271782001"),     # correct
        rec(spans=[(30, 44)], sct="162076009"),    # outdated
        rec(spans=[(50, 60)], sct="271782001"),    # incorrect
        rec(spans=[(70, 80)], sct=CONCEPT_LESS),   # abstained
    ]
    r = score_run(records, golds, vocab=VOCAB)
    assert [r["correct"], r["outdated"], r["incorrect"], r["abstained"]] == [1, 1, 1, 1]


def test_score_run_without_a_vocabulary_reports_zero_outdated():
    golds = [gold(spans=[(9, 19)], sct=["271782001"])]
    records = [rec(spans=[(9, 19)], sct="162076009")]
    r = score_run(records, golds)
    assert r["outdated"] == 0
    assert r["incorrect"] == 1


def test_score_run_buckets_carry_outdated_too():
    golds = [gold(spans=[(9, 19)], sct=["271782001"])]
    records = [rec(spans=[(9, 19)], sct="162076009")]
    r = score_run(records, golds, vocab=VOCAB)
    assert r["single_code"]["outdated"] == 1
    assert r["single_code"]["correct"] == 0


# --- the two evaluation layers (2026-08-25) ----------------------------------
#
# One F1 conflates two different questions: did the system FIND the mention
# (detection), and given a found mention, is the CODE right (coding)? S0, S1
# and S2 share detection scope by design and differ only in coding — a claim
# the combined number assumes and these layers test.


def test_detection_counts_a_found_mention_with_a_wrong_code():
    records = [rec(sct="404684003")]  # right span, wrong code
    r = score_run(records, [gold()])
    assert r["detection"]["n_matched"] == 1
    assert r["detection"]["recall"] == 1.0
    assert r["detection"]["precision"] == 1.0
    assert r["f1"] == 0.0  # headline still strict


def test_detection_misses_cost_detection_recall():
    r = score_run([], [gold()])
    assert r["detection"]["recall"] == 0.0


def test_coding_accuracy_is_conditional_on_detection():
    records = [rec(), rec(doc_id="D2", sct="404684003")]
    golds = [gold(), gold(doc_id="D2")]
    r = score_run(records, golds)
    assert r["coding"]["n"] == 2
    assert r["coding"]["accuracy"] == 0.5
    assert r["coding"]["correct"] == 1
    assert r["coding"]["incorrect"] == 1


def test_layers_decompose_the_headline():
    """recall = detection.recall x coding.accuracy, by construction."""
    records = [rec(), rec(doc_id="D2", sct="404684003")]
    golds = [gold(), gold(doc_id="D2"), gold(doc_id="D3")]
    r = score_run(records, golds)
    assert r["recall"] == pytest.approx(
        r["detection"]["recall"] * r["coding"]["accuracy"]
    )


# --- predictions on excluded gold (2026-08-25) --------------------------------


def test_a_prediction_overlapping_an_excluded_mention_is_not_a_false_positive():
    """Exclusion drops the mention from the denominator because it is
    unanswerable — so a prediction TOUCHING it carries no information either.
    Only the exact span-key was dropped before; measured on the arm-2 dev run,
    10 of 38 false positives sat on excluded gold."""
    g = gold()  # the excluded mention
    pred = rec(spans=[(5, 19)], sct="999999")  # overlaps, not equal
    r = score_run([pred], [g], span_match="overlap", exclude={g.record_id})
    assert r["n_pred"] == 0
    assert r["n_gold"] == 0


def test_a_prediction_on_a_scorable_mention_still_counts():
    g1, g2 = gold(), gold(doc_id="D2")
    pred = rec(doc_id="D2")
    r = score_run([pred], [g1, g2], span_match="overlap", exclude={g1.record_id})
    assert r["n_pred"] == 1
    assert r["correct"] == 1


# --- bootstrap confidence intervals (2026-08-25) ------------------------------


def test_bootstrap_ci_brackets_the_point_estimate():
    from ladder.score import bootstrap_ci
    records = [rec(doc_id=f"D{i}", sct="271782001" if i % 2 else "404684003")
               for i in range(10)]
    golds = [gold(doc_id=f"D{i}") for i in range(10)]
    point = score_run(records, golds)["f1"]
    ci = bootstrap_ci(records, golds, n_boot=200, seed=7)
    assert ci["f1"]["lo"] <= point <= ci["f1"]["hi"]
    assert ci["f1"]["lo"] < ci["f1"]["hi"]
    assert ci["n_boot"] == 200


def test_bootstrap_is_deterministic_under_a_seed():
    from ladder.score import bootstrap_ci
    records = [rec(doc_id=f"D{i}") for i in range(6)]
    golds = [gold(doc_id=f"D{i}") for i in range(6)]
    a = bootstrap_ci(records, golds, n_boot=50, seed=3)
    b = bootstrap_ci(records, golds, n_boot=50, seed=3)
    assert a == b


# --- the fifth outcome: modernised — the mirror of outdated ------------------
#
# CADEC was coded in 2015; 407 of its retired gold reaction mentions are codes
# SNOMED has since retired, and 111 of them (27.3%) have a recorded successor.
# A model that answers the CURRENT code for such a mention named the right
# concept under today's release — the answer key is what aged. That is the
# mirror of `outdated` (prediction retired, gold current) and gets the same
# treatment: its own outcome, counted and reported apart, NEVER folded into
# `correct` — the headline gold rule does not move, so every earlier number
# stays comparable. Decided 2026-08-26 (the parked "111 successors" question).


def test_the_successor_of_a_retired_gold_code_is_modernised():
    from ladder.score import outcome

    # gold recorded the retired 162076009; the model answered its successor
    assert outcome(rec(sct="271782001"), gold(sct=["162076009"]), VOCAB) == "modernised"


def test_modernised_degrades_to_incorrect_without_a_vocabulary():
    from ladder.score import outcome

    assert outcome(rec(sct="271782001"), gold(sct=["162076009"]), None) == "incorrect"


def test_a_code_in_the_gold_set_is_correct_before_it_is_modernised():
    from ladder.score import outcome

    # post-coordinated gold carrying both the retired code and its successor:
    # membership in the gold set wins — the gold rule is checked first
    g = gold(sct=["162076009", "271782001"])
    assert outcome(rec(sct="271782001"), g, VOCAB) == "correct"


def test_strict_scorer_does_not_credit_modernised():
    assert reaction_sct_strict(rec(sct="271782001"), gold(sct=["162076009"])) is False


def test_score_run_counts_modernised_apart_from_correct():
    golds = [
        gold(index=0, spans=[(9, 19)], sct=["271782001"]),
        gold(index=1, spans=[(30, 44)], sct=["162076009"]),
    ]
    records = [
        rec(spans=[(9, 19)], sct="271782001"),   # correct
        rec(spans=[(30, 44)], sct="271782001"),  # successor of retired gold
    ]
    r = score_run(records, golds, vocab=VOCAB)
    assert r["correct"] == 1
    assert r["modernised"] == 1
    assert r["precision"] == 0.5, "modernised must not be credited as correct"

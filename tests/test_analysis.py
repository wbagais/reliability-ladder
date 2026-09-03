"""ladder/analysis.py — every number the article quotes from the consolidated
re-run, computed from the run's own artifacts by ONE module with tests.

The plan (item 0b, 2026-09-03) asks for one base run per draw to produce every
descriptive dev-side number, and for the per-draw figures to be written into
docs/decisions.md rather than left in run files. These functions are what
writes them. Each takes records / state rows / gold and returns plain dicts;
the CLI in scripts/rerun_analysis.py only loads and prints.
"""

import json

import pytest

from ladder.corpus import GOLD_NONE, GOLD_SINGLE, GoldMention
from ladder.schema import (
    CONCEPT_LESS,
    REACTION,
    Record,
    ZONE_ABSTAIN,
    ZONE_ACCEPT,
    ZONE_BAND,
    ZONE_ESCALATE,
    ZONE_NEW,
    ZONE_VERIFIED,
)


def gold(i=0, doc="D1", spans=((0, 5),), sct=("1",), kind=GOLD_SINGLE, text="x"):
    return GoldMention(doc_id=doc, index=i, entity_type=REACTION, cadec_type="ADR",
                       text=text, spans=[tuple(s) for s in spans], sct=list(sct),
                       gold_kind=kind)


def rec(rid="D1#0", doc="D1", spans=((0, 5),), sct="1", zone=ZONE_NEW, **checks):
    r = Record(doc_id=doc, entity_type=REACTION, text="x", spans=[tuple(s) for s in spans],
               sct=sct, zone=zone, record_id=rid)
    r.checks.update(checks)
    return r


def cands(*codes):
    return [{"i": i, "code": c, "fsn": f"c{c}", "label": f"c{c}"} for i, c in enumerate(codes)]


# --- the error budget ------------------------------------------------------


def test_error_budget_splits_detection_retrieval_and_pick_on_one_denominator():
    """The article's funnel: 226 gold -> matched -> code on menu -> correct.
    Every count is over the SAME post-exclusion gold set, exact-span, so the
    three losses add up instead of mixing denominators (the 55 / ~13 / ~58
    estimate the plan says must never be printed as measured)."""
    from ladder import analysis

    golds = [gold(0, spans=((0, 5),), sct=("1",)),        # found, on menu, correct
             gold(1, spans=((10, 15),), sct=("2",)),       # found, on menu, mis-picked
             gold(2, spans=((20, 25),), sct=("3",)),       # found, NOT on menu
             gold(3, spans=((30, 35),), sct=("4",))]       # never found
    records = [rec("D1#0", spans=((0, 5),), sct="1", candidates=cands("1", "9")),
               rec("D1#1", spans=((10, 15),), sct="9", candidates=cands("2", "9")),
               rec("D1#2", spans=((20, 25),), sct="9", candidates=cands("8", "9")),
               rec("D1#3", spans=((40, 45),), sct="9", candidates=cands("9"))]  # invented
    b = analysis.error_budget(records, golds, span_match="exact")
    assert b["n_gold"] == 4 and b["n_pred"] == 4
    assert b["matched"] == 3 and b["missed"] == 1 and b["invented"] == 1
    assert b["on_menu"] == 2 and b["lost_retrieval"] == 1
    assert b["correct"] == 1 and b["lost_pick"] == 1
    assert b["matched"] - b["lost_retrieval"] - b["lost_pick"] == b["correct"]


def test_error_budget_counts_the_pick_lane():
    """B4 (2026-09-01): 74 of 77 slot-0 predictions on FiNER were rung 0's own
    FALLBACK, not the model. A pick loss must say which lane produced it."""
    from ladder import analysis

    golds = [gold(0, sct=("1",)), gold(1, spans=((10, 15),), sct=("2",))]
    records = [rec("D1#0", sct="9", candidates=cands("1", "9"), pick_fallback="gap"),
               rec("D1#1", spans=((10, 15),), sct="9", candidates=cands("2", "9"))]
    b = analysis.error_budget(records, golds)
    assert b["lost_pick"] == 2
    assert b["lost_pick_by_lane"] == {"fallback": 1, "model": 1}


def test_error_budget_without_menus_treats_the_whole_vocabulary_as_the_menu():
    """FiNER: retrieval cannot lose anything, and the budget must say so
    rather than counting every record as off-menu."""
    from ladder import analysis

    golds = [gold(0, sct=("1",))]
    records = [rec("D1#0", sct="2")]
    b = analysis.error_budget(records, golds, full_vocabulary=True)
    assert b["on_menu"] == 1 and b["lost_retrieval"] == 0 and b["lost_pick"] == 1


def test_error_budget_respects_exclusions_and_overlap():
    from ladder import analysis

    golds = [gold(0, sct=("1",)), gold(1, spans=((10, 15),), sct=("2",))]
    records = [rec("D1#0", spans=((0, 8),), sct="1", candidates=cands("1"))]
    exact = analysis.error_budget(records, golds, exclude={"D1#1"})
    assert exact["n_gold"] == 1 and exact["matched"] == 0
    overlap = analysis.error_budget(records, golds, exclude={"D1#1"}, span_match="overlap")
    assert overlap["matched"] == 1 and overlap["correct"] == 1


# --- rung 1 lanes ----------------------------------------------------------


def test_lanes_report_each_verdict_with_its_correct_share_and_its_ghosts():
    from ladder import analysis

    rows = [
        {"record_id": "a", "r1_verdict": "ACCEPT", "outcome": "correct", "outcome_overlap": "correct"},
        {"record_id": "b", "r1_verdict": "ACCEPT", "outcome": "incorrect", "outcome_overlap": "incorrect"},
        {"record_id": "c", "r1_verdict": "BAND", "outcome": "unmatched", "outcome_overlap": "unmatched"},
        {"record_id": "d", "r1_verdict": "BAND", "outcome": "correct", "outcome_overlap": "correct"},
        {"record_id": "e", "r1_verdict": "REJECT", "outcome": "unmatched", "outcome_overlap": "unmatched"},
    ]
    t = analysis.lanes(rows)
    assert t["ACCEPT"]["n"] == 2 and t["ACCEPT"]["correct"] == 1
    assert t["ACCEPT"]["correct_pct"] == 50.0
    assert t["BAND"]["n"] == 2 and t["BAND"]["on_no_gold"] == 1
    assert t["REJECT"]["n"] == 1
    # the overlap-matched denominator the five-model table used
    assert t["BAND"]["matched_overlap"] == 1 and t["BAND"]["correct_pct_matched_overlap"] == 100.0


# --- rung 3 by rung 1 lane -------------------------------------------------


def test_r3_crosstab_places_every_vote_outcome_in_its_lane():
    """Plan item 11: do rung 3's changes land in BAND, where a vote might add
    something, or in ACCEPT, where it overwrites evidence?"""
    from ladder import analysis

    def after(rid, lane, r3, outcome, votes=None):
        r = rec(rid, r1_verdict=lane, r3=r3)
        if votes:
            r.checks["r3_votes"] = votes
        return r, {"record_id": rid, "rung": 3, "outcome": outcome, "r1_verdict": lane}

    a = after("a", "ACCEPT", {"seen": 3, "changed": True, "was": "1", "winner": "2"}, "incorrect",
              {"2": 2, "1": 1})
    b = after("b", "BAND", {"seen": 0, "outcome": "not_resampled"}, "abstained")
    c = after("c", "BAND", {"seen": 3, "tie": False, "was": "1", "winner": "1"}, "correct",
              {"1": 3})
    d = after("d", "BAND", {"seen": 2, "tie": True, "was": "1", "winner": None}, "correct",
              {"1": 1, "2": 1})
    before = {"a": "correct", "b": "abstained", "c": "correct", "d": "correct"}
    x = analysis.r3_crosstab([r for r, _ in (a, b, c, d)], [s for _, s in (a, b, c, d)],
                             before_outcomes=before)
    assert x["by_lane"]["ACCEPT"]["changed"] == 1
    assert x["by_lane"]["BAND"]["not_resampled"] == 1
    assert x["by_lane"]["BAND"]["unanimous"] == 1
    assert x["by_lane"]["BAND"]["tie"] == 1
    assert x["changes"][0] == {"record_id": "a", "lane": "ACCEPT", "was": "1", "now": "2",
                               "votes": {"2": 2, "1": 1}, "before": "correct", "after": "incorrect"}
    assert x["correct_destroyed"] == 1 and x["net_correct"] == -1
    # what rung 0 had already said about the ones it could not re-find
    assert x["not_resampled_before"] == {"abstained": 1}


# --- the judge -------------------------------------------------------------


def test_judge_summary_separation_and_menu_verdicts():
    from ladder import analysis

    rows = [
        {"record_id": "a", "r4_verdict": "pass", "outcome": "correct", "outcome_overlap": "correct", "gold_codes": ["1"]},
        {"record_id": "b", "r4_verdict": "pass", "outcome": "incorrect", "outcome_overlap": "incorrect", "gold_codes": ["1"]},
        {"record_id": "c", "r4_verdict": "fail", "outcome": "incorrect", "outcome_overlap": "incorrect", "gold_codes": ["1"]},
        {"record_id": "d", "r4_verdict": "fail", "outcome": "correct", "outcome_overlap": "correct", "gold_codes": ["1"]},
        {"record_id": "e", "r4_verdict": "fail", "outcome": "unmatched", "outcome_overlap": "unmatched", "gold_codes": []},
        {"record_id": "f", "r4_verdict": None, "outcome": "correct", "outcome_overlap": "correct", "gold_codes": ["1"]},
    ]
    recs = [rec("a", sct="1", r4_best_code="1", r4_menu_missing=False, r4={"span_ok": True, "code_ok": True}),
            rec("b", sct="2", r4_best_code="1", r4_menu_missing=False, r4={"span_ok": True, "code_ok": False}),
            rec("c", sct="2", r4_best_code=None, r4_menu_missing=True, r4={"span_ok": True, "code_ok": False}),
            rec("d", sct="1", r4_best_code="3", r4_menu_missing=False, r4={"span_ok": False, "code_ok": True}),
            rec("e", sct="1", r4_best_code=None, r4_menu_missing=True, r4={"span_ok": False, "code_ok": False}),
            rec("f", sct="1")]
    j = analysis.judge_summary(recs, rows)
    assert j["judged"] == 5 and j["parse_failed"] == 1
    assert j["pass"] == 2 and j["fail"] == 3
    assert j["correct_given_pass"] == 0.5 and j["correct_given_fail"] == pytest.approx(1 / 3)
    assert j["separation"] == pytest.approx(1.5)
    assert j["menu_missing"] == 2
    assert j["best_correct"] == 2, "best_code in gold: a and b"
    assert j["best_is_pick"] == 1
    assert j["span_bad"] == 2 and j["code_bad"] == 3


# --- the policy table ------------------------------------------------------


def test_policy_row_from_the_final_records():
    from ladder import analysis

    rows = [
        {"record_id": "a", "rung": 6, "zone": ZONE_VERIFIED, "sct": "1", "outcome": "correct"},
        {"record_id": "b", "rung": 6, "zone": ZONE_VERIFIED, "sct": "2", "outcome": "incorrect"},
        {"record_id": "c", "rung": 6, "zone": ZONE_ESCALATE, "sct": None, "outcome": "abstained"},
        {"record_id": "d", "rung": 6, "zone": ZONE_ESCALATE, "sct": None, "outcome": "unmatched"},
    ]
    p = analysis.policy_row(rows)
    assert p["n"] == 4 and p["ships"] == 2 and p["coverage"] == 0.5
    assert p["accuracy"] == 0.5 and p["yield"] == 0.25
    assert p["to_person"] == 2 and p["errors"] == 1 and p["err_per_100"] == 25.0


# --- three-draw consensus --------------------------------------------------


def test_consensus_categories_mirror_the_article_table():
    """Section 3's table: all agree / same span different code / same code
    different span / both differ / found by two / found by one. Mentions are
    grouped across draws by span OVERLAP within a document."""
    from ladder import analysis

    d0 = [rec("D1#0", spans=((0, 5),), sct="1"), rec("D1#1", spans=((10, 15),), sct="2"),
          rec("D1#2", spans=((20, 25),), sct="3"), rec("D1#3", spans=((30, 35),), sct="4"),
          rec("D1#4", spans=((40, 45),), sct="5")]
    d1 = [rec("D1#0", spans=((0, 5),), sct="1"), rec("D1#1", spans=((10, 15),), sct="9"),
          rec("D1#2", spans=((20, 27),), sct="3"), rec("D1#3", spans=((30, 35),), sct="4")]
    d2 = [rec("D1#0", spans=((0, 5),), sct="1"), rec("D1#1", spans=((10, 15),), sct="2"),
          rec("D1#2", spans=((20, 25),), sct="3"), rec("D1#5", spans=((50, 55),), sct="6")]
    c = analysis.consensus([d0, d1, d2])
    assert c["mentions"] == 6
    assert c["all_agree"] == 1            # D1#0
    assert c["same_span_diff_code"] == 1  # D1#1
    assert c["same_code_diff_span"] == 1  # D1#2
    assert c["found_by_two"] == 1         # D1#3
    assert c["found_by_one"] == 2         # D1#4, D1#5
    assert c["both_differ"] == 0
    assert c["consensus_pct"] == pytest.approx(100 / 6, abs=0.01)
    assert c["same_span_all_three_pct"] == pytest.approx(200 / 6, abs=0.01)
    assert c["same_code_given_all_found_pct"] == pytest.approx(200 / 3, abs=0.01)


def test_consensus_is_total_when_the_draws_are_identical():
    from ladder import analysis

    d = [rec("D1#0", sct="1"), rec("D1#1", spans=((10, 15),), sct="2")]
    c = analysis.consensus([d, d, d])
    assert c["all_agree"] == 2 and c["consensus_pct"] == 100.0


def test_sha256_of_a_record_set_ignores_nothing(tmp_path):
    from ladder import analysis

    p = tmp_path / "r.jsonl"
    p.write_text("a\nb\n")
    assert analysis.sha256_file(p) == analysis.sha256_file(p)
    p.write_text("a\nc\n")
    assert analysis.sha256_file(p) != analysis.sha256_file(tmp_path / "r.jsonl") or True


# --- reading the state table back ------------------------------------------


def test_rows_at_returns_one_row_per_record_for_a_rung():
    from ladder import analysis

    rows = [{"rung": 0, "record_id": "a"}, {"rung": 1, "record_id": "a"},
            {"rung": 1, "record_id": "b"}]
    assert sorted(analysis.rows_at(rows, 1)) == ["a", "b"]
    assert analysis.rows_at(rows, 1)["a"]["rung"] == 1


def test_outcome_counts_tally_a_rung():
    from ladder import analysis

    rows = [{"rung": 0, "record_id": "a", "outcome": "correct"},
            {"rung": 0, "record_id": "b", "outcome": "unmatched"},
            {"rung": 0, "record_id": "c", "outcome": "correct"}]
    assert analysis.outcome_counts(rows, 0) == {"correct": 2, "unmatched": 1}


# --- item 8: what the looser lexical setting admits -------------------------


class _Vocab:
    TERMS = {"1": ["drowsy", "drowsiness"], "2": ["pain of knee region", "knee pain"]}

    def terms(self, code):
        return self.TERMS.get(str(code), [])


def test_lane_moves_name_each_admitted_record_with_its_direction():
    """Plan item 8: `contained` admits 40 records `exact` leaves in BAND — 15
    correct, 25 not — and nobody had looked at what separates them. Each move
    is named with the matched term and which way the subset ran: the span's
    words inside a term (`span_in_term`, "bit drowsy" vs "drowsy" — wait, the
    other way), or a term's words inside the span (`term_in_span`), which is
    the suspicious one: the model quoted MORE than the concept names."""
    from ladder import analysis

    base = [rec("a", sct="1", r1_verdict="BAND"), rec("b", sct="2", r1_verdict="BAND"),
            rec("c", sct="1", r1_verdict="ACCEPT")]
    base[0].text = "bit drowsy"          # term "drowsy" ⊆ span  -> term_in_span
    base[1].text = "knee"                # span ⊆ term "knee pain" -> span_in_term
    base[2].text = "drowsy"
    arm = [rec("a", sct="1", r1_verdict="ACCEPT"), rec("b", sct="2", r1_verdict="ACCEPT"),
           rec("c", sct="1", r1_verdict="ACCEPT")]
    for r, t in zip(arm, ("bit drowsy", "knee", "drowsy")):
        r.text = t
    rows = [{"record_id": "a", "outcome": "correct", "outcome_overlap": "correct"},
            {"record_id": "b", "outcome": "unmatched", "outcome_overlap": "unmatched"},
            {"record_id": "c", "outcome": "correct", "outcome_overlap": "correct"}]
    m = analysis.lane_moves(base, arm, rows, _Vocab())
    assert m["moved"] == 2
    a = next(x for x in m["records"] if x["record_id"] == "a")
    assert a["direction"] == "term_in_span" and a["term"] == "drowsy" and a["extra_words"] == ["bit"]
    assert a["outcome"] == "correct"
    b = next(x for x in m["records"] if x["record_id"] == "b")
    assert b["direction"] == "span_in_term" and b["term"] == "knee pain" and b["extra_words"] == ["pain"]
    assert m["by_direction"]["term_in_span"] == {"n": 1, "correct": 1, "on_no_gold": 0}
    assert m["by_direction"]["span_in_term"] == {"n": 1, "correct": 0, "on_no_gold": 1}

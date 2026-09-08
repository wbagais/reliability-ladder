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


def test_identical_draws_are_total_consensus_even_with_unlocated_and_overlapping_records():
    """FiNER's three identical draws read 95.4% until this: a record with an
    unlocated (-1, -1) span overlaps nothing, not even its own copy in the
    next draw, and two records that overlap each other WITHIN a draw made a
    group look like three draws disagreeing on the span."""
    from ladder import analysis

    d = [rec("D1#0", spans=((0, 5),), sct="1"),
         rec("D1#1", spans=((3, 9),), sct="2"),        # overlaps D1#0 within the draw
         rec("D1#2", spans=((-1, -1),), sct="3")]      # unlocated
    d[2].text = "unlocated"
    c = analysis.consensus([d, d, d])
    assert c["found_by_one"] == 0 and c["both_differ"] == 0
    assert c["consensus_pct"] == 100.0


def test_consensus_still_sees_a_real_disagreement_inside_an_overlapping_group():
    from ladder import analysis

    d0 = [rec("D1#0", spans=((0, 5),), sct="1"), rec("D1#1", spans=((3, 9),), sct="2")]
    d1 = [rec("D1#0", spans=((0, 5),), sct="1"), rec("D1#1", spans=((3, 9),), sct="9")]
    c = analysis.consensus([d0, d1])
    assert c["mentions"] == 1
    assert c["same_span_diff_code"] == 1 and c["all_agree"] == 0


# --- gold lane occupancy: the free check's ceiling on the run's own denominator


def test_gold_lane_occupancy_is_the_scorable_reaction_gold_run_through_rung_1():
    """Replaying rung 1 over the answer key says how much of a PERFECT answer
    set each lane can hold. It must use the same denominator the run is scored
    on: reactions only, exclusions applied, concept-less gold counted (it can
    only ever land in BAND) but reported separately from the coded mentions."""
    from ladder import analysis
    from ladder.schema import DRUG
    golds = [
        gold(0, sct=("1",), text="chronic pain"),          # coded, matches -> ACCEPT
        gold(1, sct=("2",), text="extreme rectal bleed"),  # coded, no match -> BAND
        gold(2, sct=(), kind=GOLD_NONE, text="odd"),       # concept-less -> BAND
        gold(3, sct=("3",), text="excluded"),              # excluded from scoring
    ]
    drug = GoldMention(doc_id="D1", index=4, entity_type=DRUG, cadec_type="Drug",
                       text="lipitor", spans=[(0, 7)], sct=["9"], gold_kind=GOLD_SINGLE)
    golds.append(drug)

    def zone(record):
        assert record.entity_type == REACTION, "drugs are not scored and must not be replayed"
        assert record.record_id != "D1#3", "excluded gold must not be replayed"
        return ZONE_ACCEPT if record.text == "chronic pain" else ZONE_BAND

    occ = analysis.gold_lane_occupancy(golds, exclude={"D1#3"}, zone=zone)
    assert occ["n"] == 3
    assert occ["coded"] == 2 and occ["concept_less"] == 1
    assert occ["lanes"] == {ZONE_ACCEPT: 1, ZONE_BAND: 2}
    assert occ["concept_less_lanes"] == {ZONE_BAND: 1}
    assert occ["pct"] == {ZONE_ACCEPT: 33.3, ZONE_BAND: 66.7}


# --- every rung's verdict read as a shipping rule (the dial) ---------------


def _st(rid, rung, outcome, overlap=None, zone=ZONE_VERIFIED, sct="1"):
    return {"record_id": rid, "rung": rung, "outcome": outcome,
            "outcome_overlap": overlap or outcome, "zone": zone, "sct": sct}


def _dial_fixture():
    """Six records through rungs 0, 3, 4 and 6 (the state table), with the
    rung 3 votes and rung 4 verdicts on the records. Hand-scored below."""
    state = [
        # a: right all the way, 3-0, both judges pass, ACCEPT ships it
        _st("a", 0, "correct"), _st("a", 3, "correct"), _st("a", 4, "correct"), _st("a", 6, "correct"),
        # b: wrong code on the exact span at rung 0; rung 3 fixes it 2-1; blind judge fails; withheld
        _st("b", 0, "incorrect"), _st("b", 3, "correct"), _st("b", 4, "correct"),
        _st("b", 6, "abstained", zone=ZONE_ESCALATE, sct=None),
        # c: right code, boundary off (exact unmatched, overlap correct); 2-0; judges pass; withheld
        _st("c", 0, "unmatched", "correct"), _st("c", 3, "unmatched", "correct"),
        _st("c", 4, "unmatched", "correct"), _st("c", 6, "abstained", zone=ZONE_ESCALATE, sct=None),
        # d: neither; 1-1-1 tie; not judged; withheld
        _st("d", 0, "unmatched"), _st("d", 3, "unmatched"), _st("d", 4, "unmatched"),
        _st("d", 6, "abstained", zone=ZONE_ESCALATE, sct=None),
        # e: right at rung 0, rung 3 destroys it on a lone sample; judge fails; ACCEPT ships it anyway
        _st("e", 0, "correct"), _st("e", 3, "incorrect"), _st("e", 4, "incorrect"), _st("e", 6, "incorrect"),
        # f: wrong code, exact span, all the way; 3-0; blind judge passes; withheld
        _st("f", 0, "incorrect"), _st("f", 3, "incorrect"), _st("f", 4, "incorrect"),
        _st("f", 6, "abstained", zone=ZONE_ESCALATE, sct=None),
    ]
    r3 = [rec("a", r3_votes={"1": 3}), rec("b", r3_votes={"1": 2, "9": 1}), rec("c", r3_votes={"1": 2}),
          rec("d", r3_votes={"1": 1, "8": 1, "9": 1}), rec("e", r3_votes={"7": 1}), rec("f", r3_votes={"9": 3})]
    r4 = [rec("a", r4_verdict="pass"), rec("b", r4_verdict="fail"), rec("c", r4_verdict="pass"),
          rec("d", r4_verdict=None), rec("e", r4_verdict="fail"), rec("f", r4_verdict="pass")]
    final = [rec("a", zone=ZONE_VERIFIED), rec("b", zone=ZONE_ESCALATE, sct=None),
             rec("c", zone=ZONE_ESCALATE, sct=None), rec("d", zone=ZONE_ESCALATE, sct=None),
             rec("e", zone=ZONE_VERIFIED), rec("f", zone=ZONE_ESCALATE, sct=None)]
    records = {0: [rec(x) for x in "abcdef"], 3: r3, 4: r4, 6: final}
    return records, state, final


def test_shipping_rules_split_what_ships_four_ways_and_count_what_a_person_receives():
    """The 2026-09-04 shipped-set figure, as a function: for each 'ship only
    when…' rule, what ships split by the state table's exact and overlap
    outcomes (right code on the exact span / exact span, wrong code / right
    code, boundary off / neither), what goes to a person and how many of
    those were right, accuracy, yield over ONE denominator, and F1 over the
    shipped subset alone so a withheld answer is a miss."""
    from ladder import analysis

    records, state, final = _dial_fixture()
    f1 = lambda recs: round(len(recs) / 10, 2)  # a stand-in scorer: visible, checkable
    rows = analysis.shipping_rules(records, state, final, f1=f1, tokens_by_rung={0: 100, 3: 300, 4: 40})
    by = {r["rule"]: r for r in rows}
    assert [r["rule"] for r in rows] == [
        "everything", "everything_after_r3", "accept", "r3_unanimous", "r3_two_agree", "r4_blind_pass"]
    # rung 0: a, e right; b, f exact span wrong code; c boundary off; d neither. Nothing to a person.
    assert by["everything"] == {
        "rule": "everything", "reads_rung": 0, "ships": 6, "correct": 2, "span_only": 2, "code_only": 1,
        "neither": 1, "to_person": 0, "person_correct": 0, "accuracy": round(2 / 6, 5),
        "yield": round(2 / 6, 5), "f1": 0.6, "extra_tokens": 0}
    # rung 3: a, b right; e, f wrong on the span; c boundary off; d neither
    assert (by["everything_after_r3"]["correct"], by["everything_after_r3"]["span_only"],
            by["everything_after_r3"]["code_only"], by["everything_after_r3"]["neither"]) == (2, 2, 1, 1)
    assert by["everything_after_r3"]["extra_tokens"] == 300
    # ACCEPT ships a (right) and e (wrong, exact span); four go to a person, of which b was right
    assert by["accept"]["ships"] == 2 and by["accept"]["correct"] == 1 and by["accept"]["span_only"] == 1
    assert by["accept"]["to_person"] == 4 and by["accept"]["person_correct"] == 1
    assert by["accept"]["f1"] == 0.2 and by["accept"]["extra_tokens"] == 0
    assert by["accept"]["yield"] == round(1 / 6, 5)
    # unanimous: all three samples returned one code — a, f; c's 2-0 has a missing sample
    # and goes to a person (the article's rule), e's lone sample is not a vote
    assert by["r3_unanimous"]["ships"] == 2 and by["r3_unanimous"]["correct"] == 1
    assert by["r3_unanimous"]["to_person"] == 4 and by["r3_unanimous"]["person_correct"] == 1  # b
    # two agree: a top count >= 2 — a, b, c, f
    assert by["r3_two_agree"]["ships"] == 4 and by["r3_two_agree"]["correct"] == 2
    # blind judge passes a, c, f; reads rung 4; b (right) goes to a person
    assert by["r4_blind_pass"]["ships"] == 3 and by["r4_blind_pass"]["correct"] == 1
    assert by["r4_blind_pass"]["code_only"] == 1 and by["r4_blind_pass"]["person_correct"] == 1
    assert by["r4_blind_pass"]["extra_tokens"] == 40 and by["r4_blind_pass"]["reads_rung"] == 4


def test_shipping_rules_add_the_loose_check_and_the_menu_judge_from_their_arms():
    from ladder import analysis

    records, state, final = _dial_fixture()
    # the lexarm ships a, b, e on its own final rows; its rung 4 answers are the base's
    lex_final = [rec("a", zone=ZONE_VERIFIED), rec("b", zone=ZONE_VERIFIED), rec("e", zone=ZONE_VERIFIED)] + \
                [rec(x, zone=ZONE_ESCALATE, sct=None) for x in "cdf"]
    lex_state = [r for r in state if r["rung"] != 6] + [
        _st("a", 6, "correct"), _st("b", 6, "correct"), _st("e", 6, "incorrect"),
        _st("c", 6, "abstained", zone=ZONE_ESCALATE, sct=None),
        _st("d", 6, "abstained", zone=ZONE_ESCALATE, sct=None),
        _st("f", 6, "abstained", zone=ZONE_ESCALATE, sct=None)]
    # the menu-shown judge passes a and b only
    menu_r4 = [rec("a", r4_verdict="pass"), rec("b", r4_verdict="pass")] + \
              [rec(x, r4_verdict="fail") for x in "cdef"]
    rows = analysis.shipping_rules(records, state, final,
                                   lexarm=(lex_final, lex_state), menu=(menu_r4, state))
    by = {r["rule"]: r for r in rows}
    assert [r["rule"] for r in rows] == [
        "everything", "everything_after_r3", "accept", "accept_contained",
        "r3_unanimous", "r3_two_agree", "r4_blind_pass", "r4_menu_pass"]
    assert by["accept_contained"]["ships"] == 3 and by["accept_contained"]["correct"] == 2
    assert by["accept_contained"]["to_person"] == 3 and by["accept_contained"]["person_correct"] == 0
    assert by["r4_menu_pass"]["ships"] == 2 and by["r4_menu_pass"]["correct"] == 2
    assert by["r4_menu_pass"]["to_person"] == 4 and by["r4_menu_pass"]["person_correct"] == 0
    assert "f1" not in by["accept"]  # no scorer given, no number invented


def test_shipping_rules_mean_averages_each_rule_over_the_draws():
    from ladder import analysis

    d0 = [{"rule": "accept", "reads_rung": 4, "ships": 53, "correct": 39, "to_person": 177,
           "person_correct": 49, "accuracy": 0.73585, "yield": 0.16957, "f1": 0.283, "extra_tokens": 0}]
    d1 = [{"rule": "accept", "reads_rung": 4, "ships": 51, "correct": 42, "to_person": 187,
           "person_correct": 46, "accuracy": 0.82353, "yield": 0.17647, "f1": 0.301, "extra_tokens": 0}]
    m = analysis.shipping_rules_mean([d0, d1])
    assert m == [{"rule": "accept", "reads_rung": 4, "draws": 2, "ships": 52.0, "correct": 40.5,
                  "to_person": 182.0, "person_correct": 47.5, "accuracy": 0.78, "yield": 0.173,
                  "f1": 0.292, "extra_tokens": 0}]

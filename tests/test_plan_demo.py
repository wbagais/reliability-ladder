"""scripts/plan_demo.py turns a run's archived per-rung files into the
record-by-record traces the plan page's "Ladder demo" tab shows.

The demo used to be three invented posts with measured numbers pasted beside
them. Now it is real records from `rerun-cadec-d0` and `rerun-finer-d0`, each
followed rung by rung through the files the run wrote: the menu rung 0
retrieved and the line it picked, rung 1's verdict and the checks behind it,
rung 2's attempt, rung 3's raw votes, rung 4's verdict blind and shown the
menu, where rung 5 put it, and the outcome against gold under both pairings.

Two rules the tests hold. A trace carries the model's SPAN and vocabulary
LABELS only — a quoted span longer than the tracked report's own precedent
(seven words) is withheld and replaced by its word count, and no field ever
carries a document, a prompt or a reply. And every value comes from the
files: the script selects records and names the case; it types no number.

Stdlib only: CI is python:3.12-slim with requirements.txt and pytest. The
fixture below is a synthetic two-record archive; the real archive carries
corpus text and lives under out/.
"""
from __future__ import annotations

import json
import pathlib

import pytest

from scripts.plan_demo import MAX_SPAN_WORDS, build_demo, build_demo_stripped, withhold

RUN = "toy-d0"


def _write(path: pathlib.Path, rows: list[dict]) -> None:
    path.write_text("".join(json.dumps(r) + "\n" for r in rows))


def _rec(rid, text, sct, label, checks, zone="NEW", reason=None):
    doc = rid.split("#")[0]
    return {"doc_id": doc, "entity_type": "REACTION", "text": text, "spans": [[0, len(text)]],
            "sct": sct, "sct_label": label, "meddra": None, "confidence": 1.0, "zone": zone,
            "reason": reason, "record_id": rid, "provenance": [], "checks": checks}


def _state(rid, rung, text, sct, zone, outcome, outcome_overlap, gold, **extra):
    row = {"run_id": RUN, "rung": rung, "record_id": rid, "doc_id": rid.split("#")[0],
           "text": text, "spans": [[0, len(text)]], "sct": sct, "sct_label": None, "confidence": 1.0,
           "zone": zone, "reason": None, "created_this_rung": rung == 0, "dropped_this_rung": False,
           "changed_this_rung": False, "changed_fields": [], "was_sct": None, "was_zone": None,
           "r1_verdict": None, "r1_reason": None, "r4_verdict": None, "r3_changed": None,
           "pick_fallback": None, "outcome": outcome, "correct": outcome == "correct",
           "outcome_overlap": outcome_overlap, "correct_overlap": outcome_overlap == "correct",
           "gold_codes": gold}
    row.update(extra)
    return row


@pytest.fixture
def archive(tmp_path: pathlib.Path) -> pathlib.Path:
    menu = [{"i": 0, "code": "100", "label": "spotting", "fsn": "spotting", "score": .9, "via": "dense", "query": "span"},
            {"i": 1, "code": "101", "label": "spotting in pregnancy", "fsn": "spotting in pregnancy", "score": .8, "via": "dense", "query": "span"}]
    base = {"rung0_step": "S2", "r0_negated": False, "candidates": menu, "label_rank": 0, "pick_fallback": None}
    r1 = dict(base, span_grounded=True, sct_exists=True, sct_is_finding=True, label_verified=True,
              lexical_match=True, negation_cue=None, r1_verdict="ACCEPT", r1_reason=None)
    r4 = dict(r1, r2={"outcome": "unchanged", "why": "not a correctable rung 1 rejection"},
              r3={"k": 3, "seen": 3, "tie": False, "raw": ["100", "100", "100"], "was": "100", "winner": "100"},
              r3_votes={"100": 3}, r4_menu="off", r4_verdict="pass", r4_confidence=0.9,
              r4="{'span_ok': True, 'code_ok': True, 'why': 'a prose reply that must never be copied'}")
    long_text = "one two three four five six seven eight"          # eight words: withheld
    r1_long = dict(r1, lexical_match=False, r1_verdict="BAND")
    r4_long = dict(r4, **r1_long)
    r4_long["r3"] = {"k": 3, "seen": 2, "tie": False, "raw": ["100", "101"], "was": "100", "winner": "101", "changed": True}
    r4_long["r4_verdict"] = "fail"
    # the menu arm's rung 4 says "not on this list" for the second record
    jm_a = dict(r4, r4_menu="ranked", r4={"span_ok": True, "code_ok": True, "confidence": .9, "why": "prose", "best": 0, "best_code": "100", "menu_missing": False})
    jm_b = dict(r4_long, r4_menu="ranked", r4={"span_ok": True, "code_ok": False, "confidence": .4, "why": "prose", "best": None, "best_code": None, "menu_missing": False})
    for rung, ck_a, ck_b in ((0, base, base), (1, r1, r1_long), (2, r1, r1_long), (3, r4, r4_long), (4, r4, r4_long), (5, r4, r4_long), (6, r4, r4_long)):
        _write(tmp_path / f"{RUN}.r{rung}.records.jsonl",
               [_rec("D.1#0", "spotting", "100", "spotting", ck_a, zone="VERIFIED" if rung >= 5 else "NEW"),
                _rec("D.1#1", long_text, "101" if rung >= 3 else "100", "spotting", ck_b, zone="ESCALATE" if rung >= 5 else "NEW")])
    _write(tmp_path / f"{RUN}-judgemenu.r4.records.jsonl",
           [_rec("D.1#0", "spotting", "100", "spotting", jm_a), _rec("D.1#1", long_text, "101", "spotting", jm_b)])
    state = []
    for rung in range(7):
        state.append(_state("D.1#0", rung, "spotting", "100", "VERIFIED" if rung >= 5 else "NEW", "correct", "correct", ["100"],
                            r1_verdict="ACCEPT" if rung >= 1 else None, r4_verdict="pass" if rung >= 4 else None))
        state.append(_state("D.1#1", rung, long_text, "101" if rung >= 3 else "100", "ESCALATE" if rung >= 5 else "NEW",
                            "incorrect" if rung >= 3 else "correct", "incorrect" if rung >= 3 else "correct", ["100"],
                            r1_verdict="BAND" if rung >= 1 else None, r3_changed=True if rung == 3 else None,
                            was_sct="100" if rung == 3 else None, r4_verdict="fail" if rung >= 4 else None))
    _write(tmp_path / f"{RUN}.state.jsonl", state)
    return tmp_path


LABELS = {"100": "Spotting", "101": "Spotting in pregnancy"}


def test_withhold_keeps_the_precedent_and_replaces_longer_spans_with_a_word_count():
    assert MAX_SPAN_WORDS == 7
    assert withhold("EXTREME AND EXCRUCIATING MUSCLE PAIN IN NECK") == "EXTREME AND EXCRUCIATING MUSCLE PAIN IN NECK"
    assert withhold("one two three four five six seven eight") == "(8-word quote withheld)"
    assert withhold(None) is None


def test_a_trace_follows_the_record_through_every_rung_from_the_files(archive):
    spec = [{"id": "D.1#0", "case": "the clean case", "shows": "shipped and right"}]
    out = build_demo(archive, RUN, spec, corpus="toy", labels=LABELS.get)
    assert len(out) == 1
    t = out[0]
    assert t["id"] == "D.1#0" and t["case"] == "the clean case" and t["corpus"] == "toy"
    assert t["span"] == "spotting" and t["negated"] is False
    assert t["r0"] == {"code": "100", "label": "spotting", "picked": 0, "fallback": None,
                       "menu": [{"i": 0, "label": "spotting", "gold": True}, {"i": 1, "label": "spotting in pregnancy", "gold": False}]}
    assert t["gold"] == [{"code": "100", "label": "Spotting"}]
    assert t["r1"]["verdict"] == "ACCEPT" and t["r1"]["lexical_match"] is True and t["r1"]["reason"] is None
    assert t["r2"] == {"outcome": "unchanged", "reason": None}
    assert t["r3"] == {"votes": ["Spotting", "Spotting", "Spotting"], "seen": 3, "was": "Spotting", "winner": "Spotting", "changed": False}
    assert t["r4"] == {"blind": "pass", "confidence": 0.9, "menu": "pass", "best": 0, "best_label": "spotting"}
    assert t["final"] == {"zone": "VERIFIED", "shipped": True, "outcome": "correct", "outcome_overlap": "correct"}


def test_a_long_span_is_withheld_a_vote_change_is_recorded_and_not_on_this_list_is_none(archive):
    spec = [{"id": "D.1#1", "case": "voting broke it", "shows": "held, wrong"}]
    t = build_demo(archive, RUN, spec, corpus="toy", labels=LABELS.get)[0]
    assert t["span"] == "(8-word quote withheld)"
    assert t["r1"]["verdict"] == "BAND" and t["r1"]["lexical_match"] is False
    assert t["r3"] == {"votes": ["Spotting", "Spotting in pregnancy"], "seen": 2, "was": "Spotting",
                       "winner": "Spotting in pregnancy", "changed": True}   # vocabulary labels, not menu case
    assert t["r4"]["blind"] == "fail" and t["r4"]["menu"] == "fail" and t["r4"]["best"] is None and t["r4"]["best_label"] is None
    assert t["final"] == {"zone": "ESCALATE", "shipped": False, "outcome": "incorrect", "outcome_overlap": "incorrect"}
    assert t["r0"]["code"] == "100" and t["final_code"] == {"code": "101", "label": "Spotting in pregnancy"}


def test_no_trace_field_carries_prose_from_a_prompt_or_a_reply(archive):
    spec = [{"id": "D.1#0", "case": "c", "shows": "s"}, {"id": "D.1#1", "case": "c", "shows": "s"}]
    dumped = json.dumps(build_demo(archive, RUN, spec, corpus="toy", labels=LABELS.get))
    assert "prose" not in dumped and "must never be copied" not in dumped
    for word in ("why", "prompt", "raw", "document", "context"):
        assert f'"{word}"' not in dumped, word


def test_an_unknown_record_id_is_an_error_not_a_blank_trace(archive):
    with pytest.raises(KeyError):
        build_demo(archive, RUN, [{"id": "D.9#9", "case": "c", "shows": "s"}], corpus="toy", labels=LABELS.get)


def test_rung_1_checks_come_from_the_rung_1_file_not_from_after_a_rescue(archive):
    """Rung 2 can relocate a REJECTed quote and re-validate it, so the rung 4
    record carries span_grounded=True for a record whose rung 1 verdict was
    span_ungrounded. The trace must show the checks that produced the verdict."""
    rid = "D.1#0"
    r1_path = archive / f"{RUN}.r1.records.jsonl"
    rows = [json.loads(l) for l in r1_path.read_text().splitlines()]
    for r in rows:
        if r["record_id"] == rid:
            r["checks"] = dict(r["checks"], span_grounded=False, r1_verdict="REJECT", r1_reason="span_ungrounded")
    _write(r1_path, rows)
    t = build_demo(archive, RUN, [{"id": rid, "case": "c", "shows": "s"}], corpus="toy", labels=LABELS.get)[0]
    assert t["r1"]["span_grounded"] is False


def test_a_stripped_records_file_gives_the_path_and_verdicts_but_no_span_and_no_gold(tmp_path):
    """PsyTAR's raw run lives on the other owner's machine; the published cell
    is a records file with the quoted text removed. The trace must say so
    rather than invent a span or an outcome."""
    rows = [{"doc_id": "P.1", "entity_type": "reaction", "spans": [[0, 5]], "sct": None, "sct_label": "sad", "meddra": None,
             "confidence": 1.0, "zone": "ESCALATE", "reason": "queued_for_review", "record_id": "P.1#0", "provenance": [],
             "checks": {"r0_negated": False, "label_rank": 1, "r1_verdict": "BAND", "r1_reason": None, "span_grounded": True,
                        "sct_exists": True, "sct_is_finding": True, "label_verified": True, "lexical_match": False,
                        "r2": {"outcome": "unchanged", "why": "prose"}, "r3": {"k": 3, "seen": 3, "raw": ["100", "101", "101"], "was": "100", "winner": "101", "changed": True},
                        "r4_verdict": "fail", "r4_confidence": 0.2, "r4": {"why": "prose"}}}]
    path = tmp_path / "x.records.stripped.jsonl"
    _write(path, rows)
    t = build_demo_stripped(path, "x", [{"id": "P.1#0", "case": "c", "shows": "s"}], corpus="psytar", labels=LABELS.get)[0]
    assert t["gold_known"] is False and t["gold"] == [] and "not published" in t["span"]
    assert t["r1"]["verdict"] == "BAND" and t["final"] == {"zone": "ESCALATE", "shipped": False, "outcome": None, "outcome_overlap": None}
    assert t["r3"] == {"votes": ["Spotting", "Spotting in pregnancy", "Spotting in pregnancy"], "seen": 3, "was": "Spotting", "winner": "Spotting in pregnancy", "changed": True}
    assert t["r4"] == {"blind": "fail", "confidence": 0.2, "menu": None, "best": None, "best_label": None}
    assert t["final_code"] == {"code": "101", "label": "Spotting in pregnancy"}
    assert "prose" not in json.dumps(t)
    with pytest.raises(KeyError):
        build_demo_stripped(path, "x", [{"id": "P.9#9", "case": "c", "shows": "s"}], corpus="psytar", labels=LABELS.get)


# ---------------------------------------------------------------- the document view

def test_reduce_document_keeps_the_grid_and_drops_every_word_of_the_post():
    """The demo shows a document the way the Workbench's Live tab does — rung 0
    against gold, then the grid of records by rungs 1-4 and the person column —
    from the Workbench's own payload (`dashboard.document_view`). What must not
    reach the page: the post itself, the model calls, the judge's prose, any
    quoted span over the seven-word precedent."""
    from scripts.plan_demo import reduce_document
    post = "I was extremely sick and initially felt I might not survive the week at all"
    payload = {
        "run_id": "toy-d0", "source": "run", "doc_id": "D.1", "split": "dev", "text": post,
        "order_run": [0, 1, 2, 3, 4, 5, 6],
        "records": [{
            "record_id": "D.1#0", "doc_id": "D.1", "text": "extremely sick", "spans": [[6, 20]], "sct": None,
            "sct_label": "sickness", "zone": "ESCALATE", "reason": "queued_for_review", "confidence": 1.0,
            "checks": {"r1_verdict": "BAND", "reason_band": "colloquial_no_lexical_match", "r0_negated": False,
                       "r2": {"outcome": "unchanged", "why": post}, "r3": {"k": 3, "seen": 3, "raw": ["100", "100", "100"], "was": "100", "winner": "100"},
                       "r4_verdict": "fail", "r4_confidence": 0.1, "r4": {"why": post, "best": None},
                       "candidates": [{"i": 0, "code": "100", "label": "symptom very severe", "score": .9}]},
            "timeline": [{"rung": 0, "sct": "100", "zone": "NEW", "text": "extremely sick", "spans": [[6, 20]], "r1_verdict": None, "outcome": "incorrect", "outcome_overlap": "incorrect", "gold_codes": ["213257006"]},
                         {"rung": 6, "sct": None, "zone": "ESCALATE", "text": "extremely sick", "spans": [[6, 20]], "r1_verdict": "BAND", "outcome": "abstained", "outcome_overlap": "abstained", "gold_codes": ["213257006"]}],
            "r0_path": {"steps": [{"id": "find", "state": "done", "detail": post, "negated": False},
                                  {"id": "retrieve", "state": "done", "retrieval": "dense", "candidates": [{"i": 0, "code": "100", "label": "symptom very severe", "score": .9}]},
                                  {"id": "pick", "state": "done", "choice": 0, "chosen": {"i": 0, "code": "100", "label": "symptom very severe"}, "detail": post},
                                  {"id": "trim", "state": "unchanged"}]},
            "rules": [{"id": "V", "name": "strict vocabulary check says ACCEPT", "state": "hold", "value": "BAND", "note": "colloquial_no_lexical_match"},
                      {"id": "J", "name": "blind judge says pass", "state": "hold", "value": "fail", "note": post},
                      {"id": "J+", "name": "menu-shown judge says pass", "state": "not_run", "value": None, "note": "menu-shown judge not run"}],
            "person": {"held": 2, "run": 2, "share": 1.0}}],
        "gold": [{"record_id": "D.1#0", "text": "extremely sick", "spans": [[6, 20]], "sct": ["213257006"], "gold_kind": "single", "excluded": False},
                 {"record_id": "D.1#1", "text": "one two three four five six seven eight", "spans": [[40, 70]], "sct": ["1"], "gold_kind": "single", "excluded": False}],
        "gold_diff": {"pairs": [{"gold": {"record_id": "D.1#0", "text": "extremely sick", "spans": [[6, 20]], "sct": ["213257006"], "gold_kind": "single"},
                                 "gold_labels": ["Generally unwell"], "span": "exact", "pred": "D.1#0", "pred_text": "extremely sick", "pred_spans": [[6, 20]],
                                 "pred_sct": "100", "pred_label": "sickness", "final_zone": "ESCALATE", "withheld": True, "code": "withheld_incorrect"},
                                {"gold": {"record_id": "D.1#1", "text": "one two three four five six seven eight", "spans": [[40, 70]], "sct": ["1"], "gold_kind": "single"},
                                 "gold_labels": ["X"], "span": "missed", "pred": None, "pred_text": None, "pred_spans": None, "pred_sct": None, "pred_label": None, "final_zone": None, "withheld": False, "code": None}],
                      "spurious": [], "counts": {"gold": 2, "found_exact": 1, "found_overlap": 0, "missed": 1, "spurious": 0, "predictions": 1}},
        "gold_diff_by_rung": {"6": {}},
        "rungs": {"0": {"aggregate": {}, "ledger": [], "calls": [{"prompt": post, "raw": post}], "cost": {"tokens": 100, "api_calls": 2, "latency_p95_ms": 500.0}},
                  "3": {"aggregate": {}, "ledger": [], "calls": [{"prompt": post}], "cost": {"tokens": 7000, "api_calls": 6, "latency_p95_ms": 8000.0}}},
        "menu_judge": None,
        "rules_legend": [{"id": "V", "name": "strict vocabulary check says ACCEPT", "held": 1, "run": 1, "share": 1.0}],
        "calls_total": 3, "calls_cached": 0, "state_available": True,
        "provenance": {"run_id": "toy-d0", "backend": "local-rf2", "manifest_hash": "abc", "git": {"sha": "deadbeef", "dirty": False}},
        "caveats": [{"key": "k", "text": "Rung 3 numbers are SAMPLES"}], "local_only": True,
    }
    d = reduce_document(payload, corpus="cadec")
    dumped = json.dumps(d)
    assert "the week" not in dumped and "survive" not in dumped, "post prose reached the page"
    for word in ("prompt", "raw", "why", "detail", "calls"):
        assert f'"{word}"' not in dumped, word
    assert "text" not in d, "the post itself is never carried"
    assert d["doc_id"] == "D.1" and d["words"] == len(post.split()) and d["corpus"] == "cadec"
    r = d["records"][0]
    assert r["record_id"] == "D.1#0" and r["span"] == "extremely sick" and r["r1"] == {"verdict": "BAND", "reason": "no lexical match"}
    assert r["r3"] == {"votes": {"100": 3}, "k": 3, "seen": 3, "changed": False, "tie": False}
    assert r["r4"] == {"verdict": "fail", "confidence": 0.1, "best": None}
    assert r["r0"]["menu"][0] == {"i": 0, "label": "symptom very severe", "gold": False} and r["r0"]["menu_n"] == 1 and r["r0"]["pick"] == {"state": "done", "choice": 0}
    assert [x["id"] for x in r["rules"]] == ["V", "J", "J+"] and r["rules"][0] == {"id": "V", "state": "hold", "value": "BAND"}
    assert r["person"] == {"held": 2, "run": 2}
    p0, p1 = d["pairs"]
    assert p0["gold"] == {"record_id": "D.1#0", "span": "extremely sick", "sct": ["213257006"], "labels": ["Generally unwell"], "spans": [[6, 20]]}
    assert p0["span_match"] == "exact" and p0["code"] == "withheld_incorrect" and p0["pred"] == "D.1#0"
    assert p1["gold"]["span"] == "(8-word quote withheld)" and p1["span_match"] == "missed" and p1["pred"] is None
    assert d["counts"] == payload["gold_diff"]["counts"]
    assert d["cost"]["3"] == {"tokens": 7000, "n_calls": 6, "p95_ms": 8000.0} and "1" not in d["cost"]
    assert d["legend"] == payload["rules_legend"]
    assert d["provenance"] == {"run_id": "toy-d0", "backend": "local-rf2", "manifest": "abc", "git": "deadbeef"}
    assert d["caveats"] == ["Rung 3 numbers are SAMPLES"]


def test_the_text_is_kept_only_for_a_redistributable_corpus():
    """FiNER-139 is CC-BY-SA and its excerpt may be shown; CADEC may not.
    `keep_text` is an explicit choice per corpus, off by default."""
    from scripts.plan_demo import reduce_document
    payload = {"run_id": "x", "doc_id": "F.1", "split": "dev", "text": "The effective tax rate was 47.6 percent .",
               "order_run": [0, 1], "records": [], "gold": [], "gold_diff": {"pairs": [], "spurious": [], "counts": {}},
               "rungs": {}, "rules_legend": [], "provenance": {}, "caveats": {}}
    assert "text" not in reduce_document(payload, corpus="cadec")
    assert reduce_document(payload, corpus="finer", keep_text=True)["text"] == payload["text"]

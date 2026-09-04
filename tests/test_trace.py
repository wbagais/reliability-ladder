"""Plan item 12 (2026-09-03): NOTHING RECORDED A RECORD'S STATE AT EACH RUNG,
and nothing kept the model's full input and output.

`out/*.ledger.jsonl` has one row per record per rung with verdict, zone and
cost — but rung 0 and rung 3 log per DOCUMENT, correctness is computed
afterwards by score_run and never joined back, and the prompt and reply of
every model call live only in a content-addressed cache nobody can read by
record. Four open items in the plan (9, 11, half of 3, the error budget) were
each a re-run that should have been a join.

`ladder/trace.py` is the join. Two tables, both written beside the records:

  <run>.state.jsonl     record_id x rung -> code, span, zone, verdict,
                        changed_this_rung, outcome against gold
  <run>.r<N>.calls.jsonl every model call the rung made: the FULL prompt, the
                        RAW reply, the normalised reply, tokens, latency,
                        cached or not, and the document it was about

The standing rule they carry: a rung that cannot say what it did to an
individual record cannot be credited or blamed for the aggregate.
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
    ZONE_NEW,
)


def rec(**kw):
    base = dict(
        doc_id="D1", entity_type=REACTION, text="bit drowsy", spans=[(9, 19)],
        sct="271782001", sct_label="Drowsy", zone=ZONE_NEW, record_id="D1#0",
    )
    base.update(kw)
    return Record(**base)


def gold(**kw):
    base = dict(
        doc_id="D1", index=0, entity_type=REACTION, cadec_type="ADR",
        text="bit drowsy", spans=[(9, 19)], sct=["271782001"], gold_kind=GOLD_SINGLE,
    )
    base.update(kw)
    return GoldMention(**base)


# --- the state table ---------------------------------------------------------


def test_rung_0_rows_are_creations_scored_against_gold():
    from ladder import trace

    rows = trace.state_rows(0, {}, [rec()], gold={"D1#0": gold()}, run_id="t")
    assert len(rows) == 1
    row = rows[0]
    assert row["run_id"] == "t" and row["rung"] == 0
    assert row["record_id"] == "D1#0" and row["doc_id"] == "D1"
    assert row["created_this_rung"] is True
    assert row["changed_this_rung"] is True
    assert row["sct"] == "271782001" and row["spans"] == [[9, 19]]
    assert row["outcome"] == "correct" and row["correct"] is True
    assert row["gold_codes"] == ["271782001"]


def test_a_code_change_is_named_with_what_it_replaced():
    from ladder import trace

    before = {"D1#0": rec(sct="111111111", sct_label="Other")}
    after = [rec(sct="271782001", sct_label="Drowsy")]
    row = trace.state_rows(3, before, after, gold={"D1#0": gold()})[0]
    assert row["created_this_rung"] is False
    assert row["changed_this_rung"] is True
    assert "sct" in row["changed_fields"]
    assert row["was_sct"] == "111111111"
    assert row["outcome"] == "correct"


def test_a_withdrawal_is_a_change_scored_as_abstained():
    from ladder import trace

    before = {"D1#0": rec(zone=ZONE_ACCEPT)}
    after = [rec(zone=ZONE_ABSTAIN, sct=None, reason="unresolved")]
    row = trace.state_rows(5, before, after, gold={"D1#0": gold()})[0]
    assert row["changed_this_rung"] is True
    assert set(row["changed_fields"]) >= {"sct", "zone"}
    assert row["was_zone"] == ZONE_ACCEPT and row["zone"] == ZONE_ABSTAIN
    assert row["outcome"] == "abstained" and row["correct"] is False


def test_an_untouched_record_is_a_row_that_says_so():
    """One row per record per rung, ALWAYS. A rung that only writes the rows it
    changed cannot answer 'what did rung 4 see' for the other 200."""
    from ladder import trace

    before = {"D1#0": rec()}
    after = [rec()]
    row = trace.state_rows(4, before, after, gold={"D1#0": gold()})[0]
    assert row["changed_this_rung"] is False and row["changed_fields"] == []
    assert row["outcome"] == "correct"


def test_a_prediction_on_no_gold_mention_is_unmatched_not_incorrect():
    """score.outcome returns INCORRECT for a false positive because it grades
    an answer. The state table names the reason there is no answer to grade:
    'unmatched' is a detection miss and 'incorrect' is a coding miss, and the
    error budget must not pool them."""
    from ladder import trace

    row = trace.state_rows(0, {}, [rec(spans=[(0, 3)], text="was")],
                           gold={"D1#0": gold()})[0]
    assert row["outcome"] == "unmatched" and row["correct"] is False
    assert row["gold_codes"] == []


def test_concept_less_against_concept_less_gold_is_correct():
    from ladder import trace

    row = trace.state_rows(0, {}, [rec(sct=CONCEPT_LESS)],
                           gold={"D1#0": gold(sct=[], gold_kind=GOLD_NONE)})[0]
    assert row["outcome"] == "correct"


def test_rows_carry_the_lane_fields_the_joins_need():
    """Items 9 and 11 both needed 'which rung 1 lane was this record in when
    rung 3 changed it'. The row carries the verdicts and the rung 0 lane."""
    from ladder import trace

    r = rec()
    r.checks.update(r1_verdict="BAND", r1_reason=None, r4_verdict="fail",
                    pick_fallback="gap", r3={"changed": True, "seen": 3})
    row = trace.state_rows(3, {"D1#0": rec()}, [r], gold={"D1#0": gold()})[0]
    assert row["r1_verdict"] == "BAND"
    assert row["r4_verdict"] == "fail"
    assert row["pick_fallback"] == "gap"
    assert row["r3_changed"] is True


def test_a_record_that_vanished_is_still_a_row():
    """Rung 0's filters drop records; a rung that removed one must say so."""
    from ladder import trace

    rows = trace.state_rows(1, {"D1#0": rec(), "D1#1": rec(record_id="D1#1")},
                            [rec()], gold={})
    gone = [r for r in rows if r["record_id"] == "D1#1"]
    assert gone and gone[0]["dropped_this_rung"] is True


def test_write_rows_appends_jsonl(tmp_path):
    from ladder import trace

    p = tmp_path / "s.jsonl"
    trace.write_rows(p, [{"a": 1}])
    trace.write_rows(p, [{"a": 2}])
    assert [json.loads(l)["a"] for l in p.read_text().splitlines()] == [1, 2]


# --- the call trace ----------------------------------------------------------


def test_call_trace_keeps_the_full_prompt_and_the_raw_reply(tmp_path):
    from ladder import trace

    t = trace.CallTrace(tmp_path / "c.jsonl", rung=0, role="extractor",
                        spec="ollama/x", sources={"D1": "the post text"})
    row = t.record(content="PROMPT\n\nPOST:\nthe post text", raw="```json\n{}\n```",
                   normalised="{}", mode="S2",
                   usage={"in": 5, "out": 2, "seconds": 0.1, "cached": False,
                          "timed_out": False, "truncated": False},
                   temperature=0.0, sample_index=0)
    t.close()
    on_disk = json.loads((tmp_path / "c.jsonl").read_text().splitlines()[0])
    assert on_disk == row
    assert on_disk["prompt"] == "PROMPT\n\nPOST:\nthe post text"
    assert on_disk["raw"] == "```json\n{}\n```"
    assert on_disk["normalised"] == "{}"
    assert on_disk["doc_id"] == "D1"
    assert on_disk["rung"] == 0 and on_disk["mode"] == "S2"
    assert on_disk["cached"] is False and on_disk["tokens_in"] == 5
    assert on_disk["model"] == "ollama/x" and on_disk["role"] == "extractor"
    assert on_disk["temperature"] == 0.0 and on_disk["sample_index"] == 0
    assert "sha256" in on_disk and on_disk["call_index"] == 0


def test_call_trace_infers_the_document_from_the_longest_source_in_the_prompt():
    """Rung 4 embeds the post in its template; rung 0 passes it as text. Both
    put the source in the content, so the document is inferred from the
    prompt rather than threaded through every rung's call signature. The
    LONGEST match wins, because one source can be a prefix of another."""
    from ladder import trace

    t = trace.CallTrace(None, rung=4, sources={"D1": "ab", "D2": "abcd"})
    assert t.infer_doc("judge this: abcd") == "D2"
    assert t.infer_doc("judge this: ab") == "D1"
    assert t.infer_doc("nothing here") is None


def test_a_caller_with_a_trace_records_every_call_including_cache_hits(tmp_path, monkeypatch):
    """Two calls, the second served from disk: TWO rows, the second marked
    cached. A replayed run is still a run, and its trace must say which calls
    it paid for."""
    from ladder import llm, trace

    caller = llm.Caller("ollama/gpt-oss:20b", role="extractor",
                        cache_dir=tmp_path / "cache")
    hits = {"n": 0}

    def fake_chat(messages, sample_index=0, temperature=0.0, max_tokens=None):
        hits["n"] += 1
        return llm.LLMResponse(text='{"mentions": []}', prompt_tokens=3,
                               completion_tokens=2, latency_s=0.01,
                               cached=hits["n"] > 1)

    monkeypatch.setattr(caller.client, "chat", fake_chat)
    caller.trace = trace.CallTrace(tmp_path / "calls.jsonl", rung=0,
                                   sources={"D1": "post"})
    caller("ask", "post", "S2")
    caller("ask", "post", "S2")
    caller.trace.close()
    rows = [json.loads(l) for l in (tmp_path / "calls.jsonl").read_text().splitlines()]
    assert len(rows) == 2
    assert rows[0]["cached"] is False and rows[1]["cached"] is True
    assert rows[0]["raw"] == '{"mentions": []}' and rows[0]["doc_id"] == "D1"
    assert rows[1]["call_index"] == 1


def test_a_caller_without_a_trace_is_unchanged(tmp_path, monkeypatch):
    from ladder import llm

    caller = llm.Caller("ollama/gpt-oss:20b", cache_dir=tmp_path / "cache")
    monkeypatch.setattr(caller.client, "chat", lambda *a, **k: llm.LLMResponse(
        text="{}", prompt_tokens=1, completion_tokens=1, latency_s=0.0))
    assert caller.trace is None
    assert caller("p", "", "judge")[0] == "{}"


# --- the cache directory is a run setting, not a symlink ----------------------


def test_the_llm_cache_directory_can_be_named_per_run(tmp_path, monkeypatch):
    """A DRAW is a run against a COLD cache. Until now that meant swapping a
    symlink between three directories, which no run file recorded. The
    directory is now an environment setting that for_rung reads and the run
    stamps, so 'which cache did draw 2 use' has an answer on disk."""
    from ladder import llm

    monkeypatch.setenv("LADDER_LLM_CACHE", str(tmp_path / "d2"))
    c = llm.for_rung(0, {"model": {"extractor": "ollama/gpt-oss:20b"}})
    assert c.client.cache_dir == tmp_path / "d2"
    assert llm.cache_dir_for() == tmp_path / "d2"


def test_without_the_setting_the_default_cache_stands(monkeypatch):
    from ladder import llm

    monkeypatch.delenv("LADDER_LLM_CACHE", raising=False)
    assert llm.cache_dir_for() == llm.DEFAULT_CACHE_DIR


# --- the overlap outcome, for the error budget ---------------------------------


def test_rows_also_carry_the_overlap_span_outcome():
    """The article reports exact and overlap side by side, and the error
    budget splits detection from coding under both. A row scored exact-only
    files "extreme rectal bleed" against gold "rectal bleed" as unmatched,
    which is a boundary miss, not a detection miss."""
    from ladder import trace

    r = rec(text="bit drowsy today", spans=[(9, 25)])
    row = trace.state_rows(0, {}, [r], gold={"D1#0": gold()})[0]
    assert row["outcome"] == "unmatched"
    assert row["outcome_overlap"] == "correct"
    assert row["correct_overlap"] is True
    exact = trace.state_rows(0, {}, [rec()], gold={"D1#0": gold()})[0]
    assert exact["outcome_overlap"] == "correct"
    none = trace.state_rows(0, {}, [rec(spans=[(0, 3)], text="was")],
                            gold={"D1#0": gold()})[0]
    assert none["outcome_overlap"] == "unmatched"
    unscored = trace.state_rows(0, {}, [rec()])[0]
    assert unscored["outcome_overlap"] == "unscored" and unscored["correct_overlap"] is None

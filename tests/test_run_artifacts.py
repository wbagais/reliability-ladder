"""The run writes what the article needs, per rung, beside the records.

Before 2026-09-03 a run left four files: ledger, records (FINAL state only),
results.csv and the manifest copy. Every rung's aggregate — rung 0's parse
counts, rung 3's vote spread, rung 4's verdict split — went to stdout and
nowhere else, and the record set as it stood AFTER rung 3 and BEFORE rung 4
existed only in memory. Plan item 12.

Now every run also writes:
  <run>.r<N>.records.jsonl   the record set as each rung left it
  <run>.state.jsonl          one row per record per rung, scored (ladder/trace.py)
  <run>.r<N>.calls.jsonl     every model call the rung made, prompt and reply
  <run>.aggregates.json      each rung's aggregate dict, plus run metadata
"""

import json

import pytest

from ladder.corpus import GOLD_SINGLE, GoldMention
from ladder.schema import REACTION, Record, ZONE_NEW

#          0        9       17          29
SOURCE = "suffered extreme rectal bleed today"


def rec(**kw):
    base = dict(
        doc_id="D1", entity_type=REACTION, text="rectal bleed", spans=[(17, 29)],
        sct="12063002", sct_label="Rectal hemorrhage", zone=ZONE_NEW,
        record_id="D1#0", confidence=1.0,
    )
    base.update(kw)
    return Record(**base)


def gold(**kw):
    base = dict(
        doc_id="D1", index=0, entity_type=REACTION, cadec_type="ADR",
        text="rectal bleed", spans=[(17, 29)], sct=["12063002"], gold_kind=GOLD_SINGLE,
    )
    base.update(kw)
    return GoldMention(**base)


class Vocab:
    """Enough of a registry for rung 1: 12063002 is a real, active finding."""

    def exists(self, c):
        return str(c) == "12063002"

    def is_active(self, c):
        return True

    def finding_status(self, c):
        return "finding"

    def lexical_match(self, text, code, mode="exact"):
        return False

    def replacements(self, c):
        return []

    def terms(self, c):
        return ["Rectal hemorrhage"]


MAN = {
    "rung_order": [0, 1, 2, 3, 4, 5, 6],
    "rungs": {"1": {"mode": "observe"}, "5": {"abstain_zones": ["BAND"]}},
    "model": {},
}


def run(tmp_path, run_id="t"):
    from ladder.run import run_ladder

    return run_ladder(
        MAN, "dev", [1, 5], [rec()], {"D1": SOURCE}, Vocab(), tmp_path, run_id,
        gold={"D1#0": gold()},
    )


def test_every_rung_leaves_its_own_record_snapshot(tmp_path):
    run(tmp_path)
    r1 = (tmp_path / "t.r1.records.jsonl").read_text().splitlines()
    r5 = (tmp_path / "t.r5.records.jsonl").read_text().splitlines()
    assert json.loads(r1[0])["zone"] == "NEW", "rung 1 observes; the zone must not move"
    assert json.loads(r1[0])["checks"]["r1_verdict"] == "BAND"
    assert json.loads(r5[0])["zone"] == "ABSTAIN"


def test_the_state_table_has_one_scored_row_per_record_per_rung(tmp_path):
    run(tmp_path)
    rows = [json.loads(l) for l in (tmp_path / "t.state.jsonl").read_text().splitlines()]
    assert [r["rung"] for r in rows] == [1, 5]
    assert rows[0]["r1_verdict"] == "BAND" and rows[0]["outcome"] == "correct"
    assert rows[1]["zone"] == "ABSTAIN" and rows[1]["outcome"] == "abstained"
    assert rows[1]["changed_this_rung"] is True and rows[0]["changed_this_rung"] is False


def test_aggregates_are_written_with_the_run_metadata(tmp_path, monkeypatch):
    monkeypatch.setenv("LADDER_LLM_CACHE", str(tmp_path / "cache-d1"))
    result = run(tmp_path)
    agg = json.loads((tmp_path / "t.aggregates.json").read_text())
    assert agg["run_id"] == "t" and agg["split"] == "dev"
    assert agg["order"] == [1, 5]
    assert agg["llm_cache"] == str(tmp_path / "cache-d1")
    assert "git" in agg and "started_utc" in agg and "finished_utc" in agg
    assert "1" in agg["rungs"] and "5" in agg["rungs"]
    assert agg["rungs"]["5"]["seconds"] >= 0
    assert result["run_id"] == "t"


def test_a_rung_without_a_model_writes_no_call_trace(tmp_path):
    run(tmp_path)
    assert not (tmp_path / "t.r1.calls.jsonl").exists()
    assert not (tmp_path / "t.r5.calls.jsonl").exists()


def test_the_state_table_is_written_without_gold_too(tmp_path):
    """--predictions runs and the ablation still get the join; the outcome
    column is simply 'unscored' rather than absent."""
    from ladder.run import run_ladder

    run_ladder(MAN, "dev", [1], [rec()], {"D1": SOURCE}, Vocab(), tmp_path, "ng")
    rows = [json.loads(l) for l in (tmp_path / "ng.state.jsonl").read_text().splitlines()]
    assert rows[0]["outcome"] == "unscored" and rows[0]["correct"] is None


def test_cmd_ladder_passes_the_exclusion_applied_gold_to_the_trace(tmp_path):
    """run.py builds gold once, exclusions applied, and hands the SAME dict to
    the results rows and the state table. Two gold sets is two answers."""
    import inspect

    from ladder import run

    src = inspect.getsource(run.cmd_ladder)
    assert "gold=gold" in src, "cmd_ladder does not pass its gold into run_ladder"
    assert src.index("excluded = clean_mod.exclusions_for(man)") < src.index("run_ladder("), (
        "gold must be built BEFORE the run so every rung's state row is scored"
    )

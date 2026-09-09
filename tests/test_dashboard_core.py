"""Dashboard M1 core data layer — run discovery, span keys, provenance, caveats.

All corpus text in these tests is SYNTHETIC. Never quote CADEC (C1 — the
licence rule applies to test fixtures exactly as to notebook outputs).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from dashboard import caveats as caveats_mod
from dashboard import runsindex
from dashboard import scrub
from dashboard.util import span_key, parse_span_param, format_span_param
from dashboard.provenance import provenance_for

# --- synthetic run fixture ---------------------------------------------------

SYN_TEXT = "Made-up example sentence with a pretend ache in it for testing."


def make_run(dir: Path, run_id: str = "syn-run-1", doc_ids=("SYN.1", "SYN.2"),
             rung3_disabled: bool = False, oracle: bool = False,
             r1_mode: str = "observe") -> Path:
    dir.mkdir(parents=True, exist_ok=True)
    records = [
        {
            "doc_id": doc_ids[0], "entity_type": "reaction", "text": "pretend ache",
            "spans": [[32, 44]], "sct": "1111111111", "sct_label": "pretend ache",
            "zone": "VERIFIED", "record_id": f"{doc_ids[0]}#0",
            "provenance": [{"rung": 5, "from": "NEW", "to": "VERIFIED", "reason": None}],
            "checks": {"r1_verdict": "ACCEPT", "r1_reason": None,
                       "rung0_step": "S2", "rung0_retrieval": "dense",
                       "label_verified": True},
        },
        {
            "doc_id": doc_ids[1], "entity_type": "reaction", "text": "made up twinge",
            "spans": [[5, 11], [20, 27]], "sct": None,
            "zone": "ESCALATE", "record_id": f"{doc_ids[1]}#0",
            "provenance": [{"rung": 5, "from": "NEW", "to": "ABSTAIN", "reason": "withheld"},
                            {"rung": 6, "from": "ABSTAIN", "to": "ESCALATE", "reason": "queued_for_review"}],
            "checks": {"r1_verdict": "BAND", "r1_reason": None,
                       "withheld": {"sct": "2222222222", "confidence": 0.4}},
        },
        {
            # schema-invalid: unlocated spans — unreviewable by a span-keyed
            # desk, must render "unlocatable", never an error (R4 criteria).
            "doc_id": doc_ids[1], "entity_type": "reaction", "text": "phantom",
            "spans": [[-1, -1]], "sct": None,
            "zone": "ESCALATE", "record_id": f"{doc_ids[1]}#1",
            "provenance": [{"rung": 5, "from": "NEW", "to": "ABSTAIN", "reason": "withheld"},
                            {"rung": 6, "from": "ABSTAIN", "to": "ESCALATE", "reason": "queued_for_review"}],
            "checks": {"r1_verdict": "REJECT", "r1_reason": "schema_invalid"},
        },
    ]
    (dir / f"{run_id}.records.jsonl").write_text(
        "\n".join(json.dumps(r) for r in records) + "\n")
    ledger_rows = [
        {"run_id": run_id, "rung": 0, "doc_id": d, "record_id": d, "zone": "NEW",
         "outcome": "extracted", "reason": None, "tokens_in": 100, "tokens_out": 50,
         "api_calls": 2, "latency_ms": 1000.0, "usd": 0.0, "human_minutes": 0.0,
         "ts": 0.0, "extra": {"denominator": "r0_documents", "evaluable": "pass"},
         "verdict": None}
        for d in doc_ids
    ]
    ledger_rows.append(
        {"run_id": run_id, "rung": 1, "doc_id": doc_ids[0], "record_id": f"{doc_ids[0]}#0",
         "zone": "NEW", "outcome": "judged", "reason": None, "tokens_in": 0,
         "tokens_out": 0, "api_calls": 0, "latency_ms": 1.0, "usd": 0.0,
         "human_minutes": 0.0, "ts": 0.0,
         "extra": {"denominator": "r1_offered", "evaluable": "pass", "mode": r1_mode},
         "verdict": "ACCEPT"})
    # one correctable REJECT (code_unknown) and one that is not (schema_invalid)
    for rid, reason in ((f"{doc_ids[1]}#0", "code_unknown"),
                        (f"{doc_ids[1]}#1", "schema_invalid")):
        ledger_rows.append(
            {"run_id": run_id, "rung": 1, "doc_id": doc_ids[1], "record_id": rid,
             "zone": "NEW", "outcome": "judged", "reason": reason, "tokens_in": 0,
             "tokens_out": 0, "api_calls": 0, "latency_ms": 1.0, "usd": 0.0,
             "human_minutes": 0.0, "ts": 0.0,
             "extra": {"denominator": "r1_offered", "evaluable": "fail",
                       "mode": r1_mode},
             "verdict": "REJECT"})
    # every rung logs one row per record even when it does not fire — "did
    # not fire" must stay distinguishable from "did not run" in the ledger.
    # Outcomes use the pipeline's own vocabulary (r2 "unchanged"; r5
    # "settled"/"abstained").
    for rung, rid, outcome in ((2, f"{doc_ids[0]}#0", "unchanged"),
                               (5, f"{doc_ids[0]}#0", "settled"),
                               (5, f"{doc_ids[1]}#0", "abstained")):
        ledger_rows.append(
            {"run_id": run_id, "rung": rung, "doc_id": rid.split("#")[0],
             "record_id": rid, "zone": "NEW", "outcome": outcome,
             "reason": None, "tokens_in": 0, "tokens_out": 0, "api_calls": 0,
             "latency_ms": 0.1, "usd": 0.0, "human_minutes": 0.0, "ts": 0.0,
             "extra": {"denominator": f"r{rung}_offered", "evaluable": "pass"},
             "verdict": None})
    if rung3_disabled:
        ledger_rows.append(
            {"run_id": run_id, "rung": 3, "doc_id": "-", "record_id": "rung3",
             "zone": "CONFIG", "outcome": "disabled",
             "reason": "manifest.rungs.3.enabled=false", "tokens_in": 0,
             "tokens_out": 0, "api_calls": 0, "latency_ms": 0.0, "usd": 0.0,
             "human_minutes": 0.0, "ts": 0.0,
             "extra": {"evaluable": "could_not_run"}, "verdict": None})
    else:
        ledger_rows.append(
            {"run_id": run_id, "rung": 3, "doc_id": doc_ids[0], "record_id": doc_ids[0],
             "zone": "NEW", "outcome": "voted", "reason": None, "tokens_in": 500,
             "tokens_out": 300, "api_calls": 6, "latency_ms": 5000.0, "usd": 0.0,
             "human_minutes": 0.0, "ts": 0.0,
             "extra": {"denominator": "r3_documents", "evaluable": "pass"},
             "verdict": None})
    ledger_rows.append(
        {"run_id": run_id, "rung": 4, "doc_id": doc_ids[0], "record_id": f"{doc_ids[0]}#0",
         "zone": "NEW", "outcome": "judged", "reason": None, "tokens_in": 200,
         "tokens_out": 20, "api_calls": 1, "latency_ms": 900.0, "usd": 0.0,
         "human_minutes": 0.0, "ts": 0.0,
         "extra": {"denominator": "r4_offered", "evaluable": "pass"}, "verdict": None})
    ledger_rows.append(
        {"run_id": run_id, "rung": 6, "doc_id": doc_ids[1], "record_id": f"{doc_ids[1]}#0",
         "zone": "ESCALATE",
         "outcome": "resolved_oracle" if oracle else "escalated",
         "reason": "queued_for_review", "tokens_in": 0, "tokens_out": 0,
         "api_calls": 0, "latency_ms": 0.0, "usd": 0.0, "human_minutes": 2.0,
         "ts": 0.0,
         "extra": {"denominator": "r6_queue", "evaluable": "fail",
                   "minutes_source": "simulated"}, "verdict": None})
    (dir / f"{run_id}.ledger.jsonl").write_text(
        "\n".join(json.dumps(r) for r in ledger_rows) + "\n")
    (dir / f"{run_id}.results.csv").write_text(
        "rung,layer,n_records,accept,band,reject,abstained,escalated,verified,"
        "r1_reject_pct,r1_mode,coverage,f1_sct_strict,yield,settled,corrupted,"
        "sct_outdated,sct_abstained,err_per_100,sct_modernised,tokens_per_record,"
        "p95_s,reviews_per_100,marginal_tokens_per_error,marginal_reviews_per_error,"
        "ci_low,ci_high\n"
        "0,bare LLM,2,0,0,0,0,0,0,,,1.0,0.5,0.5,0,1,0,0,50.0,0,75.0,1.0,0.0,,,,\n"
        "6,human loop,2,0,0,0,0,1,1,,,0.5,1.0,0.5,2,0,0,0,0.0,0,0.0,0.0,50.0,,,,\n")
    (dir / f"{run_id}.manifest.json").write_text(json.dumps({
        "vocabulary": {"snomed_backend": "local-rf2"},
        "model": {"extractor": "ollama/fake:1b", "judge": "ollama/fake2:1b"},
        "rung_order": [0, 1, 2, 3, 4, 5, 6],
        "rungs": {"6": {"mode": "oracle" if oracle else "simulated",
                        "minutes_per_record": 2.0}},
    }))
    return dir


# --- run discovery -----------------------------------------------------------


def test_discover_runs_groups_artifacts_by_stem(tmp_path):
    make_run(tmp_path / "out")
    runs = runsindex.discover_runs([(tmp_path / "out", False)])
    assert "syn-run-1" in runs
    info = runs["syn-run-1"]
    assert info.files["records"].name == "syn-run-1.records.jsonl"
    assert info.files["ledger"].name == "syn-run-1.ledger.jsonl"
    assert info.files["results"].name == "syn-run-1.results.csv"
    assert info.files["manifest"].name == "syn-run-1.manifest.json"
    assert info.archived is False


def test_discover_runs_recurses_into_archive_subdirs(tmp_path):
    make_run(tmp_path / "archive" / "some-branch", run_id="old-run")
    runs = runsindex.discover_runs([(tmp_path / "archive", True)])
    assert "old-run" in runs
    assert runs["old-run"].archived is True


def test_discover_runs_disambiguates_colliding_ids(tmp_path):
    make_run(tmp_path / "out", run_id="dup")
    make_run(tmp_path / "archive" / "branch-a", run_id="dup")
    runs = runsindex.discover_runs(
        [(tmp_path / "out", False), (tmp_path / "archive", True)])
    assert len(runs) == 2
    assert "dup" in runs  # first source keeps the bare id
    assert any(k.endswith("/dup") and k != "dup" for k in runs)


def test_split_inferred_from_doc_ids(tmp_path):
    make_run(tmp_path / "out")
    runs = runsindex.discover_runs([(tmp_path / "out", False)])
    splits = {"dev": ["SYN.1", "SYN.2", "SYN.3"], "test": ["OTHER.1"]}
    assert runsindex.infer_split(runs["syn-run-1"], splits) == "dev"
    assert runsindex.infer_split(runs["syn-run-1"], {"test": ["OTHER.1"]}) == "unknown"


def test_main_checkout_archive_found_through_worktree_gitfile(tmp_path):
    main = tmp_path / "main"
    (main / ".git").mkdir(parents=True)
    (main / "out" / "archive").mkdir(parents=True)
    wt = tmp_path / "main" / ".claude" / "worktrees" / "wt1"
    wt.mkdir(parents=True)
    (wt / ".git").write_text(f"gitdir: {main}/.git/worktrees/wt1\n")
    assert runsindex.main_checkout_archive(wt) == main / "out" / "archive"
    # a normal checkout (its .git is a directory): its own out/archive or None
    assert runsindex.main_checkout_archive(main) is None


# --- span-key identity (C: record identity is by span key, never record_id) --


def test_span_key_ignores_segment_order_and_record_id():
    assert span_key("SYN.1", [(5, 11), (20, 27)]) == span_key("SYN.1", [(20, 27), (5, 11)])
    assert span_key("SYN.1", [(5, 11)]) != span_key("SYN.2", [(5, 11)])


def test_span_param_roundtrip_discontinuous():
    spans = [(5, 11), (20, 27)]
    s = format_span_param(spans)
    assert parse_span_param(s) == [(5, 11), (20, 27)]
    # order-insensitive identity
    assert span_key("D", parse_span_param("20:27,5:11")) == span_key("D", spans)


def test_span_param_survives_unlocatable_minus_one_spans():
    # schema-invalid records carry (-1,-1) and must stay addressable (R4).
    s = format_span_param([(-1, -1)])
    assert parse_span_param(s) == [(-1, -1)]


# --- provenance (C3) ---------------------------------------------------------


def test_provenance_names_all_five_fields(tmp_path):
    make_run(tmp_path / "out")
    runs = runsindex.discover_runs([(tmp_path / "out", False)])
    info = runs["syn-run-1"]
    p = provenance_for(info, split="dev", span_match="exact")
    assert p["run_id"] == "syn-run-1"
    assert p["split"] == "dev"
    assert p["span_match"] == "exact"
    assert p["backend"] == "local-rf2"
    assert len(p["manifest_hash"]) >= 8


def test_provenance_without_manifest_copy_is_explicitly_absent(tmp_path):
    d = make_run(tmp_path / "out")
    (d / "syn-run-1.manifest.json").unlink()
    runs = runsindex.discover_runs([(tmp_path / "out", False)])
    p = provenance_for(runs["syn-run-1"], split="dev", span_match="exact")
    assert p["manifest_hash"] == "absent"
    assert p["backend"] == "unknown"


# --- caveats are data (C4) ---------------------------------------------------


def test_caveat_texts_exist_as_data():
    for key in ("rung3_samples", "judge_2b", "minutes_declared",
                "outdated_separate", "backend_dependent", "oracle_ceiling"):
        assert key in caveats_mod.CAVEATS
        assert len(caveats_mod.CAVEATS[key]) > 20
    assert "declared" in caveats_mod.CAVEATS["minutes_declared"]
    assert "never" in caveats_mod.CAVEATS["outdated_separate"]


def test_caveats_attach_from_ledger_facts(tmp_path):
    make_run(tmp_path / "out")
    runs = runsindex.discover_runs([(tmp_path / "out", False)])
    rows = runsindex.read_ledger(runs["syn-run-1"])
    keys = caveats_mod.keys_for_run(ledger_rows=rows, split="dev")
    assert "rung3_samples" in keys      # rung 3 ran (not disabled)
    assert "judge_2b" in keys           # rung 4 rows present
    assert "minutes_declared" in keys   # human_minutes on rung 6 rows
    assert "backend_dependent" in keys  # rung 1 verdicts present
    assert "oracle_ceiling" not in keys


def test_disabled_rung3_attaches_no_sample_caveat_and_oracle_flags(tmp_path):
    make_run(tmp_path / "out", run_id="r3off", rung3_disabled=True, oracle=True)
    runs = runsindex.discover_runs([(tmp_path / "out", False)])
    rows = runsindex.read_ledger(runs["r3off"])
    keys = caveats_mod.keys_for_run(ledger_rows=rows, split="test")
    assert "rung3_samples" not in keys
    assert "oracle_ceiling" in keys
    assert "spent_test" in keys


# --- export scrubbing (C1) ---------------------------------------------------


def test_scrub_removes_text_bearing_keys_recursively():
    payload = {
        "doc_id": "SYN.1", "text": SYN_TEXT, "spans": [[1, 2]],
        "sct": "123", "sct_label": "model free text",
        "nested": {"source": SYN_TEXT, "label": "vocab label"},
        "list": [{"context": SYN_TEXT, "code": "9"}],
    }
    clean = scrub.scrub_payload(payload)
    dumped = json.dumps(clean)
    assert SYN_TEXT not in dumped
    assert "model free text" not in dumped  # model text can echo the post
    assert clean["doc_id"] == "SYN.1"
    assert clean["nested"]["label"] == "vocab label"  # vocabulary labels stay
    assert clean["list"][0]["code"] == "9"


def test_scrub_assert_clean_raises_on_leaked_text():
    with pytest.raises(scrub.CorpusTextLeak):
        scrub.assert_clean(json.dumps({"a": SYN_TEXT}), known_texts=[SYN_TEXT])
    scrub.assert_clean(json.dumps({"a": "just numbers 1 2 3"}),
                       known_texts=[SYN_TEXT])


# --- 2026-09-09 refresh: the per-rung artifacts every run writes now -------


def test_discover_runs_does_not_mistake_per_rung_snapshots_for_runs(tmp_path):
    """Since 2026-09-03 a run also leaves <run>.r<N>.records.jsonl,
    <run>.state.jsonl, <run>.r<N>.calls.jsonl and <run>.aggregates.json.
    The b2-menu archive listed 219 "runs" of which 150 were rung snapshots."""
    from dashboard.runsindex import discover_runs

    d = tmp_path / "out"
    d.mkdir()
    for name in ("r.records.jsonl", "r.ledger.jsonl", "r.r0.records.jsonl",
                 "r.r3.records.jsonl", "r.state.jsonl", "r.r0.calls.jsonl",
                 "r.r4.calls.jsonl", "r.aggregates.json"):
        (d / name).write_text("{}\n")
    runs = discover_runs([(d, False)])
    assert set(runs) == {"r"}, sorted(runs)
    files = runs["r"].files
    assert files["records"].name == "r.records.jsonl"
    assert files["state"].name == "r.state.jsonl"
    assert files["aggregates"].name == "r.aggregates.json"
    assert files["r0.records"].name == "r.r0.records.jsonl"
    assert files["r3.records"].name == "r.r3.records.jsonl"
    assert files["r0.calls"].name == "r.r0.calls.jsonl"
    assert files["r4.calls"].name == "r.r4.calls.jsonl"


def test_default_sources_include_the_tracked_runs_archive(tmp_path):
    """runs/archive/ has held the consolidated re-run's corpus-free four per
    run since 2026-09-07 — it is on every clone, so a fresh checkout is not
    an empty dashboard."""
    from dashboard.state import AppState

    (tmp_path / "runs" / "archive" / "c").mkdir(parents=True)
    (tmp_path / "runs" / "archive" / "c" / "x.ledger.jsonl").write_text("")
    state = AppState(repo_root=tmp_path)
    assert (tmp_path / "out", False) == state.sources[0]
    assert (tmp_path / "runs" / "archive", True) in state.sources
    assert "x" in state.runs()
    assert state.runs()["x"].archived is True

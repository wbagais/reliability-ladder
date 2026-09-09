"""Dashboard Live run — one document, through the REAL rungs, in-process.

The tab the plan page's "Ladder demo" pane is a static picture of: a text
the operator pastes (or a dev/pool document they pick) is run through
`ladder.run.run_ladder` — the pipeline's own driver, every rung's own
`apply`, the model calls through `llm.for_rung` — up to a chosen rung, into
a TEMPORARY directory that is read back for the view and then deleted.
Nothing lands under `out/`, no run id enters the runs list, and the payload
says on every number that one document is not a measurement.

CI has no Ollama, no corpus and no index, so the extractor and judge here
are scripted callers bound through the same `for_rung` seam the run uses,
and the vocabulary is the nine-concept registry from test_registry_lookup.
Rung 0 runs its real bare path (mode A, offsets by search); rungs 1, 2, 4,
5 and 6 are the real modules untouched. Rung 3 is DISABLED in the manifest
— a recorded state the payload must carry, never a silent skip.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

pytest.importorskip(
    "fastapi", reason="dashboard extras not installed (CI runs without them)")
from fastapi.testclient import TestClient  # noqa: E402

from ladder.corpus import Document, GoldMention
from ladder.schema import REACTION
from tests.test_registry_lookup import reg  # noqa: F401  (fixture)

from dashboard.app import create_app
from dashboard.live import LiveError, LiveRunner
from dashboard.state import AppState

#          0        9       17          29
TEXT = "suffered extreme rectal bleed today"

EXTRACT = {"mentions": [{"span_text": "rectal bleed", "start": 17, "end": 29,
                         "code": "999999", "confidence": 0.9}]}
CORRECT = {"span_text": "rectal bleed", "start": 17, "end": 29,
           "code": "12063002", "confidence": 0.9}
JUDGE = {"span_ok": True, "code_ok": True, "confidence": 0.9, "why": "fine"}


class FakeCaller:
    """What `llm.for_rung` hands a rung: callable as (prompt, text, mode),
    with the trace hook `run_ladder` attaches so calls land in the trace."""

    def __init__(self, spec: str, role: str, replies: dict):
        self.spec, self.role, self.replies = spec, role, replies
        self.trace = None
        self.latencies: list[float] = []

    def __call__(self, prompt, text, mode, temperature=None, sample_index=0):
        raw = json.dumps(self.replies.get(mode, {}))
        content = f"{prompt}\n\nPOST:\n{text}" if text else prompt
        usage = {"in": 10, "out": 5, "seconds": 0.01, "model": self.spec,
                 "cached": False, "timed_out": False, "usd": 0.0,
                 "truncated": False}
        if self.trace is not None:
            self.trace.record(content=content, raw=raw, normalised=raw,
                              mode=mode, usage=usage, temperature=0.0,
                              sample_index=sample_index)
        return raw, usage

    def latency_p95(self):
        return None


@pytest.fixture()
def fake_models(monkeypatch):
    from ladder import llm

    def for_rung(n, manifest=None, override=None, cache_dir=None):
        role = llm.ROLE_BY_RUNG.get(n)
        if role is None:
            return None
        if role == "judge":
            return FakeCaller("fake/judge", role, {"judge": JUDGE})
        return FakeCaller("fake/extractor", role,
                          {"A": EXTRACT, "correct": CORRECT})

    monkeypatch.setattr(llm, "for_rung", for_rung)
    monkeypatch.setattr(llm, "check_models", lambda man, rungs, available=None: [])


def manifest(tmp_path: Path) -> dict:
    return {
        "rung_order": [0, 1, 2, 3, 4, 5, 6],
        "model": {"extractor": "fake/extractor", "judge": "fake/judge",
                  "temperature": 0.0},
        "corpus": {"adapter": "cadec", "cadec_root": str(tmp_path / "no-corpus"),
                   "splits_dir": str(tmp_path / "no-splits")},
        "vocabulary": {"snomed_backend": "local-rf2", "meddra_mode": "reference"},
        "output": {"dir": str(tmp_path / "out")},
        "rungs": {
            "0": {"rung0_step": None, "rung0_mode": "recall",
                  "rung0_offsets": "search", "rung0_fewshot": False,
                  "rung0_trim": False, "rung0_split": False},
            "1": {"mode": "observe"}, "2": {}, "3": {"enabled": False},
            "4": {}, "5": {}, "6": {"mode": "simulated", "minutes_per_record": 2.0},
        },
    }


def corpus() -> dict[str, Document]:
    m = GoldMention(doc_id="LIVE.1", index=0, entity_type=REACTION,
                    cadec_type="ADR", text="rectal bleed", spans=[(17, 29)],
                    sct=["12063002"], gold_kind="single")
    return {"LIVE.1": Document("LIVE.1", "ARTHROTEC", TEXT, [m]),
            "TST.1": Document("TST.1", "LIPITOR", "held out text.", [])}


@pytest.fixture()
def state(tmp_path, reg):  # noqa: F811
    return AppState(
        repo_root=tmp_path, sources=[(tmp_path / "out", False)],
        corpus=corpus(), splits={"dev": ["LIVE.1"], "test": ["TST.1"], "pool": []},
        exclusion_rows=[], registry=reg, manifest=manifest(tmp_path),
    )


@pytest.fixture()
def runner(state, fake_models):
    return LiveRunner(state, background=False)


@pytest.fixture()
def client(state, runner):
    return TestClient(create_app(state, live_runner=runner))


# --- the run itself ----------------------------------------------------------


def test_pasted_text_runs_through_the_real_rungs_up_to_the_chosen_one(runner):
    job = runner.start(text=TEXT, through_rung=6)
    assert job.status == "done", job.error
    res = job.result
    assert res["source"] == "pasted" and res["split"] == "live"
    assert res["order_run"] == [0, 1, 2, 3, 4, 5, 6]
    assert res["text"] == TEXT
    # rung 0 (real bare path, scripted reply) made one record from the text
    assert len(res["records"]) == 1
    rec = res["records"][0]
    assert rec["text"] == "rectal bleed" and rec["spans"] == [[17, 29]]
    # the per-rung timeline is the state table — rung 1 rejected the fake
    # code, rung 2 fired on that statable fact and rewrote it
    tl = {row["rung"]: row for row in rec["timeline"]}
    assert tl[0]["sct"] == "999999"
    assert tl[1]["r1_verdict"] == "REJECT" and tl[1]["r1_reason"] == "code_unknown"
    assert tl[2]["sct"] == "12063002" and tl[2]["changed_this_rung"] is True
    assert 3 not in tl, "a disabled rung writes no state row"
    assert tl[4]["r4_verdict"] == "pass"
    assert tl[6]["zone"] in ("ESCALATE", "VERIFIED", "ABSTAIN")
    # rung 3 disabled is a RECORDED state
    assert res["rungs"]["3"]["aggregate"] == {"disabled": True}
    assert res["rungs"]["3"]["ledger"][0]["outcome"] == "disabled"


def test_every_model_call_is_shown_with_prompt_and_raw_reply(runner):
    res = runner.start(text=TEXT, through_rung=4).result
    calls = {n: r["calls"] for n, r in res["rungs"].items()}
    assert [c["mode"] for c in calls["0"]] == ["A"]
    assert calls["0"][0]["prompt"].endswith("POST:\n" + TEXT)
    assert json.loads(calls["0"][0]["raw"]) == EXTRACT
    assert [c["mode"] for c in calls["2"]] == ["correct"]
    assert "999999" in calls["2"][0]["prompt"], "rung 2 states the fact back"
    assert [c["mode"] for c in calls["4"]] == ["judge"]
    assert calls["4"][0]["model"] == "fake/judge"
    assert calls["1"] == [] and calls["3"] == []
    # cost: three separate measures per rung, never fused
    assert res["rungs"]["0"]["cost"]["tokens"] == 15
    assert res["rungs"]["0"]["cost"]["api_calls"] == 1
    assert "latency_p95_ms" in res["rungs"]["0"]["cost"]
    assert res["calls_total"] == 3 and res["calls_cached"] == 0


def test_stopping_at_a_rung_runs_nothing_above_it(runner):
    res = runner.start(text=TEXT, through_rung=1).result
    assert res["order_run"] == [0, 1]
    assert set(res["rungs"]) == {"0", "1"}
    assert res["records"][0]["timeline"][-1]["rung"] == 1
    assert res["records"][0]["zone"] == "NEW", "rung 1 observes; nothing moved it"


def test_a_corpus_document_is_scored_against_its_gold(runner):
    res = runner.start(doc_id="LIVE.1", through_rung=2).result
    assert res["source"] == "corpus" and res["split"] == "dev"
    assert res["doc_id"] == "LIVE.1" and res["text"] == TEXT
    assert [g["record_id"] for g in res["gold"]] == ["LIVE.1#0"]
    tl = {row["rung"]: row for row in res["records"][0]["timeline"]}
    assert tl[1]["outcome"] == "incorrect" and tl[1]["gold_codes"] == ["12063002"]
    assert tl[2]["outcome"] == "correct", "rung 2's correction is credited to rung 2"


def test_pasted_text_has_no_gold_and_says_so(runner):
    res = runner.start(text=TEXT, through_rung=1).result
    assert res["gold"] is None
    assert all(row["outcome"] == "unscored"
               for row in res["records"][0]["timeline"])


def test_a_finished_job_reports_every_rung_done_after_its_scratch_dir_is_gone(runner):
    job = runner.start(text=TEXT, through_rung=2)
    assert not Path(job.scratch_dir).exists()
    assert job.public()["progress"]["rungs_done"] == [0, 1, 2]
    assert job.public()["progress"]["rung_running"] is None


def test_nothing_is_written_under_out_and_no_run_id_appears(runner, state, tmp_path):
    before = set((tmp_path / "out").rglob("*")) if (tmp_path / "out").exists() else set()
    job = runner.start(text=TEXT, through_rung=6)
    after = set((tmp_path / "out").rglob("*")) if (tmp_path / "out").exists() else set()
    assert after == before
    assert job.result["run_id"] not in state.runs()
    assert not Path(job.result["scratch_dir"]).exists(), "the temp dir is gone"


def test_provenance_and_caveats_name_the_live_run_for_what_it_is(runner):
    res = runner.start(text=TEXT, through_rung=6).result
    p = res["provenance"]
    assert p["run_id"].startswith("live-") and p["split"] == "live"
    assert p["live"] is True and p["archived"] is False
    assert p["backend"] == "local-rf2"
    assert p["models"] == {"0": "fake/extractor", "2": "fake/extractor",
                           "4": "fake/judge"}
    assert "live_single_document" in res["caveats"]
    assert "judge_2b" in res["caveats"], "rung 4 ran: its caveat attaches"
    assert "rung3_samples" not in res["caveats"], "rung 3 was disabled"
    assert "minutes_declared" in res["caveats"]


# --- refusals ----------------------------------------------------------------


def test_refuses_empty_text_and_ambiguous_input(runner):
    with pytest.raises(LiveError) as e:
        runner.start(text="   ", through_rung=1)
    assert e.value.status == 400
    with pytest.raises(LiveError) as e:
        runner.start(text=TEXT, doc_id="LIVE.1", through_rung=1)
    assert e.value.status == 400
    with pytest.raises(LiveError) as e:
        runner.start(through_rung=1)
    assert e.value.status == 400


def test_refuses_the_spent_test_split(runner):
    """C2: no launcher can target the test split — a live look at a held-out
    document is still a look."""
    with pytest.raises(LiveError) as e:
        runner.start(doc_id="TST.1", through_rung=1)
    assert e.value.status == 403 and "spent" in e.value.detail


def test_refuses_an_unknown_document_and_an_unknown_rung(runner):
    with pytest.raises(LiveError) as e:
        runner.start(doc_id="NOPE.1", through_rung=1)
    assert e.value.status == 404
    with pytest.raises(LiveError) as e:
        runner.start(text=TEXT, through_rung=9)
    assert e.value.status == 400


def test_one_live_run_at_a_time(state, fake_models):
    r = LiveRunner(state, background=False)
    r._busy.acquire()
    try:
        with pytest.raises(LiveError) as e:
            r.start(text=TEXT, through_rung=1)
        assert e.value.status == 409
    finally:
        r._busy.release()


def test_a_run_that_dies_reports_the_error_not_a_hang(state, monkeypatch, fake_models):
    from ladder import llm

    def boom(*a, **k):
        raise SystemExit("[run] refusing to start — model missing")

    monkeypatch.setattr(llm, "check_models", boom)
    job = LiveRunner(state, background=False).start(text=TEXT, through_rung=1)
    assert job.status == "error" and "model missing" in job.error
    assert not Path(job.scratch_dir).exists()


# --- the routes --------------------------------------------------------------


def test_live_routes_start_and_report_a_job(client):
    r = client.post("/api/live/run", json={"text": TEXT, "through_rung": 2})
    assert r.status_code == 200, r.text
    job_id = r.json()["job_id"]
    s = client.get("/api/live/job", params={"id": job_id}).json()
    assert s["status"] == "done"
    assert s["result"]["order_run"] == [0, 1, 2]
    assert s["result"]["provenance"]["live"] is True


def test_live_route_refusals_surface_verbatim(client):
    assert client.post("/api/live/run", json={"text": "", "through_rung": 1}).status_code == 400
    r = client.post("/api/live/run", json={"doc_id": "TST.1", "through_rung": 1})
    assert r.status_code == 403 and "spent" in r.json()["detail"]
    assert client.get("/api/live/job", params={"id": "nope"}).status_code == 404


def test_live_options_describe_the_dials_from_the_manifest(client):
    o = client.get("/api/live/options").json()
    assert o["rung_order"] == [0, 1, 2, 3, 4, 5, 6]
    assert o["models"] == {"extractor": "fake/extractor", "judge": "fake/judge"}
    assert o["splits_offered"] == ["dev", "pool"], "test is spent (C2)"
    assert o["rungs"]["3"]["enabled"] is False
    assert o["rungs"]["6"]["mode"] == "simulated"
    assert o["corpus_available"] is True


def test_live_run_is_never_exportable(client):
    assert client.get("/api/export/live", params={"id": "x"}).status_code == 404


def test_background_mode_reports_running_then_done(state, fake_models):
    runner = LiveRunner(state, background=True)
    job = runner.start(text=TEXT, through_rung=1)
    deadline = time.time() + 20
    while job.status == "running" and time.time() < deadline:
        time.sleep(0.05)
    assert job.status == "done", job.error
    assert job.result["order_run"] == [0, 1]

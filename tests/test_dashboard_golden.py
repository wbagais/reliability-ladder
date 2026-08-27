"""Golden test — the app's rendering of phaseF-test-1 pinned to the recorded
values (docs/decisions.md 2026-08-26, spec R3 criteria).

Needs the licensed corpus, the SNOMED index and the archived baselines, so it
skips cleanly where any is absent (CI has no data) — same pattern as the
integration tests.
"""
from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip(
    "fastapi", reason="dashboard extras not installed (CI runs without them)")
from fastapi.testclient import TestClient  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
RUN = "phaseF-test-1"


def _state():
    from dashboard.state import AppState

    return AppState(repo_root=REPO)


def _ready() -> str | None:
    state = _state()
    try:
        info = state.get_run(RUN)
    except KeyError:
        return "archived phaseF-test-1 not found"
    if not info.files.get("records"):
        return "phaseF-test-1.records.jsonl missing"
    if state.corpus() is None:
        return "licensed corpus absent"
    if state.registry() is None:
        return "SNOMED index absent"
    return None


pytestmark = pytest.mark.skipif(_ready() is not None, reason=str(_ready()))


@pytest.fixture(scope="module")
def client() -> TestClient:
    from dashboard.app import create_app

    return TestClient(create_app(_state()))


def test_runs_list_names_the_archived_test_run(client):
    runs = {r["key"]: r for r in client.get("/api/runs").json()["runs"]}
    assert RUN in runs
    assert runs[RUN]["archived"] is True
    assert runs[RUN]["split"] == "test"


def test_golden_shipped_score_exact(client):
    body = client.get("/api/run/score",
                      params={"run": RUN, "span_match": "exact"}).json()
    s, ci = body["score"], body["ci"]
    assert round(s["f1"], 3) == 0.204
    assert round(ci["f1"]["lo"], 3) == 0.150
    assert round(ci["f1"]["hi"], 3) == 0.260
    # five outcomes, report order, exact: 60 / 0 / 91 / 2 / 0
    assert s["correct"] == 60
    assert s["outdated"] == 0
    assert s["abstained"] == 91
    assert s["incorrect"] == 2
    assert s["modernised"] == 0
    prov = body["provenance"]
    assert prov["run_id"] == RUN
    assert prov["split"] == "test"
    assert prov["span_match"] == "exact"
    assert prov["backend"] == "local-rf2"
    assert prov["manifest_hash"] not in ("absent", "")
    assert "spent_test" in body["caveats"]
    assert "outdated_separate" in body["caveats"]


def test_golden_shipped_score_overlap(client):
    body = client.get("/api/run/score",
                      params={"run": RUN, "span_match": "overlap"}).json()
    assert round(body["score"]["f1"], 3) == 0.215


def test_golden_reviews_per_100_from_results_csv(client):
    body = client.get("/api/run/results", params={"run": RUN}).json()
    r6 = next(r for r in body["rows"] if r["rung"] == "6")
    assert r6["reviews_per_100"] == 77.07
    assert "minutes_declared" in body["caveats"]
    assert "rung3_samples" in body["caveats"]
    assert "judge_2b" in body["caveats"]


def test_golden_ledger_denominators_and_failure_labels(client):
    body = client.get("/api/run/costs", params={"run": RUN}).json()
    assert body["denominators"]["0"] == {"denominator": "r0_documents", "rows": 60}
    assert body["denominators"]["6"]["denominator"] == "r6_queue"
    # zero timed_out / truncated / json_decode across the run (recorded)
    assert body["failure_labels"] == {}
    assert body["panels"]["reviews"]["6"]["routed"] == 242


def test_golden_dependencies(client):
    body = client.get("/api/run/dependencies", params={"run": RUN}).json()
    assert body["run_kind"] == "stack"
    nodes = {n["rung"]: n for n in body["nodes"]}
    assert nodes[1]["mode"] == "observe"
    # 16 REJECT, all schema_invalid — none statable, so 0 correctable, 0 attempts
    assert nodes[2]["eligible"] == {"reject": 16, "correctable": 0, "attempted": 0}
    assert nodes[5]["abstained"] == 242
    assert nodes[6]["queue"] == 242
    dens = {d["rung"]: d for d in body["denominators"]}
    assert dens[6]["source_rung"] == 5


def test_golden_flow_counts(client):
    body = client.get("/api/run/flow",
                      params={"run": RUN, "span_match": "exact"}).json()
    assert body["shipped"]["n"] == 72
    assert body["escalated"]["n"] == 242
    assert body["escalated"]["unlocatable"] == 16
    # the queue's withheld answers were already exact-correct 45x (recorded)
    assert body["escalated"]["withheld_correct"] == 45
    assert body["shipped"]["correct"] == 60

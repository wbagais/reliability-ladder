"""Dashboard M1 app — the read-only API behind tabs R1/R3/R4/R5.

Constraint tests (spec.md: violating any is a bug by definition):
  C1 loopback-only + export scrubbing; C2 read-only (no run invocation);
  C3 provenance on every number-carrying payload; C4 caveats auto-attached;
  C5 three cost measures, never fused.

All corpus text here is SYNTHETIC (C1 applies to fixtures).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip(
    "fastapi", reason="dashboard extras not installed (CI runs without them)")
from fastapi.testclient import TestClient  # noqa: E402

from ladder.corpus import Document, GoldMention
from ladder.schema import REACTION

from dashboard.app import create_app
from dashboard.state import AppState
from test_dashboard_core import SYN_TEXT, make_run

SYN2_TEXT = "some fake twinge words padded out to look like a post body here."


def syn_corpus() -> dict[str, Document]:
    m1 = GoldMention(doc_id="SYN.1", index=0, entity_type=REACTION,
                     cadec_type="ADR", text="pretend ache", spans=[(32, 44)],
                     sct=["1111111111"], gold_kind="single")
    m2 = GoldMention(doc_id="SYN.2", index=0, entity_type=REACTION,
                     cadec_type="ADR", text="fake twinge", spans=[(5, 11), (20, 27)],
                     sct=["2222222222"], gold_kind="single")
    m3 = GoldMention(doc_id="SYN.2", index=1, entity_type=REACTION,
                     cadec_type="Finding", text="look", spans=[(40, 44)],
                     sct=[], gold_kind="concept_less")
    return {
        "SYN.1": Document("SYN.1", "ARTHROTEC", SYN_TEXT, [m1]),
        "SYN.2": Document("SYN.2", "LIPITOR", SYN2_TEXT, [m2, m3]),
        "SYN.3": Document("SYN.3", "LIPITOR", "third synthetic body.", []),
    }


@pytest.fixture()
def client(tmp_path) -> TestClient:
    make_run(tmp_path / "out")
    make_run(tmp_path / "archive" / "old-branch", run_id="base-run")
    state = AppState(
        repo_root=tmp_path,
        sources=[(tmp_path / "out", False), (tmp_path / "archive", True)],
        corpus=syn_corpus(),
        splits={"dev": ["SYN.1", "SYN.2", "SYN.3"], "test": ["TST.1"], "pool": []},
        exclusion_rows=[{"record_id": "SYN.9#9", "doc_id": "SYN.9",
                         "reason": "retired_code", "detail": "42"}],
        registry=None,
        manifest={"corpus": {"n_mentions_total": 9111},
                  "vocabulary": {"snomed_backend": "local-rf2"}},
    )
    return TestClient(create_app(state))


# --- C2: read-only, no run invocation ---------------------------------------


#: The one non-GET route: the live run (2026-09-09). It spends model calls
#: and writes to a scratch directory that is deleted, never to out/ — see
#: tests/test_dashboard_live.py for what it may and may not do.
NON_GET_ALLOWED = {"/api/live/run"}


def test_every_route_is_get_only(client):
    for route in client.app.routes:
        methods = getattr(route, "methods", None)
        if methods and route.path not in NON_GET_ALLOWED:
            assert methods <= {"GET", "HEAD"}, f"{route.path} allows {methods}"
    posts = {r.path for r in client.app.routes
             if "POST" in (getattr(r, "methods", None) or set())}
    assert posts == NON_GET_ALLOWED


def test_no_dashboard_module_can_launch_anything():
    pkg = Path(__file__).resolve().parent.parent / "dashboard"
    for py in pkg.rglob("*.py"):
        src = py.read_text(encoding="utf-8")
        for needle in ("subprocess", "os.system", "Popen", "os.exec"):
            assert needle not in src, f"{py.name} contains {needle} (C2: M1 launches nothing)"


# --- C1: loopback only -------------------------------------------------------


def test_serve_refuses_non_loopback_host():
    from dashboard.__main__ import validate_host
    assert validate_host("127.0.0.1") == "127.0.0.1"
    for bad in ("0.0.0.0", "192.168.1.5", "example.com", ""):
        with pytest.raises(SystemExit):
            validate_host(bad)


# --- runs list ---------------------------------------------------------------


def test_runs_list_includes_local_and_archived(client):
    body = client.get("/api/runs").json()
    keys = {r["key"] for r in body["runs"]}
    assert {"syn-run-1", "base-run"} <= keys
    by_key = {r["key"]: r for r in body["runs"]}
    assert by_key["base-run"]["archived"] is True
    assert by_key["syn-run-1"]["archived"] is False
    assert by_key["syn-run-1"]["split"] == "dev"


# --- R3 results + C3/C4/C5 ---------------------------------------------------


def test_results_payload_carries_provenance_and_caveats(client):
    body = client.get("/api/run/results", params={"run": "syn-run-1"}).json()
    prov = body["provenance"]
    assert prov["run_id"] == "syn-run-1"
    assert prov["split"] == "dev"
    assert prov["backend"] == "local-rf2"
    assert "rung3_samples" in body["caveats"]
    assert "judge_2b" in body["caveats"]
    assert "minutes_declared" in body["caveats"]
    # absent CSV cells are null non-values, never zero (visual law)
    r0 = next(r for r in body["rows"] if r["rung"] == "0")
    assert r0["r1_reject_pct"] is None
    assert r0["ci_low"] is None


def test_cost_panels_are_three_separate_axes_never_fused(client):
    body = client.get("/api/run/costs", params={"run": "syn-run-1"}).json()
    panels = body["panels"]
    assert set(panels) == {"tokens", "latency", "reviews"}
    assert "usd" in body  # carried alongside, never summed in
    dumped = json.dumps(body)
    for fused in ("total_cost", "cost_usd_total", "combined"):
        assert fused not in dumped
    # denominators come from the ledger's own naming
    assert body["denominators"]["0"]["denominator"] == "r0_documents"
    assert body["denominators"]["6"]["denominator"] == "r6_queue"


def test_disabled_rung_renders_as_non_value_not_zero(tmp_path):
    make_run(tmp_path / "out", run_id="r3off", rung3_disabled=True)
    state = AppState(repo_root=tmp_path, sources=[(tmp_path / "out", False)],
                     corpus=syn_corpus(),
                     splits={"dev": ["SYN.1", "SYN.2"]}, exclusion_rows=[],
                     registry=None, manifest={})
    c = TestClient(create_app(state))
    body = c.get("/api/run/costs", params={"run": "r3off"}).json()
    nv = {n["rung"]: n for n in body["non_values"]}
    assert 3 in nv and nv[3]["reason"] == "manifest.rungs.3.enabled=false"


def test_score_comes_only_from_ladder_score(client):
    body = client.get("/api/run/score",
                      params={"run": "syn-run-1", "span_match": "exact"}).json()
    from ladder.clean import load_exclusions  # noqa: F401 (documenting path)
    from ladder.corpus import gold_records
    from ladder.score import bootstrap_ci, score_run
    from ladder.run import read_predictions

    run_dir = None
    for r in client.get("/api/runs").json()["runs"]:
        if r["key"] == "syn-run-1":
            run_dir = Path(r["dir"])
    records = read_predictions(run_dir / "syn-run-1.records.jsonl",
                               {"SYN.1", "SYN.2", "SYN.3"})
    golds = gold_records(syn_corpus(), ["SYN.1", "SYN.2"])
    expected = score_run(records, golds, span_match="exact", exclude=set())
    assert body["score"]["f1"] == expected["f1"]
    assert body["score"]["detection"]["f1"] == expected["detection"]["f1"]
    for o in ("correct", "outdated", "abstained", "incorrect", "modernised"):
        assert body["score"][o] == expected[o]
    ci = bootstrap_ci(records, golds, span_match="exact", exclude=set())
    assert body["ci"]["f1"] == ci["f1"]
    assert "outdated_separate" in body["caveats"]
    assert body["provenance"]["span_match"] == "exact"


def test_compare_refuses_mismatched_splits(tmp_path):
    make_run(tmp_path / "out", run_id="dev-run")
    make_run(tmp_path / "out", run_id="other-run", doc_ids=("TST.1", "TST.2"))
    state = AppState(repo_root=tmp_path, sources=[(tmp_path / "out", False)],
                     corpus=syn_corpus(),
                     splits={"dev": ["SYN.1", "SYN.2"], "test": ["TST.1", "TST.2"]},
                     exclusion_rows=[], registry=None, manifest={})
    c = TestClient(create_app(state))
    r = c.get("/api/run/compare", params={"a": "dev-run", "b": "other-run",
                                          "span_match": "exact"})
    assert r.status_code == 409
    assert "split" in r.json()["detail"]


# --- the third result layer: rung 1's label check ----------------------------


def test_score_payload_carries_label_check_counts_from_recorded_checks(client):
    body = client.get("/api/run/score",
                      params={"run": "syn-run-1", "span_match": "exact"}).json()
    lc = body["label_check"]
    # fixture: SYN.1#0 has label_verified true; the other two records carry
    # no label_verified check (no code, or no label) -> unchecked
    assert lc == {"verified": 1, "flagged": 0, "unchecked": 2}


# --- rung dependencies (Results tab: how the rungs connect) ------------------


def test_verdict_flow_crosstab_computed_from_records(client):
    body = client.get("/api/run/dependencies", params={"run": "syn-run-1"}).json()
    vf = body["verdict_flow"]
    b = {x["verdict"]: x for x in vf["buckets"]}
    # fixture: ACCEPT record settled; BAND and REJECT records escalated
    assert b["ACCEPT"]["n"] == 1 and b["ACCEPT"]["settled"] == 1
    assert b["ACCEPT"]["abstained"] == 0
    assert b["BAND"]["n"] == 1 and b["BAND"]["abstained"] == 1
    assert b["BAND"]["queued"] == 1
    assert b["REJECT"]["n"] == 1 and b["REJECT"]["abstained"] == 1
    # r4 interaction per bucket, from recorded checks (absent = never judged)
    assert b["ACCEPT"]["r4"]["absent"] == 1
    assert vf["total"] == 3
    assert vf["mode"] == "observe"


def test_verdict_flow_gate_mode_is_flagged(tmp_path):
    make_run(tmp_path / "out", run_id="gated", r1_mode="gate")
    state = AppState(repo_root=tmp_path, sources=[(tmp_path / "out", False)],
                     corpus=syn_corpus(), splits={"dev": ["SYN.1", "SYN.2"]},
                     exclusion_rows=[], registry=None, manifest={})
    c = TestClient(create_app(state))
    vf = c.get("/api/run/dependencies", params={"run": "gated"}).json()["verdict_flow"]
    assert vf["mode"] == "gate"


def test_score_payload_carries_per_layer_composition(client):
    body = client.get("/api/run/score",
                      params={"run": "syn-run-1", "span_match": "exact"}).json()
    comp = body["composition"]
    s = body["score"]
    # detection layer vocabulary: matched / missed (FN) / spurious (FP)
    m = s["detection"]["n_matched"]
    assert comp["detection"] == {"matched": m,
                                 "missed": s["n_gold"] - m,
                                 "spurious": s["n_pred"] - m}
    # coding layer: the five outcomes of PAIRED predictions, report order
    assert list(comp["coding"]) == ["correct", "outdated", "abstained",
                                    "incorrect", "modernised"]
    assert comp["coding"]["correct"] == s["correct"]
    # label layer: rung 1's label_check vocabulary
    assert comp["label"] == body["label_check"]


def test_records_filter_by_verdict_and_disposition(client):
    # the diagram's subsets drill through to Traceability: a ribbon is a
    # (r1 verdict, disposition) subset of records
    r = client.get("/api/run/records", params={
        "run": "syn-run-1", "verdict": "BAND", "disposition": "escalated"}).json()
    assert [x["record_id"] for x in r["records"]] == ["SYN.2#0"]
    r = client.get("/api/run/records", params={
        "run": "syn-run-1", "verdict": "ACCEPT"}).json()
    assert [x["record_id"] for x in r["records"]] == ["SYN.1#0"]
    r = client.get("/api/run/records", params={
        "run": "syn-run-1", "disposition": "shipped"}).json()
    assert [x["record_id"] for x in r["records"]] == ["SYN.1#0"]


def test_flow_map_actuals_and_possible_paths_observe(client):
    body = client.get("/api/run/dependencies", params={"run": "syn-run-1"}).json()
    fm = body["flow_map"]
    assert fm["mode"] == "observe"
    b = {x["verdict"]: x for x in fm["buckets"]}
    # r2 only ever touches REJECT — the bypass is structural, not styling
    assert b["ACCEPT"]["through_r2"] is False
    assert b["BAND"]["through_r2"] is False
    assert b["REJECT"]["through_r2"] is True
    # actual paths carry their counts; untaken-but-possible paths are kind
    # "possible" with n 0 — the reader sees what CAN happen vs what DID
    assert b["ACCEPT"]["shipped"] == {"n": 1, "kind": "actual"}
    assert b["ACCEPT"]["person"]["n"] == 0
    assert b["ACCEPT"]["person"]["kind"] == "possible"
    assert b["BAND"]["shipped"]["kind"] == "possible"
    assert b["BAND"]["person"] == {"n": 1, "kind": "actual"}
    # the rescue path exists as an option even when this run never took it
    assert b["REJECT"]["r2"]["rescue"]["kind"] == "possible"
    assert b["REJECT"]["r2"]["rescue"]["n"] == 0
    # abstain_on_reject defaults true: a REJECT structurally cannot ship
    assert "shipped" not in b["REJECT"]
    # observe mode: no gate exit anywhere
    assert all("exit_at_r1" not in x for x in fm["buckets"])


def test_flow_map_gate_mode_reject_exits_at_r1(tmp_path):
    make_run(tmp_path / "out", run_id="gated", r1_mode="gate")
    state = AppState(repo_root=tmp_path, sources=[(tmp_path / "out", False)],
                     corpus=syn_corpus(), splits={"dev": ["SYN.1", "SYN.2"]},
                     exclusion_rows=[], registry=None, manifest={})
    c = TestClient(create_app(state))
    fm = c.get("/api/run/dependencies", params={"run": "gated"}).json()["flow_map"]
    assert fm["mode"] == "gate"
    b = {x["verdict"]: x for x in fm["buckets"]}
    # gate mode: the REJECT ribbon leaves the stack at rung 1 — an ACTUAL
    # path in this run, and one that observe runs must not render at all.
    # n follows the RECORDS' checks (one REJECT record), not the ledger's
    # row count — ribbons are records.
    assert b["REJECT"]["exit_at_r1"] == {"n": 1, "kind": "actual"}
    assert "person" not in b["REJECT"]  # routed out, not queued


def test_dependency_nodes_carry_a_meaning_sentence(client):
    body = client.get("/api/run/dependencies", params={"run": "syn-run-1"}).json()
    nodes = {n["rung"]: n for n in body["nodes"]}
    for rung in range(7):
        assert len(nodes[rung].get("meaning", "")) > 20, f"rung {rung} has no meaning"
    # the epistemics the cards must state
    assert "never" in nodes[1]["meaning"]        # can prove wrong, never right
    assert "refus" in nodes[5]["meaning"].lower()  # refuses rather than answers


def test_dependencies_computed_from_the_runs_own_artifacts(client):
    body = client.get("/api/run/dependencies", params={"run": "syn-run-1"}).json()
    assert body["rung_order"] == [0, 1, 2, 3, 4, 5, 6]  # from the manifest copy
    assert body["run_kind"] == "stack"
    nodes = {n["rung"]: n for n in body["nodes"]}
    # r1 mode comes from the ledger's own recorded mode, never assumed
    assert nodes[1]["mode"] == "observe"
    assert nodes[1]["routes"] is False
    # r2's trigger annotated with THIS run's counts: 2 REJECT, 1 correctable
    assert nodes[2]["eligible"] == {"reject": 2, "correctable": 1, "attempted": 0}
    # r6's queue is r5's abstained residue, sized from the ledger
    assert nodes[6]["queue"] == 1
    assert nodes[5]["abstained"] is not None
    # verdict edges into r5 from both judging rungs; queue edge 5 -> 6
    kinds = {(e["src"], e["dst"]): e["kind"] for e in body["edges"]}
    assert kinds[(1, 5)] == "verdict"
    assert kinds[(4, 5)] == "verdict"
    assert kinds[(5, 6)] == "queue"
    assert kinds[(0, 1)] == "records"
    assert "provenance" in body


def test_dependencies_gate_mode_rewires_and_disabled_rung_is_stated(tmp_path):
    make_run(tmp_path / "out", run_id="gated", rung3_disabled=True,
             r1_mode="gate")
    state = AppState(repo_root=tmp_path, sources=[(tmp_path / "out", False)],
                     corpus=syn_corpus(), splits={"dev": ["SYN.1", "SYN.2"]},
                     exclusion_rows=[], registry=None, manifest={})
    c = TestClient(create_app(state))
    body = c.get("/api/run/dependencies", params={"run": "gated"}).json()
    nodes = {n["rung"]: n for n in body["nodes"]}
    assert nodes[1]["mode"] == "gate"
    assert nodes[1]["routes"] is True  # rendered differently: r1 ROUTES
    assert nodes[3]["disabled"] is True  # recorded state, never a silent skip
    assert "gate" in body["caveats"] or any(
        "confound" in t for t in body["caveats"].values())


def test_ablate_run_is_detected_and_labeled(tmp_path):
    d = make_run(tmp_path / "out", run_id="abl")
    # an ablate ledger carries only the rung it ran (Phase E's r6 ledgers)
    import json as _json
    rows = [_json.loads(l) for l in
            (d / "abl.ledger.jsonl").read_text().splitlines()]
    keep = [r for r in rows if r["rung"] == 6]
    (d / "abl.ledger.jsonl").write_text(
        "\n".join(_json.dumps(r) for r in keep) + "\n")
    state = AppState(repo_root=tmp_path, sources=[(tmp_path / "out", False)],
                     corpus=syn_corpus(), splits={"dev": ["SYN.1", "SYN.2"]},
                     exclusion_rows=[], registry=None, manifest={})
    c = TestClient(create_app(state))
    body = c.get("/api/run/dependencies", params={"run": "abl"}).json()
    assert body["run_kind"] == "ablate"
    assert body["rungs_present"] == [6]


def test_denominator_sources_name_the_feeding_rung(client):
    body = client.get("/api/run/dependencies", params={"run": "syn-run-1"}).json()
    dens = {d["rung"]: d for d in body["denominators"]}
    assert dens[6]["denominator"] == "r6_queue"
    assert dens[6]["source_rung"] == 5
    assert "abstained" in dens[6]["source_label"]
    assert dens[1]["source_rung"] == 0


# --- R4 walkthrough + span-key identity --------------------------------------


def test_record_detail_found_by_span_key_in_any_segment_order(client):
    r = client.get("/api/run/record", params={
        "run": "syn-run-1", "doc_id": "SYN.2", "spans": "20:27,5:11"}).json()
    assert r["record"]["record_id"] == "SYN.2#0"
    assert r["record"]["checks"]["withheld"]["sct"] == "2222222222"
    assert any(row["rung"] == 6 for row in r["ledger_rows"])
    assert "provenance" in r


def test_unlocatable_record_renders_explicit_state(client):
    r = client.get("/api/run/record", params={
        "run": "syn-run-1", "doc_id": "SYN.2", "spans": "-1:-1"}).json()
    assert r["record"]["unlocatable"] is True


def test_walkthrough_timeline_has_a_node_per_rung_with_stated_nothing(client):
    body = client.get("/api/run/walkthrough",
                      params={"run": "syn-run-1", "doc_id": "SYN.2"}).json()
    rec = next(r for r in body["records"] if r["record_id"] == "SYN.2#0")
    rungs = [n["rung"] for n in rec["timeline"]]
    assert rungs == [0, 1, 2, 3, 4, 5, 6]
    r2 = next(n for n in rec["timeline"] if n["rung"] == 2)
    assert r2["state"] == "did_not_fire"  # stated, not omitted
    assert "provenance" in body


# --- R5 traceability ---------------------------------------------------------


def test_aggregate_drills_to_records_by_outcome(client):
    body = client.get("/api/run/records", params={
        "run": "syn-run-1", "outcome": "abstained", "span_match": "exact"}).json()
    ids = {r["record_id"] for r in body["records"]}
    assert "SYN.2#0" in ids
    assert "provenance" in body


def test_llm_view_reports_not_retained_instead_of_empty(client):
    r = client.get("/api/run/record_llm", params={
        "run": "syn-run-1", "doc_id": "SYN.1", "spans": "32:44"}).json()
    assert r["local_only"] is True
    assert all(c["status"] == "not_retained" for c in r["calls"]) or r["calls"] == []


# --- C3: every number-carrying payload carries provenance --------------------


def test_every_numbered_endpoint_carries_provenance(client):
    numbered = [
        ("/api/run/results", {"run": "syn-run-1"}),
        ("/api/run/costs", {"run": "syn-run-1"}),
        ("/api/run/score", {"run": "syn-run-1", "span_match": "exact"}),
        ("/api/run/flow", {"run": "syn-run-1"}),
        ("/api/run/records", {"run": "syn-run-1"}),
        ("/api/run/walkthrough", {"run": "syn-run-1", "doc_id": "SYN.2"}),
        ("/api/run/record", {"run": "syn-run-1", "doc_id": "SYN.1", "spans": "32:44"}),
        ("/api/corpus/stats", {}),
        ("/api/corpus/zones", {}),
    ]
    for path, params in numbered:
        body = client.get(path, params=params).json()
        assert "provenance" in body, f"{path} carries numbers without provenance"


# --- R1 corpus views ---------------------------------------------------------


def test_corpus_stats_computed_and_mismatch_warns(client):
    body = client.get("/api/corpus/stats").json()
    assert body["n_mentions"] == 3  # computed from data, not hard-coded
    assert any("9111" in w or "9,111" in w for w in body["warnings"])
    assert body["discontinuous"]["reaction_mentions"] == 1


def test_test_split_shows_spent_banner_and_dev_default_does_not(client):
    dev = client.get("/api/corpus/docs").json()
    assert dev["spent_split"] is False
    assert {d["doc_id"] for d in dev["docs"]} == {"SYN.1", "SYN.2", "SYN.3"}
    t = client.get("/api/corpus/docs", params={"split": "test"}).json()
    assert t["spent_split"] is True


def test_excluded_mentions_render_as_excluded_not_errors(client):
    body = client.get("/api/corpus/exclusions").json()
    assert body["rows"][0]["reason"] == "retired_code"
    assert body["rows"][0]["record_id"] == "SYN.9#9"


def test_document_view_marks_gold_spans_and_discontinuous(client):
    body = client.get("/api/corpus/doc", params={"doc_id": "SYN.2"}).json()
    assert body["text"] == SYN2_TEXT  # loopback-only view, not an export
    m = body["mentions"][0]
    assert m["spans"] == [[5, 11], [20, 27]]
    assert m["discontinuous"] is True


class StubRegistry:
    """label() like ladder.registry.Registry — the only lookup path used."""

    LABELS = {"1111111111": "pretend ache (finding)"}

    def exists(self, code):
        return code in self.LABELS or code == "2222222222"

    def label(self, code):
        return self.LABELS.get(code)


def _doc_client(tmp_path, registry):
    state = AppState(repo_root=tmp_path, sources=[],
                     corpus=syn_corpus(),
                     splits={"dev": ["SYN.1", "SYN.2", "SYN.3"]},
                     exclusion_rows=[], registry=registry, manifest={})
    return TestClient(create_app(state))


def test_document_mentions_carry_codes_with_vocabulary_labels(tmp_path):
    c = _doc_client(tmp_path, StubRegistry())
    body = c.get("/api/corpus/doc", params={"doc_id": "SYN.1"}).json()
    assert body["registry_available"] is True
    [m] = body["mentions"]
    # never a bare SCTID alone when the registry can label it
    assert m["codes"] == [{"code": "1111111111",
                           "label": "pretend ache (finding)",
                           "in_vocabulary": True}]
    # a code the registry holds but cannot label states that, not nothing
    m2 = c.get("/api/corpus/doc", params={"doc_id": "SYN.2"}).json()["mentions"][0]
    assert m2["codes"] == [{"code": "2222222222", "label": None,
                            "in_vocabulary": True}]


def test_concept_less_mention_renders_explicitly_not_as_empty(tmp_path):
    c = _doc_client(tmp_path, StubRegistry())
    body = c.get("/api/corpus/doc", params={"doc_id": "SYN.2"}).json()
    cl = next(m for m in body["mentions"] if m["record_id"] == "SYN.2#1")
    assert cl["gold_kind"] == "concept_less"
    assert cl["concept_less"] is True
    assert cl["codes"] == []


def test_document_codes_without_registry_state_the_absence(client):
    # the `client` fixture has registry=None: labels are stated unavailable,
    # never silently blank
    body = client.get("/api/corpus/doc", params={"doc_id": "SYN.1"}).json()
    assert body["registry_available"] is False
    [m] = body["mentions"]
    assert m["codes"] == [{"code": "1111111111", "label": None,
                           "in_vocabulary": None}]


def test_zone_strip_degrades_cleanly_without_registry(client):
    body = client.get("/api/corpus/zones").json()
    assert body["available"] is False
    assert "registry" in body["reason"]


# --- C1: export scrubbing ----------------------------------------------------


def test_exports_contain_no_corpus_text(client):
    svg = client.get("/api/export/figure",
                     params={"run": "syn-run-1", "span_match": "exact"})
    assert svg.status_code == 200
    for needle in (SYN_TEXT, SYN2_TEXT, "pretend ache", "fake twinge"):
        assert needle not in svg.text
    assert "syn-run-1" in svg.text  # provenance burned into the margin
    csv_r = client.get("/api/export/results", params={"run": "syn-run-1"})
    for needle in (SYN_TEXT, SYN2_TEXT):
        assert needle not in csv_r.text


def test_export_records_are_scrubbed_to_desk_file_fields(client):
    r = client.get("/api/export/records",
                   params={"run": "syn-run-1", "span_match": "exact"})
    body = r.json()
    dumped = json.dumps(body)
    for needle in (SYN_TEXT, SYN2_TEXT, "pretend ache", "fake twinge", "\"text\""):
        assert needle not in dumped
    assert "provenance" in body


def test_llm_view_is_not_exportable(client):
    r = client.get("/api/export/record_llm",
                   params={"run": "syn-run-1", "doc_id": "SYN.1", "spans": "32:44"})
    assert r.status_code == 404


# --- 2026-09-09 refresh: traced calls beat reconstruction --------------------


def _write_calls(dir: Path, run_id: str, rung: int, rows: list[dict]) -> None:
    (dir / f"{run_id}.r{rung}.calls.jsonl").write_text(
        "\n".join(json.dumps(r) for r in rows) + "\n")


def test_llm_view_serves_traced_calls_when_the_run_wrote_them(client, tmp_path):
    """A run since 2026-09-03 leaves <run>.r<N>.calls.jsonl with the FULL
    prompt and raw reply of every call. When it exists the view reads it —
    the request-hash reconstruction is the fallback for older runs only."""
    out = tmp_path / "out"
    _write_calls(out, "syn-run-1", 0, [
        {"call_index": 0, "rung": 0, "role": "extractor", "model": "ollama/x",
         "mode": "find", "doc_id": "SYN.1", "prompt": "FIND\n\nPOST:\n" + SYN_TEXT,
         "raw": '{"mentions": []}', "normalised": '{"mentions": []}',
         "cached": False, "tokens_in": 10, "tokens_out": 3, "seconds": 1.5,
         "timed_out": False, "truncated": False, "temperature": 0.0,
         "sample_index": 0},
        {"call_index": 1, "rung": 0, "role": "extractor", "model": "ollama/x",
         "mode": "pick", "doc_id": "SYN.2", "prompt": "other doc",
         "raw": "{}", "normalised": "{}", "cached": True, "tokens_in": 1,
         "tokens_out": 1, "seconds": 0.0, "timed_out": False,
         "truncated": False, "temperature": 0.0, "sample_index": 0},
    ])
    _write_calls(out, "syn-run-1", 4, [
        {"call_index": 0, "rung": 4, "role": "judge", "model": "ollama/j",
         "mode": "judge", "doc_id": "SYN.1",
         "prompt": "JUDGE 1111111111 pretend ache", "raw": '{"span_ok": true}',
         "normalised": '{"span_ok": true}', "cached": False, "tokens_in": 5,
         "tokens_out": 2, "seconds": 0.2, "timed_out": False,
         "truncated": False, "temperature": 0.0, "sample_index": 0},
    ])
    r = client.get("/api/run/record_llm", params={
        "run": "syn-run-1", "doc_id": "SYN.1", "spans": "32:44"}).json()
    assert r["local_only"] is True
    assert r["source"] == "call_trace"
    assert [(c["rung"], c["status"]) for c in r["calls"]] == \
        [(0, "traced"), (4, "traced")]
    c0 = r["calls"][0]
    assert c0["prompt"].endswith(SYN_TEXT) and c0["reply"] == '{"mentions": []}'
    assert c0["cached"] is False and c0["prompt_tokens"] == 10
    assert c0["call"] == "find"
    assert "other doc" not in json.dumps(r), "another document's call leaked in"


def test_llm_view_falls_back_to_reconstruction_without_call_traces(client):
    r = client.get("/api/run/record_llm", params={
        "run": "syn-run-1", "doc_id": "SYN.1", "spans": "32:44"}).json()
    assert r["source"] == "reconstruction"


# --- Data tab (2026-09-09, sketch section 3): the "in run" column ----------


def test_docs_list_carries_how_the_selected_run_did_on_each_document(client):
    """One column per document: the run's final zones on it and the pairing
    against its gold — exact, overlap, missed, model-only — through the
    scorer's own pairing (dashboard.live.gold_diff), so the table is also
    a way into the results ("most missed" sorts to the interesting ones)."""
    body = client.get("/api/corpus/docs", params={"split": "dev", "run": "syn-run-1"}).json()
    by = {d["doc_id"]: d for d in body["docs"]}
    assert by["SYN.1"]["in_run"] == {"zones": {"VERIFIED": 1}, "exact": 1,
                                     "overlap": 0, "missed": 0, "model_only": 0,
                                     "gold": 1, "records": 1}
    assert by["SYN.2"]["in_run"] == {"zones": {"ESCALATE": 2}, "exact": 1,
                                     "overlap": 0, "missed": 1, "model_only": 1,
                                     "gold": 2, "records": 2}
    assert by["SYN.3"]["in_run"] == {"zones": {}, "exact": 0, "overlap": 0,
                                     "missed": 0, "model_only": 0, "gold": 0,
                                     "records": 0}
    assert body["run"] == "syn-run-1"


def test_docs_list_without_a_run_has_no_in_run_column(client):
    body = client.get("/api/corpus/docs", params={"split": "dev"}).json()
    assert all("in_run" not in d for d in body["docs"]) and body["run"] is None


def test_docs_list_refuses_an_unknown_run(client):
    assert client.get("/api/corpus/docs", params={"split": "dev", "run": "nope"}).status_code == 404


def test_docs_list_says_when_a_run_has_no_records_file(client, tmp_path):
    """The tracked runs/archive copies are corpus-free by design — no
    records file. Their "in run" column must read "records not on this
    machine", never "everything missed"."""
    d = tmp_path / "out"
    (d / "ledger-only.ledger.jsonl").write_text("")
    body = client.get("/api/corpus/docs", params={"split": "dev", "run": "ledger-only"}).json()
    assert body["run"] == "ledger-only" and body["records_available"] is False
    assert all(x["in_run"] is None for x in body["docs"])
    body = client.get("/api/corpus/docs", params={"split": "dev", "run": "syn-run-1"}).json()
    assert body["records_available"] is True


# --- Results drill-down (2026-09-09, sketch section 6): a run's document ----
# through the same grid as Live, from the run's own artifacts.


def test_run_document_renders_a_batch_documents_grid_from_its_artifacts(client):
    r = client.get("/api/run/document", params={"run": "syn-run-1", "doc_id": "SYN.2"})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["source"] == "run" and d["run_id"] == "syn-run-1" and d["doc_id"] == "SYN.2"
    assert d["text"] == SYN2_TEXT
    assert d["order_run"] == [0, 1, 2, 3, 4, 5, 6], "the rungs the ledger says ran, in manifest order"
    assert [x["record_id"] for x in d["records"]] == ["SYN.2#0", "SYN.2#1"]
    rec = d["records"][0]
    assert [x["id"] for x in rec["rules"]] == ["V", "V+", "3", "2", "J", "J+"]
    assert rec["rules"][0]["state"] == "hold" and rec["rules"][0]["value"] == "BAND"
    assert rec["person"]["run"] >= 1
    assert rec["r0_path"]["steps"][0]["id"] == "input"
    # this fixture wrote no state table (pre-2026-09-03 shape): one row, the
    # final state, and the payload says so
    assert d["state_available"] is False
    assert len(rec["timeline"]) == 1 and rec["timeline"][0]["rung"] == 6
    assert d["gold_diff"]["counts"] == {"gold": 2, "found_exact": 1, "found_overlap": 0,
                                        "missed": 1, "spurious": 1, "predictions": 2}
    assert "6" in d["gold_diff_by_rung"]
    # the ledger names the denominator: the fixture wrote one rung-6 row for
    # this document, so one is what a person received, not the two records
    assert d["rungs"]["6"]["cost"]["routed_to_person"] == 1
    assert d["menu_judge"] is None
    assert d["provenance"]["live"] is False and d["provenance"]["run_id"] == "syn-run-1"
    assert d["provenance"]["models"] == {"extractor": "ollama/fake:1b", "judge": "ollama/fake2:1b"}
    assert "results_drilldown" in d["caveats"]
    assert [x["id"] for x in d["rules_legend"]] == ["V", "V+", "3", "2", "J", "J+"]


def test_run_document_refuses_unknown_document_and_run(client):
    assert client.get("/api/run/document", params={"run": "syn-run-1", "doc_id": "NOPE"}).status_code == 404
    assert client.get("/api/run/document", params={"run": "nope", "doc_id": "SYN.2"}).status_code == 404


def test_run_document_is_never_exportable(client):
    assert client.get("/api/export/document", params={"run": "syn-run-1", "doc_id": "SYN.2"}).status_code == 404


# --- the top bar (2026-09-09, sketch section 2): three tabs, the rest "later"


def test_the_tab_bar_is_three_tabs_and_the_placeholders_are_later(client):
    body = client.get("/api/tabs").json()
    shipped = [t for t in body["tabs"] if t["shipped"]]
    later = [t for t in body["tabs"] if not t["shipped"]]
    assert [t["label"] for t in shipped] == ["Data", "Results", "Live"]
    assert [t["id"] for t in shipped] == ["explorer", "results", "live"]
    assert sorted(t["label"] for t in later) == ["Demo", "Desk", "Run monitor", "Rung workbench"]
    assert "walkthrough" not in {t["id"] for t in body["tabs"]}
    assert "trace" not in {t["id"] for t in body["tabs"]}

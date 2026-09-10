"""Results, redesign step 5 (the sketch's section 6): the flow from the
LEDGER so a fresh clone draws it, and the six shipping rules over a whole
batch run — Figure 3 as a table, ending the flow.

The tracked runs/archive copy of the base run is corpus-free by design:
ledger, aggregates, results.csv, manifest — no records file. Every count
here must therefore come from the ledger's one-row-per-record-per-rung.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

pytest.importorskip(
    "fastapi", reason="dashboard extras not installed (CI runs without them)")

from dashboard import dependencies  # noqa: E402
from dashboard.state import AppState  # noqa: E402
from test_dashboard_app import client  # noqa: E402,F401  (fixture)

REPO = Path(__file__).resolve().parent.parent
ARCHIVE = REPO / "runs" / "archive" / "consolidated-2026-09-03"


@pytest.fixture()
def base_run():
    if not (ARCHIVE / "rerun-cadec-d0.ledger.jsonl").exists():
        pytest.skip("tracked consolidated re-run absent")
    state = AppState(repo_root=REPO, sources=[(ARCHIVE, True)],
                     corpus=None, registry=None, splits={}, exclusion_rows=[],
                     manifest={})
    return state, state.get_run("rerun-cadec-d0")


def test_the_crosstab_from_the_ledger_matches_the_one_from_records(base_run):
    """ACCEPT 53 all settled (r4 pass 39 / fail 14); BAND 176 all queued
    (pass 96 / fail 73 / unparsed 7); REJECT 1 queued (pass 1) — the numbers
    the records-derived crosstab gave on the archived copy with records
    (decisions, 2026-08-26 and this session). One rescued record moves from
    REJECT to BAND, as it does on the record."""
    state, info = base_run
    vf = dependencies.verdict_flow_from_ledger(state.ledger_entries(info), "observe")
    by = {b["verdict"]: b for b in vf["buckets"]}
    assert vf["total"] == 230
    assert (by["ACCEPT"]["n"], by["ACCEPT"]["settled"], by["ACCEPT"]["queued"]) == (53, 53, 0)
    assert by["ACCEPT"]["r4"] == {"pass": 39, "fail": 14, "parse_failed": 0, "absent": 0}
    assert (by["BAND"]["n"], by["BAND"]["abstained"], by["BAND"]["queued"]) == (176, 176, 176)
    assert by["BAND"]["r4"] == {"pass": 96, "fail": 73, "parse_failed": 7, "absent": 0}
    assert (by["REJECT"]["n"], by["REJECT"]["queued"]) == (1, 1)
    assert vf["r3_changed_known"] is False, "the ledger does not say which vote changed a code"


def test_dependencies_use_the_ledger_when_the_run_has_no_records(client, tmp_path):
    out = tmp_path / "out"
    shutil.copy(out / "syn-run-1.ledger.jsonl", out / "ledger-only.ledger.jsonl")
    d = client.get("/api/run/dependencies", params={"run": "ledger-only"}).json()
    assert d["flow_source"] == "ledger"
    assert d["verdict_flow"]["total"] > 0
    assert client.get("/api/run/dependencies", params={"run": "syn-run-1"}).json()["flow_source"] == "records"


def test_the_six_rules_over_the_batch_from_the_ledger_alone(base_run):
    """Figure 3 as a table: each verdict read as a shipping rule over the
    230 records. What the ledger cannot answer (the loose vocabulary check,
    unanimity among the votes, the menu-shown judge) reads NOT RUN, never a
    hold."""
    state, info = base_run
    r = dependencies.rules_over_run(state, info)
    assert r["total"] == 230 and r["source"] == "ledger" and r["scorable"] is False
    by = {x["id"]: x for x in r["rules"]}
    assert [x["id"] for x in r["rules"]] == ["V", "V+", "3", "2", "J", "J+"]
    assert (by["V"]["ships"], by["V"]["held"], by["V"]["run"]) == (53, 177, True)
    assert by["V"]["own"] is True, "this run's own rule: rung 5 abstains on BAND and REJECT"
    assert by["V+"]["run"] is False and by["3"]["run"] is False and by["J+"]["run"] is False
    assert (by["2"]["ships"], by["2"]["held"]) == (203, 27)
    assert (by["J"]["ships"], by["J"]["held"]) == (136, 94)
    assert by["V"]["right"] is None, "no records, no corpus: right/wrong unknown"
    lanes = r["lanes_r3"]
    assert lanes["all"] == {"voted": 203, "tie": 15, "no_vote": 12}
    assert sum(lanes["ACCEPT"].values()) == 53 and sum(lanes["BAND"].values()) == 176


def test_the_rules_route_carries_provenance(client):
    d = client.get("/api/run/rules", params={"run": "syn-run-1"}).json()
    assert [x["id"] for x in d["rules"]] == ["V", "V+", "3", "2", "J", "J+"]
    assert d["provenance"]["run_id"] == "syn-run-1"
    assert d["source"] == "records"

"""docs/plan.html carries the measured result, and every number its charts
draw comes from the tracked archive rather than from a literal typed into the
script block.

v18 of the page drove its charts from a hand-typed `const D=[...]` copied from
a run that was later superseded, and its prose still quoted that run months
after the consolidated re-run replaced it. Nothing could say the page and the
archive disagreed. v19 embeds one JSON block, `<script id="plan-data">`, which
the page's JavaScript reads and these tests compare against
`runs/archive/consolidated-2026-09-03/`, `matrix.csv` and the PsyTAR
full-ladder cell — the same "two records of one fact" rule as everything in
docs/three-checks.md.

Stdlib only: CI is python:3.12-slim with requirements.txt and pytest.
"""
from __future__ import annotations

import csv
import json
import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
PAGE = ROOT / "docs" / "plan.html"
ARCHIVE = ROOT / "runs" / "archive" / "consolidated-2026-09-03"
REPORT = ARCHIVE / "rerun" / "cadec.json"
FINER_REPORT = ARCHIVE / "rerun" / "finer.json"
MATRIX = ROOT / "matrix.csv"
PSYTAR = (ROOT / "runs" / "archive" / "matrix-2026-09-07" / "overnight"
          / "full-psytar" / "psytar-gpt-oss_20b-d0")
CI = ROOT / ".gitlab-ci.yml"

_DATA = re.compile(
    r'<script[^>]*id="plan-data"[^>]*type="application/json"[^>]*>(.*?)</script>',
    re.S)
_TAB = re.compile(r'class="tab(?: on)?" data-p="([a-z]+)"')
_REF = re.compile(r'(?:href|src)="([^"]+)"')

RUNG_COLS = ("n_records", "accept", "band", "reject", "abstained", "escalated",
             "verified", "coverage", "f1_sct_strict", "yield", "err_per_100",
             "tokens_per_record", "p95_s", "reviews_per_100")


def _page() -> str:
    return PAGE.read_text()


def _data() -> dict:
    m = _DATA.search(_page())
    assert m, "docs/plan.html has no <script id=\"plan-data\" type=\"application/json\"> block"
    return json.loads(m.group(1))


def _results_csv(path: pathlib.Path) -> list[dict]:
    with path.open() as fh:
        return list(csv.DictReader(fh))


def _num(v: str):
    if v == "":
        return None
    f = float(v)
    return int(f) if f.is_integer() else f


def _same_rows(page_rows: list[dict], csv_rows: list[dict], where: str) -> None:
    assert len(page_rows) == 7, f"{where}: seven rungs, not {len(page_rows)}"
    for page, disk in zip(page_rows, csv_rows):
        assert int(page["rung"]) == int(disk["rung"]), where
        for col in RUNG_COLS:
            want = _num(disk[col])
            got = page[col]
            if want is None:
                assert got is None, (where, page["rung"], col, got)
            else:
                assert got == pytest.approx(want, abs=1e-4), (where, page["rung"], col, got, want)


# ---------------------------------------------------------------- the block

def test_the_page_embeds_one_data_block_and_the_script_reads_it():
    d = _data()
    assert d["version"] == 19
    src = _page()
    assert "plan-data" in src.split("<script>", 1)[1], "the JavaScript never reads the data block"
    assert not re.search(r"const D\s*=\s*\[", src), \
        "the v18 hand-typed rung array is still there; the charts must read plan-data"


def test_the_cadec_rung_table_is_the_first_base_draw_of_the_consolidated_rerun():
    d = _data()["cadec"]
    assert d["run"] == "rerun-cadec-d0"
    _same_rows(d["rungs"], _results_csv(ARCHIVE / "rerun-cadec-d0.results.csv"), "cadec")


def test_the_finer_rung_table_is_the_first_finer_draw():
    d = _data()["finer"]
    assert d["run"] == "rerun-finer-d0"
    _same_rows(d["rungs"], _results_csv(ARCHIVE / "finer" / "rerun-finer-d0.results.csv"), "finer")


def test_the_psytar_full_ladder_is_the_published_cell():
    d = _data()["psytar"]
    files = sorted(PSYTAR.glob("*.results.csv"))
    assert len(files) == 1, files
    _same_rows(d["rungs"], _results_csv(files[0]), "psytar")
    # the finding the row carries: three paid layers, zero records routed
    for r in d["rungs"]:
        if r["rung"] in (2, 3, 4):
            assert r["coverage"] == 1.0 and r["abstained"] == 0 and r["escalated"] == 0


def test_the_lanes_shipping_rules_and_consensus_are_the_tracked_report():
    report = json.loads(REPORT.read_text())
    d = _data()["cadec"]
    for draw, lanes in d["lanes"].items():
        want = report["draws"][draw]["lanes"]
        for lane, row in lanes.items():
            assert row["n"] == want[lane]["n"], (draw, lane)
            assert row["correct_pct"] == pytest.approx(want[lane]["correct_pct"], abs=1e-2), (draw, lane)
    want_rules = report["draws"]["rerun-cadec-d0"]["shipping_rules"]
    assert [r["rule"] for r in d["shipping_rules"]] == [r["rule"] for r in want_rules]
    for got, want in zip(d["shipping_rules"], want_rules):
        for k in ("ships", "correct", "span_only", "code_only", "neither", "to_person",
                  "person_correct", "extra_tokens"):
            assert got[k] == want[k], (got["rule"], k)
        for k in ("accuracy", "yield", "f1"):
            assert got[k] == pytest.approx(want[k], abs=1e-3), (got["rule"], k)
    assert d["consensus"] == {k: report["consensus"][k] for k in d["consensus"]}
    assert d["gold_lanes"]["exact"] == pytest.approx(report["gold_lanes"]["exact"]["pct"]["ACCEPT"], abs=0.05)
    assert d["gold_lanes"]["contained"] == pytest.approx(report["gold_lanes"]["contained"]["pct"]["ACCEPT"], abs=0.05)
    for draw, want in report["draws"].items():
        got = d["rung0"][draw]
        assert got["f1_exact"] == pytest.approx(want["rung0"]["exact"]["f1"], abs=1e-3), draw
        assert got["f1_overlap"] == pytest.approx(want["rung0"]["overlap"]["f1"], abs=1e-3), draw
        assert got["detection_exact"] == pytest.approx(want["rung0"]["exact"]["detection"]["f1"], abs=1e-3), draw
        assert got["coding_exact"] == pytest.approx(want["rung0"]["exact"]["coding"]["accuracy"], abs=1e-3), draw
    b = report["draws"]["rerun-cadec-d0"]["budget"]["exact"]
    assert d["budget"] == {k: b[k] for k in d["budget"]}
    for draw, want in report["draws"].items():
        got = d["judge"][draw]
        assert got["blind"] == pytest.approx(want["r4"]["separation"], abs=1e-2), draw
        assert got["menu"] == pytest.approx(report["arms"]["judgemenu"][draw]["r4"]["separation"], abs=1e-2), draw


def test_the_matrix_is_matrix_csv_cell_for_cell():
    with MATRIX.open() as fh:
        want = list(csv.DictReader(fh))
    got = _data()["matrix"]
    assert len(got) == len(want) == 28
    for g, w in zip(got, want):
        assert (g["corpus"], g["model"], g["retrieval"]) == (w["corpus"], w["model"], w["retrieval"])
        assert g["records"] == int(w["records"]) and g["accept"] == int(w["accept"])
        assert g["occupancy"] == pytest.approx(float(w["occupancy"]), abs=1e-4)
        if w["correctness"] == "":
            assert g["correctness"] is None
        else:
            assert g["correctness"] == pytest.approx(float(w["correctness"]), abs=1e-4)


# ---------------------------------------------------------------- the prose

SUPERSEDED = [
    "196 of 248",       # the pre-re-run test-split routing figure
    "80.4",             # the five-model ACCEPT lane of an earlier sweep
    "89.3",
    "518,042",          # "two paid resolvers cost 518,042 tokens for -0.004"
    "425,355",          # rung 3's tokens on the superseded run
    "0.371",            # answered accuracy of the superseded run
    "0 of 704",         # FiNER ACCEPT on the pre-re-run arm
    "treamlit",         # the host that was never used
    "results.reference.json",
    "GitHub Pages",     # the project publishes with GitLab Pages
    "v3 (csiro",        # the corpus is v2; csiro:10948 is the collection edition
    "Use v3",
    "tuned <b>on dev only</b>; sweep",  # rung 5's threshold is retired, not swept
    "~6,754",           # the gold count is 9,111
    "200-record dev split",
    "600–800 frozen test split",
    "rxnorm version",
    "BioPortal first",
    "docs/article-v2.md</code>;\nthe evidence",   # the v18 status banner's article pointer
]


def test_no_superseded_number_or_host_survives_in_the_page():
    src = _page()
    hits = [s for s in SUPERSEDED if s in src]
    assert not hits, "superseded in docs/plan.html: " + ", ".join(hits)


CURRENT = [
    "rerun-cadec-d0",           # the run every dev-side number comes from
    "0.204",                    # held-out F1, run once
    "242",                      # held-out records to a person
    "3.4",                      # menu-shown judge separation lower bound
    "article-infoq-CADEC.md",
    "runs/archive/consolidated-2026-09-03",
    "gatecheck", "crosscheck", "stagecheck",
    "PsyTAR",
    "GitLab Pages",
]


def test_the_page_carries_the_current_result():
    src = _page()
    missing = [s for s in CURRENT if s not in src]
    assert not missing, "docs/plan.html does not mention: " + ", ".join(missing)


def test_the_six_tabs_are_there():
    assert _TAB.findall(_page()) == ["plan", "demo", "flow", "arch", "iter", "gloss"]


# ---------------------------------------------------------------- the links

def test_every_local_reference_resolves_and_pages_publishes_the_figures():
    src = _page()
    bad = []
    for target in _REF.findall(src):
        if target.startswith(("http://", "https://", "mailto:", "#", "data:")):
            continue
        if not (PAGE.parent / target.partition("#")[0]).exists():
            bad.append(target)
    assert not bad, "docs/plan.html links to files that do not exist: " + ", ".join(bad)
    if "figures/" in src:
        pages = CI.read_text().split("pages:", 1)[1]
        assert "docs/figures" in pages, \
            "the page embeds docs/figures/*.png but the pages job does not copy docs/figures"


# ---------------------------------------------------------------- the demo

def _ledger_by_record(path: pathlib.Path) -> dict:
    out: dict = {}
    with path.open() as fh:
        for line in fh:
            row = json.loads(line)
            out.setdefault(row["record_id"], {})[row["rung"]] = row
    return out


def test_the_demo_traces_are_real_records_of_the_tracked_ledger_and_carry_no_prose():
    """Two records of one fact: the trace (from the raw run) and the tracked
    ledger row (in git) must agree on the rung 1 reason, on rung 2's outcome
    and on whether rung 5 shipped the record. And the spec in
    scripts/plan_demo.py is the page's list, so the two cannot drift."""
    from scripts.plan_demo import MAX_SPAN_WORDS, SPEC
    demo = _data()["demo"]
    ledgers = {"rerun-cadec-d0": _ledger_by_record(ARCHIVE / "rerun-cadec-d0.ledger.jsonl"),
               "rerun-finer-d0": _ledger_by_record(ARCHIVE / "finer" / "rerun-finer-d0.ledger.jsonl")}
    stripped = {}
    with sorted(PSYTAR.glob("*.records.stripped.jsonl"))[0].open() as fh:
        for line in fh:
            r = json.loads(line)
            stripped[r["record_id"]] = r
    runs = ("rerun-cadec-d0", "psytar-gpt-oss_20b-d0", "rerun-finer-d0")
    assert [t["id"] for t in demo] == [s["id"] for run in runs for s in SPEC[run]]
    assert len(demo) >= 20, "the demo should cover every path on every dataset"
    # every dataset shows every path it has a record on: ACCEPT ships, BAND held, and the REJECT paths where they exist
    def path(t):
        lane = t["r1"]["verdict"]
        if lane == "REJECT":
            return "rescued" if t["r2"]["outcome"] == "rescued" else "reject"
        return "ships" if t["final"]["shipped"] else "held"
    by = {}
    for t in demo:
        by.setdefault(t["corpus"], set()).add(path(t))
    assert by["cadec"] == {"ships", "held", "rescued", "reject"}
    assert by["psytar"] == {"ships", "held"}          # PsyTAR produced no REJECT
    assert by["finer"] == {"held", "reject"}          # FiNER's ACCEPT lane is empty by construction
    for t in demo:
        if t["run"] in ledgers:
            rows = ledgers[t["run"]][t["id"]]
            assert rows[1]["reason"] == t["r1"]["reason"], t["id"]
            assert rows[2]["outcome"] == t["r2"]["outcome"], t["id"]
            assert (rows[5]["zone"] == "VERIFIED") == t["final"]["shipped"], t["id"]
            assert t["gold_known"] is True
        else:
            r = stripped[t["id"]]
            assert r["checks"]["r1_verdict"] == t["r1"]["verdict"], t["id"]
            assert (r["zone"] == "VERIFIED") == t["final"]["shipped"], t["id"]
            assert t["gold_known"] is False and t["gold"] == [] and "not published" in t["span"]
        assert len(t["span"].split()) <= MAX_SPAN_WORDS or t["span"].endswith("quote withheld)"), t["id"]
        dumped = json.dumps(t)
        for word in ("why", "prompt", "raw", "document", "context"):
            assert f'"{word}"' not in dumped, (t["id"], word)


# ---------------------------------------------------------------- the batch flow

def _lanes_from_ledger(path: pathlib.Path) -> list[dict]:
    by: dict = {}
    with path.open() as fh:
        for line in fh:
            row = json.loads(line)
            by.setdefault(row["record_id"], {})[row["rung"]] = row
    out = []
    for t in by.values():
        if 1 not in t or 5 not in t:
            continue  # document-level rows carry no lane
        rescued = t.get(2, {}).get("outcome") == "rescued"
        out.append({"lane": t[1]["verdict"], "lane4": "BAND" if rescued else t[1]["verdict"], "rescued": rescued,
                    "judge": t.get(4, {}).get("verdict") or "unjudged", "ships": t[5]["zone"] == "VERIFIED"})
    return out


def _lanes_from_records(path: pathlib.Path) -> list[dict]:
    out = []
    with path.open() as fh:
        for line in fh:
            r = json.loads(line)
            c = r["checks"]
            rescued = (c.get("r2") or {}).get("outcome") == "rescued"
            out.append({"lane": c["r1_verdict"], "lane4": "BAND" if rescued else c["r1_verdict"], "rescued": rescued,
                        "judge": c.get("r4_verdict") or "unjudged", "ships": r["zone"] == "VERIFIED"})
    return out


def test_the_batch_flow_is_recomputed_from_the_tracked_per_record_files():
    """Every ribbon width on the demo tab's batch flow is a count of records
    in a tracked file: the ledger (CADEC, FiNER) or the stripped records
    (PsyTAR). Recompute them here, independently of the generator."""
    flow = _data()["flow"]
    sources = {"cadec": _lanes_from_ledger(ARCHIVE / "rerun-cadec-d0.ledger.jsonl"),
               "finer": _lanes_from_ledger(ARCHIVE / "finer" / "rerun-finer-d0.ledger.jsonl"),
               "psytar": _lanes_from_records(sorted(PSYTAR.glob("*.records.stripped.jsonl"))[0])}
    assert set(flow) == set(sources)
    for corpus, recs in sources.items():
        f = flow[corpus]
        assert f["n"] == len(recs) == _data()[corpus]["rungs"][0]["n_records"], corpus
        for lane in ("ACCEPT", "BAND", "REJECT"):
            assert f["lanes"][lane] == sum(1 for r in recs if r["lane"] == lane), (corpus, lane)
            for v in ("pass", "fail", "unjudged"):
                assert f["judge"][lane][v] == sum(1 for r in recs if r["lane4"] == lane and r["judge"] == v), (corpus, lane, v)
            assert f["to5"][lane]["ships"] == sum(1 for r in recs if r["lane4"] == lane and r["ships"]), (corpus, lane)
            assert f["to5"][lane]["held"] == sum(1 for r in recs if r["lane4"] == lane and not r["ships"]), (corpus, lane)
        assert f["rescued"] == sum(1 for r in recs if r["rescued"]), corpus
        assert f["ships"] == sum(1 for r in recs if r["ships"]) and f["ships"] + f["held"] == f["n"], corpus
        # the shipping rule is ACCEPT: nothing else ships, and every ACCEPT ships
        assert f["to5"]["BAND"]["ships"] == 0 and f["to5"]["REJECT"]["ships"] == 0, corpus
        assert f["to5"]["ACCEPT"]["held"] == 0, corpus
        assert sum(f["judge"][L][v] for L in f["judge"] for v in f["judge"][L]) == f["n"], corpus
    # the right-answer counts agree with the results table the Plan tab shows
    for corpus in sources:
        rows = {r["rung"]: r for r in _data()[corpus]["rungs"]}
        f = flow[corpus]
        assert f["ship_right"] == round(rows[5]["f1_sct_strict"] * f["ships"]) if f["ships"] else f["ship_right"] == 0
        assert f["ship_right"] + f["person_right"] == round(rows[4]["yield"] * f["n"]), corpus


def test_the_codes_voting_changed_per_lane_come_from_the_tracked_reports():
    flow = _data()["flow"]
    cad = json.loads(REPORT.read_text())["draws"]["rerun-cadec-d0"]["r3"]["by_lane"]
    fin = json.loads(FINER_REPORT.read_text())["draws"]["rerun-finer-d0"]["r3"]["by_lane"]
    psy: dict = {}
    with sorted(PSYTAR.glob("*.records.stripped.jsonl"))[0].open() as fh:
        for line in fh:
            r = json.loads(line)
            if (r["checks"].get("r3") or {}).get("changed"):
                psy[r["checks"]["r1_verdict"]] = psy.get(r["checks"]["r1_verdict"], 0) + 1
    for corpus, want in (("cadec", cad), ("finer", fin)):
        for lane in ("ACCEPT", "BAND", "REJECT"):
            assert flow[corpus]["changed_by_lane"][lane] == want.get(lane, {}).get("changed", 0), (corpus, lane)
    for lane in ("ACCEPT", "BAND", "REJECT"):
        assert flow["psytar"]["changed_by_lane"][lane] == psy.get(lane, 0), lane
    for corpus in flow:
        assert sum(flow[corpus]["changed_by_lane"].values()) == flow[corpus]["changed"], corpus


# ---------------------------------------------------------------- the documents the demo draws

def test_the_demo_documents_are_the_workbench_view_of_real_documents_with_no_post():
    """The demo draws a document the way the Workbench's Live tab does. Every
    document is one a demo example lives in; every record of it is a record
    of the tracked ledger with the same rung 1 verdict and the same fate; no
    quoted span exceeds the seven-word precedent; and nothing that could
    carry the post — the post, a prompt, a reply, the judge's prose — has a
    key in the block."""
    from scripts.plan_demo import DOCS, MAX_SPAN_WORDS
    data = _data()
    docs = data["documents"]
    ledgers = {"rerun-cadec-d0": _ledger_by_record(ARCHIVE / "rerun-cadec-d0.ledger.jsonl"),
               "rerun-finer-d0": _ledger_by_record(ARCHIVE / "finer" / "rerun-finer-d0.ledger.jsonl")}
    stripped = {}
    with sorted(PSYTAR.glob("*.records.stripped.jsonl"))[0].open() as fh:
        for line in fh:
            r = json.loads(line)
            stripped[r["record_id"]] = r
    want = {(run, d) for run, ids in DOCS.items() for d in ids}
    assert {(d["run"], d["doc_id"]) for d in docs} == want
    for t in data["demo"]:
        assert any(d["run"] == t["run"] and d["doc_id"] == t["id"].split("#")[0] for d in docs), t["id"]
    for d in docs:
        # the excerpt is carried only for the redistributable corpus (FiNER-139, CC-BY-SA);
        # a CADEC post or a PsyTAR review never reaches the page
        if d["corpus"] == "finer":
            assert isinstance(d.get("text"), str) and d["text"] and "synthetic" not in d
        elif d["corpus"] == "cadec":
            # a CADEC document carries a SYNTHETIC stand-in (scripts/plan_synth.py): the real
            # spans at the post's word positions, invented words everywhere else, marked as such
            assert d.get("synthetic") is True and isinstance(d.get("text"), str), d["doc_id"]
            assert len(d["text"].split()) == d["words"] == len(d["word_spans"]), d["doc_id"]
            for r in d["records"]:
                for a, b in r["spans"]:
                    assert d["text"][a:b] in r["span"], (d["doc_id"], r["record_id"])
            for g in d["gold_spans"]:
                p = next(p for p in d["pairs"] if p["gold"]["record_id"] == g["record_id"])
                for a, b in g["spans"]:
                    assert d["text"][a:b] in p["gold"]["span"], (d["doc_id"], g["record_id"])
        else:
            assert "text" not in d and "gold_spans" not in d, d["doc_id"]
        dumped = json.dumps({k: v for k, v in d.items() if k != "text"})
        assert d.get("local_text") is None and data.get("local_text") is None, "the local copy never reaches the tree"
        for word in ("why", "prompt", "raw", "reply", "detail", "calls", "context"):
            assert f'"{word}"' not in dumped, (d["doc_id"], word)
        for r in d["records"]:
            assert len(r["span"].split()) <= MAX_SPAN_WORDS or r["span"].endswith("quote withheld)") or r["span"] == "(not published)", r["record_id"]
            if d["run"] in ledgers:
                rows = ledgers[d["run"]][r["record_id"]]
                assert rows[1]["verdict"] == r["r1"]["verdict"], r["record_id"]
                assert (rows[5]["zone"] == "VERIFIED") == (r["final"]["zone"] == "VERIFIED"), r["record_id"]
            else:
                s = stripped[r["record_id"]]
                assert s["checks"]["r1_verdict"] == r["r1"]["verdict"] and s["zone"] == r["final"]["zone"], r["record_id"]
        for p in d["pairs"]:
            assert len(p["gold"]["span"].split()) <= MAX_SPAN_WORDS or p["gold"]["span"].endswith("quote withheld)")
        if d["counts"]:
            c = d["counts"]
            assert c["found_exact"] + c["found_overlap"] + c["missed"] == c["gold"] == len(d["pairs"])
            assert c["spurious"] == len(d["spurious"]) and c["predictions"] == len(d["records"])


def test_the_demo_opens_on_cadec():
    """The owner's call (2026-09-10): the demo opens on CADEC, the corpus the
    article is about, now that its documents read as text (a synthetic
    stand-in) rather than grey blocks."""
    page = PAGE.read_text()
    assert 'let dSet="cadec"' in page
    assert "It opens on CADEC" in page

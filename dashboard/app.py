"""The Workbench API. Every read route is GET; the ONE POST is the live run
(`/api/live/run`, 2026-09-09), which runs a single document through the real
rungs in-process into a scratch directory and writes nothing under `out/`
(C2 still holds: nothing launches a process, nothing targets the test split,
nothing produces a run). Every payload that carries a number carries
provenance (C3) and the caveats its numbers demand (C4); exports live under
/api/export/ and are scrubbed (C1); cost is three separate panels (C5).
"""
from __future__ import annotations

import csv
import io
import json
from pathlib import Path

from fastapi import Body, FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles

from dashboard import caveats as caveats_mod
from dashboard import (corpus_views, dependencies, document_view, ledger_views,
                       llm_view, scoring, walkthrough)
from dashboard.live import LiveError, LiveRunner
from dashboard.provenance import provenance_for
from dashboard.runsindex import RunInfo
from dashboard.scrub import assert_clean, scrub_payload
from dashboard.state import AppState
from dashboard.util import format_span_param, parse_span_param

STATIC_DIR = Path(__file__).parent / "static"

#: The tab bar names later milestones so the layout is stable when they land
#: (spec: structure the tab bar so they can be added). `shipped` is what the
#: frontend reads; `milestone` is the label. M1 shipped the first four; the
#: live run (2026-09-09) is the single-document half of M3's workbench.
TABS = [
    {"id": "explorer", "label": "Data explorer", "milestone": "M1", "shipped": True},
    {"id": "results", "label": "Results", "milestone": "M1", "shipped": True},
    {"id": "walkthrough", "label": "Walkthrough", "milestone": "M1", "shipped": True},
    {"id": "trace", "label": "Traceability", "milestone": "M1", "shipped": True},
    {"id": "live", "label": "Live run", "milestone": "M3", "shipped": True},
    {"id": "workbench", "label": "Rung workbench", "milestone": "M3", "shipped": False},
    {"id": "monitor", "label": "Run monitor", "milestone": "M3", "shipped": False},
    {"id": "desk", "label": "Desk", "milestone": "M4", "shipped": False},
    {"id": "demo", "label": "Demo", "milestone": "M2", "shipped": False},
]


def create_app(state: AppState, live_runner: LiveRunner | None = None) -> FastAPI:
    app = FastAPI(title="Ladder Workbench", docs_url=None, redoc_url=None)
    live = live_runner if live_runner is not None else LiveRunner(state)

    def _run(key: str) -> RunInfo:
        try:
            return state.get_run(key)
        except KeyError:
            raise HTTPException(404, f"unknown run {key!r}")

    def _prov(info: RunInfo, span_match: str = "-") -> dict:
        return provenance_for(info, split=state.run_split(info),
                              span_match=span_match)

    def _caveats(info: RunInfo, extra: list[str] = ()) -> dict:
        rows = [
            {"rung": e.rung, "outcome": e.outcome, "verdict": e.verdict,
             "human_minutes": e.human_minutes}
            for e in state.ledger_entries(info)
        ]
        keys = caveats_mod.keys_for_run(rows, split=state.run_split(info))
        for k in extra:
            if k not in keys:
                keys.append(k)
        return caveats_mod.texts(keys)

    def _corpus_prov(span_match: str = "-") -> dict:
        man_path = state.repo_root / "manifest.json"
        import hashlib
        digest = (hashlib.sha256(man_path.read_bytes()).hexdigest()[:12]
                  if man_path.exists() else "absent")
        return {
            "run_id": None, "split": "corpus", "span_match": span_match,
            "backend": state.manifest().get("vocabulary", {}).get(
                "snomed_backend", "unknown"),
            "manifest_hash": digest, "archived": False,
        }

    # -- meta -----------------------------------------------------------------

    @app.get("/api/health")
    def health():
        return {"ok": True, "milestone": "M1+live", "read_only": True,
                "writes_files": False, "live_run": True}

    @app.get("/api/tabs")
    def tabs():
        return {"tabs": TABS, "active_milestone": "M1+live"}

    # -- live run: one document, the real rungs, a scratch dir ----------------

    @app.get("/api/live/options")
    def live_options():
        return {**live.options(), "provenance": _corpus_prov()}

    @app.post("/api/live/run")
    def live_run(body: dict = Body(...)):
        try:
            job = live.start(
                text=body.get("text"), doc_id=body.get("doc_id"),
                through_rung=int(body.get("through_rung", 6)),
            )
        except LiveError as exc:
            raise HTTPException(exc.status, exc.detail)
        except (TypeError, ValueError) as exc:
            raise HTTPException(400, str(exc))
        return job.public()

    @app.get("/api/live/job")
    def live_job(id: str):
        try:
            return live.job(id).public()
        except LiveError as exc:
            raise HTTPException(exc.status, exc.detail)

    # -- runs -----------------------------------------------------------------

    @app.get("/api/runs")
    def runs():
        out = []
        for key, info in sorted(state.runs().items(),
                                key=lambda kv: -kv[1].mtime):
            out.append({
                "key": key,
                "run_id": info.run_id,
                "dir": str(info.dir),
                "archived": info.archived,
                "split": state.run_split(info),
                "files": sorted(info.files),
                "mtime": info.mtime,
            })
        return {"runs": out}

    # -- R3: results & comparison --------------------------------------------

    def _results_rows(info: RunInfo) -> list[dict]:
        from dashboard.runsindex import read_results

        rows = []
        for raw in read_results(info):
            row = {}
            for k, v in raw.items():
                if v is None or v == "":
                    row[k] = None  # absent measurement: non-value, never zero
                elif k in ("rung", "layer", "r1_mode"):
                    row[k] = v
                else:
                    try:
                        row[k] = float(v) if "." in v or "e" in v.lower() else int(v)
                    except ValueError:
                        row[k] = v
            rows.append(row)
        return rows

    @app.get("/api/run/results")
    def run_results(run: str):
        info = _run(run)
        return {
            "rows": _results_rows(info),
            "provenance": _prov(info),
            "caveats": _caveats(info),
        }

    @app.get("/api/run/costs")
    def run_costs(run: str):
        info = _run(run)
        payload = ledger_views.costs_payload(state, info)
        payload["provenance"] = _prov(info)
        payload["caveats"] = _caveats(info)
        return payload

    @app.get("/api/run/score")
    def run_score(run: str, span_match: str = Query("exact")):
        info = _run(run)
        scored = scoring.score_payload(state, info, span_match)
        if scored is None:
            return {"available": False,
                    "reason": "corpus unavailable — scores need the licensed corpus",
                    "provenance": _prov(info, span_match)}
        label_check = scoring.label_check_counts(state.records(info))
        return {
            "available": True,
            **scored,
            # the third result layer (rung 1's label_check) — span-independent
            "label_check": label_check,
            # per-layer composition, each in its own outcome vocabulary
            "composition": scoring.composition(scored["score"], label_check),
            "provenance": _prov(info, span_match),
            "caveats": _caveats(info, extra=["outdated_separate"]),
        }

    @app.get("/api/run/compare")
    def run_compare(a: str, b: str, span_match: str = Query("exact")):
        ia, ib = _run(a), _run(b)
        sa, sb = state.run_split(ia), state.run_split(ib)
        if sa != sb:
            raise HTTPException(
                409, f"split mismatch: {a} is {sa}, {b} is {sb} — a comparison "
                "across splits compares nothing")
        payload = {
            "a": {"results": _results_rows(ia), "provenance": _prov(ia, span_match),
                  "score": scoring.score_payload(state, ia, span_match)},
            "b": {"results": _results_rows(ib), "provenance": _prov(ib, span_match),
                  "score": scoring.score_payload(state, ib, span_match)},
            "provenance": _prov(ia, span_match),
            "caveats": {**_caveats(ia), **_caveats(ib)},
        }
        r3 = caveats_mod.CAVEATS["rung3_samples"]
        if "rung3_samples" in payload["caveats"]:
            payload["rung3_cross_draw"] = (
                "rung 3 deltas are cross-draw: the two runs drew different "
                "samples. " + r3)
        return payload

    @app.get("/api/run/dependencies")
    def run_dependencies(run: str):
        info = _run(run)
        payload = dependencies.dependencies_payload(state, info)
        payload["provenance"] = _prov(info)
        payload["caveats"] = {
            **_caveats(info),
            **dependencies.gate_caveat(payload["r1_mode"]),
        }
        return payload

    @app.get("/api/run/flow")
    def run_flow(run: str, span_match: str = Query("exact")):
        info = _run(run)
        annotations = scoring.annotate_records(state, info, span_match)
        payload = ledger_views.flow_payload(state, info, annotations)
        payload["provenance"] = _prov(info, span_match)
        payload["caveats"] = _caveats(info)
        return payload

    # -- R5: traceability -----------------------------------------------------

    @app.get("/api/run/records")
    def run_records(run: str, span_match: str = Query("exact"),
                    zone: str | None = None, outcome: str | None = None,
                    doc_id: str | None = None, verdict: str | None = None,
                    disposition: str | None = None):
        info = _run(run)
        annotations = scoring.annotate_records(state, info, span_match)
        records = state.records(info)
        ann = annotations or [{} for _ in records]

        def _disposition(rec) -> str:
            if rec.zone in ("VERIFIED", "RESOLVED"):
                return "shipped"
            if rec.zone in ("ESCALATE", "ABSTAIN"):
                return "escalated"
            return "open"

        out = []
        for rec, a in zip(records, ann):
            if zone and rec.zone != zone:
                continue
            if doc_id and rec.doc_id != doc_id:
                continue
            if outcome and a.get("outcome") != outcome:
                continue
            # the diagram's subsets: a ribbon is (r1 verdict, disposition)
            if verdict and (rec.checks or {}).get("r1_verdict") != verdict:
                continue
            if disposition and _disposition(rec) != disposition:
                continue
            out.append({
                "record_id": rec.record_id,  # display only — identity is the span key
                "doc_id": rec.doc_id,
                "spans": [list(s) for s in rec.spans],
                "span_param": format_span_param(rec.spans) if rec.spans else "",
                "zone": rec.zone,
                "sct": rec.sct,
                "sct_label": rec.sct_label,
                "outcome": a.get("outcome"),
                "withheld_outcome": a.get("withheld_outcome"),
                "unlocatable": walkthrough.unlocatable(rec),
            })
        return {"records": out, "scored": annotations is not None,
                "provenance": _prov(info, span_match),
                "caveats": _caveats(info)}

    @app.get("/api/run/record")
    def run_record(run: str, doc_id: str, spans: str,
                   span_match: str = Query("exact")):
        info = _run(run)
        rec = walkthrough.find_record(state, info, doc_id, parse_span_param(spans))
        if rec is None:
            raise HTTPException(404, "no record at that span key")
        records = state.records(info)
        gold = {}
        for mode in ("exact", "overlap"):
            annotations = scoring.annotate_records(state, info, mode)
            if annotations is None:
                gold = None
                break
            gold[mode] = annotations[records.index(rec)]
        return {
            "record": {
                "record_id": rec.record_id,
                "doc_id": rec.doc_id,
                "spans": [list(s) for s in rec.spans],
                "text": rec.text,  # loopback-only view
                "sct": rec.sct, "sct_label": rec.sct_label,
                "zone": rec.zone, "reason": rec.reason,
                "confidence": rec.confidence,
                "checks": rec.checks,
                "history": rec.provenance,
                "unlocatable": walkthrough.unlocatable(rec),
            },
            "panels": walkthrough.panels(rec),
            "ledger_rows": walkthrough.record_ledger_rows(state, info, rec),
            "gold": gold,
            "provenance": _prov(info, span_match),
            "caveats": _caveats(info),
        }

    @app.get("/api/run/document")
    def run_document(run: str, doc_id: str):
        """The Results drill-down: this run's document through the Live grid."""
        info = _run(run)
        payload = document_view.run_document_payload(state, info, doc_id)
        if payload is None:
            raise HTTPException(404, f"document {doc_id!r} unavailable (corpus absent, or not in it)")
        return payload

    @app.get("/api/run/record_llm")
    def run_record_llm(run: str, doc_id: str, spans: str):
        info = _run(run)
        payload = llm_view.record_llm_payload(state, info, doc_id,
                                              parse_span_param(spans))
        payload["provenance"] = _prov(info)
        return payload

    # -- R4: walkthrough ------------------------------------------------------

    @app.get("/api/run/docs")
    def run_docs(run: str, span_match: str = Query("exact"),
                 q: str | None = None, drug: str | None = None):
        info = _run(run)
        annotations = scoring.annotate_records(state, info, span_match)
        records = state.records(info)
        ann = annotations or [{} for _ in records]
        docs: dict[str, dict] = {}
        for rec, a in zip(records, ann):
            d = docs.setdefault(rec.doc_id, {
                "doc_id": rec.doc_id,
                "drug_group": rec.doc_id.split(".")[0],
                "n_records": 0, "outcomes": {}, "zones": {}})
            d["n_records"] += 1
            d["zones"][rec.zone] = d["zones"].get(rec.zone, 0) + 1
            o = a.get("outcome")
            if o:
                d["outcomes"][o] = d["outcomes"].get(o, 0) + 1
        out = [d for d in docs.values()
               if (not q or q.lower() in d["doc_id"].lower())
               and (not drug or d["drug_group"] == drug)]
        return {"docs": sorted(out, key=lambda d: d["doc_id"]),
                "split": state.run_split(info),
                "provenance": _prov(info, span_match),
                "caveats": _caveats(info)}

    @app.get("/api/run/walkthrough")
    def run_walkthrough(run: str, doc_id: str,
                        span_match: str = Query("exact")):
        info = _run(run)
        annotations = scoring.annotate_records(state, info, span_match)
        by_id = None
        if annotations is not None:
            by_id = {id(r): a for r, a in zip(state.records(info), annotations)}
        payload = walkthrough.walkthrough_payload(state, info, doc_id, by_id)
        corpus = state.corpus()
        payload["text"] = corpus[doc_id].text if corpus and doc_id in corpus else None
        payload["gold_mentions"] = (
            corpus_views.doc_payload(state, doc_id) or {}).get("mentions")
        payload["provenance"] = _prov(info, span_match)
        payload["caveats"] = _caveats(info)
        return payload

    # -- R1: corpus -----------------------------------------------------------

    @app.get("/api/corpus/stats")
    def corpus_stats():
        payload = corpus_views.stats_payload(state)
        if payload is None:
            return {"available": False, "reason": "corpus unavailable",
                    "provenance": _corpus_prov()}
        return {"available": True, **payload, "provenance": _corpus_prov()}

    @app.get("/api/corpus/splits")
    def corpus_splits():
        splits = state.splits() or {}
        return {
            "splits": {k: {"n_docs": len(v)} for k, v in splits.items()},
            "seed": state.manifest().get("seed"),
            "stratified_by": state.manifest().get("corpus", {}).get("stratified_by"),
            "provenance": _corpus_prov(),
        }

    @app.get("/api/corpus/docs")
    def corpus_docs(split: str | None = None, q: str | None = None,
                    drug: str | None = None, run: str | None = None):
        info = _run(run) if run else None
        payload = corpus_views.docs_payload(state, split, q, drug, run_info=info)
        if payload is None:
            return {"available": False, "reason": "corpus unavailable",
                    "spent_split": split == "test", "docs": [], "run": run,
                    "provenance": _corpus_prov()}
        if info is not None:
            payload["run_key"] = run
        return {**payload, "provenance": _corpus_prov()}

    @app.get("/api/corpus/doc")
    def corpus_doc(doc_id: str):
        payload = corpus_views.doc_payload(state, doc_id)
        if payload is None:
            raise HTTPException(404, "document unavailable")
        return {**payload, "provenance": _corpus_prov()}

    @app.get("/api/corpus/exclusions")
    def corpus_exclusions():
        return {"rows": state.exclusion_rows(), "provenance": _corpus_prov()}

    @app.get("/api/corpus/zones")
    def corpus_zones(split: str = Query("dev")):
        payload = corpus_views.zones_payload(state, split)
        payload["provenance"] = _corpus_prov()
        if payload.get("available"):
            payload["caveats"] = caveats_mod.texts(["backend_dependent"])
        return payload

    # -- C1 exports: scrubbed, no corpus text ---------------------------------

    @app.get("/api/export/results")
    def export_results(run: str):
        info = _run(run)
        rows = _results_rows(info)
        prov = _prov(info)
        buf = io.StringIO()
        buf.write("# " + _prov_line(prov) + "\n")
        if rows:
            w = csv.DictWriter(buf, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows({k: ("" if v is None else v) for k, v in r.items()}
                        for r in rows)
        text = buf.getvalue()
        assert_clean(text, known_texts=_known_texts(state, info))
        return PlainTextResponse(text, media_type="text/csv")

    @app.get("/api/export/records")
    def export_records(run: str, span_match: str = Query("exact")):
        info = _run(run)
        annotations = scoring.annotate_records(state, info, span_match)
        records = state.records(info)
        ann = annotations or [{} for _ in records]
        rows = []
        for rec, a in zip(records, ann):
            rows.append(scrub_payload({
                "record_id": rec.record_id,
                "doc_id": rec.doc_id,
                "spans": [list(s) for s in rec.spans],
                "sct": rec.sct,
                "zone": rec.zone,
                "outcome": a.get("outcome"),
                "checks": rec.checks,
            }))
        payload = {"records": rows, "provenance": _prov(info, span_match),
                   "caveats": _caveats(info)}
        assert_clean(json.dumps(payload), known_texts=_known_texts(state, info))
        return payload

    @app.get("/api/export/figure")
    def export_figure(run: str, span_match: str = Query("exact")):
        info = _run(run)
        rows = _results_rows(info)
        scored = scoring.score_payload(state, info, span_match)
        prov = _prov(info, span_match)
        svg = _figure_svg(rows, scored, prov)
        assert_clean(svg, known_texts=_known_texts(state, info))
        return Response(svg, media_type="image/svg+xml")

    # -- SPA ------------------------------------------------------------------

    if STATIC_DIR.is_dir():
        app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

        @app.get("/")
        def index():
            return FileResponse(STATIC_DIR / "index.html")

    return app


def _prov_line(prov: dict) -> str:
    return (f"run {prov['run_id']} · split {prov['split']} · span "
            f"{prov['span_match']} · backend {prov['backend']} · manifest "
            f"{prov['manifest_hash']}")


def _known_texts(state: AppState, info: RunInfo) -> list[str]:
    """Belt-and-braces for assert_clean: the source texts this run touched,
    plus every record's quoted text."""
    texts: list[str] = []
    corpus = state.corpus()
    if corpus is not None:
        from dashboard.runsindex import run_doc_ids

        for d in run_doc_ids(info):
            if d in corpus:
                texts.append(corpus[d].text)
    for rec in state.records(info):
        if rec.text:
            texts.append(rec.text)
    return texts


def _figure_svg(rows: list[dict], scored: dict | None, prov: dict) -> str:
    """A minimal per-rung answered-accuracy figure with the provenance line
    burned into the margin (R3: exports carry provenance). Numbers only."""
    width, height = 640, 320
    bars = []
    xs = 60
    bw = 70
    plotted = [r for r in rows if r.get("f1_sct_strict") is not None]
    for i, r in enumerate(plotted):
        v = float(r["f1_sct_strict"] or 0.0)
        h = int(v * 200)
        x = xs + i * (bw + 10)
        bars.append(
            f'<rect x="{x}" y="{250 - h}" width="{bw}" height="{h}" '
            f'fill="#4a7ba6"/>'
            f'<text x="{x + bw / 2}" y="268" text-anchor="middle" '
            f'font-size="11">rung {r["rung"]}</text>'
            f'<text x="{x + bw / 2}" y="{244 - h}" text-anchor="middle" '
            f'font-size="10">{v:.3f}</text>')
    title = "answered accuracy per rung (denominator: rung snapshot)"
    ci_line = ""
    if scored is not None:
        s, ci = scored["score"], scored["ci"]
        ci_line = (f'<text x="{xs}" y="40" font-size="11">shipped F1 '
                   f'{s["f1"]:.3f} [{ci["f1"]["lo"]:.3f}-{ci["f1"]["hi"]:.3f}] '
                   f'({s["span_match"]})</text>')
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" '
        f'height="{height}" font-family="system-ui">'
        f'<rect width="{width}" height="{height}" fill="white"/>'
        f'<text x="{xs}" y="24" font-size="13" font-weight="bold">{title}</text>'
        f'{ci_line}{"".join(bars)}'
        f'<text x="{xs}" y="{height - 10}" font-size="10" fill="#555">'
        f'{_prov_line(prov)}</text></svg>')

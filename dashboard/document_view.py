"""Results drill-down — a batch run's document through the SAME grid as the
Live tab, from the run's own artifacts: the final records, the state table
(one row per record per rung, since 2026-09-03), the per-rung call traces,
the per-rung record snapshots, the ledger and the aggregates. Nothing is
re-run and nothing is re-derived: the payload has the shape `live.run_one`
produces, built by the same helpers (`rung0_path`, `gold_diff`,
`shipping_rules`), so one renderer draws both.

A run from before the state table wrote only the final records: the
timeline is then one row, the final state, and `state_available` says so.
The menu-shown judge (J+) is the live run's own second pass and is never
computed here; a batch run judged blind, or with the menu if its manifest
said so, and that is the J it has.
"""
from __future__ import annotations

import json
from collections import Counter
from typing import Any

from dashboard import caveats as caveats_mod
from dashboard.live import RULES, gold_diff, rung0_path, shipping_rules
from dashboard.provenance import provenance_for
from dashboard.runsindex import RunInfo, read_manifest_copy
from dashboard.state import AppState

TIMELINE_KEYS = (
    "rung", "sct", "sct_label", "zone", "reason", "text", "spans", "confidence",
    "created_this_rung", "dropped_this_rung", "changed_this_rung", "changed_fields",
    "was_sct", "was_zone", "r1_verdict", "r1_reason", "r4_verdict", "r3_changed",
    "pick_fallback", "outcome", "outcome_overlap", "gold_codes",
)


def _rows(path) -> list[dict]:
    if path is None or not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            out.append(json.loads(line))
    return out


def run_document_payload(state: AppState, info: RunInfo, doc_id: str) -> dict[str, Any] | None:
    corpus = state.corpus()
    if corpus is None or doc_id not in corpus:
        return None
    doc = corpus[doc_id]
    man = read_manifest_copy(info) or {}
    order = list(man.get("rung_order", [0, 1, 2, 3, 4, 5, 6]))
    entries = state.ledger_entries(info)
    present = {e.rung for e in entries}
    order_run = [n for n in order if n in present]
    disabled = {e.rung for e in entries if e.outcome == "disabled"}
    vocab = state.registry()

    records = [r for r in state.records(info) if r.doc_id == doc_id]
    record_ids = {r.record_id for r in records}

    # the state table, this document's rows
    state_rows = [row for row in _rows(info.files.get("state")) if row.get("doc_id") == doc_id]
    state_available = bool(state_rows)
    timelines: dict[str, list[dict]] = {}
    for row in state_rows:
        timelines.setdefault(row["record_id"], []).append({k: row.get(k) for k in TIMELINE_KEYS})

    # every call the run made for this document, per rung
    calls_by_rung: dict[int, list[dict]] = {}
    for kind, path in info.files.items():
        if kind.endswith(".calls"):
            n = int(kind[1:].split(".")[0])
            calls_by_rung[n] = [c for c in _rows(path) if c.get("doc_id") == doc_id]

    # gold, and the diff at every rung from the run's own snapshots
    excluded = state.exclusions()
    golds = [m for m in doc.mentions if m.record_id not in excluded]
    gold_view = [{"record_id": m.record_id, "text": m.text,
                  "spans": [list(s) for s in m.spans], "sct": list(m.sct),
                  "gold_kind": m.gold_kind, "excluded": m.record_id in excluded}
                 for m in doc.mentions]
    diff = gold_diff(records, golds, vocab)
    diff_by_rung: dict[str, Any] = {}
    last: list = []
    for n in order_run:
        snap = info.files.get(f"r{n}.records")
        if snap is not None and snap.exists():
            from ladder.run import read_predictions
            last = [r for r in read_predictions(snap, {doc_id} | {r.doc_id for r in records} | set(corpus))
                    if r.doc_id == doc_id]
        elif n == order_run[-1]:
            last = records
        diff_by_rung[str(n)] = gold_diff(last, golds, vocab)

    last_rung = order_run[-1] if order_run else None
    shaped = []
    for rec in records:
        d = rec.to_dict()
        tl = timelines.get(rec.record_id)
        if not tl:
            # no state table: the final state is the only row there is
            tl = [{**{k: None for k in TIMELINE_KEYS}, "rung": last_rung, "sct": rec.sct,
                   "sct_label": rec.sct_label, "zone": rec.zone, "reason": rec.reason,
                   "text": rec.text, "spans": [list(s) for s in rec.spans],
                   "confidence": rec.confidence, "changed_fields": [],
                   "r1_verdict": (rec.checks or {}).get("r1_verdict"),
                   "r1_reason": (rec.checks or {}).get("r1_reason"),
                   "r4_verdict": (rec.checks or {}).get("r4_verdict"),
                   "gold_codes": []}]
        d["timeline"] = tl
        at_r0 = next((row for row in tl if row["rung"] == 0), None)
        as_left = {**d, **{k: at_r0[k] for k in ("text", "spans", "sct", "sct_label", "confidence")}} \
            if at_r0 else d
        d["r0_path"] = rung0_path(as_left, calls_by_rung.get(0, []))
        d["rules"] = shipping_rules(d, order_run, disabled, vocab, None, menu_ran=False)
        run_n = sum(1 for r in d["rules"] if r["state"] != "not_run")
        held = sum(1 for r in d["rules"] if r["state"] == "hold")
        d["person"] = {"held": held, "run": run_n, "share": (held / run_n) if run_n else None}
        shaped.append(d)

    # cost per rung, over this document's ledger rows
    doc_entries = [e for e in entries if e.doc_id == doc_id or e.record_id in record_ids]
    aggregates = {}
    agg_path = info.files.get("aggregates")
    if agg_path is not None and agg_path.exists():
        aggregates = json.loads(agg_path.read_text(encoding="utf-8")).get("rungs", {})
    rungs: dict[str, Any] = {}
    calls_total = calls_cached = 0
    for n in order_run:
        rows = [e for e in doc_entries if e.rung == n]
        calls = calls_by_rung.get(n, [])
        calls_total += len(calls)
        calls_cached += sum(1 for c in calls if c.get("cached"))
        lat = sorted(float(c.get("seconds", 0.0)) * 1000 for c in calls if not c.get("cached"))
        rungs[str(n)] = {
            "aggregate": aggregates.get(str(n), {"disabled": True} if n in disabled else {}),
            "ledger": [{"rung": e.rung, "outcome": e.outcome, "verdict": e.verdict,
                        "zone": e.zone, "human_minutes": e.human_minutes} for e in rows],
            "calls": calls,
            "cost": {
                "tokens": sum(e.tokens_in + e.tokens_out for e in rows),
                "tokens_in": sum(e.tokens_in for e in rows),
                "tokens_out": sum(e.tokens_out for e in rows),
                "api_calls": sum(e.api_calls for e in rows),
                "latency_p95_ms": (lat[min(len(lat) - 1, int(round(0.95 * (len(lat) - 1))))]
                                   if lat else None),
                "routed_to_person": sum(1 for e in rows if e.zone == "ESCALATE" and n == 6),
                "human_minutes": sum(e.human_minutes or 0 for e in rows),
                "usd": sum(e.usd or 0 for e in rows),
                "wall_s": None,
            },
        }

    legend = []
    for rid, name in RULES:
        rows = [next(r for r in d["rules"] if r["id"] == rid) for d in shaped]
        run_n = sum(1 for r in rows if r["state"] != "not_run")
        held = sum(1 for r in rows if r["state"] == "hold")
        legend.append({"id": rid, "name": name, "held": held, "run": run_n,
                       "share": (held / run_n) if run_n else None})

    caveat_rows = [{"rung": e.rung, "outcome": e.outcome, "verdict": e.verdict,
                    "human_minutes": e.human_minutes} for e in entries]
    split = state.run_split(info)
    keys = ["results_drilldown"] + caveats_mod.keys_for_run(caveat_rows, split=split)
    if not state_available:
        keys.append("no_state_table")
    prov = provenance_for(info, split=split, span_match="exact+overlap")
    model = man.get("model") or {}
    prov.update(live=False, models={k: model.get(k) for k in ("extractor", "judge") if model.get(k)},
                temperature=model.get("temperature"))
    return {
        "run_id": info.run_id, "source": "run", "doc_id": doc_id, "split": split,
        "text": doc.text, "order_run": order_run, "records": shaped,
        "gold": gold_view, "gold_diff": diff, "gold_diff_by_rung": diff_by_rung,
        "rungs": rungs, "menu_judge": None, "rules_legend": legend,
        "calls_total": calls_total, "calls_cached": calls_cached,
        "state_available": state_available,
        "provenance": prov, "caveats": caveats_mod.texts(keys), "local_only": True,
    }

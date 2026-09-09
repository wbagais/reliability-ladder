"""R4 — example walkthrough. Panels are driven by RECORDED `checks` and
ledger rows — no re-derivation (spec R4 criteria). Record identity is by span
key, never record_id. A per-record rung timeline states what changed at each
rung, including "nothing": "did not fire" and "did not run" are different
claims and both are rendered.
"""
from __future__ import annotations

from typing import Any

from dashboard.runsindex import RunInfo, read_manifest_copy
from dashboard.state import AppState
from dashboard.util import span_key

CHECK_KEYS_R0 = ("rung0_step", "rung0_retrieval", "rung0_menu_order",
                 "offsets", "negated", "r0_negated", "honoured_tool")


def find_record(state: AppState, info: RunInfo, doc_id: str, spans) -> Any | None:
    """Span-key lookup — the scorer's identity rule, never record_id."""
    want = span_key(doc_id, spans)
    for rec in state.records(info):
        if span_key(rec.doc_id, rec.spans) == want:
            return rec
    return None


def record_ledger_rows(state: AppState, info: RunInfo, rec) -> list[dict]:
    """The record's own rows plus its document's per-document rows (rung 0
    logs one row per DOCUMENT — that is the denominator the ledger names)."""
    rows = []
    for e in state.ledger_entries(info):
        if e.doc_id != rec.doc_id and e.doc_id != "-":
            continue
        if e.record_id in (rec.record_id, rec.doc_id) or e.doc_id == "-":
            rows.append({
                "rung": e.rung, "zone": e.zone, "outcome": e.outcome,
                "reason": e.reason, "verdict": e.verdict,
                "tokens_in": e.tokens_in, "tokens_out": e.tokens_out,
                "api_calls": e.api_calls, "latency_ms": e.latency_ms,
                "usd": e.usd, "human_minutes": e.human_minutes,
                "denominator": e.extra.get("denominator"),
                "evaluable": e.extra.get("evaluable"),
                "per_document": e.record_id == e.doc_id,
            })
    return rows


def _rung_order(info: RunInfo) -> list[int]:
    man = read_manifest_copy(info) or {}
    return list(man.get("rung_order", [0, 1, 2, 3, 4, 5, 6]))


def unlocatable(rec) -> bool:
    return not rec.spans or any(a < 0 or b <= a for a, b in rec.spans)


def panels(rec) -> dict[str, Any]:
    """Per-rung panels from the record's recorded checks — never re-derived."""
    c = rec.checks or {}
    r1_verdict = c.get("r1_verdict")
    r1_reason = c.get("r1_reason")
    audit = c.get("r1_audit") or {}

    r2 = c.get("r2")
    if r2 is None:
        if r1_verdict == "REJECT":
            r2_state = {"fired": False,
                        "why": f"REJECT ({r1_reason}) but no correction recorded"}
        else:
            r2_state = {"fired": False,
                        "why": f"not eligible — rung 1 verdict {r1_verdict or 'none'}"}
    else:
        r2_state = {"fired": True, **r2}

    cands = c.get("candidates") or []
    return {
        "r0": {
            **{k: c.get(k) for k in CHECK_KEYS_R0 if k in c},
            "n_candidates": len(cands),
            "candidates": [
                {"i": x.get("i"), "code": x.get("code"), "label": x.get("label"),
                 "score": x.get("score"), "via": x.get("via")}
                for x in cands[:10]
            ],
        },
        "r1": {
            "verdict": r1_verdict, "reason": r1_reason,
            "all_reasons": audit.get("reasons"),
            "unevaluable": audit.get("unevaluable"),
            "lexical_match": c.get("lexical_match"),
            "sct_exists": c.get("sct_exists"), "sct_active": c.get("sct_active"),
            "label_verified": c.get("label_verified"),
        },
        "r2": r2_state,
        "r3": {
            **(c.get("r3") or {"outcome": "no_record"}),
            "votes": c.get("r3_votes"),
            "unanimous_none": c.get("r3_unanimous_none"),
        },
        "r4": {
            "verdict": c.get("r4_verdict"),
            "confidence": c.get("r4_confidence"),
            **{k: v for k, v in (c.get("r4") or {}).items() if k != "why"},
            "why": (c.get("r4") or {}).get("why"),
        },
        "r5": {"withheld": c.get("withheld")},
        "r6": c.get("r6"),
    }


def timeline(state: AppState, info: RunInfo, rec,
             rung_rows: dict[int, list]) -> list[dict]:
    """One node per rung in the run's order. States:
    changed | judged | did_not_fire | did_not_run | not_in_run."""
    c = rec.checks or {}
    prov_by_rung: dict[int, list[dict]] = {}
    for p in rec.provenance or []:
        prov_by_rung.setdefault(int(p.get("rung", -1)), []).append(p)

    nodes = []
    for rung in _rung_order(info):
        rows = rung_rows.get(rung, [])
        disabled = any(r.outcome == "disabled" for r in rows)
        ran = bool(rows) and not disabled
        prov = prov_by_rung.get(rung)
        node: dict[str, Any] = {"rung": rung}
        if disabled:
            node.update(state="did_not_run",
                        detail=rows[0].reason or "disabled")
        elif not rows:
            node.update(state="not_in_run", detail="no ledger rows")
        elif prov:
            last = prov[-1]
            node.update(state="changed",
                        detail=f"{last['from']} -> {last['to']}"
                        + (f" ({last.get('reason')})" if last.get("reason") else ""))
        elif rung == 0:
            node.update(state="changed", detail="extracted")
        elif rung == 1 and c.get("r1_verdict"):
            node.update(state="judged", detail=c["r1_verdict"])
        elif rung == 2 and c.get("r2"):
            node.update(state="judged", detail=c["r2"].get("outcome"))
        elif rung == 3 and (c.get("r3") or {}).get("seen"):
            r3 = c["r3"]
            node.update(state="changed" if r3.get("changed") else "judged",
                        detail=f"seen {r3.get('seen')}/{r3.get('k')}")
        elif rung == 4 and c.get("r4_verdict") is not None:
            node.update(state="judged", detail=c["r4_verdict"])
        else:
            node.update(state="did_not_fire", detail="nothing changed")
        assert ran or node["state"] in ("did_not_run", "not_in_run")
        nodes.append(node)
    return nodes


def walkthrough_payload(state: AppState, info: RunInfo, doc_id: str,
                        annotations_by_id: dict[int, dict] | None) -> dict:
    records = [r for r in state.records(info) if r.doc_id == doc_id]
    entries = state.ledger_entries(info)
    rung_rows: dict[int, list] = {}
    for e in entries:
        rung_rows.setdefault(e.rung, []).append(e)

    out = []
    for rec in records:
        ann = (annotations_by_id or {}).get(id(rec))
        out.append({
            "record_id": rec.record_id,  # display only, never identity
            "doc_id": rec.doc_id,
            "spans": [list(s) for s in rec.spans],
            "text": rec.text,  # loopback-only view; scrubbed from exports
            "sct": rec.sct, "sct_label": rec.sct_label,
            "zone": rec.zone, "reason": rec.reason,
            "confidence": rec.confidence,
            "unlocatable": unlocatable(rec),
            "panels": panels(rec),
            "timeline": timeline(state, info, rec, rung_rows),
            "final": {"state": "shipped" if rec.zone in ("VERIFIED", "RESOLVED")
                      else "escalated" if rec.zone == "ESCALATE" else rec.zone},
            "gold": ann,
        })
    return {"doc_id": doc_id, "records": out}

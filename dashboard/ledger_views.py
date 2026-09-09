"""Ledger-derived views: the three cost panels (C5), ledger-named
denominators, failure labels, non-values, and the record-flow data (V2).

Aggregation goes through `ladder.ledger.Ledger.cost_by_rung` — the pipeline's
ONE accounting path — applied to rows read by `Ledger.read`. Two accounting
paths is how a benchmark ends up with two numbers for the same run.
"""
from __future__ import annotations

from collections import Counter
from types import SimpleNamespace
from typing import Any

from ladder.ledger import Ledger

from dashboard.runsindex import RunInfo
from dashboard.state import AppState

FAILURE_LABELS = ("timed_out", "truncated", "json_decode")  # most specific first


def costs_payload(state: AppState, info: RunInfo) -> dict[str, Any]:
    entries = state.ledger_entries(info)
    n_records = len(state.records(info)) or None
    shim = SimpleNamespace(rows=entries)
    per_rung = Ledger.cost_by_rung(shim, n_records=n_records)

    tokens: dict[str, Any] = {}
    latency: dict[str, Any] = {}
    reviews: dict[str, Any] = {}
    usd: dict[str, Any] = {}
    for rung, c in sorted(per_rung.items()):
        r = str(rung)
        tokens[r] = {
            "tokens_in": c["tokens_in"], "tokens_out": c["tokens_out"],
            "tokens_per_record": round(c["tokens_per_record"], 2),
            "api_calls": c["api_calls"],
        }
        latency[r] = {"p95_s": round(c["p95_latency_s"], 4)}
        routed = sum(1 for e in entries if e.rung == rung and e.human_minutes)
        reviews[r] = {
            "routed": routed,
            "reviews_per_100": round(c["reviews_per_100"], 2),
            "human_minutes": c["human_minutes"],
        }
        usd[r] = round(c["usd"], 6)

    denominators: dict[str, Any] = {}
    for rung in sorted({e.rung for e in entries}):
        names = Counter(
            e.extra.get("denominator") for e in entries
            if e.rung == rung and e.extra.get("denominator"))
        denominators[str(rung)] = {
            "denominator": names.most_common(1)[0][0] if names else None,
            "rows": sum(1 for e in entries if e.rung == rung),
        }

    failure_labels: dict[str, Any] = {}
    for rung in sorted({e.rung for e in entries}):
        counts = Counter(
            e.reason for e in entries
            if e.rung == rung and e.reason in FAILURE_LABELS)
        if counts:
            failure_labels[str(rung)] = {k: counts.get(k, 0) for k in FAILURE_LABELS}

    # could_not_run and any absent measurement is a hatched NON-VALUE — the
    # absence of a measurement must not read as one (visual law).
    non_values = []
    by_rung_cnr: dict[int, list] = {}
    for e in entries:
        if e.extra.get("evaluable") == "could_not_run":
            by_rung_cnr.setdefault(e.rung, []).append(e)
    for rung, rows in sorted(by_rung_cnr.items()):
        non_values.append({
            "rung": rung,
            "count": len(rows),
            "reason": rows[0].reason or rows[0].outcome,
            "disabled": any(r.outcome == "disabled" for r in rows),
        })

    return {
        "panels": {"tokens": tokens, "latency": latency, "reviews": reviews},
        "usd": usd,
        "denominators": denominators,
        "failure_labels": failure_labels,
        "non_values": non_values,
        "totals": Ledger.totals(shim),
    }


def verdict_counts(state: AppState, info: RunInfo, rung: int) -> dict[str, int]:
    entries = state.ledger_entries(info)
    return dict(Counter(e.verdict for e in entries
                        if e.rung == rung and e.verdict))


def flow_payload(state: AppState, info: RunInfo,
                 annotations: list[dict] | None) -> dict[str, Any]:
    """V2 record flow: records -> rung-1 zones -> shipped vs escalated,
    shipped split correct/wrong, escalated split withheld-correct / other /
    unlocatable. Counts from the ledger and the records' own checks.

    `annotations` is scoring.annotate_records output, aligned with
    state.records(info); None when the corpus is absent (counts still render,
    correctness splits become stated non-values)."""
    records = state.records(info)
    ann = annotations or [{} for _ in records]
    pairs = [(r, a) for r, a in zip(records, ann) if r.entity_type == "reaction"]
    verdicts = verdict_counts(state, info, 1)

    shipped = [(r, a) for r, a in pairs if r.zone in ("VERIFIED", "RESOLVED")]
    escalated = [(r, a) for r, a in pairs if r.zone == "ESCALATE"]
    n_open = len(pairs) - len(shipped) - len(escalated)

    scored = annotations is not None
    shipped_correct = sum(1 for _, a in shipped if a.get("outcome") == "correct")
    unlocatable = sum(
        1 for r, _ in escalated
        if not r.spans or any(a < 0 or b <= a for a, b in r.spans))
    withheld_correct = sum(
        1 for _, a in escalated if a.get("withheld_outcome") == "correct")

    return {
        "n_records": len(pairs),
        "rung1_verdicts": verdicts,
        "shipped": {
            "n": len(shipped),
            "correct": shipped_correct if scored else None,
            "wrong": (len(shipped) - shipped_correct) if scored else None,
        },
        "escalated": {
            "n": len(escalated),
            "unlocatable": unlocatable,
            "withheld_correct": withheld_correct if scored else None,
        },
        "open": {"n": n_open},
        "scored": scored,
    }

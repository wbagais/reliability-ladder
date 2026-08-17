"""Risk–coverage analysis: where should the abstention gate sit?

Rung 2 blanks any field whose confidence falls below a threshold. The default
(0.7) is a guess, and a guess is wrong per model: a model whose confidence
never drops below 0.8 will never abstain, so the layer looks inert when the
signal was there all along.

Everything here is computed from a finished run's per-field outputs — no model
calls — so a user can find their own operating point before paying for a rerun.
"""

from __future__ import annotations

DEFAULT_GRID = [i / 100 for i in range(0, 101, 2)]


def sweep(fields: list[dict], thresholds: list[float] | None = None) -> list[dict]:
    """For each threshold: what you keep, what it costs, what you gain.

    `fields` are per-field output records ({confidence, status}). A field is
    *kept* when the rung answered it and its confidence clears the gate.
    """
    total = len(fields)
    if not total:
        return []
    rows = []
    base_correct = sum(f["status"] == "correct" for f in fields)
    base_wrong = sum(f["status"] == "wrong" for f in fields)
    for tau in thresholds or DEFAULT_GRID:
        kept = [f for f in fields
                if f["status"] != "abstained" and f["confidence"] >= tau]
        correct = sum(f["status"] == "correct" for f in kept)
        wrong = sum(f["status"] == "wrong" for f in kept)
        rows.append({
            "threshold": round(tau, 4),
            "coverage": len(kept) / total,
            "error_rate": (wrong / len(kept)) if kept else 0.0,
            "yield": correct / total,
            "errors_screened": base_wrong - wrong,
            "correct_lost": base_correct - correct,
        })
    return rows


def best_yield(rows: list[dict]) -> dict | None:
    """The threshold with the highest yield (ties -> the stricter gate)."""
    if not rows:
        return None
    return max(rows, key=lambda r: (r["yield"], r["threshold"]))


def free_lunch(rows: list[dict]) -> dict | None:
    """The strictest gate that screens errors without costing a single correct
    answer — the operating point worth knowing about."""
    candidates = [r for r in rows if r["correct_lost"] == 0 and r["errors_screened"] > 0]
    return max(candidates, key=lambda r: r["threshold"]) if candidates else None

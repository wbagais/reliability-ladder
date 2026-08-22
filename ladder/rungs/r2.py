"""Rung 2 — abstention. Owner A. Zero model calls.

Rung 2 declines rather than resolves. It runs LAST (order 0-1-3-5-4-2-6):
abstaining before self-correction and voting have had their turn throws away
records those rungs would have recovered.

Rung 2 is where a rung 1 verdict is finally allowed to cost coverage. Rung 1
runs in "observe" mode by default — it judges without routing, so rungs 3-6 see
the full unfiltered set — which means the BAND and REJECT records are still in
flight when rung 2 arrives. Rung 2 therefore reads `checks["r1_verdict"]`
rather than the zone, and falls back to the zone when rung 1 was gating (or
absent). One mechanism, both modes.

Three things a record can be abstained for, each logged separately because they
are different failures:

    unresolved       still in BAND after every resolver ran — plausible, but
                     nothing in the ladder could verify it
    rejected         rung 1 said it was provably wrong and rung 3 never rescued
                     it. Abstaining is the honest end state; shipping it is not
    low_confidence   the model's own confidence sits below tau

Abstention is a withdrawal, never a deletion — constraint 5 of the safety
design. The proposed answer is preserved in `checks["withheld"]` so rung 6 can
show a person what the system was going to say. The system has no authority to
rule anything out.

CONCEPT_LESS is NOT an abstention. "No code in the vocabulary is correct" is a
positive, scoreable answer that CADEC's gold also gives (445 mentions). Folding
it into abstention would make the system look cautious where it was actually
right, and would destroy the only clean abstention target the corpus offers.

tau is tuned on dev and written into the manifest BEFORE the first test run.
`sweep()` produces the risk-coverage curve that choice comes from; it takes the
correctness oracle as an argument rather than importing a scorer, so the one
shared scorer stays Owner B's file and there is still only one of it.
"""

from __future__ import annotations

import time
from typing import Any, Callable

from ladder.schema import (
    R_LOW_CONFIDENCE,
    R_UNRESOLVED,
    Record,
    ZONE_ABSTAIN,
    ZONE_ACCEPT,
    ZONE_BAND,
    ZONE_NEW,
    ZONE_REJECT,
    ZONE_VERIFIED,
)

RUNG = 2
NAME = "abstention"

DEFAULTS = {
    "tau": 0.0,
    "abstain_zones": [ZONE_BAND],
    "abstain_on_reject": True,
}


def _r1_verdict(rec: Record) -> str | None:
    """What rung 1 concluded, whether or not it acted on it."""
    return rec.checks.get("r1_verdict")


def decide(rec: Record, cfg: dict[str, Any] | None = None) -> tuple[str, str | None]:
    """(zone, reason) for one record. Pure, so the sweep can replay it."""
    cfg = {**DEFAULTS, **(cfg or {})}
    # Rung 1's verdict wins over the zone: in observe mode the zone never moved,
    # and in gate mode the two agree unless a later rung changed the zone — in
    # which case that later rung's routing is the more recent fact.
    standing = rec.zone if rec.zone not in (ZONE_NEW,) else None
    verdict = standing if standing in (ZONE_ACCEPT, ZONE_BAND, ZONE_REJECT) else _r1_verdict(rec)

    if verdict == ZONE_REJECT:
        reason = rec.reason or rec.checks.get("r1_reason")
        if cfg["abstain_on_reject"]:
            return ZONE_ABSTAIN, reason
        return rec.zone, reason
    tau = float(cfg["tau"] or 0.0)
    if tau > 0 and rec.confidence is not None and rec.confidence < tau:
        return ZONE_ABSTAIN, R_LOW_CONFIDENCE
    if verdict in cfg["abstain_zones"]:
        return ZONE_ABSTAIN, R_UNRESOLVED
    if verdict == ZONE_ACCEPT:
        return ZONE_VERIFIED, None
    return rec.zone, rec.reason


def apply(records: list[Record], sources: dict[str, str], cfg: dict[str, Any]) -> list[Record]:
    ledger = cfg.get("ledger")
    params = {k: v for k, v in cfg.items() if k in DEFAULTS}
    for rec in records:
        t0 = time.perf_counter()
        new_zone, reason = decide(rec, params)
        if new_zone == ZONE_ABSTAIN and rec.zone != ZONE_ABSTAIN:
            # Withdraw the answer, but keep it — abstention escalates, never
            # discards. Rung 6 shows the person what was withheld.
            rec.checks["withheld"] = {"sct": rec.sct, "confidence": rec.confidence}
            rec.sct = None
        rec.mark(RUNG, new_zone, reason)
        if ledger:
            ledger.log(
                RUNG,
                rec.doc_id,
                rec.record_id,
                new_zone,
                "abstained" if new_zone == ZONE_ABSTAIN else "settled",
                reason=reason,
                latency_ms=(time.perf_counter() - t0) * 1000,
            )
    return records


# --- tau sweep (dev only) ---------------------------------------------------


def sweep(
    records: list[Record],
    is_correct: Callable[[Record], bool],
    cfg: dict[str, Any] | None = None,
    taus: list[float] | None = None,
) -> list[dict[str, float]]:
    """Risk-coverage curve over tau. Dev split only — never touch test with this.

    `is_correct(record)` is the shared scorer, injected. One point per tau:

        coverage             answered / all
        selective_precision  correct among answered
        risk                 1 - selective_precision
        yield                correct / all  -- the honest headline: abstaining
                             raises precision mechanically, so precision alone
                             always argues for abstaining more
        over_abstention      abstained records that WOULD have been correct
    """
    cfg = {**DEFAULTS, **(cfg or {})}
    if taus is None:
        taus = [i / 20 for i in range(21)]
    n = len(records)
    out = []
    for tau in taus:
        params = {**cfg, "tau": tau}
        answered = correct = over = 0
        for rec in records:
            zone_, _ = decide(rec, params)
            was_right = is_correct(rec)
            if zone_ == ZONE_ABSTAIN:
                over += 1 if was_right else 0
            else:
                answered += 1
                correct += 1 if was_right else 0
        out.append(
            {
                "tau": round(tau, 4),
                "coverage": round(answered / n, 5) if n else 0.0,
                "selective_precision": round(correct / answered, 5) if answered else 0.0,
                "risk": round(1 - correct / answered, 5) if answered else 0.0,
                "yield": round(correct / n, 5) if n else 0.0,
                "over_abstention": over,
                "answered": answered,
                "correct": correct,
            }
        )
    return out


def aurc(curve: list[dict[str, float]]) -> float:
    """Area under the risk-coverage curve. Lower is better."""
    pts = sorted(((p["coverage"], p["risk"]) for p in curve))
    area = 0.0
    for (c0, r0), (c1, r1) in zip(pts, pts[1:]):
        area += (c1 - c0) * (r0 + r1) / 2
    span = pts[-1][0] - pts[0][0] if len(pts) > 1 else 0.0
    return round(area / span, 5) if span else 0.0


def free_lunch(curve: list[dict[str, float]]) -> dict[str, float] | None:
    """The strictest tau that screens errors without losing a single correct answer.

    It separates "the gate is miscalibrated" from "the mechanism does not
    work" — two conclusions that look identical from a coverage number alone.
    """
    best = None
    for point in curve:
        if point["over_abstention"] == 0 and point["coverage"] < 1.0:
            if best is None or point["tau"] > best["tau"]:
                best = point
    return best

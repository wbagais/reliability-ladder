"""Rung 6 — the human loop. Zero model calls; the resolver is a person.

Rung 6 is a RUNG, not an exhortation: "tell the model to escalate when unsure"
is rung 5. What rung 6 owns is everything after the escalation — the queue of
abstained records, the price of routing each one to a person (human minutes,
the third cost measure, never fused with tokens or usd), and the application of
a person's resolutions back onto the records in the shape the scorer grades.

THE QUEUE is the abstained residue: every record rung 5 left in ABSTAIN, each
still carrying the answer the system withdrew in `checks["withheld"]`
(abstention is a withdrawal, never a deletion — the person gets to see what
the system was going to say).

THREE POSTURES, one mode switch:

    simulated   (manifest default) the queue is routed and priced at
                `minutes_per_record`. No answer is invented, so coverage
                cannot move; the ledger row for each record carries the
                declared minutes with `minutes_source: "simulated"`. This
                measures the BILL of stopping at rung 5, not the person.
    desk        a resolutions file — written by a review session at
                scripts/r6_desk.py — is applied. Minutes are MEASURED
                (seconds at the desk, searching included). This is the only
                posture that can change an answer.
    oracle      not a mode of its own: `oracle_resolutions()` writes a desk
                file deterministically from gold, and desk mode applies it.
                A desk simulated FROM GOLD is an ORACLE CEILING — the best a
                perfect reviewer could do on this queue — and never a
                measurement of human work. Every ledger row it produces says
                `resolved_oracle`, the aggregate says `oracle: true`, and it
                is REFUSED on the test split outright: Phase F runs test
                once, and an oracle desk would put the answer key inside it.

RESOLUTIONS ARE MATCHED BY SPAN, NEVER BY POSITION — the same rule as the
scorer, for the same reason: record_id is a position, and positions agree
between files only by luck. A resolution row carries the record's span set;
segment order is meaningless (`ladder/score.py` on CADEC's own gold).

The rows deliberately contain NO corpus text: record ids, offsets, codes and
vocabulary labels only, so a resolutions file is shareable where the corpus is
not.

MODEL: none. `ladder/llm.py:ROLE_BY_RUNG` gives rung 6 no role on purpose — a
"simulated desk" that needed an LLM would be rung 2 in a trench coat, and the
attribution the ladder is built on would collapse.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Iterable

from ladder.corpus import GOLD_NONE, GoldMention
from ladder.schema import (
    CONCEPT_LESS,
    Record,
    ZONE_ABSTAIN,
    ZONE_ESCALATE,
    ZONE_RESOLVED,
)

RUNG = 6
NAME = "human loop"

DEFAULTS: dict[str, Any] = {
    "mode": "simulated",
    "minutes_per_record": 2.0,
    "resolutions": None,
}

MODES = ("simulated", "desk")

#: What a person can say about one queued record. Append, never reorder.
#:   code          this SCTID is the answer (the withheld one, or another)
#:   concept_less  no code in the vocabulary is correct — a positive claim
#:   uphold        the abstention stands; reviewed, and still no shippable code
#:   skip          looked at, not decided; stays in the queue
DECISIONS = ("code", "concept_less", "uphold", "skip")

R_QUEUED = "queued_for_review"
R_UPHELD = "abstention_upheld"

#: Reviewer names beginning with this mark a resolution as gold-derived.
ORACLE_PREFIX = "oracle"


# --- the queue ---------------------------------------------------------------


def queue(records: list[Record]) -> list[Record]:
    """The records a person is asked about: rung 5's abstained residue."""
    return [r for r in records if r.zone == ZONE_ABSTAIN]


# --- the resolution format ---------------------------------------------------


def _span_key(doc_id: str, spans: Iterable) -> tuple:
    """Document plus span SET — identical in spirit to the scorer's key."""
    return (doc_id, frozenset((int(a), int(b)) for a, b in spans))


def resolution_row(
    rec: Record,
    decision: str,
    sct: str | None = None,
    label: str | None = None,
    seconds: float | None = None,
    searches: int = 0,
    reviewer: str = "",
) -> dict[str, Any]:
    """One desk decision, validated. Carries NO corpus text on purpose."""
    if decision not in DECISIONS:
        raise ValueError(f"decision {decision!r} is not one of {DECISIONS}")
    if decision == "code" and not sct:
        raise ValueError("a 'code' decision needs the code it decided on")
    return {
        "record_id": rec.record_id,
        "doc_id": rec.doc_id,
        "spans": [list(s) for s in rec.spans],
        "decision": decision,
        "sct": str(sct) if sct else None,
        "label": label,
        "seconds": seconds,
        "searches": searches,
        "reviewer": reviewer,
        "ts": time.time(),
    }


def load_resolutions(path: str | Path) -> list[dict[str, Any]]:
    """Read and validate a desk file. A malformed row fails the run loudly —
    silently dropping a person's decision would misprice the whole queue."""
    rows = []
    for i, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines()):
        if not line.strip():
            continue
        row = json.loads(line)
        if row.get("decision") not in DECISIONS:
            raise ValueError(
                f"{path}:{i + 1}: decision {row.get('decision')!r} is not one of "
                f"{DECISIONS}"
            )
        if row["decision"] == "code" and not row.get("sct"):
            raise ValueError(f"{path}:{i + 1}: a 'code' decision carries no code")
        rows.append(row)
    return rows


def match_resolutions(
    q: list[Record], rows: list[dict[str, Any]]
) -> tuple[dict[int, dict[str, Any]], list[dict[str, Any]]]:
    """Pair each queued record with at most one resolution, BY SPAN KEY.

    Returns ({id(record): row}, unmatched_rows). One-to-one: a second row for
    the same span is unmatched, never a silent overwrite — same posture as
    rung 3's votes. Later sessions in an appended file therefore never clobber
    an earlier decision; re-reviewing a record means a new file.
    """
    by_key: dict[tuple, Record] = {}
    for rec in q:
        by_key.setdefault(_span_key(rec.doc_id, rec.spans), rec)
    matched: dict[int, dict[str, Any]] = {}
    unmatched: list[dict[str, Any]] = []
    for row in rows:
        rec = by_key.get(_span_key(row["doc_id"], row["spans"]))
        if rec is None or id(rec) in matched:
            unmatched.append(row)
            continue
        matched[id(rec)] = row
    return matched, unmatched


# --- the oracle generator ----------------------------------------------------


def oracle_resolutions(
    q: list[Record], golds: list[GoldMention]
) -> list[dict[str, Any]]:
    """A desk file written by the answer key. THE CEILING, NOT A MEASUREMENT.

    What a perfect reviewer could do with this queue and this vocabulary:
    a queued span that is a gold mention gets its gold code (the withheld
    answer when it was already in the gold set — the reviewer confirming the
    system — otherwise the annotation's first code); CONCEPT_LESS gold gets
    CONCEPT_LESS; a span the annotators never marked is UPHELD, because a
    perfect reviewer declines to code a non-mention rather than inventing one.

    Every row is stamped reviewer="oracle:gold" and carries no seconds — an
    oracle has no measured minutes, so desk mode prices these at the declared
    simulated rate and labels them so.
    """
    by_key = {_span_key(g.doc_id, g.spans): g for g in golds}
    rows = []
    for rec in q:
        g = by_key.get(_span_key(rec.doc_id, rec.spans))
        withheld = str((rec.checks.get("withheld") or {}).get("sct") or "")
        if g is None:
            decision, sct = "uphold", None
        elif not g.sct or g.gold_kind == GOLD_NONE:
            decision, sct = "concept_less", None
        else:
            gold_codes = [str(c) for c in g.sct]
            decision = "code"
            sct = withheld if withheld in gold_codes else gold_codes[0]
        rows.append(
            resolution_row(rec, decision, sct=sct, reviewer=f"{ORACLE_PREFIX}:gold")
        )
    return rows


# --- the rung ----------------------------------------------------------------


def _is_oracle(row: dict[str, Any]) -> bool:
    return str(row.get("reviewer") or "").startswith(ORACLE_PREFIX)


def apply(
    records: list[Record], sources: dict[str, str], cfg: dict[str, Any]
) -> tuple[list[Record], dict[str, Any]]:
    cfg = {**DEFAULTS, **(cfg or {})}
    mode = cfg["mode"]
    if mode not in MODES:
        raise ValueError(
            f"rungs.6.mode={mode!r} is not one of {MODES}. A desk nobody "
            "defined would price a queue under a label the article cannot "
            "explain."
        )
    ledger = cfg.get("ledger")
    mpr = float(cfg["minutes_per_record"])
    q = queue(records)
    agg: dict[str, Any] = {"mode": mode, "queue": len(q)}

    if mode == "simulated":
        for rec in q:
            rec.mark(RUNG, ZONE_ESCALATE, R_QUEUED)
            if ledger:
                ledger.log(
                    RUNG,
                    rec.doc_id,
                    rec.record_id,
                    ZONE_ESCALATE,
                    "escalated",
                    reason=R_QUEUED,
                    human_minutes=mpr,
                    denominator="r6_queue",
                    # Escalation ships no answer; same reading as rung 5's
                    # ABSTAIN. The minutes are declared, not measured.
                    evaluable="fail",
                    minutes_source="simulated",
                )
        agg.update(
            human_minutes=round(len(q) * mpr, 2),
            minutes_source="simulated",
            minutes_per_record=mpr,
        )
        return records, agg

    # -- desk: apply a review session ----------------------------------------
    path = cfg.get("resolutions")
    if not path:
        raise RuntimeError(
            "rungs.6.mode='desk' needs a resolutions file (cfg['resolutions']). "
            "'The desk did not run' and 'the desk resolved nothing' are "
            "different claims; refusing here keeps them apart. Produce one "
            "with scripts/r6_desk.py."
        )
    rows = load_resolutions(path)
    oracle = any(_is_oracle(r) for r in rows)
    if oracle and cfg.get("split") == "test":
        raise RuntimeError(
            "oracle resolutions on the test split are refused: Phase F runs "
            "test ONCE, and a gold-derived desk would put the answer key "
            "inside that run."
        )
    matched, unmatched = match_resolutions(q, rows)

    counts = {d: 0 for d in DECISIONS}
    total_minutes = 0.0
    sources_seen: set[str] = set()
    for rec in q:
        row = matched.get(id(rec))
        if row is None:
            rec.mark(RUNG, ZONE_ESCALATE, R_QUEUED)
            if ledger:
                ledger.log(
                    RUNG, rec.doc_id, rec.record_id, ZONE_ESCALATE, "escalated",
                    reason=R_QUEUED, human_minutes=0.0,
                    denominator="r6_queue", evaluable="fail",
                    minutes_source="unreviewed",
                )
            continue
        decision = row["decision"]
        counts[decision] += 1
        if row.get("seconds") is not None:
            minutes, minutes_source = float(row["seconds"]) / 60.0, "measured"
        else:
            minutes, minutes_source = mpr, "simulated"
        total_minutes += minutes
        sources_seen.add(minutes_source)

        if decision == "code":
            rec.sct = str(row["sct"])
            if row.get("label"):
                rec.sct_label = row["label"]
            zone_, outcome, reason, ok = ZONE_RESOLVED, "resolved", None, True
        elif decision == "concept_less":
            rec.sct = CONCEPT_LESS
            zone_, outcome, reason, ok = ZONE_RESOLVED, "resolved", None, True
        elif decision == "uphold":
            zone_, outcome, reason, ok = ZONE_RESOLVED, "resolved", R_UPHELD, False
        else:  # skip
            zone_, outcome, reason, ok = ZONE_ESCALATE, "escalated", R_QUEUED, False
        if outcome == "resolved" and _is_oracle(row):
            outcome = "resolved_oracle"
        rec.checks["r6"] = {
            "decision": decision,
            "reviewer": row.get("reviewer"),
            "seconds": row.get("seconds"),
            "searches": row.get("searches", 0),
        }
        rec.mark(RUNG, zone_, reason, decision=decision)
        if ledger:
            ledger.log(
                RUNG, rec.doc_id, rec.record_id, zone_, outcome,
                reason=reason, human_minutes=round(minutes, 4),
                denominator="r6_queue",
                evaluable="pass" if ok else "fail",
                minutes_source=minutes_source,
                decision=decision, reviewer=row.get("reviewer"),
            )

    agg.update(
        resolved=counts,
        unmatched_resolutions=len(unmatched),
        human_minutes=round(total_minutes, 2),
        minutes_source=(
            "mixed" if len(sources_seen) > 1 else (next(iter(sources_seen), "none"))
        ),
        oracle=oracle,
    )
    if oracle:
        agg["oracle_note"] = (
            "ORACLE CEILING: these resolutions were generated from the gold "
            "annotations, not by a person. They bound what a perfect reviewer "
            "could recover from this queue and measure NOTHING about human "
            "work. Label every number derived from this run accordingly."
        )
    return records, agg

"""Plan item 17(c), 2026-09-02: NINE RECORDS ARE UNREVIEWABLE BY CONSTRUCTION.

The schema-invalid residue carries unlocated `(-1, -1)` spans; several records
collapse onto one span key, and a span-keyed desk refuses to guess which
resolution belongs to which record. They stayed ESCALATE at zero minutes with
the same reason as an unreviewed record — invisible in the aggregate. Now they
carry their own disposition, `unreviewable`, counted in both modes and priced
at zero in desk mode, so "the desk could not act" and "the desk did not act"
are different rows.
"""

import json

import pytest

from ladder.ledger import Ledger
from ladder.schema import (
    REACTION,
    R_UNREVIEWABLE,
    Record,
    ZONE_ABSTAIN,
    ZONE_ESCALATE,
)


def queued(record_id, spans, sct="271782001"):
    r = Record(doc_id="D1", entity_type=REACTION, text="x", spans=spans,
               sct=None, zone=ZONE_ABSTAIN, record_id=record_id, reason="rejected")
    r.checks["withheld"] = {"sct": sct, "confidence": 1.0}
    return r


def test_the_reason_is_declared_in_the_schema():
    assert R_UNREVIEWABLE == "unreviewable"


def test_unlocated_and_colliding_spans_are_unreviewable():
    from ladder.rungs import r6

    q = [queued("D1#0", [(-1, -1)]), queued("D1#1", [(-1, -1)]),
         queued("D1#2", [(3, 5)]), queued("D1#3", [(3, 5)]), queued("D1#4", [(9, 12)])]
    bad = r6.unreviewable(q)
    assert {r.record_id for r in bad} == {"D1#0", "D1#1", "D1#2", "D1#3"}


def test_desk_mode_marks_them_and_prices_them_at_zero(tmp_path):
    from ladder.rungs import r6

    q = [queued("D1#0", [(-1, -1)]), queued("D1#1", [(-1, -1)]), queued("D1#2", [(9, 12)])]
    res = tmp_path / "res.jsonl"
    res.write_text(json.dumps(r6.resolution_row(q[2], "uphold", seconds=30)) + "\n")
    ledger = Ledger(tmp_path / "l.jsonl", run_id="t")
    _, agg = r6.apply(q, {"D1": "x"}, {"mode": "desk", "resolutions": str(res),
                                       "ledger": ledger, "minutes_per_record": 2.0})
    ledger.close()
    assert agg["unreviewable"] == 2
    assert q[0].zone == ZONE_ESCALATE and q[0].reason == R_UNREVIEWABLE
    rows = {e.record_id: e for e in ledger.rows if e.rung == 6}
    assert rows["D1#0"].reason == R_UNREVIEWABLE and rows["D1#0"].human_minutes == 0.0
    assert rows["D1#0"].extra["minutes_source"] == "unreviewable"
    assert rows["D1#2"].outcome == "resolved"


def test_simulated_mode_counts_them_but_still_prices_the_queue(tmp_path):
    """The headline rung 6 cost is the COUNT routed to a person, and a person
    still receives an unreviewable record. Simulated pricing is unchanged;
    the count is what becomes visible."""
    from ladder.rungs import r6

    q = [queued("D1#0", [(-1, -1)]), queued("D1#1", [(9, 12)])]
    ledger = Ledger(tmp_path / "l.jsonl", run_id="t")
    _, agg = r6.apply(q, {"D1": "x"}, {"mode": "simulated", "ledger": ledger,
                                       "minutes_per_record": 2.0})
    ledger.close()
    assert agg["unreviewable"] == 1
    assert agg["human_minutes"] == 4.0
    rows = {e.record_id: e for e in ledger.rows if e.rung == 6}
    assert rows["D1#0"].extra.get("unreviewable") is True
    assert rows["D1#1"].extra.get("unreviewable") is False


def test_a_resolution_for_an_unreviewable_span_is_unmatched_never_applied(tmp_path):
    from ladder.rungs import r6

    q = [queued("D1#0", [(-1, -1)]), queued("D1#1", [(-1, -1)])]
    res = tmp_path / "res.jsonl"
    res.write_text(json.dumps(r6.resolution_row(q[0], "code", sct="1")) + "\n")
    _, agg = r6.apply(q, {"D1": "x"}, {"mode": "desk", "resolutions": str(res)})
    assert agg["unmatched_resolutions"] == 1
    assert q[0].sct is None and q[1].sct is None

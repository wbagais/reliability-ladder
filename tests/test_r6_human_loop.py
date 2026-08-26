"""Rung 6 — the human loop, as a rung.

"Tell the model to escalate when unsure" is rung 5. Rung 6 is what happens to
the records rung 5 abstained on: they are routed to a person, the routing is
PRICED in human minutes (the third cost measure, never fused with tokens or
usd), and a person's resolutions — produced at the desk in scripts/r6_desk.py —
are applied back onto the records in a format the span-keyed scorer grades
directly.

Three postures, tested separately because they make different claims:

    simulated   the queue is routed and priced at manifest.rungs.6.
                minutes_per_record. No answer is invented; coverage must not
                move. This is the honest default: it measures the bill, not
                the person.
    desk        a resolutions file from a real review session is applied.
                Minutes are MEASURED (seconds at the desk), matched by span
                key — never by record position.
    oracle      resolutions generated deterministically from gold. A ceiling,
                not a measurement of human work, and it must say so in every
                number it produces. Refused on the test split outright.
"""

from __future__ import annotations

import json

import pytest

from ladder.corpus import GoldMention
from ladder.ledger import Ledger
from ladder.rungs import r6
from ladder.schema import (
    CONCEPT_LESS,
    Record,
    ZONE_ABSTAIN,
    ZONE_ESCALATE,
    ZONE_RESOLVED,
    ZONE_VERIFIED,
)
from ladder import score


# --- fixtures ----------------------------------------------------------------


def abstained(doc_id="D.1", spans=((20, 32),), withheld="12063002", rid="D.1#0"):
    """A record the way rung 5 leaves it: answer withdrawn but preserved."""
    return Record(
        doc_id=doc_id,
        entity_type="reaction",
        text="rectal bleed",
        spans=[tuple(s) for s in spans],
        sct=None,
        zone=ZONE_ABSTAIN,
        reason="unresolved",
        record_id=rid,
        checks={"withheld": {"sct": withheld, "confidence": 1.0}},
    )


def verified(doc_id="D.1", rid="D.1#9"):
    return Record(
        doc_id=doc_id,
        entity_type="reaction",
        text="nausea",
        spans=[(50, 56)],
        sct="422587007",
        zone=ZONE_VERIFIED,
        record_id=rid,
    )


def gold(doc_id="D.1", spans=((20, 32),), sct=("12063002",), kind="single", index=0):
    return GoldMention(
        doc_id=doc_id,
        index=index,
        entity_type="reaction",
        cadec_type="ADR",
        text="rectal bleed",
        spans=[tuple(s) for s in spans],
        sct=list(sct),
        gold_kind=kind,
    )


def resolution(rec, decision, sct=None, seconds=30.0, reviewer="tester", **extra):
    row = r6.resolution_row(
        rec, decision, sct=sct, seconds=seconds, reviewer=reviewer, **extra
    )
    return row


def run_r6(records, cfg, tmp_path):
    led = Ledger(tmp_path / "ledger.jsonl", run_id="t")
    out = r6.apply(records, {}, {"ledger": led, "split": "dev", **cfg})
    led.close()
    assert isinstance(out, tuple), "r6 follows the (records, aggregates) convention"
    recs, agg = out
    return recs, agg, led


# --- the queue ---------------------------------------------------------------


def test_queue_is_the_abstained_residue():
    recs = [abstained(), verified()]
    assert r6.queue(recs) == [recs[0]]


def test_rung6_needs_no_model():
    """ROLE_BY_RUNG gives rung 6 no role: the desk is a person, not a model.
    A simulated desk that needed an LLM would be rung 2 in a trench coat."""
    from ladder import llm as llm_mod

    assert llm_mod.for_rung(6, {}) is None


# --- simulated mode ----------------------------------------------------------


def test_simulated_mode_escalates_and_prices_the_queue(tmp_path):
    recs = [abstained(), verified()]
    recs, agg, led = run_r6(
        recs, {"mode": "simulated", "minutes_per_record": 2.0}, tmp_path
    )
    assert recs[0].zone == ZONE_ESCALATE
    assert recs[0].sct is None, "simulated review must not invent an answer"
    rows = [e for e in led.rows if e.rung == 6]
    assert len(rows) == 1
    assert rows[0].human_minutes == 2.0
    assert rows[0].outcome == "escalated"
    # The price is declared, not measured — every number must say so.
    assert rows[0].extra["minutes_source"] == "simulated"
    assert agg["mode"] == "simulated"
    assert agg["queue"] == 1
    assert agg["human_minutes"] == 2.0
    assert agg["minutes_source"] == "simulated"


def test_simulated_mode_leaves_settled_records_alone(tmp_path):
    recs = [verified()]
    recs, agg, led = run_r6(recs, {"mode": "simulated"}, tmp_path)
    assert recs[0].zone == ZONE_VERIFIED
    assert recs[0].provenance == []
    assert not [e for e in led.rows if e.rung == 6]
    assert agg["queue"] == 0


# --- desk mode: applying resolutions -----------------------------------------


def test_desk_mode_requires_a_resolutions_file(tmp_path):
    """'The desk did not run' and 'the desk resolved nothing' are different
    claims; a desk run without resolutions is the first, and must refuse."""
    with pytest.raises(RuntimeError, match="(?i)resolutions"):
        run_r6([abstained()], {"mode": "desk"}, tmp_path)


def _write_rows(tmp_path, rows):
    p = tmp_path / "resolutions.jsonl"
    p.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    return str(p)


def test_desk_code_resolution_feeds_the_scorer(tmp_path):
    rec = abstained()
    path = _write_rows(tmp_path, [resolution(rec, "code", sct="12063002")])
    recs, agg, led = run_r6([rec], {"mode": "desk", "resolutions": path}, tmp_path)
    assert rec.zone == ZONE_RESOLVED
    assert rec.sct == "12063002"
    # The whole point of the format: the scorer grades the resolved record
    # with no translation step.
    assert score.outcome(rec, gold()) == score.CORRECT
    row = [e for e in led.rows if e.rung == 6][0]
    assert row.outcome == "resolved"
    assert row.human_minutes == pytest.approx(0.5)  # 30 measured seconds
    assert row.extra["minutes_source"] == "measured"
    assert agg["resolved"]["code"] == 1


def test_desk_concept_less_and_uphold(tmp_path):
    a, b = abstained(rid="D.1#0"), abstained(spans=((40, 47),), rid="D.1#1")
    path = _write_rows(
        tmp_path,
        [resolution(a, "concept_less"), resolution(b, "uphold")],
    )
    recs, agg, led = run_r6([a, b], {"mode": "desk", "resolutions": path}, tmp_path)
    assert a.sct == CONCEPT_LESS and a.zone == ZONE_RESOLVED
    assert b.sct is None and b.zone == ZONE_RESOLVED
    assert b.reason == "abstention_upheld"
    up = [e for e in led.rows if e.record_id == b.record_id][0]
    assert up.extra["evaluable"] == "fail", "an upheld abstention ships no answer"


def test_resolutions_match_by_span_never_by_position(tmp_path):
    """The desk writes spans; the rung matches on the span SET. A resolution
    whose segments are listed in another order, under another record_id, must
    still find its record — and must never land on a different span."""
    rec = abstained(spans=((5, 9), (20, 32)), rid="D.1#7")
    row = resolution(rec, "code", sct="12063002")
    row["spans"] = [[20, 32], [5, 9]]  # reversed segment order
    row["record_id"] = "D.1#999"  # wrong position on purpose
    other = abstained(spans=((60, 70),), rid="D.1#8")
    path = _write_rows(tmp_path, [row])
    recs, agg, led = run_r6(
        [rec, other], {"mode": "desk", "resolutions": path}, tmp_path
    )
    assert rec.sct == "12063002"
    assert other.sct is None and other.zone == ZONE_ESCALATE


def test_unreviewed_records_escalate_with_zero_minutes(tmp_path):
    """Desk mode never fabricates minutes for records nobody looked at."""
    rec, unseen = abstained(rid="D.1#0"), abstained(spans=((60, 70),), rid="D.1#1")
    path = _write_rows(tmp_path, [resolution(rec, "code", sct="12063002")])
    recs, agg, led = run_r6(
        [rec, unseen], {"mode": "desk", "resolutions": path}, tmp_path
    )
    assert unseen.zone == ZONE_ESCALATE
    row = [e for e in led.rows if e.record_id == unseen.record_id][0]
    assert row.human_minutes == 0.0
    assert row.outcome == "escalated"


def test_skip_is_charged_the_seconds_it_took(tmp_path):
    """A skipped record was still looked at; the looking is the cost."""
    rec = abstained()
    path = _write_rows(tmp_path, [resolution(rec, "skip", seconds=12.0)])
    recs, agg, led = run_r6([rec], {"mode": "desk", "resolutions": path}, tmp_path)
    assert rec.zone == ZONE_ESCALATE
    row = [e for e in led.rows if e.rung == 6][0]
    assert row.human_minutes == pytest.approx(0.2)


def test_unmatched_resolutions_are_counted_never_applied(tmp_path):
    rec = abstained()
    stray = resolution(abstained(spans=((90, 99),)), "code", sct="99")
    path = _write_rows(tmp_path, [resolution(rec, "code", sct="12063002"), stray])
    recs, agg, led = run_r6([rec], {"mode": "desk", "resolutions": path}, tmp_path)
    assert agg["unmatched_resolutions"] == 1
    assert rec.sct == "12063002"


def test_code_resolution_without_a_code_is_rejected(tmp_path):
    rec = abstained()
    row = resolution(rec, "code", sct="12063002")
    row["sct"] = None
    path = _write_rows(tmp_path, [row])
    with pytest.raises(ValueError, match="(?i)code"):
        run_r6([rec], {"mode": "desk", "resolutions": path}, tmp_path)


def test_missing_seconds_fall_back_to_the_simulated_rate_and_say_so(tmp_path):
    a = abstained(rid="D.1#0")
    b = abstained(spans=((40, 47),), rid="D.1#1")
    rows = [
        resolution(a, "code", sct="12063002", seconds=None),
        resolution(b, "code", sct="12063002", seconds=60.0),
    ]
    path = _write_rows(tmp_path, rows)
    recs, agg, led = run_r6(
        [a, b], {"mode": "desk", "resolutions": path, "minutes_per_record": 2.0},
        tmp_path,
    )
    entry = [e for e in led.rows if e.record_id == a.record_id][0]
    assert entry.human_minutes == 2.0
    assert entry.extra["minutes_source"] == "simulated"
    # one declared rate, one measured clock: the aggregate must not pretend
    # the total is one kind of number
    assert agg["minutes_source"] == "mixed"


# --- oracle: the labeled ceiling ---------------------------------------------


def test_oracle_resolutions_come_from_gold_and_say_so():
    q = [
        abstained(spans=((20, 32),), withheld="12063002", rid="D.1#0"),
        abstained(spans=((40, 47),), withheld="404640003", rid="D.1#1"),
        abstained(spans=((60, 70),), withheld="111111111", rid="D.1#2"),
    ]
    golds = [
        gold(spans=((20, 32),), sct=("12063002", "131148009"), index=0),
        gold(spans=((40, 47),), sct=(), kind="concept_less", index=1),
        # no gold at (60, 70): a span the annotators never marked
    ]
    rows = r6.oracle_resolutions(q, golds)
    by_rid = {r["record_id"]: r for r in rows}
    # withheld answer preferred when it is already in the gold set
    assert by_rid["D.1#0"]["decision"] == "code"
    assert by_rid["D.1#0"]["sct"] == "12063002"
    assert by_rid["D.1#1"]["decision"] == "concept_less"
    # a span that is not a gold mention is upheld, not invented
    assert by_rid["D.1#2"]["decision"] == "uphold"
    for r in rows:
        assert r["reviewer"].startswith("oracle"), "every row must be labeled"
        assert r.get("seconds") is None, "an oracle has no measured minutes"


def test_oracle_takes_the_first_gold_code_when_withheld_is_wrong():
    q = [abstained(withheld="999999999")]
    rows = r6.oracle_resolutions(q, [gold(sct=("12063002", "131148009"))])
    assert rows[0]["sct"] == "12063002"


def test_oracle_run_is_labeled_in_every_number(tmp_path):
    rec = abstained()
    rows = r6.oracle_resolutions([rec], [gold()])
    path = _write_rows(tmp_path, rows)
    recs, agg, led = run_r6(
        [rec], {"mode": "desk", "resolutions": path, "minutes_per_record": 2.0},
        tmp_path,
    )
    assert agg["oracle"] is True
    assert "ceiling" in agg["oracle_note"].lower()
    entry = [e for e in led.rows if e.rung == 6][0]
    assert entry.outcome == "resolved_oracle"
    # oracle minutes are priced at the declared rate, and labeled simulated
    assert entry.human_minutes == 2.0
    assert entry.extra["minutes_source"] == "simulated"


def test_oracle_resolutions_are_refused_on_the_test_split(tmp_path):
    """Phase F runs the test split ONCE. An oracle desk on it would put the
    answer key inside the run — refused outright, not warned about."""
    rec = abstained()
    path = _write_rows(tmp_path, r6.oracle_resolutions([rec], [gold()]))
    led = Ledger(tmp_path / "l.jsonl", run_id="t")
    with pytest.raises(RuntimeError, match="(?i)test"):
        r6.apply(
            [rec],
            {},
            {"ledger": led, "split": "test", "mode": "desk", "resolutions": path},
        )


# --- unknown mode ------------------------------------------------------------


def test_unknown_mode_is_refused(tmp_path):
    with pytest.raises(ValueError, match="(?i)mode"):
        run_r6([abstained()], {"mode": "crowd"}, tmp_path)

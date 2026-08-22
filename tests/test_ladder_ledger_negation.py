"""Ledger accounting and the negation cue list."""

import json

from ladder.ledger import Ledger
from ladder.negation import is_negated


def spans_of(text, needle):
    i = text.index(needle)
    return [(i, i + len(needle))]


# --- ledger -----------------------------------------------------------------


def test_ledger_is_append_only_and_one_row_per_call(tmp_path):
    path = tmp_path / "l.jsonl"
    with Ledger(path, run_id="r") as led:
        led.log(1, "D1", "D1#0", "ACCEPT", "passed")
        led.log(1, "D1", "D1#1", "REJECT", "rejected", reason="code_unknown")
        led.log(3, "D1", "D1#1", "BAND", "settled", tokens_in=120, tokens_out=30, api_calls=1)
    lines = path.read_text().strip().split("\n")
    assert len(lines) == 3
    assert [json.loads(x)["rung"] for x in lines] == [1, 1, 3]
    assert Ledger.read(path)[2].tokens_in == 120


def test_cost_is_kept_in_three_currencies_and_never_fused(tmp_path):
    with Ledger(tmp_path / "l.jsonl", run_id="r") as led:
        led.log(3, "D1", "D1#0", "BAND", "settled", tokens_in=100, tokens_out=20, latency_ms=800)
        led.log(3, "D1", "D1#1", "BAND", "settled", tokens_in=100, tokens_out=20, latency_ms=200)
        led.log(6, "D1", "D1#1", "RESOLVED", "settled", human_minutes=2.0)
        costs = led.cost_by_rung(n_records=2)
        totals = led.totals()
    assert costs[3]["tokens_per_record"] == 120.0
    assert costs[3]["human_minutes"] == 0.0
    assert costs[6]["tokens_per_record"] == 0.0
    assert costs[6]["reviews_per_100"] == 50.0
    assert totals["tokens"] == 240 and totals["human_minutes"] == 2.0
    # No key anywhere adds minutes to tokens or to dollars.
    assert "total_cost" not in totals and "cost" not in costs[3]


def test_reason_breakdown_is_the_rung1_headline(tmp_path):
    with Ledger(tmp_path / "l.jsonl", run_id="r") as led:
        for reason in ["code_unknown", "code_unknown", "span_ungrounded"]:
            led.log(1, "D1", "x", "REJECT", "rejected", reason=reason)
        led.log(1, "D1", "y", "ACCEPT", "passed")
        assert dict(led.reasons(1)) == {"code_unknown": 2, "span_ungrounded": 1}
        assert dict(led.zone_counts(1)) == {"REJECT": 3, "ACCEPT": 1}


def test_p95_uses_the_tail_not_the_centre(tmp_path):
    with Ledger(tmp_path / "l.jsonl", run_id="r") as led:
        for ms in [10] * 90 + [5000] * 10:
            led.log(5, "D1", "x", "BAND", "settled", latency_ms=ms)
        costs = led.cost_by_rung()[5]
    mean_s = (90 * 0.010 + 10 * 5.0) / 100
    assert costs["p95_latency_s"] == 5.0, "p95 must sit in the tail voting blows out"
    assert costs["p95_latency_s"] > mean_s


# --- negation ---------------------------------------------------------------

DENIED = "I feel a bit drowsy & have a little blurred vision, so far no gastric problems."


def test_the_plans_worked_example_fires():
    negated, cue = is_negated(DENIED, spans_of(DENIED, "gastric problems"))
    assert negated and cue == "no"


def test_an_asserted_mention_in_the_same_sentence_does_not_fire():
    assert not is_negated(DENIED, spans_of(DENIED, "bit drowsy"))[0]
    assert not is_negated(DENIED, spans_of(DENIED, "little blurred vision"))[0]


def test_a_cue_inside_the_mention_is_part_of_the_complaint():
    """Patients report absences as symptoms: "no energy" is the mention."""
    text = "Since starting it I have no energy at all."
    assert not is_negated(text, spans_of(text, "no energy"))[0]


def test_a_clause_boundary_stops_the_scope():
    text = "I had no rash, but the muscle pain was unbearable."
    assert not is_negated(text, spans_of(text, "muscle pain"))[0]


def test_a_sentence_boundary_stops_the_scope():
    text = "I had no rash. The muscle pain was unbearable."
    assert not is_negated(text, spans_of(text, "muscle pain"))[0]


def test_pseudo_negation_does_not_fire():
    text = "There is no doubt that the muscle pain came from this drug."
    assert not is_negated(text, spans_of(text, "muscle pain"))[0]


def test_contraction_cue_fires():
    text = "I did not get any rash and I don't have nausea now."
    assert is_negated(text, spans_of(text, "nausea"))[0]

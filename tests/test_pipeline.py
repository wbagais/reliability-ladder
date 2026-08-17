import json

from bench.pipeline import run_item
from tests.conftest import FakeClient


def _out_map(output):
    return {f.field: f for f in output.fields}


def wrong_total_reply():
    return json.dumps({
        "answer": {"company": "ACME SDN BHD", "date": "01/02/2024", "total": "999"},
        "confidence": {"company": 0.9, "date": 0.9, "total": 0.4},
        "verdicts": {"company": "matches", "date": "matches", "total": "matches"},
    })


def test_rung0_takes_output_as_is(fake_client, dataset):
    out = run_item(fake_client, dataset, dataset.items[0], layers=set())
    m = _out_map(out)
    assert m["date"].value == "01/02/2024"  # raw, not normalized
    assert m["total"].value == "42.00"
    assert out.cost.tokens == 150
    assert len(fake_client.calls) == 1


def test_rung0_survives_garbage_output(dataset):
    client = FakeClient(default="I cannot answer that.")
    out = run_item(client, dataset, dataset.items[0], layers=set())
    assert all(f.value is None for f in out.fields)
    assert out.abstained


def test_rung1_normalizes_and_recomputes_verdicts(fake_client, dataset):
    # item 1: trusted total is 99.00 but doc/gold say 10.00 -> mechanical "conflicts"
    client = FakeClient(default=json.dumps({
        "answer": {"company": "BETA STORE", "date": "02/02/2024", "total": "RM10.00"},
        "confidence": {"company": 0.9, "date": 0.9, "total": 0.9},
        "verdicts": {"company": "matches", "date": "matches", "total": "matches"},
    }))
    out = run_item(client, dataset, dataset.items[1], layers={1})
    m = _out_map(out)
    assert m["date"].value == "2024-02-02"      # ISO
    assert m["total"].value == "10.00"          # currency stripped
    assert m["total"].verdict == "conflicts"    # model said matches; mechanics disagree


def test_rung2_abstains_on_low_confidence(dataset):
    client = FakeClient(default=wrong_total_reply())
    out = run_item(client, dataset, dataset.items[0], layers={1, 2})
    m = _out_map(out)
    assert m["total"].value is None             # conf 0.4 < 0.7
    assert m["company"].value == "ACME SDN BHD"


def test_rung3_revise_fixes_draft(dataset):
    good = json.dumps({
        "answer": {"company": "ACME SDN BHD", "date": "01/02/2024", "total": "42.00"},
        "confidence": {"company": 0.9, "date": 0.9, "total": 0.9},
        "verdicts": {"company": "matches", "date": "matches", "total": "matches"},
    })
    client = FakeClient(replies={"DRAFT ANSWER": good}, default=wrong_total_reply())
    out = run_item(client, dataset, dataset.items[0], layers={1, 2, 3})
    m = _out_map(out)
    assert m["total"].value == "42.00"
    assert len(client.calls) == 2               # base + revise


def test_rung4_judge_filters_failed_fields(fake_client, dataset):
    fake_client.replies = {
        "grading another model's output": json.dumps(
            {"grades": {"company": "pass", "date": "pass", "total": "fail"}}
        )
    }
    out = run_item(fake_client, dataset, dataset.items[0], layers={1, 2, 4})
    m = _out_map(out)
    assert m["total"].value is None
    assert m["company"].value == "ACME SDN BHD"
    assert len(fake_client.calls) == 2          # base + judge


def test_rung5_votes_across_variants(dataset):
    # variant framings differ; route two variants to a wrong total, three to right
    right = json.dumps({
        "answer": {"company": "ACME SDN BHD", "date": "01/02/2024", "total": "42.00"},
        "confidence": {"company": 0.9, "date": 0.9, "total": 0.9},
        "verdicts": {"company": "matches", "date": "matches", "total": "matches"},
    })
    wrong = json.dumps({
        "answer": {"company": "ACME SDN BHD", "date": "01/02/2024", "total": "13.00"},
        "confidence": {"company": 0.9, "date": 0.9, "total": 0.9},
        "verdicts": {"company": "matches", "date": "matches", "total": "matches"},
    })
    client = FakeClient(
        replies={
            "Work through the document carefully": wrong,   # variant 2
            "one at a time": wrong,                          # variant 3
        },
        default=right,                                       # variants 0, 1, 4
    )
    out = run_item(client, dataset, dataset.items[0], layers={1, 2, 5})
    m = _out_map(out)
    assert m["total"].value == "42.00"
    assert m["total"].confidence == 0.6          # 3/5 vote share
    assert len(client.calls) == 5


def test_rung6_simulated_human_resolves_escalations(dataset):
    client = FakeClient(default=wrong_total_reply())  # total conf 0.4 -> abstain -> escalate
    out = run_item(client, dataset, dataset.items[0], layers={1, 2, 6})
    m = _out_map(out)
    assert m["total"].value == "42.00"           # human == gold
    assert m["total"].confidence == 1.0
    assert out.cost.human_minutes == 2.0


def test_rung6_live_mode_uses_resolver(dataset):
    client = FakeClient(default=wrong_total_reply())
    seen = []

    def resolver(item, path, value, conf):
        seen.append(path)
        return "77.00"

    out = run_item(client, dataset, dataset.items[0], layers={1, 2, 6},
                   human_resolver=resolver)
    m = _out_map(out)
    assert m["total"].value == "77.00"
    assert seen == ["total"]


def test_extraction_mode_has_na_verdicts(extraction_dataset):
    client = FakeClient()
    out = run_item(client, extraction_dataset, extraction_dataset.items[0], layers={1, 2})
    assert all(f.verdict == "n_a" for f in out.fields)

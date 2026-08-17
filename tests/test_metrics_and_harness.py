import json

from bench.adapters.user_upload import load_dataset, validate
from bench.harness import run_benchmark, validate_results
from bench.metrics import apply_deltas, score_rung
from schemas.runner import Cost, FieldResult, RunnerOutput
from tests.conftest import FakeClient


def _output(values: dict, dollars=0.01):
    return RunnerOutput(
        fields=[FieldResult(field=k, value=v, verdict="n_a", confidence=0.9)
                for k, v in values.items()],
        cost=Cost(tokens=100, dollars=dollars, latency_s=0.1),
    )


def test_determinism_hand_computed(dataset):
    # item0: total flips between two values across K=2 -> field agreement
    # company 2/2, date 2/2, total 1/2 -> (1 + 1 + 0.5)/3
    runs = [
        [
            _output({"company": "A", "date": "2024-02-01", "total": "42.00"}),
            _output({"company": "A", "date": "2024-02-01", "total": "43.00"}),
        ],
        [
            _output({"company": "B", "date": "2024-02-02", "total": "10.00"}),
            _output({"company": "B", "date": "2024-02-02", "total": "10.00"}),
        ],
    ]
    scores = score_rung(dataset, runs)
    expected = ((1 + 1 + 0.5) / 3 + 1.0) / 2
    assert scores["determinism"]["field_agreement"] == round(expected, 4)


def test_accuracy_and_coverage_hand_computed(dataset):
    # item0 K=1: company right, date right (normalized match), total wrong
    # item1 K=1: all right, but date abstained -> coverage 2/3
    runs = [
        [_output({"company": "ACME SDN BHD", "date": "2024-02-01", "total": "41.00"})],
        [_output({"company": "BETA STORE", "date": None, "total": "10.00"})],
    ]
    scores = score_rung(dataset, runs)
    assert scores["accuracy"]["accuracy_on_answered"] == round((2 / 3 + 1.0) / 2, 4)
    assert scores["accuracy"]["coverage"] == round((1.0 + 2 / 3) / 2, 4)


def test_apply_deltas():
    a = {"determinism": {"field_agreement": 0.5}, "accuracy": {"accuracy_on_answered": 0.6},
         "cost": {"dollars": 0.01}}
    b = {"determinism": {"field_agreement": 0.8}, "accuracy": {"accuracy_on_answered": 0.9},
         "cost": {"dollars": 0.03}}
    apply_deltas([a, b])
    assert b["determinism"]["delta"] == 0.3
    assert abs(b["accuracy"]["delta"] - 0.3) < 1e-9
    assert b["cost"]["delta_dollars"] == 0.02


def test_validator_messages():
    errors = validate({"items": []})
    assert any("output_schema" in e for e in errors)
    errors = validate({"output_schema": {"properties": {"a": {"type": "number"}}},
                       "items": [{"doc": "x", "gold": {"a": "not-a-number"}}]})
    assert any("should be a number" in e for e in errors)
    errors = validate({"output_schema": {"properties": {"a": {"type": "string"}}},
                       "items": [{"doc": "", "gold": {"a": "x"}}]})
    assert any('"doc"' in e for e in errors)


def test_v1_legacy_format_still_loads():
    v1 = {
        "domain": "legacy",
        "fields": ["total", "date"],
        "items": [{
            "doc": "TOTAL 5.00 on 01/01/2024",
            "trusted_record": {"total": "5.00", "date": "01/01/2024"},
            "gold": [
                {"field": "total", "value": "5.00", "verdict": "matches"},
                {"field": "date", "value": "01/01/2024", "verdict": "matches"},
            ],
        }],
    }
    ds = load_dataset(v1)
    assert ds.items[0].gold == {"total": "5.00", "date": "01/01/2024"}
    assert ds.verification_mode


def test_prompt_file_is_read(tmp_path):
    (tmp_path / "prompt.txt").write_text("A long\nmulti-line\nprompt.")
    data = {
        "output_schema": {"properties": {"a": {"type": "string"}}},
        "prompt_file": "prompt.txt",
        "items": [{"doc": "x", "gold": {"a": "y"}}],
    }
    p = tmp_path / "data.json"
    p.write_text(json.dumps(data))
    assert load_dataset(p).prompt == "A long\nmulti-line\nprompt."


def test_explain_transitions_categorizes(dataset):
    from bench.metrics import explain_transitions

    prev = [
        [_output({"company": "ACME SDN BHD", "date": "2024-02-01", "total": "41.00"})],
        [_output({"company": "WRONG", "date": "2024-02-02", "total": None})],
    ]
    new = [
        [_output({"company": "ACME SDN BHD", "date": "2024-02-01", "total": "42.00"})],
        [_output({"company": None, "date": "2024-02-02", "total": "10.00"})],
    ]
    ex = explain_transitions(dataset, prev, new)
    t = ex["transitions"]
    assert t["wrong->correct"] == 1        # item0 total fixed
    assert t["wrong->abstained"] == 1      # item1 company screened out
    assert t["abstained->correct"] == 1    # item1 total recovered
    assert t["correct->correct"] == 3      # untouched fields
    changes = {(e["field"], e["change"]) for e in ex["examples"]}
    assert ("total", "wrong->correct") in changes


def test_harness_attaches_explain(dataset, tmp_path):
    results = run_benchmark(dataset, model_spec="ollama/fake", k=2, out=None,
                            client=FakeClient())
    dom = results["domains"][0]
    assert "explain" not in dom["rungs"][0]          # rung 0 has no predecessor
    assert all("explain" in r for r in dom["rungs"][1:])
    assert all("explain" in a for a in dom["ablations"])


def test_harness_attaches_diagnostics(dataset):
    results = run_benchmark(dataset, model_spec="ollama/fake", k=2, out=None,
                            client=FakeClient())
    rungs = {r["rung"]: r for r in results["domains"][0]["rungs"]}
    calib = rungs[2]["diagnostics"]
    assert calib["threshold"] == 0.7
    assert calib["n_correct"] + calib["n_wrong"] == 12  # 2 items x 2 k x 3 fields
    voting = rungs[5]["diagnostics"]
    assert len(voting["variant_accuracy"]) == 5
    assert voting["full_agreement_rate"] == 1.0         # fake client always agrees
    esc = rungs[6]["diagnostics"]
    assert esc["total_item_runs"] == 4


def test_harness_end_to_end_schema_valid(dataset, tmp_path):
    out = tmp_path / "results.json"
    results = run_benchmark(
        dataset,
        model_spec="ollama/fake",
        k=2,
        out=out,
        client=FakeClient(),
    )
    validate_results(results)  # would raise on violation
    on_disk = json.loads(out.read_text())
    dom = on_disk["domains"][0]
    assert dom["n_items"] == 2
    assert [r["rung"] for r in dom["rungs"]] == [0, 1, 2, 3, 4, 5, 6]
    assert [a["rung"] for a in dom["ablations"]] == [1, 2, 3, 4, 5, 6]
    assert dom["rungs"][0]["cost"]["delta_dollars"] == 0.0
    # rung 6 with the always-right fake escalates nothing on item0 but the
    # conflicting item1 total gets human minutes
    assert dom["rungs"][6]["cost"]["human_minutes"] > 0

import json

from bench.harness import run_benchmark
from bench.outputs import read_items, read_outputs, sidecar_path
from tests.conftest import FakeClient


def test_sidecar_path():
    assert sidecar_path("results.json").name == "results.outputs.jsonl"
    assert sidecar_path("/tmp/run7.json").name == "run7.outputs.jsonl"


def test_outputs_written_and_readable(dataset, tmp_path):
    out = tmp_path / "results.json"
    results = run_benchmark(dataset, model_spec="ollama/fake", k=2, out=out,
                            client=FakeClient(), save_outputs=True)
    side = sidecar_path(out)
    assert side.exists()
    assert results["domains"][0]["outputs_file"] == side.name

    items = read_items(side)
    assert set(items) == {0, 1}
    assert items[0]["doc"].startswith("ACME SDN BHD")
    assert items[0]["gold"]["total"] == "42.00"

    recs = read_outputs(side, item=0, k=0)
    assert {r["rung"] for r in recs} == {0, 1, 2, 3, 4, 5, 6}
    assert all(r["ablation"] is False for r in recs)

    rung0 = next(r for r in recs if r["rung"] == 0)
    by_field = {f["field"]: f for f in rung0["fields"]}
    assert by_field["company"]["status"] == "correct"
    assert by_field["company"]["gold"] == "ACME SDN BHD"
    assert set(by_field) == {"company", "date", "total"}


def test_status_reflects_gold(dataset, tmp_path):
    # item 1's trusted total (99.00) conflicts with gold (10.00); the fake client
    # always answers ACME/42.00, so item 1's fields must be scored wrong.
    out = tmp_path / "r.json"
    run_benchmark(dataset, model_spec="ollama/fake", k=1, out=out,
                  client=FakeClient(), save_outputs=True, rungs=[0], ablations=False)
    rec = read_outputs(sidecar_path(out), item=1, k=0)[0]
    statuses = {f["field"]: f["status"] for f in rec["fields"]}
    assert statuses == {"company": "wrong", "date": "wrong", "total": "wrong"}


def test_abstained_status_recorded(dataset, tmp_path):
    client = FakeClient(default=json.dumps({
        "answer": {"company": "ACME SDN BHD", "date": "01/02/2024", "total": "42.00"},
        "confidence": {"company": 0.9, "date": 0.9, "total": 0.2},
        "verdicts": {"company": "matches", "date": "matches", "total": "matches"},
    }))
    out = tmp_path / "r.json"
    run_benchmark(dataset, model_spec="ollama/fake", k=1, out=out, client=client,
                  save_outputs=True, rungs=[0, 1, 2], ablations=False)
    recs = {r["rung"]: r for r in read_outputs(sidecar_path(out), item=0, k=0)}
    assert next(f for f in recs[0]["fields"] if f["field"] == "total")["status"] == "correct"
    total2 = next(f for f in recs[2]["fields"] if f["field"] == "total")
    assert total2["status"] == "abstained"   # conf 0.2 < 0.7
    assert total2["value"] is None


def test_no_sidecar_when_disabled(dataset, tmp_path):
    out = tmp_path / "results.json"
    run_benchmark(dataset, model_spec="ollama/fake", k=1, out=out,
                  client=FakeClient(), save_outputs=False)
    assert not sidecar_path(out).exists()


def test_read_outputs_filters_ablations(dataset, tmp_path):
    out = tmp_path / "results.json"
    run_benchmark(dataset, model_spec="ollama/fake", k=1, out=out,
                  client=FakeClient(), save_outputs=True)
    side = sidecar_path(out)
    assert all(not r["ablation"] for r in read_outputs(side, item=0))
    assert any(r["ablation"] for r in read_outputs(side, item=0, include_ablations=True))

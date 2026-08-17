"""K-runs loop over rung configurations -> results.json (CONTRACT 2).

Cumulative rungs 0..6 are layer sets {} , {1}, {1,2}, ... {1..6}; ablations are
{r} alone on top of the bare call. Every emitted results.json is validated
against schemas/results.schema.json before it is written.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

import jsonschema

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bench.llm import DEFAULT_CACHE_DIR, LLMClient
from bench.metrics import apply_deltas, explain_transitions, score_rung
from bench.pipeline import RUNG_NAMES, HumanResolver, run_item
from schemas.adapter import Dataset

RESULTS_SCHEMA_PATH = Path(__file__).resolve().parents[1] / "schemas" / "results.schema.json"

ProgressCb = Callable[[str, float], None]


def _configs(rungs: list[int], ablations: bool):
    for r in rungs:
        yield f"rung{r}", r, set(range(1, r + 1))
    if ablations:
        for r in rungs:
            if r >= 1:
                yield f"ablation{r}", r, {r}


def run_benchmark(
    dataset: Dataset,
    model_spec: str,
    k: int = 10,
    n_items: int | None = None,
    rungs: list[int] | None = None,
    ablations: bool = True,
    out: str | Path | None = "results.json",
    api_key: str | None = None,
    cache_dir: Path | str = DEFAULT_CACHE_DIR,
    progress: ProgressCb | None = None,
    human_resolver: HumanResolver | None = None,
    client: LLMClient | None = None,  # injectable for tests (fake LLM)
) -> dict:
    rungs = rungs if rungs is not None else list(range(7))
    items = dataset.items[:n_items] if n_items else dataset.items
    ds = Dataset(
        domain=dataset.domain,
        output_schema=dataset.output_schema,
        items=items,
        prompt=dataset.prompt,
        economics=dataset.economics,
    )
    if client is None:
        client = LLMClient(model_spec, cache_dir=cache_dir, api_key=api_key)

    configs = list(_configs(rungs, ablations))
    total_steps = len(configs) * len(items) * k
    step = 0
    scored: dict[str, dict] = {}
    raw_runs: dict[str, list] = {}

    for label, rung_no, layers in configs:
        runs = []
        for item in items:
            k_outputs = []
            for ki in range(k):
                k_outputs.append(
                    run_item(client, ds, item, layers, sample_index=ki,
                             human_resolver=human_resolver)
                )
                step += 1
                if progress:
                    progress(f"{label} · item {len(runs) + 1}/{len(items)} · run {ki + 1}/{k}",
                             step / total_steps)
            runs.append(k_outputs)
        entry = score_rung(ds, runs)
        entry["rung"] = rung_no
        entry["name"] = RUNG_NAMES[rung_no]
        scored[label] = entry
        raw_runs[label] = runs

    # per-rung internals for the dashboard (replayed from cache — no new calls)
    from bench.diagnostics import abstention_calibration, escalation_reasons, voting_variants

    if "rung2" in scored and "rung0" in raw_runs:
        scored["rung2"]["diagnostics"] = abstention_calibration(ds, raw_runs["rung0"])
    if "rung5" in scored:
        scored["rung5"]["diagnostics"] = voting_variants(client, ds, k)
    if "rung6" in scored and "rung5" in raw_runs:
        scored["rung6"]["diagnostics"] = escalation_reasons(ds, raw_runs["rung5"])

    # explainability: what each rung actually changed vs the rung below it
    # (ablations are compared against rung 0)
    present = [r for r in rungs if f"rung{r}" in scored]
    for prev_r, cur_r in zip(present, present[1:]):
        scored[f"rung{cur_r}"]["explain"] = explain_transitions(
            ds, raw_runs[f"rung{prev_r}"], raw_runs[f"rung{cur_r}"]
        )
    for r in rungs:
        if f"ablation{r}" in scored and "rung0" in raw_runs:
            scored[f"ablation{r}"]["explain"] = explain_transitions(
                ds, raw_runs["rung0"], raw_runs[f"ablation{r}"]
            )

    cumulative = [scored[f"rung{r}"] for r in rungs if f"rung{r}" in scored]
    apply_deltas(cumulative)
    ablation_list = [scored[f"ablation{r}"] for r in rungs if f"ablation{r}" in scored]
    baseline = scored.get("rung0")
    if baseline is not None and ablation_list:
        apply_deltas(ablation_list, baseline=baseline)

    results = {
        "model": model_spec,
        "temperature": 0.0,
        "k_runs": k,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "domains": [
            {
                "name": ds.domain,
                "n_items": len(items),
                "economics": ds.economics,
                "rungs": cumulative,
                "ablations": ablation_list,
            }
        ],
    }
    validate_results(results)
    if out:
        Path(out).write_text(json.dumps(results, indent=1))
    return results


def validate_results(results: dict) -> None:
    schema = json.loads(RESULTS_SCHEMA_PATH.read_text())
    jsonschema.validate(results, schema)

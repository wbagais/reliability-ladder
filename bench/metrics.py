"""The three scores: determinism, accuracy(+coverage), cost — with bootstrap CIs.

Determinism is purely mechanical string comparison across the K runs (per spec):
for each field, the fraction of runs matching the modal value; averaged across
fields, then items. Accuracy is scored against gold with the same schema-driven
normalization the rungs use, so rungs are compared on meaning, not formatting.
"""

from __future__ import annotations

import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bench.flatten import flatten_json, schema_node_for_path
from bench.normalize import values_match
from schemas.adapter import Dataset
from schemas.runner import RunnerOutput

BOOTSTRAP_B = 500
BOOTSTRAP_SEED = 7


def _bootstrap_ci(per_item: list[float]) -> tuple[float, float]:
    vals = [v for v in per_item if v is not None]
    if len(vals) < 2:
        v = vals[0] if vals else 0.0
        return round(v, 4), round(v, 4)
    rng = random.Random(BOOTSTRAP_SEED)
    means = sorted(
        sum(rng.choices(vals, k=len(vals))) / len(vals) for _ in range(BOOTSTRAP_B)
    )
    return round(means[int(0.025 * BOOTSTRAP_B)], 4), round(means[int(0.975 * BOOTSTRAP_B)], 4)


def _mean(vals: list[float]) -> float:
    vals = [v for v in vals if v is not None]
    return sum(vals) / len(vals) if vals else 0.0


def _field_values(output: RunnerOutput) -> dict[str, str | None]:
    return {f.field: f.value for f in output.fields}


def score_rung(
    dataset: Dataset, runs: list[list[RunnerOutput]]
) -> dict:
    """runs[item_index][k] -> the three scores for one rung configuration."""
    det_items: list[float] = []
    acc_items: list[float | None] = []
    cov_items: list[float] = []
    tokens_items: list[float] = []
    dollars_items: list[float] = []
    latency_items: list[float] = []
    human_items: list[float] = []

    for item, k_outputs in zip(dataset.items, runs):
        gold_flat = flatten_json(item.gold)
        paths = list(gold_flat.keys())
        k = len(k_outputs)
        value_maps = [_field_values(o) for o in k_outputs]

        # determinism: modal-value share per field, averaged over fields
        shares = []
        for p in paths:
            vals = [m.get(p) for m in value_maps]
            modal = max(set(vals), key=vals.count)
            shares.append(vals.count(modal) / k)
        det_items.append(_mean(shares))

        # accuracy on answered + coverage, pooled over the K runs
        answered = correct = 0
        for m in value_maps:
            for p in paths:
                v = m.get(p)
                if v is None:
                    continue
                answered += 1
                node = schema_node_for_path(dataset.output_schema, p)
                if values_match(v, gold_flat[p], node):
                    correct += 1
        cov_items.append(answered / (k * len(paths)) if paths else 0.0)
        acc_items.append(correct / answered if answered else None)

        # cost: mean per single pass (the K runs are the instrument, not the bill)
        tokens_items.append(_mean([o.cost.tokens for o in k_outputs]))
        dollars_items.append(_mean([o.cost.dollars for o in k_outputs]))
        latency_items.append(_mean([o.cost.latency_s for o in k_outputs]))
        human_items.append(_mean([o.cost.human_minutes for o in k_outputs]))

    det_lo, det_hi = _bootstrap_ci(det_items)
    acc_lo, acc_hi = _bootstrap_ci(acc_items)
    return {
        "determinism": {
            "field_agreement": round(_mean(det_items), 4),
            "delta": 0.0,
            "ci_low": det_lo,
            "ci_high": det_hi,
        },
        "accuracy": {
            "accuracy_on_answered": round(_mean(acc_items), 4),
            "coverage": round(_mean(cov_items), 4),
            "delta": 0.0,
            "ci_low": acc_lo,
            "ci_high": acc_hi,
        },
        "cost": {
            "tokens": int(round(_mean(tokens_items))),
            "dollars": round(_mean(dollars_items), 6),
            "latency_s": round(_mean(latency_items), 3),
            "human_minutes": round(_mean(human_items), 3),
            "delta_dollars": 0.0,
        },
    }


def field_state(value: str | None, gold_value, node: dict) -> str:
    """One field's outcome in one run: correct / wrong / abstained."""
    if value is None:
        return "abstained"
    return "correct" if values_match(value, gold_value, node) else "wrong"


def explain_transitions(
    dataset: Dataset,
    prev_runs: list[list[RunnerOutput]],
    new_runs: list[list[RunnerOutput]],
    max_examples: int = 40,
) -> dict:
    """What a rung actually DID vs the previous one: per-field state transitions
    (pooled over items × K runs) + concrete before→after examples (k=0 only)."""
    counts: dict[str, int] = {}
    examples: list[dict] = []
    for idx, (item, prev_k, new_k) in enumerate(zip(dataset.items, prev_runs, new_runs)):
        gold_flat = flatten_json(item.gold)
        for k, (po, no) in enumerate(zip(prev_k, new_k)):
            pm, nm = _field_values(po), _field_values(no)
            for p, gv in gold_flat.items():
                node = schema_node_for_path(dataset.output_schema, p)
                ps = field_state(pm.get(p), gv, node)
                ns = field_state(nm.get(p), gv, node)
                key = f"{ps}->{ns}"
                counts[key] = counts.get(key, 0) + 1
                changed_value = pm.get(p) != nm.get(p)
                if k == 0 and (ps != ns or changed_value) and len(examples) < max_examples:
                    examples.append({
                        "item": idx,
                        "field": p,
                        "before": pm.get(p),
                        "after": nm.get(p),
                        "gold": None if gv is None else str(gv),
                        "change": key if ps != ns else "reformatted",
                    })
    return {"transitions": counts, "examples": examples}


def apply_deltas(rungs: list[dict], baseline: dict | None = None) -> None:
    """Fill delta fields vs the previous entry (or vs a fixed baseline, for ablations)."""
    prev = baseline
    for r in rungs:
        if prev is not None:
            r["determinism"]["delta"] = round(
                r["determinism"]["field_agreement"] - prev["determinism"]["field_agreement"], 4
            )
            r["accuracy"]["delta"] = round(
                r["accuracy"]["accuracy_on_answered"] - prev["accuracy"]["accuracy_on_answered"], 4
            )
            r["cost"]["delta_dollars"] = round(
                r["cost"]["dollars"] - prev["cost"]["dollars"], 6
            )
        prev = r if baseline is None else baseline

"""Per-rung internals for the dashboard's rung-by-rung view.

Everything here is computed from runs that already happened (or from cached
calls), so it adds no model traffic. Stored under each rung's "diagnostics"
key in results.json.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bench.flatten import flatten_json, schema_node_for_path
from bench.llm import LLMClient
from bench.normalize import values_match
from bench.parse import parse_reply
from bench.pipeline import CONF_THRESHOLD
from bench.prompts import N_VARIANTS, base_messages
from schemas.adapter import Dataset
from schemas.runner import RunnerOutput


def _mean(vals):
    vals = list(vals)
    return round(sum(vals) / len(vals), 4) if vals else None


def abstention_calibration(dataset: Dataset, rung0_runs: list[list[RunnerOutput]]) -> dict:
    """Is the model's self-reported confidence a usable abstention signal?"""
    conf_correct, conf_wrong = [], []
    for item, k_outputs in zip(dataset.items, rung0_runs):
        gold = flatten_json(item.gold)
        for out in k_outputs:
            for f in out.fields:
                if f.value is None:
                    continue
                node = schema_node_for_path(dataset.output_schema, f.field)
                (conf_correct if values_match(f.value, gold.get(f.field), node)
                 else conf_wrong).append(f.confidence)
    return {
        "threshold": CONF_THRESHOLD,
        "n_correct": len(conf_correct),
        "n_wrong": len(conf_wrong),
        "mean_conf_correct": _mean(conf_correct),
        "mean_conf_wrong": _mean(conf_wrong),
        "wrong_above_threshold": sum(c >= CONF_THRESHOLD for c in conf_wrong),
        "correct_below_threshold": sum(c < CONF_THRESHOLD for c in conf_correct),
    }


def voting_variants(client: LLMClient, dataset: Dataset, k: int) -> dict:
    """Per-variant accuracy + agreement, replayed from the cache (no new calls
    when rung 5 already ran)."""
    per_variant_correct = [[] for _ in range(N_VARIANTS)]
    full_agreement = []
    for item in dataset.items:
        gold = flatten_json(item.gold)
        for ki in range(k):
            flats = []
            for v in range(N_VARIANTS):
                resp = client.chat(
                    base_messages(dataset.prompt or "", dataset.output_schema,
                                  item.doc, item.trusted_record, v),
                    sample_index=ki,
                )
                ans, _, _ = parse_reply(resp.text)
                flats.append(flatten_json(ans) if ans else {})
            for p, gv in gold.items():
                node = schema_node_for_path(dataset.output_schema, p)
                canon = []
                for v in range(N_VARIANTS):
                    val = flats[v].get(p)
                    per_variant_correct[v].append(
                        1.0 if val is not None and values_match(val, gv, node) else 0.0
                    )
                    canon.append(str(val))
                full_agreement.append(1.0 if len(set(canon)) == 1 else 0.0)
    return {
        "variant_accuracy": [_mean(c) for c in per_variant_correct],
        "full_agreement_rate": _mean(full_agreement),
    }


def escalation_reasons(dataset: Dataset, rung5_runs: list[list[RunnerOutput]]) -> dict:
    """Why fields reach the human at rung 6, from the rung-5 outputs it sees."""
    reasons = {"abstained": 0, "conflict_verdict": 0, "low_confidence": 0}
    escalated_item_runs = 0
    total_item_runs = 0
    for k_outputs in rung5_runs:
        for out in k_outputs:
            total_item_runs += 1
            hit = False
            for f in out.fields:
                if f.value is None:
                    reasons["abstained"] += 1
                    hit = True
                elif f.verdict == "conflicts":
                    reasons["conflict_verdict"] += 1
                    hit = True
                elif f.confidence < CONF_THRESHOLD:
                    reasons["low_confidence"] += 1
                    hit = True
            escalated_item_runs += hit
    return {
        "reasons": reasons,
        "escalated_item_runs": escalated_item_runs,
        "total_item_runs": total_item_runs,
    }

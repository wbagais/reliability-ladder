"""Per-field run outputs — the sidecar to results.json.

results.json holds aggregates (it is loaded whole by the app, so it must stay
small). The actual field-by-field outputs of every rung go here instead, as
JSONL: one line per (config, item, k), streamed on read so a large private run
never has to be loaded into memory at once.

Each field record carries the value the rung produced AND its status against
gold — "correct", "wrong", or "abstained" — which is what the viewer colours.

Line kinds:
  {"kind": "item",   "item": 3, "doc": "...", "gold": {...}}
  {"kind": "output", "config": "rung3", "rung": 3, "item": 3, "k": 0,
   "fields": [{"field": "total", "value": "42.00", "gold": "42.00",
               "status": "correct", "verdict": "matches", "confidence": 0.9}]}
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bench.flatten import flatten_json, schema_node_for_path
from bench.metrics import field_state
from schemas.adapter import Dataset
from schemas.runner import RunnerOutput

DOC_EXCERPT_CHARS = 4000


def sidecar_path(results_path: str | Path) -> Path:
    """results.json -> results.outputs.jsonl"""
    p = Path(results_path)
    return p.with_suffix("").with_suffix(".outputs.jsonl") if p.suffix else Path(
        str(p) + ".outputs.jsonl"
    )


def write_outputs(
    path: str | Path,
    dataset: Dataset,
    runs_by_config: dict[str, list[list[RunnerOutput]]],
) -> Path:
    """Write every rung's per-field output, with status against gold."""
    path = Path(path)
    with path.open("w") as fh:
        for idx, item in enumerate(dataset.items):
            fh.write(json.dumps({
                "kind": "item",
                "item": idx,
                "doc": item.doc[:DOC_EXCERPT_CHARS],
                "gold": item.gold,
            }, ensure_ascii=False) + "\n")

        for config, runs in runs_by_config.items():
            rung = int(config.replace("rung", "").replace("ablation", ""))
            is_ablation = config.startswith("ablation")
            for idx, (item, k_outputs) in enumerate(zip(dataset.items, runs)):
                gold_flat = flatten_json(item.gold)
                for k, out in enumerate(k_outputs):
                    fields = []
                    for f in out.fields:
                        node = schema_node_for_path(dataset.output_schema, f.field)
                        gv = gold_flat.get(f.field)
                        fields.append({
                            "field": f.field,
                            "value": f.value,
                            "gold": None if gv is None else str(gv),
                            "status": field_state(f.value, gv, node),
                            "verdict": f.verdict,
                            "confidence": f.confidence,
                        })
                    fh.write(json.dumps({
                        "kind": "output",
                        "config": config,
                        "rung": rung,
                        "ablation": is_ablation,
                        "item": idx,
                        "k": k,
                        "fields": fields,
                    }, ensure_ascii=False) + "\n")
    return path


def read_items(path: str | Path) -> dict[int, dict]:
    """The item header lines (doc excerpt + gold), keyed by item index."""
    items: dict[int, dict] = {}
    with Path(path).open() as fh:
        for line in fh:
            rec = json.loads(line)
            if rec.get("kind") != "item":
                break
            items[rec["item"]] = rec
    return items


def read_outputs(
    path: str | Path,
    item: int | None = None,
    k: int | None = None,
    include_ablations: bool = False,
) -> list[dict]:
    """Stream the output lines, filtering as we go (never loads the whole file)."""
    out: list[dict] = []
    with Path(path).open() as fh:
        for line in fh:
            rec = json.loads(line)
            if rec.get("kind") != "output":
                continue
            if item is not None and rec["item"] != item:
                continue
            if k is not None and rec["k"] != k:
                continue
            if not include_ablations and rec.get("ablation"):
                continue
            out.append(rec)
    return out

"""Leaf-path flattening — how nested JSON output stays data-agnostic.

Any output object is flattened to {leaf_path: scalar}, e.g.
    {"vendor": {"name": "Acme"}, "lines": [{"price": 1}]}
    -> {"vendor.name": "Acme", "lines[0].price": 1}
Every leaf path is a "field" for the Runner contract and all metrics.
Arrays are compared by index (MVP). A path maps back to its schema node by
stripping indices, so normalization/format checks stay schema-driven.
"""

from __future__ import annotations

import re

_INDEX_RE = re.compile(r"\[\d+\]")


def index_free_path(path: str) -> str:
    """'lines[0].price' -> 'lines.price' (how models key confidence maps)."""
    return _INDEX_RE.sub("", path)


def flatten_json(obj, prefix: str = "") -> dict[str, object]:
    """Flatten nested dicts/lists to {dot-and-index path: scalar}."""
    out: dict[str, object] = {}
    if isinstance(obj, dict):
        for k, v in obj.items():
            key = f"{prefix}.{k}" if prefix else str(k)
            out.update(flatten_json(v, key))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            out.update(flatten_json(v, f"{prefix}[{i}]"))
    else:
        out[prefix] = obj
    return out


def schema_node_for_path(schema: dict, path: str) -> dict:
    """Walk a JSON Schema to the node describing `path` (indices stripped).

    Handles root-array schemas: a path like "[0].name" has an empty first
    segment after index-stripping, which just unwraps the array.
    """
    node = schema or {}
    for part in _INDEX_RE.sub("", path).split("."):
        while node.get("type") == "array":
            node = node.get("items", {})
        if part == "":
            continue
        node = (node.get("properties") or {}).get(part, {})
    while node.get("type") == "array":
        node = node.get("items", {})
    return node


def schema_field_names(schema: dict) -> list[str]:
    """Index-free leaf field names of a schema (arrays shown as `name[]`)."""
    names: list[str] = []

    def walk(node: dict, prefix: str):
        if node.get("type") == "array":
            walk(node.get("items", {}), f"{prefix}[]")
        elif node.get("type") == "object" or "properties" in node:
            for k, v in (node.get("properties") or {}).items():
                walk(v, f"{prefix}.{k}" if prefix else k)
        else:
            names.append(prefix)

    walk(schema or {}, "")
    return names


def fields_to_schema(fields: list[str]) -> dict:
    """Backward compatibility: a flat field list -> trivial all-string schema."""
    return {
        "type": "object",
        "properties": {f: {"type": "string"} for f in fields},
        "required": list(fields),
    }

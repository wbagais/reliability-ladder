"""The ONE runtime adapter: user-shape JSON (v2, or legacy v1) -> Dataset.

Also home of the upload validator. Errors are plain language so a user can fix
their file themselves — their data never needs to be shared with anyone.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from bench.flatten import fields_to_schema
from bench.normalize import normalize_number
from schemas.adapter import Dataset, Item

DEFAULT_ECONOMICS = {
    "value_correct": 1.0,
    "cost_wrong": 10.0,
    "cost_abstain": 0.5,
    "dollars_per_human_min": 1.0,
}

_TYPE_NAMES = {str: "a string", bool: "a boolean", int: "a number", float: "a number"}


def _is_v1(data: dict) -> bool:
    return "fields" in data and "output_schema" not in data


def _convert_v1_item(raw: dict) -> dict:
    """Legacy per-field gold list -> v2 gold object (verdicts are derived, not stored)."""
    gold_obj = {g["field"]: g.get("value") for g in raw.get("gold", [])}
    return {
        "doc": raw.get("doc", ""),
        "gold": gold_obj,
        "trusted_record": raw.get("trusted_record"),
    }


def _check_gold(gold, node, path: str, where: str, errors: list[str]) -> None:
    """Recursively check gold against its schema node. Permissive on anything
    the schema leaves open (unresolved $ref, missing properties): never a
    false error just because the schema is partial."""
    if not isinstance(node, dict) or not node or "$ref" in node:
        return
    label = f"gold.{path}" if path else "gold"
    ntype = node.get("type")
    if ntype == "array":
        if gold is not None and not isinstance(gold, list):
            errors.append(f"{where}: {label} should be a list (output_schema says array).")
            return
        for i, v in enumerate(gold or []):
            _check_gold(v, node.get("items", {}), f"{path}[{i}]", where, errors)
        return
    if ntype == "object" or "properties" in node:
        if gold is not None and not isinstance(gold, dict):
            errors.append(f"{where}: {label} should be an object (output_schema says object).")
            return
        props = node.get("properties") or {}
        for k, v in (gold or {}).items():
            child = props.get(k)
            if child is None:
                if props and node.get("unevaluatedProperties") is False \
                        or node.get("additionalProperties") is False:
                    errors.append(f'{where}: gold has "{path + "." if path else ""}{k}" '
                                  "but output_schema does not define that field.")
                continue  # schema is open here — permissive
            _check_gold(v, child, f"{path}.{k}" if path else k, where, errors)
        return
    # leaf
    if gold is None:
        return
    if ntype in ("number", "integer") and normalize_number(gold) is None:
        errors.append(f'{where}: {label} is "{gold}" but output_schema says it '
                      "should be a number.")
    elif (ntype or "string") == "string" and not isinstance(gold, (str, int, float)):
        errors.append(f"{where}: {label} is {_TYPE_NAMES.get(type(gold), type(gold).__name__)} "
                      "but output_schema says it should be a string.")


def _schema_ok(schema) -> bool:
    """A usable root schema: an object with properties, or an array of them."""
    if not isinstance(schema, dict):
        return False
    if schema.get("properties"):
        return True
    return schema.get("type") == "array" and isinstance(schema.get("items"), dict)


def validate(data) -> list[str]:
    """Structural check with human-readable messages. Empty list = valid."""
    errors: list[str] = []
    if not isinstance(data, dict):
        return ["The file must contain a JSON object at the top level, not a "
                f"{type(data).__name__}."]
    if "domains" in data and "k_runs" in data and "items" not in data:
        return ["This looks like a RESULTS file (benchmark output), not a dataset. "
                "Load it on the Dashboard page — the uploader here expects your "
                "input data (items with doc + gold)."]

    if _is_v1(data):
        if not isinstance(data.get("fields"), list) or not data["fields"]:
            errors.append('"fields" must be a non-empty list of field names.')
        schema = fields_to_schema(data.get("fields") or [])
    else:
        schema = data.get("output_schema")
        if not _schema_ok(schema):
            errors.append('Missing or unusable "output_schema": a JSON Schema whose root is '
                          'an object with "properties", or an array whose "items" describe '
                          'the elements (or a legacy flat "fields" list).')
            schema = {}

    items = data.get("items")
    if not isinstance(items, list) or not items:
        errors.append('"items" must be a non-empty list. Aim for 50-100 items.')
        return errors

    v1 = _is_v1(data)
    root_is_array = schema.get("type") == "array"
    for i, raw in enumerate(items):
        where = f"item {i}"
        if not isinstance(raw, dict):
            errors.append(f"{where}: must be an object with doc/gold.")
            continue
        doc = raw.get("doc")
        if not isinstance(doc, str) or not doc.strip():
            errors.append(f'{where}: "doc" must be a non-empty string (the raw input text).')
        gold = raw.get("gold")
        if v1:
            if not isinstance(gold, list):
                errors.append(f'{where}: legacy format needs "gold" as a list of '
                              '{field, value, verdict} objects.')
                continue
            gold = _convert_v1_item(raw)["gold"]
        expected = list if root_is_array else dict
        if not isinstance(gold, expected):
            shape = "array" if root_is_array else "object"
            errors.append(f'{where}: "gold" must be a JSON {shape} matching output_schema '
                          '(the correct answer for this item).')
            continue
        tr = raw.get("trusted_record")
        if tr is not None and not isinstance(tr, (dict, list)):
            errors.append(f'{where}: "trusted_record" must be a JSON object/array (or '
                          'omitted entirely for pure extraction).')
        if schema:
            _check_gold(gold, schema, "", where, errors)

    econ = data.get("economics")
    if econ is not None:
        if not isinstance(econ, dict):
            errors.append('"economics" must be an object of numbers, e.g. '
                          '{"value_correct": 1.0, "cost_wrong": 10.0}.')
        else:
            for k, v in econ.items():
                if not isinstance(v, (int, float)):
                    errors.append(f'economics.{k}: must be a number, got "{v}".')
    return errors


def _resolve_refs(node, base_dir: Path, depth: int = 0):
    """Inline file `$ref`s (e.g. "./common/measuring.json") so the schema is
    self-contained. Refs whose file can't be found are dropped, leaving an open
    node — validation stays permissive there instead of erroring falsely."""
    if depth > 20 or not isinstance(node, (dict, list)):
        return node
    if isinstance(node, list):
        return [_resolve_refs(v, base_dir, depth) for v in node]
    ref = node.get("$ref")
    if isinstance(ref, str) and not ref.startswith("#"):
        rest = {k: v for k, v in node.items() if k != "$ref"}
        path = base_dir / ref.split("#", 1)[0]
        try:
            loaded = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            node = rest  # unreachable ref: degrade to an open node
        else:
            loaded.pop("$id", None), loaded.pop("$schema", None)
            node = {**loaded, **rest}  # local keys (description etc.) win
            base_dir = path.resolve().parent
    return {k: _resolve_refs(v, base_dir, depth + 1) for k, v in node.items()}


def load_dataset(source: str | Path | dict) -> Dataset:
    """Load + validate a v1/v2 upload. Raises ValueError listing every problem."""
    base_dir = Path.cwd()
    if isinstance(source, (str, Path)):
        base_dir = Path(source).resolve().parent
        data = json.loads(Path(source).read_text())
    else:
        data = source
    if isinstance(data.get("output_schema"), dict):
        data = {**data, "output_schema": _resolve_refs(data["output_schema"], base_dir)}

    # long prompts can live in a plain text file next to the JSON
    if data.get("prompt_file") and not data.get("prompt"):
        pf = Path(data["prompt_file"])
        if not pf.is_absolute():
            pf = base_dir / pf
        if not pf.exists():
            raise ValueError(
                f'"prompt_file" points to {pf} but there is no such file '
                "(the path is resolved relative to the JSON file)."
            )
        data = {**data, "prompt": pf.read_text().strip()}
    errors = validate(data)
    if errors:
        raise ValueError("The data file has problems:\n- " + "\n- ".join(errors))

    if _is_v1(data):
        schema = fields_to_schema(data["fields"])
        raw_items = [_convert_v1_item(it) for it in data["items"]]
    else:
        schema = data["output_schema"]
        raw_items = data["items"]

    items = [
        Item(doc=r["doc"], gold=r["gold"], trusted_record=r.get("trusted_record"))
        for r in raw_items
    ]
    economics = {**DEFAULT_ECONOMICS, **(data.get("economics") or {})}
    return Dataset(
        domain=data.get("domain", "user_data"),
        output_schema=schema,
        items=items,
        prompt=data.get("prompt"),
        economics=economics,
    )

"""Array-root schemas with file $refs — the shape of the user's private data."""

import json

from bench.adapters.user_upload import load_dataset, validate
from bench.flatten import flatten_json, schema_node_for_path

MEASURING = {
    "type": "object",
    "properties": {
        "value": {"type": "number"},
        "unit": {"type": "string"},
    },
}

ARRAY_SCHEMA = {
    "type": "array",
    "items": {
        "type": "object",
        "unevaluatedProperties": False,
        "properties": {
            "instruction": {"type": "string"},
            "pH": {"type": "object", "$ref": "./common/measuring.json"},
            "materialDocument": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "writtenName": {"type": "string"},
                        "substance": {"type": "array", "items": {"type": "string"}},
                    },
                },
            },
        },
    },
}

GOLD = [
    {
        "instruction": "Dissolve 5 g in 100 mL water",
        "pH": {"value": 7.2, "unit": "pH"},
        "materialDocument": [
            {"writtenName": "water", "substance": ["H2O"]},
            {"writtenName": "salt"},
        ],
    }
]


def _data(schema=ARRAY_SCHEMA):
    return {
        "domain": "sop",
        "output_schema": schema,
        "items": [{"doc": "Dissolve 5 g of salt in 100 mL water, adjust to pH 7.2.",
                   "gold": GOLD}],
    }


def test_array_root_schema_validates():
    assert validate(_data()) == []


def test_array_root_gold_must_be_list():
    bad = _data()
    bad["items"][0]["gold"] = {"instruction": "x"}
    assert any("must be a JSON array" in e for e in validate(bad))


def test_unresolved_ref_is_permissive_not_false_error():
    # pH's inner keys live behind a $ref the validator can't see — no errors
    assert validate(_data()) == []


def test_wrong_type_inside_array_is_caught():
    bad = _data()
    bad["items"][0]["gold"] = [{"instruction": {"nested": "not-a-string"}}]
    assert any("should be a string" in e for e in validate(bad))


def test_refs_resolve_from_disk(tmp_path):
    (tmp_path / "common").mkdir()
    (tmp_path / "common" / "measuring.json").write_text(json.dumps(MEASURING))
    p = tmp_path / "data.json"
    p.write_text(json.dumps(_data()))
    ds = load_dataset(p)
    node = schema_node_for_path(ds.output_schema, "[0].pH.value")
    assert node.get("type") == "number"
    # pipeline-side flattening of an array-root gold works too
    flat = flatten_json(ds.items[0].gold)
    assert flat["[0].pH.value"] == 7.2
    assert flat["[0].materialDocument[1].writtenName"] == "salt"
    assert schema_node_for_path(ds.output_schema, "[0].materialDocument[1].writtenName") \
        == {"type": "string"}


def test_load_dataset_without_ref_files_still_works():
    ds = load_dataset(_data())
    assert len(ds.items) == 1
    assert schema_node_for_path(ds.output_schema, "[0].instruction") == {"type": "string"}

from bench.flatten import (
    fields_to_schema,
    flatten_json,
    index_free_path,
    schema_field_names,
    schema_node_for_path,
)

NESTED = {
    "type": "object",
    "properties": {
        "vendor": {"type": "object", "properties": {"name": {"type": "string"}}},
        "lines": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"price": {"type": "number"}},
            },
        },
        "total": {"type": "number"},
    },
}


def test_flatten_nested():
    obj = {"vendor": {"name": "Acme"}, "lines": [{"price": 1.5}, {"price": 2}], "total": 3.5}
    assert flatten_json(obj) == {
        "vendor.name": "Acme",
        "lines[0].price": 1.5,
        "lines[1].price": 2,
        "total": 3.5,
    }


def test_schema_node_for_path_strips_indices():
    assert schema_node_for_path(NESTED, "lines[3].price") == {"type": "number"}
    assert schema_node_for_path(NESTED, "vendor.name") == {"type": "string"}
    assert schema_node_for_path(NESTED, "nope") == {}


def test_schema_field_names():
    assert schema_field_names(NESTED) == ["vendor.name", "lines[].price", "total"]


def test_fields_to_schema_roundtrip():
    schema = fields_to_schema(["a", "b"])
    assert schema["properties"]["a"] == {"type": "string"}
    assert schema["required"] == ["a", "b"]


def test_index_free_path():
    assert index_free_path("lines[0].price") == "lines.price"

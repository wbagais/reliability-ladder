"""
CONTRACT 3 (v2) — Dataset adapter interface.

Any dataset (SROIE, or a user-uploaded sample) maps to ONE standard shape.
Adding a dataset = producing one JSON file. Everything downstream (rungs,
metrics, app) stays unchanged.

v2 changes (2026-08-16, logged in docs/decisions.md):
- `output_schema` (a JSON Schema) replaces the flat `fields` list, so the
  desired output can be any nested JSON object. A flat `fields` list is still
  accepted and auto-converts to a trivial all-string schema.
- `gold` is the full correct output JSON object (the answer key — never shown
  to the model), not a per-field list.
- `trusted_record` is OPTIONAL. Present -> verification task with
  matches/conflicts/not_found verdicts. Absent -> pure extraction ("n_a").

Internally the schema is flattened to leaf paths ("vendor.name",
"line_items[0].price"); every leaf path is a "field" for the Runner contract
and all metrics (see bench/flatten.py).
"""

from dataclasses import dataclass, field
from typing import Literal, Protocol

Verdict = Literal["matches", "conflicts", "not_found", "n_a"]


@dataclass
class Item:
    doc: str                          # raw input text of the document
    gold: dict                        # correct output object (answer key, hidden from model)
    trusted_record: dict | None = None  # reference to verify against; None = pure extraction


@dataclass
class Dataset:
    domain: str
    output_schema: dict               # JSON Schema of the desired output object
    items: list[Item] = field(default_factory=list)
    prompt: str | None = None         # user's task instruction (default generated if None)
    economics: dict | None = None     # value_correct, cost_wrong, cost_abstain, ...

    @property
    def verification_mode(self) -> bool:
        return any(it.trusted_record is not None for it in self.items)


class Adapter(Protocol):
    """Maps a raw dataset into the standard Dataset."""

    def load(self) -> Dataset:
        ...


# --- USER-UPLOAD FORMAT (JSON the user fills in) -----------------------------
# A user brings ~50-100 items in this shape to get their own curve:
#
# {
#   "domain": "my_invoices",
#   "prompt": "Extract the fields below from the invoice text.",   // optional
#   "output_schema": {                       // any JSON Schema; nesting allowed
#     "type": "object",
#     "properties": {
#       "total":  {"type": "number"},
#       "date":   {"type": "string", "format": "date"},
#       "vendor": {"type": "object", "properties": {"name": {"type": "string"}}}
#     },
#     "required": ["total", "date"]
#   },
#   "economics": {                           // optional, adjustable in the app
#     "value_correct": 1.0, "cost_wrong": 10.0, "cost_abstain": 0.5,
#     "dollars_per_human_min": 1.0
#   },
#   "items": [
#     {
#       "doc": "raw text of the document...",
#       "gold": {"total": 42.0, "date": "2024-01-01", "vendor": {"name": "Acme"}},
#       "trusted_record": {"total": "42.00", "date": "2024-01-02"}   // optional
#     }
#   ]
# }
#
# Legacy v1 (flat `fields` list + per-field gold with verdicts) is still read.

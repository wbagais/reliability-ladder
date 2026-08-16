"""
CONTRACT 3 — Dataset adapter interface.

Any dataset (SROIE, CORD, or a user-uploaded sample) maps to ONE standard
shape. Adding a dataset = writing one adapter. Everything downstream
(rungs, metrics, app) stays unchanged.

This is also the shape a USER uploads for the "bring your own data" flow.
"""

from dataclasses import dataclass
from typing import Literal, Protocol

Verdict = Literal["matches", "conflicts", "not_found"]


@dataclass
class GoldField:
    """The human-labeled correct answer for one field. This is the expensive part."""
    field: str
    value: str | None
    verdict: Verdict


@dataclass
class Item:
    doc: str                    # raw input text / OCR of the document
    trusted_record: dict        # structured source of truth to verify against
    gold: list[GoldField]       # human-labeled correct value + verdict per field


class Adapter(Protocol):
    """Maps a raw dataset into a list of standard Items."""

    domain: str                 # e.g. "sroie"
    fields: list[str]           # field list for this domain

    def load(self) -> list[Item]:
        ...


# --- USER-UPLOAD FORMAT (JSON the user fills in) -----------------------------
# A user brings ~50-100 items in this shape to get their own curve:
#
# {
#   "domain": "my_invoices",
#   "fields": ["total", "date", "vendor"],
#   "economics": {
#     "value_correct": 1.0,
#     "cost_wrong": 10.0,
#     "cost_abstain": 0.5,
#     "dollars_per_compute": 1.0,
#     "dollars_per_human_min": 1.0
#   },
#   "items": [
#     {
#       "doc": "raw text of the document...",
#       "trusted_record": {"total": "42.00", "date": "2024-01-01", "vendor": "Acme"},
#       "gold": [
#         {"field": "total",  "value": "42.00",      "verdict": "matches"},
#         {"field": "date",   "value": "2024-01-02", "verdict": "conflicts"},
#         {"field": "vendor", "value": null,          "verdict": "not_found"}
#       ]
#     }
#   ]
# }

"""Deterministic value normalization — the core of rung 1 and of all scoring.

Normalization is schema-driven: the field's JSON-Schema node decides whether a
value is treated as a number, a date, or free text. The same normalization is
used when scoring accuracy, so rungs are compared on meaning, not formatting.
"""

from __future__ import annotations

import re
from datetime import datetime

_DATE_FORMATS = [
    "%Y-%m-%d",
    "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y",
    "%d/%m/%y", "%d-%m-%y",
    "%d %b %Y", "%d %B %Y", "%d-%b-%Y", "%d-%b-%y",
    "%b %d, %Y", "%B %d, %Y",
    "%Y/%m/%d", "%Y%m%d", "%d%m%Y",
    "%m/%d/%Y",  # last: least likely in our data (day-first regions)
]

_NUM_RE = re.compile(r"-?\d[\d,]*\.?\d*")


def normalize_date(value: str) -> str | None:
    """Parse a date in common formats -> ISO YYYY-MM-DD, else None."""
    v = value.strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(v, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def normalize_number(value: str | int | float) -> str | None:
    """Strip currency symbols/commas -> canonical decimal string, else None."""
    if isinstance(value, (int, float)):
        return f"{float(value):.2f}"
    m = _NUM_RE.search(value.replace(" ", ""))
    if not m:
        return None
    try:
        return f"{float(m.group().replace(',', '')):.2f}"
    except ValueError:
        return None


def normalize_text(value: str) -> str:
    """Case-fold, collapse whitespace, drop spacing around punctuation."""
    v = re.sub(r"\s+", " ", str(value)).strip().upper()
    v = re.sub(r"\s*([,.;:&/-])\s*", r"\1", v)
    return v


def normalize_value(value, field_schema: dict | None) -> str | None:
    """Normalize one scalar according to its schema node. None if unparseable."""
    if value is None:
        return None
    s = str(value).strip()
    if s == "":
        return None
    schema = field_schema or {}
    ftype = schema.get("type", "string")
    if ftype in ("number", "integer") or schema.get("format") in ("number", "currency"):
        return normalize_number(value if isinstance(value, (int, float)) else s)
    if schema.get("format") == "date":
        return normalize_date(s) or normalize_text(s)
    return normalize_text(s)


def values_match(a, b, field_schema: dict | None) -> bool:
    """Schema-aware equality: both normalize to the same non-None value."""
    na, nb = normalize_value(a, field_schema), normalize_value(b, field_schema)
    if na is None or nb is None:
        return na is None and nb is None
    return na == nb


def format_ok(value, field_schema: dict | None) -> bool:
    """Deterministic format/type check for rung 1/2: value parses per schema."""
    if value is None:
        return False
    schema = field_schema or {}
    ftype = schema.get("type", "string")
    if ftype in ("number", "integer") or schema.get("format") in ("number", "currency"):
        return normalize_number(value if isinstance(value, (int, float)) else str(value)) is not None
    if schema.get("format") == "date":
        return normalize_date(str(value).strip()) is not None
    if "enum" in schema:
        return normalize_text(str(value)) in {normalize_text(str(e)) for e in schema["enum"]}
    return str(value).strip() != ""

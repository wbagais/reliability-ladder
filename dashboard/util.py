"""Shared helpers. Record identity is by SPAN KEY everywhere — the scorer's
own rule (`ladder.score._span_key`), reused rather than reimplemented so the
dashboard cannot drift from the pipeline's definition. record_id is a
POSITION and is never used for identity (spec R4 criteria)."""
from __future__ import annotations

from ladder.score import _span_key


def span_key(doc_id: str, spans) -> tuple:
    """(doc_id, frozenset of (start, end)) — segment order carries no meaning."""
    return _span_key(doc_id, spans)


def format_span_param(spans) -> str:
    """Spans as a URL-safe string, canonically ordered: "5:11,20:27".

    ":" rather than "-" so the schema-invalid (-1,-1) spans R4 must still
    address stay parseable."""
    return ",".join(f"{a}:{b}" for a, b in sorted((int(a), int(b)) for a, b in spans))


def parse_span_param(s: str) -> list[tuple[int, int]]:
    out = []
    for seg in s.split(","):
        a, _, b = seg.partition(":")
        out.append((int(a), int(b)))
    return sorted(out)

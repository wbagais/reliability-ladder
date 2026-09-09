"""C1 — no export path contains corpus text.

The desk-file rule, applied to every export: ids, offsets, codes, vocabulary
labels and numbers only. Two layers:

- `scrub_payload` structurally removes every text-bearing key before an export
  payload is built (the corpus reaches a record as `text`, `context`,
  `source`, `quoted`, `snippet`, `body`, `post`, and negation cues quote the
  post's own words).
- `assert_clean` is the belt-and-braces check a test can drive with known
  corpus strings: it raises if any appears in the serialized export.

Viewing corpus text in the browser is NOT an export — the server binds to
loopback (C1) and the text never leaves the machine. Exports are the download
endpoints under /api/export/ and nothing else.
"""
from __future__ import annotations

from typing import Any

#: Keys whose values quote the source post (or a window of it), plus MODEL
#: free text (`sct_label`, `why`) which can echo the post verbatim. Candidate
#: `label`/`fsn` fields are VOCABULARY text and stay — the desk-file rule
#: allows vocabulary labels explicitly.
TEXT_BEARING_KEYS = frozenset({
    "text", "context", "source", "sources", "quoted", "snippet", "body",
    "post", "negation_cue", "span_text", "prompt", "reply", "raw",
    "messages", "content", "sct_label", "why",
})


class CorpusTextLeak(RuntimeError):
    pass


def scrub_payload(payload: Any) -> Any:
    """Recursively drop text-bearing keys. Everything else passes unchanged."""
    if isinstance(payload, dict):
        return {
            k: scrub_payload(v)
            for k, v in payload.items()
            if k not in TEXT_BEARING_KEYS
        }
    if isinstance(payload, (list, tuple)):
        return [scrub_payload(v) for v in payload]
    return payload


def assert_clean(serialized: str, known_texts: list[str] | None = None) -> None:
    """Raise CorpusTextLeak if any known corpus string appears in an export."""
    for t in known_texts or []:
        needle = t.strip()
        if len(needle) >= 12 and needle in serialized:
            raise CorpusTextLeak(
                "corpus text found in an export payload — C1 violation"
            )

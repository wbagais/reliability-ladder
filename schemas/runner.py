"""
CONTRACT 1 — the rung interface.

    apply(records, sources, cfg) -> records

Every rung (0-6) implements it, which is what makes rungs interchangeable,
execution order a config value, and a new rung twenty minutes' work rather than
an hour. Do not change the signature without both owners agreeing.

History: this file used to carry a second, field-level `Runner` shape (one
document in, per-field results + cost out) for the data-agnostic SROIE track.
That track was retired on 2026-08-22 — see docs/decisions.md — and the shape
went with it.
"""

from typing import Any, Protocol


class Rung(Protocol):
    """A rung of the CADEC ladder.

        apply(records, sources, cfg) -> records

    `records`  every record in flight, in any zone. A rung decides for itself
               which zones it acts on and leaves the rest untouched. Rung 0 is
               the exception: it receives an EMPTY list and builds records from
               `sources`.
    `sources`  doc_id -> the archived document text. Read-only, and the only
               text any rung ever sees — there is no free-text entry point.
    `cfg`      this rung's manifest section, plus the shared handles the run
               injects once: `ledger`, `registry` (a schemas.vocabulary.
               Vocabulary), `meddra`, `client`.

    A rung may mutate `zone`, `reason`, `provenance` and `checks`, plus the
    answer fields it is defined to change. It logs one ledger row per record it
    looks at, whether or not it changed anything — a rung that touched a record
    for free is still a fact about the run.
    """

    RUNG: int
    NAME: str

    def apply(
        self, records: list[Any], sources: dict[str, str], cfg: dict[str, Any]
    ) -> list[Any]: ...

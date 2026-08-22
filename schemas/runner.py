"""
CONTRACT 1 — Runner interface. Two shapes, one per track.

Every rung (0-6) implements one of these. Any rung is interchangeable: the
harness calls a rung without knowing which one it is, which is what makes
execution order a config value and a new rung twenty minutes' work.

Do not change either signature without both people agreeing — this is the
coordination surface between A's rungs and B's.

  Runner   the field-level shape: one document in, field results + cost out.
           Used by the data-agnostic bench/ track (SROIE and user uploads).
  Rung     the record-level shape from v17 §4: a whole batch of mention
           records in, the same records back with zones and reasons updated.
           Used by the CADEC track.

They are not variants of each other. The first scores a fixed set of field
slots per document; the second routes a variable-length set of mentions whose
membership is itself part of what is being measured.
"""

from dataclasses import dataclass
from typing import Any, Literal, Protocol

Verdict = Literal["matches", "conflicts", "not_found", "n_a"]
# "n_a" (v2, 2026-08-16): pure-extraction tasks have no trusted record to
# verify against, so verdicts don't apply. See docs/decisions.md.


@dataclass
class FieldResult:
    field: str                  # leaf path, e.g. "vendor.name" or "lines[0].price"
    value: str | None          # extracted value, None if abstained/not found
    verdict: Verdict
    confidence: float           # 0.0 - 1.0


@dataclass
class Cost:
    tokens: int = 0
    dollars: float = 0.0
    latency_s: float = 0.0
    human_minutes: float = 0.0  # only rung 6 sets this


@dataclass
class RunnerOutput:
    fields: list[FieldResult]
    cost: Cost
    abstained: bool = False     # True if the rung declined to answer


class Runner(Protocol):
    """A rung. Takes one document (+ optional trusted record), returns results + cost."""

    rung: int
    name: str

    def run(self, doc: str, record: dict | None) -> RunnerOutput:
        ...


# ---------------------------------------------------------------------------
# The record-level shape (v17 §4). One batch in, the same batch back.
# ---------------------------------------------------------------------------


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

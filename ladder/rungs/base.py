"""The rung interface. Agreed at the step-3 fixture gate; frozen after it.

    def apply(records: list[Record], sources: dict[str, str], cfg: dict) -> list[Record]

`records`  every record currently in flight, in any zone. A rung decides for
           itself which zones it acts on and leaves the rest untouched.
`sources`  doc_id -> the archived post text. Read-only. This is the only text
           any rung ever sees; there is no free-text entry point in the package.
`cfg`      the manifest section for this rung, plus two shared handles:
             cfg["ledger"]    -> Ledger, for cost + zone transitions
             cfg["registry"]  -> Registry, the SNOMED index (may be None)
             cfg["client"]    -> LLM client, for rungs that talk to a model

A rung may mutate `zone`, `reason`, `provenance` and `checks`, plus the answer
fields it is defined to change. It must log one ledger row per record it looks
at, whether or not it changed anything — a rung that touched a record for free
is still a fact about the run.
"""

from __future__ import annotations

from typing import Any, Protocol

from ladder.schema import Record


class Rung(Protocol):
    RUNG: int
    NAME: str

    def apply(
        self, records: list[Record], sources: dict[str, str], cfg: dict[str, Any]
    ) -> list[Record]: ...


RUNG = -1
NAME = "no-op"


def apply(records: list[Record], sources: dict[str, str], cfg: dict[str, Any]) -> list[Record]:
    """The no-op rung from the step-3 gate: proves the pipeline runs end to end.

    Kept in the tree on purpose. When a real rung starts behaving oddly, running
    the pipeline with `--rungs noop` says whether the fault is in the rung or in
    the harness underneath it.
    """
    ledger = cfg.get("ledger")
    for r in records:
        if ledger:
            ledger.log(RUNG, r.doc_id, r.record_id, r.zone, "unchanged")
    return records

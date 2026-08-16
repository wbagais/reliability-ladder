"""
CONTRACT 1 — Runner interface.

Every rung (0-6) implements this signature. Any rung is interchangeable:
the app / harness can call any rung without knowing which one it is.

Do not change this signature without both people agreeing — it is the
core coordination surface between A's rungs (0-2) and B's rungs (3-6).
"""

from dataclasses import dataclass
from typing import Literal, Protocol

Verdict = Literal["matches", "conflicts", "not_found"]


@dataclass
class FieldResult:
    field: str
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
    """A rung. Takes one document + its trusted record, returns results + cost."""

    rung: int
    name: str

    def run(self, doc: str, record: dict) -> RunnerOutput:
        ...

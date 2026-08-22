"""Append-only run ledger + the cost meter.

One row per (rung, record). Nothing in this project is measured anywhere else:
the results table, the marginal-cost curve and the rung-1 reason breakdown are
all `GROUP BY` over this file. That is deliberate — two accounting paths is how
a benchmark ends up with two different numbers for the same run.

Cost is kept in the three currencies the plan insists on and never fused into
one dollar figure: tokens, seconds, human minutes. `usd` is carried alongside
because a hosted run has a real bill, but nothing downstream is allowed to add
it to human minutes.

Append-only means append-only: rows are never rewritten. A rung that changes a
record writes a new row; the record's history is the sequence of its rows.
"""

from __future__ import annotations

import json
import os
import time
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable

SCHEMA_VERSION = 1


@dataclass
class Entry:
    """One row. Fields are APPEND-ONLY — new ones go on the end, always."""

    run_id: str
    rung: int
    doc_id: str
    record_id: str
    zone: str
    outcome: str  # settled | passed | rejected | abstained | escalated | unchanged
    reason: str | None = None
    tokens_in: int = 0
    tokens_out: int = 0
    api_calls: int = 0
    latency_ms: float = 0.0
    usd: float = 0.0
    human_minutes: float = 0.0
    ts: float = field(default_factory=time.time)
    extra: dict[str, Any] = field(default_factory=dict)


class Ledger:
    """Append-only JSONL writer + the aggregations every report needs."""

    def __init__(self, path: str | os.PathLike, run_id: str, append: bool = False):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.run_id = run_id
        self._fh = self.path.open("a" if append else "w", encoding="utf-8")
        self.rows: list[Entry] = []

    # -- write ---------------------------------------------------------------

    def log(
        self,
        rung: int,
        doc_id: str,
        record_id: str,
        zone: str,
        outcome: str,
        reason: str | None = None,
        tokens_in: int = 0,
        tokens_out: int = 0,
        api_calls: int = 0,
        latency_ms: float = 0.0,
        usd: float = 0.0,
        human_minutes: float = 0.0,
        **extra: Any,
    ) -> Entry:
        e = Entry(
            run_id=self.run_id,
            rung=rung,
            doc_id=doc_id,
            record_id=record_id,
            zone=zone,
            outcome=outcome,
            reason=reason,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            api_calls=api_calls,
            latency_ms=latency_ms,
            usd=usd,
            human_minutes=human_minutes,
            extra=extra,
        )
        self.rows.append(e)
        self._fh.write(json.dumps(asdict(e), ensure_ascii=False) + "\n")
        return e

    def flush(self) -> None:
        self._fh.flush()

    def close(self) -> None:
        self._fh.flush()
        self._fh.close()

    def __enter__(self) -> "Ledger":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    # -- read ----------------------------------------------------------------

    @staticmethod
    def read(path: str | os.PathLike) -> list[Entry]:
        rows = []
        for line in Path(path).read_text(encoding="utf-8").splitlines():
            if line.strip():
                rows.append(Entry(**json.loads(line)))
        return rows

    # -- aggregate -----------------------------------------------------------

    def cost_by_rung(self, n_records: int | None = None) -> dict[int, dict[str, float]]:
        """Per-rung cost in the three currencies, never fused.

        `tokens_per_record` divides by the number of records that ENTERED the
        rung, not the batch, because a rung that only touches rejects is cheap
        precisely because few records reach it — and a per-batch average would
        hide that.
        """
        agg: dict[int, dict[str, float]] = defaultdict(
            lambda: dict(
                tokens_in=0.0,
                tokens_out=0.0,
                api_calls=0.0,
                latency_ms=0.0,
                usd=0.0,
                human_minutes=0.0,
                records=0.0,
            )
        )
        latencies: dict[int, list[float]] = defaultdict(list)
        for r in self.rows:
            a = agg[r.rung]
            a["tokens_in"] += r.tokens_in
            a["tokens_out"] += r.tokens_out
            a["api_calls"] += r.api_calls
            a["latency_ms"] += r.latency_ms
            a["usd"] += r.usd
            a["human_minutes"] += r.human_minutes
            a["records"] += 1
            if r.latency_ms:
                latencies[r.rung].append(r.latency_ms)
        for rung, a in agg.items():
            n = n_records or a["records"] or 1
            a["tokens_per_record"] = (a["tokens_in"] + a["tokens_out"]) / n
            a["p95_latency_s"] = _p95(latencies.get(rung, [])) / 1000.0
            a["reviews_per_100"] = 100.0 * sum(
                1 for r in self.rows if r.rung == rung and r.human_minutes
            ) / n
        return dict(agg)

    def reasons(self, rung: int) -> Counter:
        """The rung-1 headline: not the rate, the breakdown."""
        return Counter(r.reason for r in self.rows if r.rung == rung and r.reason)

    def zone_counts(self, rung: int) -> Counter:
        return Counter(r.zone for r in self.rows if r.rung == rung)

    def totals(self) -> dict[str, float]:
        """Batch totals. Per-record figures hide the bill."""
        return {
            "tokens": sum(r.tokens_in + r.tokens_out for r in self.rows),
            "api_calls": sum(r.api_calls for r in self.rows),
            "wall_clock_s": sum(r.latency_ms for r in self.rows) / 1000.0,
            "usd": sum(r.usd for r in self.rows),
            "human_minutes": sum(r.human_minutes for r in self.rows),
            "reviewed": sum(1 for r in self.rows if r.human_minutes),
            "rows": len(self.rows),
        }


def _p95(values: Iterable[float]) -> float:
    vals = sorted(values)
    if not vals:
        return 0.0
    idx = min(len(vals) - 1, int(round(0.95 * (len(vals) - 1))))
    return vals[idx]

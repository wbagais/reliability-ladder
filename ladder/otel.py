"""ladder/otel.py — emit ledger rows as OpenTelemetry spans.

Off unless LADDER_OTEL=1. Every run so far is reproducible without this, and an
observability layer that changed what it observed would be an odd thing to ship
in this project specifically.

    LADDER_OTEL=1 LADDER_N=0 PYTHONPATH=. python3 scripts/ladder_run.py

Points at Phoenix on localhost:4317 by default; OTEL_EXPORTER_OTLP_ENDPOINT
overrides. Phoenix UI is on :6006.

Span attributes use OTel GenAI conventions where they exist (gen_ai.*) and a
ladder.* namespace where they do not. The two that matter most have no
convention anywhere:

    ladder.denominator  which set this record counts toward
    ladder.evaluable    pass | fail | could_not_run  -- THREE values

Every finding in this project came from a denominator shifting silently or a
could-not-run being coerced into a pass or a fail. A trace without these two
renders both failures as healthy.
"""
from __future__ import annotations

import os
from typing import Any

from ladder.ledger import Ledger

ENABLED = os.environ.get("LADDER_OTEL") == "1"
ENDPOINT = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317")

_tracer = None


def tracer():
    """Lazy init so importing this module costs nothing when disabled."""
    global _tracer
    if _tracer is not None:
        return _tracer
    from opentelemetry import trace
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

    provider = TracerProvider(resource=Resource.create({
        "service.name": "ai-reliability-ladder",
    }))
    provider.add_span_processor(
        BatchSpanProcessor(OTLPSpanExporter(endpoint=ENDPOINT, insecure=True)))
    trace.set_tracer_provider(provider)
    _tracer = trace.get_tracer("ladder")
    return _tracer


class OtelLedger(Ledger):
    """A Ledger that also emits one span per row. Drop-in: same signature.

    Spans are zero-duration markers carrying latency as an attribute rather
    than as span duration, because the ledger is written after the call
    completes and back-dating a span would misreport concurrency.
    """

    def __init__(self, *a, run_meta: dict[str, Any] | None = None, **kw):
        super().__init__(*a, **kw)
        self.run_meta = run_meta or {}

    def log(self, *a, **kw):
        e = super().log(*a, **kw)
        if not ENABLED:
            return e
        try:
            self._emit(e, kw.get("denominator"), kw.get("evaluable"))
        except Exception as exc:  # never let telemetry break a run
            print(f"[otel] span dropped: {exc}")
        return e

    def _emit(self, e, denominator, evaluable):
        with tracer().start_as_current_span(f"rung{e.rung}") as sp:
            sp.set_attribute("ladder.run_id", e.run_id)
            sp.set_attribute("ladder.rung", e.rung)
            sp.set_attribute("ladder.doc_id", e.doc_id)
            sp.set_attribute("ladder.record_id", e.record_id)
            sp.set_attribute("ladder.zone", e.zone)
            sp.set_attribute("ladder.outcome", e.outcome)
            if e.reason:
                sp.set_attribute("ladder.reason", e.reason)
            if e.verdict:
                sp.set_attribute("ladder.verdict", e.verdict)

            # the two nothing else models
            if denominator:
                sp.set_attribute("ladder.denominator", str(denominator))
            sp.set_attribute("ladder.evaluable", evaluable or "unset")

            # cost, kept as three separate measures -- never fused
            sp.set_attribute("gen_ai.usage.input_tokens", e.tokens_in)
            sp.set_attribute("gen_ai.usage.output_tokens", e.tokens_out)
            sp.set_attribute("ladder.api_calls", e.api_calls)
            sp.set_attribute("ladder.latency_ms", e.latency_ms)
            sp.set_attribute("ladder.human_minutes", e.human_minutes)

            # provenance: a run is not comparable to another without these
            for k, v in self.run_meta.items():
                sp.set_attribute(f"ladder.run.{k}", str(v))

            for k, v in (e.extra or {}).items():
                if k not in ("denominator", "evaluable"):
                    sp.set_attribute(f"ladder.extra.{k}", str(v))


def run_meta(man: dict, model: str, split: str, order: list[int],
             temperature: float | None = None, backend: str = "") -> dict:
    """The provenance every run must carry. Temperature is here because rung 5's
    entire result is a function of it and it was never stamped."""
    return {
        "model": model,
        "split": split,
        "order": ",".join(str(r) for r in order),
        "temperature": temperature if temperature is not None else "n/a",
        "backend": backend,
        "snomed_release": man.get("vocabulary", {}).get("release", "?"),
        "corpus": man.get("corpus", {}).get("version", "?"),
    }

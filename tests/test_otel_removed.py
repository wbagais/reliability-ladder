"""The OpenTelemetry layer was removed 2026-08-31 — these tests keep it removed.

`ladder/otel.py` was never imported by anything. Its own docstring, and README,
documented `LADDER_OTEL=1 ... python3 scripts/ladder_run.py` as the way to turn
it on, but `ladder_run.py` never imported it either, so that command emitted no
spans and no error. Meanwhile `provenance` recorded `ladder_otel` into every
run's `env` block, so a run could claim tracing was on while producing nothing.

A provenance field that reports a capability the repo does not have is worse
than no field: provenance is the thing every number in this project is defended
with. These tests fail if any of the three come back.
"""
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]


def test_otel_module_is_gone():
    assert not (ROOT / "ladder" / "otel.py").exists()


def test_provenance_records_no_otel_field():
    """The env block must not advertise a flag nothing reads."""
    src = (ROOT / "ladder" / "provenance.py").read_text(encoding="utf-8")
    assert "ladder_otel" not in src
    assert "LADDER_OTEL" not in src


def test_readme_does_not_document_the_removed_export():
    """README told the reader to run a command that did nothing."""
    src = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "LADDER_OTEL" not in src
    assert "OTEL_EXPORTER_OTLP_ENDPOINT" not in src

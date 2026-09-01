"""Every switch the manifest declares must be a switch something reads.

Written 2026-08-31, straight after `manifest.model.temperature` turned out to be
declared and never read. The same question asked of every other key found four
more, and this file is the answer to all four. The rule they share: a setting
whose declared value and real value agree only because the code happens to do
what the manifest happens to say is not configuration, it is a coincidence with
documentation. NONE of these change a shipped number — every one is inert at
its declared value, which is exactly how the temperature key looked.
"""

import json
import pathlib

import pytest

_ROOT = pathlib.Path(__file__).resolve().parent.parent


# --- vocabulary.snomed_backend: the highest-stakes of the four --------------
#
# CLAUDE.md's hard rule: "Never report a rung 1 rejection rate without saying
# which backend produced it" — the two differ by 23.9% of CADEC gold. The
# manifest named the backend and `run.py` was hardwired to Registry, so setting
# it to "ols4" would have changed NOTHING while every results file claimed
# ols4. provenance.vocabulary() stamps the live backend, so the two facts were
# both on record and nothing compared them.


def test_the_declared_backend_is_read():
    from ladder import run

    assert run.check_snomed_backend({"vocabulary": {"snomed_backend": "local-rf2"}}) \
        == "local-rf2"


def test_an_undeclared_backend_is_the_local_index():
    """The FiNER manifests declare `backend: finer-tags` and no SNOMED backend
    at all; absent must stay the documented default rather than a refusal."""
    from ladder import run

    assert run.check_snomed_backend({}) == "local-rf2"
    assert run.check_snomed_backend({"vocabulary": {}}) == "local-rf2"


def test_ols4_is_refused_rather_than_silently_ignored():
    """`Ols4Vocabulary` is real and serves rung 1's surface, but NOT rung 0's
    (`shortlist`, `resolve`, `search_labelled`) or `replacements`. Wiring it
    into a full run is a measurement, not a fix — so the declaration is
    REFUSED, loudly, which is still the whole point: after this a results file
    cannot claim a backend the run did not use."""
    from ladder import run

    with pytest.raises(SystemExit) as exc:
        run.check_snomed_backend({"vocabulary": {"snomed_backend": "ols4"}})
    msg = str(exc.value)
    assert "ols4" in msg and "vocab_crosscheck" in msg


def test_an_unknown_backend_is_refused():
    from ladder import run

    with pytest.raises(SystemExit):
        run.check_snomed_backend({"vocabulary": {"snomed_backend": "sqlite3"}})


# --- vocabulary.meddra_mode -------------------------------------------------


def test_the_declared_meddra_mode_is_read():
    from ladder import run

    assert run.check_meddra_mode({"vocabulary": {"meddra_mode": "reference"}}) \
        == "reference"
    assert run.check_meddra_mode({}) == "reference"


def test_answer_space_is_refused_because_the_step_that_used_it_is_gone():
    """`answer_space` meant showing the model the MedDRA list, which was S3.
    S3 was dropped 2026-08-24 and rung 0 has not read MedDRA since — so the
    mode is unimplementable, and accepting it would let a manifest declare an
    experiment that cannot run."""
    from ladder import run

    with pytest.raises(SystemExit) as exc:
        run.check_meddra_mode({"vocabulary": {"meddra_mode": "answer_space"}})
    assert "S3" in str(exc.value)


# --- rungs.1.outdated_check -------------------------------------------------


def test_rung_1_declares_the_outdated_check_it_documents():
    """The manifest note says `off | flag`. `off` did not exist: the key was
    absent from r1.DEFAULTS and _record_history flagged unconditionally."""
    from ladder.rungs import r1

    assert r1.DEFAULTS["outdated_check"] == "flag"


def test_flag_records_the_successor_as_it_always_did():
    from ladder.rungs import r1

    class Vocab:
        def is_active(self, code): return False
        def replacements(self, code): return ["999"]

    checks = {}
    r1._record_history(checks, Vocab(), "111", mode="flag")
    assert checks["sct_outdated"] is True
    assert checks["sct_replacement"] == "999"


def test_off_records_nothing():
    from ladder.rungs import r1

    class Vocab:
        def is_active(self, code): return False
        def replacements(self, code): return ["999"]

    checks = {}
    r1._record_history(checks, Vocab(), "111", mode="off")
    assert "sct_outdated" not in checks
    assert "sct_replacement" not in checks


def test_the_default_is_still_flag_when_no_mode_is_passed():
    """Every published number was produced with this flagging. The default
    argument is what keeps that true for any caller that has not been updated."""
    from ladder.rungs import r1

    class Vocab:
        def is_active(self, code): return False
        def replacements(self, code): return []

    checks = {}
    r1._record_history(checks, Vocab(), "111")
    assert checks["sct_outdated"] is False


# --- ladder/otel.py is DELETED, and this is what keeps it deleted ----------
#
# Removed 2026-08-31, the day after it was wired. The wiring was correct and
# the feature was not wanted: one commit ever (44882a3, 2026-08-23) which
# touched only the module and a HAND-MADE smoke row, never an entry point —
# "phoenix transport verified" meant verified against `{"run_id": "smoke",
# "doc_id": "D1"}`, not against a ladder run. Five phases, two corpora and zero
# decisions.md entries later, nothing had used it, and its spans were a strict
# copy of the ledger row that is already JSONL on disk and already what
# ladder_top.py, provenance and every out/harness script read. Same failure
# class as the five declarations fixed the same day: shipped, advertised in
# README.md and docs/plan.html, and inert.


def test_the_otel_module_is_gone():
    assert not (_ROOT / "ladder" / "otel.py").exists()
    assert not (_ROOT / "runs" / "otel-smoke.jsonl").exists()


def test_nothing_references_the_deleted_exporter():
    """Including the docs. A feature the README advertises and no code
    implements is the defect this whole file is about, pointed the other way.
    """
    hits = []
    for pat in ("**/*.py", "**/*.md", "**/*.html", "**/*.txt", "**/*.yml"):
        for path in _ROOT.glob(pat):
            # RELATIVE parts, not absolute: this repo is worked in worktrees
            # under .claude/, so filtering on path.parts excluded every file
            # and the guard passed while README.md still advertised the thing.
            rel = path.relative_to(_ROOT)
            if any(part in (".git", "out", "runs", ".claude", "public",
                            "versions", "__pycache__") for part in rel.parts):
                continue
            # The RECORD may name a deleted thing — that is what a record is
            # for. This guard is about files that ADVERTISE or IMPLEMENT it.
            if path.name in ("test_declarations_are_read.py", "decisions.md",
                             "CLAUDE.md"):
                continue
            text = path.read_text(errors="ignore")
            if "LADDER_OTEL" in text or "ladder.otel" in text \
                    or "OtelLedger" in text or "opentelemetry" in text:
                hits.append(str(rel))
    assert not hits, "the exporter is deleted; these still advertise it: " + \
        ", ".join(sorted(set(hits)))


def test_the_ledger_is_built_directly_again():
    """`run.ledger_for` existed only to choose between Ledger and OtelLedger.
    With one option left, the indirection is a branch that cannot branch."""
    from ladder import run

    assert not hasattr(run, "ledger_for")


# --- the model name that does not exist -------------------------------------


def test_no_tracked_manifest_names_a_model_ollama_does_not_have():
    """`ollama/granite4:micro-h` has no such model — the ollama name carries
    the `ibm/` namespace. `manifest.finer.json` has a `_judge_name_note` about
    it because that exact name spent 133 minutes in rungs 0 and 3 and then
    died at rung 4 on the first full FiNER run (docs/decisions.md 2026-08-29).
    Three other tracked manifests still carried it.
    """
    bad = []
    for path in sorted(_ROOT.glob("manifest*.json")):
        man = json.loads(path.read_text())
        for role, spec in (man.get("model") or {}).items():
            if isinstance(spec, str) and spec.endswith("/granite4:micro-h") \
                    and "ibm/" not in spec:
                bad.append(f"{path.name}:{role} = {spec}")
    assert not bad, "ollama namespaces this model under ibm/: " + "; ".join(bad)


def test_the_script_checks_the_backend_it_opens():
    """Line 24 duplicated `_vocab_for`'s Registry construction and so
    duplicated its blind spot."""
    src = (_ROOT / "scripts/ladder_run.py").read_text()
    assert "check_snomed_backend(man)" in src

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


# --- ladder/otel.py was not merely unread, it was UNIMPORTED ----------------
#
# The module docstring tells you to run `LADDER_OTEL=1 ... scripts/ladder_run.py`
# and nothing anywhere imported it, so that command emitted no spans. Its
# `run_meta` — the function whose docstring says "Temperature is here because
# rung 5's entire result is a function of it and it was never stamped" — had no
# callers, so it still was not stamped.


def test_the_default_ledger_is_untouched(tmp_path):
    """LADDER_OTEL unset must give the SAME plain Ledger every published run
    used. Not a subclass: exactly Ledger."""
    from ladder import run
    from ladder.ledger import Ledger

    led = run.ledger_for(tmp_path / "x.ledger.jsonl", run_id="r1", man={},
                         split="dev", order=[0], registry=None, enabled=False)
    assert type(led) is Ledger


def test_otel_gets_a_ledger_and_a_temperature_when_it_is_switched_on(tmp_path):
    from ladder import run
    from ladder.otel import OtelLedger

    man = {"model": {"extractor": "ollama/gpt-oss:20b", "temperature": 0},
           "vocabulary": {"snomed_release": "REL"}}
    led = run.ledger_for(tmp_path / "x.ledger.jsonl", run_id="r1", man=man,
                         split="dev", order=[0, 1], registry=None, enabled=True)
    assert isinstance(led, OtelLedger)
    assert led.run_meta["temperature"] == 0.0
    assert led.run_meta["model"] == "ollama/gpt-oss:20b"
    assert led.run_meta["split"] == "dev"


def test_a_run_with_no_model_still_gets_a_ledger(tmp_path):
    """Telemetry must never break a run — the same rule OtelLedger.log already
    follows when a span fails to emit. A manifest naming no extractor is a hard
    error at `llm.resolve`, and it must not become a hard error HERE, before
    the run has even reached a rung."""
    from ladder import run

    led = run.ledger_for(tmp_path / "x.ledger.jsonl", run_id="r1", man={},
                         split="dev", order=[0], registry=None, enabled=True)
    assert led.run_meta["model"] == "n/a"


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


def test_the_entry_point_otel_names_builds_its_ledger_through_the_wiring():
    """`ladder/otel.py`'s docstring names `scripts/ladder_run.py` by name as
    the way to switch tracing on. That script built a plain `Ledger` of its
    own, so the documented command emitted nothing there either — wiring
    `ladder/run.py` alone would have left the documented one still dead."""
    src = (_ROOT / "scripts/ladder_run.py").read_text()
    assert "ledger_for(" in src
    assert "Ledger(\"runs/ladder.ledger.jsonl\"" not in src


def test_the_script_checks_the_backend_it_opens():
    """Line 24 duplicated `_vocab_for`'s Registry construction and so
    duplicated its blind spot."""
    src = (_ROOT / "scripts/ladder_run.py").read_text()
    assert "check_snomed_backend(man)" in src

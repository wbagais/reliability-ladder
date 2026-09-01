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
    hits, looked = [], 0
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
            # for. This guard is about files that ADVERTISE or IMPLEMENT it:
            # README.md, docs/plan.html, the wiki, the code. The record files
            # are decisions.md, CLAUDE.md and the MR-*.md write-ups at the root
            # — the last of which caught me, because the MR description for
            # THIS branch explains the deletion and so necessarily names it.
            if path.name in ("test_declarations_are_read.py", "decisions.md",
                             "CLAUDE.md") or path.name.startswith("MR-"):
                continue
            text = path.read_text(errors="ignore")
            looked += 1
            if "LADDER_OTEL" in text or "ladder.otel" in text \
                    or "OtelLedger" in text or "opentelemetry" in text:
                hits.append(str(rel))
    # THE GUARD ON THE GUARD. This test passed VACUOUSLY when it was written:
    # it filtered on absolute path.parts, and this repo is worked in worktrees
    # under .claude/, so every path was excluded and nothing was read while
    # README.md still advertised the exporter. A count of what was actually
    # opened is what makes the empty result mean something.
    assert looked > 50, f"only read {looked} files — the walk is broken, not clean"
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
    bad, seen = [], 0
    for path in sorted(_ROOT.glob("manifest*.json")):
        seen += 1
        man = json.loads(path.read_text())
        for role, spec in (man.get("model") or {}).items():
            if isinstance(spec, str) and spec.endswith("/granite4:micro-h") \
                    and "ibm/" not in spec:
                bad.append(f"{path.name}:{role} = {spec}")
    assert seen >= 5, f"only {seen} manifests globbed — an empty pass is not a pass"
    assert not bad, "ollama namespaces this model under ibm/: " + "; ".join(bad)


def test_the_script_checks_the_backend_it_opens():
    """Line 24 duplicated `_vocab_for`'s Registry construction and so
    duplicated its blind spot."""
    src = (_ROOT / "scripts/ladder_run.py").read_text()
    assert "check_snomed_backend(man)" in src


# --- rung DEFAULTS that were declared and never read ------------------------
#
# The same audit as the manifest's, run over every rung's DEFAULTS. `r4`'s
# `temperature` was the first (fixed 2026-08-31); these three are the rest.
# All are REMOVED rather than wired, and the reason differs from r4's: there is
# no manifest declaration to defer to here, so the question is only whether the
# knob exists. Each one's own comment says the answer is no — turning it into a
# real setting would create an unmeasured arm, which is a measurement, not a
# fix.


def test_rung_2_declares_no_attempt_count_it_does_not_honour():
    """`"max_attempts": 1` with the comment "one retry. More is a different
    experiment." Never read: `_attempt` runs exactly once, hardcoded, so a
    manifest setting 3 would have changed nothing."""
    from ladder.rungs import r2

    assert "max_attempts" not in r2.DEFAULTS


def test_rung_2_declares_no_withdrawal_switch_it_does_not_honour():
    """`"allow_withdrawal": True`, never read. Withdrawal is unconditional and
    is Constraint 5 — withdrawal, never deletion — which is a design rule, not
    a setting that can be turned off."""
    from ladder.rungs import r2

    assert "allow_withdrawal" not in r2.DEFAULTS


def test_rung_4_declares_no_vocabulary_term_switch():
    """`"show_vocabulary_term": False`, added 39a94f0 and never read since."""
    from ladder.rungs import r4

    assert "show_vocabulary_term" not in r4.DEFAULTS


# --- dead code, the shape otel.run_meta had ---------------------------------


def test_the_dead_reporters_are_gone():
    """Two public functions with no caller in ladder/, scripts/ or tests/.

    `r0.report_run` is worse than unused: it reads `agg["documents"]` and
    `agg["tool_calls"]`, which the modern `apply()` aggregate does not carry,
    so calling it today would raise KeyError. `report(mode, recs, agg)` is the
    live one. `vocab.lexical_overlap` is the OLS4-era "check 6"; `lexical_match`
    on both backends replaced it.
    """
    from ladder import vocab
    from ladder.rungs import r0

    assert not hasattr(r0, "report_run")
    assert not hasattr(vocab, "lexical_overlap")
    assert hasattr(r0, "report"), "the LIVE reporter must survive the deletion"

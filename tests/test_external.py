"""Tests for ladder.checks.external — every claim kind, made to fail on the
defect that actually happened.

THE DEFECTS THESE REPRODUCE, all from 2026-09-08 and all within one hour:

    a test count       docs said 43, the suite had 62
    a version          pyproject said 0.1.0 after the package had grown a CLI,
                       a dashboard, relations and three provenance features
    a symbol           docs/TODO-provenance.md described `confirm()` as unbuilt
                       future work after it had shipped
    a url              the README pointed at gitlab.com when the canonical
                       remote was github.com

And one the checker itself produced: a file that legitimately states two
numbers for two different facts — "62 tests" of one package and "114 tests
across the three" — reported as a contradiction. A checker that invents
failures is worse than one that misses them, so that case has a test of its
own.
"""
from __future__ import annotations

import json
import pathlib
import subprocess
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from ladder.checks import FAIL, PASS, SKIP
from ladder.checks import external


# ── a package on disk, small enough to reason about ──────────────────
@pytest.fixture
def pkg(tmp_path):
    """A minimal package: version 0.6.0, no dependencies, two test functions,
    and a `confirm` symbol."""
    root = tmp_path / "pkg"
    (root / "src" / "thing").mkdir(parents=True)
    (root / "tests").mkdir()
    (root / "pyproject.toml").write_text(
        '[project]\nname = "thing"\nversion = "0.6.0"\ndependencies = []\n')
    (root / "src" / "thing" / "core.py").write_text(
        "def confirm():\n    pass\n\n\nclass Ledger:\n    def merge(self):\n        pass\n")
    (root / "tests" / "test_a.py").write_text(
        "def test_one():\n    pass\n\n\ndef test_two():\n    pass\n")
    return root


@pytest.fixture
def docs(tmp_path):
    """A repository whose documents cite facts about that package."""
    root = tmp_path / "repo"
    root.mkdir()
    return root


def spec(root, claims):
    return {"repo": "https://example.com/thing", "local": str(root),
            "claims": claims}


def only(results, needle):
    hits = [r for r in results if needle in r.check]
    assert hits, f"no result mentioning {needle!r} in {[r.check for r in results]}"
    return hits[0]


# ── reading the truth out of a package ───────────────────────────────
def test_version_is_read_from_pyproject(pkg):
    assert external.actual_version(pkg) == "0.6.0"


def test_a_wrong_version_fails(pkg, docs):
    """The declaration said 0.5.2 for days while pyproject said 0.1.0. Neither
    number had been read off the file."""
    r = external.check_one("thing", spec(pkg, [
        {"kind": "version", "value": "0.5.2"}]), docs, collect=False)
    assert only(r, "version").status == FAIL
    assert "0.6.0" in only(r, "version").found


def test_the_right_version_passes(pkg, docs):
    r = external.check_one("thing", spec(pkg, [
        {"kind": "version", "value": "0.6.0"}]), docs, collect=False)
    assert only(r, "version").status == PASS


def test_tests_are_counted(pkg, docs):
    r = external.check_one("thing", spec(pkg, [
        {"kind": "tests", "value": 2}]), docs, collect=False)
    assert only(r, "tests").status == PASS


def test_a_stale_test_count_fails(pkg, docs):
    """The release notes said 43 of a suite that had 62, and nothing looked."""
    r = external.check_one("thing", spec(pkg, [
        {"kind": "tests", "value": 43}]), docs, collect=False)
    assert only(r, "tests").status == FAIL


def test_dependencies_are_read(pkg, docs):
    r = external.check_one("thing", spec(pkg, [
        {"kind": "dependencies", "value": 0}]), docs, collect=False)
    assert only(r, "dependencies").status == PASS


def test_an_added_dependency_fails_the_no_dependencies_claim(pkg, docs):
    """'No dependencies' is claimed in two documents and is the reason the
    package is usable elsewhere. One addition makes both sentences false."""
    (pkg / "pyproject.toml").write_text(
        '[project]\nname = "thing"\nversion = "0.6.0"\ndependencies = ["requests"]\n')
    r = external.check_one("thing", spec(pkg, [
        {"kind": "dependencies", "value": 0}]), docs, collect=False)
    assert only(r, "dependencies").status == FAIL


def test_a_defined_symbol_passes(pkg, docs):
    for name in ("confirm", "merge", "Ledger"):
        r = external.check_one("thing", spec(pkg, [
            {"kind": "symbol", "value": name}]), docs, collect=False)
        assert only(r, "symbol").status == PASS, name


def test_a_symbol_that_does_not_exist_fails(pkg, docs):
    """docs/TODO-provenance.md described shipped work as outstanding for a day.
    Asserting the symbol exists is the closest a checker gets to reading prose."""
    r = external.check_one("thing", spec(pkg, [
        {"kind": "symbol", "value": "never_built"}]), docs, collect=False)
    assert only(r, "symbol").status == FAIL


def test_a_test_function_is_not_a_symbol(pkg, docs):
    """Symbols come from the package, not its tests — otherwise a claim could be
    satisfied by a test that merely names the thing."""
    r = external.check_one("thing", spec(pkg, [
        {"kind": "symbol", "value": "test_one"}]), docs, collect=False)
    assert only(r, "symbol").status == FAIL


# ── the documents that cite a claim ──────────────────────────────────
def test_a_cited_value_must_appear_in_the_document(pkg, docs):
    (docs / "NOTES.md").write_text("thing ships with 2 tests and no dependencies.\n")
    r = external.check_one("thing", spec(pkg, [
        {"kind": "tests", "value": 2, "cited_in": ["NOTES.md"]}]), docs, collect=False)
    assert only(r, "cited in NOTES.md").status == PASS


def test_a_document_stating_a_different_value_fails(pkg, docs):
    """The 43-versus-62 case exactly: a number in a document that no longer
    matches the package it describes."""
    (docs / "NOTES.md").write_text("thing ships with 43 tests.\n")
    r = external.check_one("thing", spec(pkg, [
        {"kind": "tests", "value": 2, "cited_in": ["NOTES.md"]}]), docs, collect=False)
    bad = only(r, "cited in NOTES.md")
    assert bad.status == FAIL and "43" in bad.found


def test_two_facts_in_one_file_are_not_a_contradiction(pkg, docs):
    """The false positive this checker produced on its first run:
    docs/RELEASE-v1.0.md says '62 tests' of one package and '114 tests across
    the three', which are two facts. Scoping the search to lines naming the
    package is what separates them."""
    (docs / "NOTES.md").write_text(
        "thing ships with 2 tests.\n"
        "114 tests across the three tools in this study.\n")
    r = external.check_one("thing", spec(pkg, [
        {"kind": "tests", "value": 2, "cited_in": ["NOTES.md"]}]), docs, collect=False)
    assert only(r, "cited in NOTES.md").status == PASS


def test_a_contradiction_on_the_same_line_is_caught(pkg, docs):
    (docs / "NOTES.md").write_text("thing ships with 2 tests, up from 43 tests.\n")
    r = external.check_one("thing", spec(pkg, [
        {"kind": "tests", "value": 2, "cited_in": ["NOTES.md"]}]), docs, collect=False)
    assert only(r, "contradicted in NOTES.md").status == FAIL


def test_a_missing_cited_file_fails(pkg, docs):
    r = external.check_one("thing", spec(pkg, [
        {"kind": "tests", "value": 2, "cited_in": ["GONE.md"]}]), docs, collect=False)
    assert only(r, "cited in GONE.md").status == FAIL


def test_a_url_must_match_a_real_remote(pkg, docs):
    """The README pointed at gitlab.com while the remote was github.com — a
    dead link on the one installable thing here."""
    subprocess.run(["git", "init", "-q"], cwd=pkg, check=False)
    subprocess.run(["git", "remote", "add", "origin",
                    "https://github.com/someone/thing.git"], cwd=pkg, check=False)
    ok = external.check_one("thing", spec(pkg, [
        {"kind": "url", "value": "https://github.com/someone/thing"}]), docs, collect=False)
    assert only(ok, "url").status == PASS
    bad = external.check_one("thing", spec(pkg, [
        {"kind": "url", "value": "https://gitlab.com/someone/thing"}]), docs, collect=False)
    assert only(bad, "url").status == FAIL


# ── absence and malformed input ──────────────────────────────────────
def test_a_missing_clone_is_a_skip_with_the_clone_command(tmp_path, docs):
    """A contributor without the sibling checkout should still be able to run
    everything else — but the output has to say what was not checked."""
    r = external.check_one("thing", {"repo": "https://example.com/thing",
                                     "local": str(tmp_path / "absent"),
                                     "claims": [{"kind": "tests", "value": 2}]},
                           docs)
    assert len(r) == 1 and r[0].status == SKIP
    assert "git clone" in r[0].found


def test_an_unknown_claim_kind_is_a_skip_not_a_pass(pkg, docs):
    """Silently passing an unrecognised claim would let a typo disable a check
    without anything saying so."""
    r = external.check_one("thing", spec(pkg, [
        {"kind": "colour", "value": "green"}]), docs, collect=False)
    assert r[0].status == SKIP


def test_absent_declarations_file_is_a_skip(tmp_path):
    r = external.run(tmp_path / "nothing.json", tmp_path)
    assert len(r) == 1 and r[0].status == SKIP


def test_underscore_keys_are_notes_not_packages(tmp_path, pkg, docs):
    """external.json opens with a `_note` block explaining why the file exists.
    Treating it as a package to check would fail on every run."""
    f = tmp_path / "external.json"
    f.write_text(json.dumps({"_note": ["why this file exists"],
                             "thing": spec(pkg, [{"kind": "version",
                                                  "value": "0.6.0"}])}))
    r = external.run(f, docs)
    assert all("_note" not in x.check for x in r)
    assert any(x.status == PASS for x in r)


# ── the real declarations file, if it is there ───────────────────────
def test_the_repositorys_own_declarations_are_valid():
    """Not that the claims hold — that the file parses and every claim has the
    fields the checker needs. A malformed declaration disables a check."""
    f = pathlib.Path(__file__).resolve().parent.parent / "external.json"
    if not f.is_file():
        pytest.skip("external.json not present")
    spec_ = json.loads(f.read_text())
    for name, block in spec_.items():
        if name.startswith("_"):
            continue
        assert "repo" in block and "claims" in block, name
        for c in block["claims"]:
            assert "kind" in c and "value" in c, f"{name}: {c}"
            assert isinstance(c.get("cited_in", []), list), f"{name}: {c}"

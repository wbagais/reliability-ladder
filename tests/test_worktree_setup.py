"""The paths a fresh worktree SYMLINKS must be gitignored as symlinks.

Found 2026-08-31 while setting a worktree up to validate `preflight_rungs`.
`.gitignore` carried `ladder/cache/` with a trailing slash, which matches a
DIRECTORY — and the standing worktree convention does not create a directory,
it symlinks the main checkout's cache in. Git does not treat a symlink as a
directory, so `ladder/cache` sat in `git status` as untracked and unignored,
one `git add -A` from committing the embedding vectors.

Same shape as the declared-and-never-read audit: the rule and the situation
agreed for exactly as long as nobody exercised the difference.

TWO CHECKS, and the split is deliberate. The regression itself is a missing
LINE in `.gitignore`, so it is asserted directly and needs nothing but the
file. The broader check — every symlinked path, evaluated by git's own
matcher — needs the `git` binary, which `python:3.12-slim` does not carry (the
runner's helper image does the clone), so it skips in CI. Written this way
round on purpose: the part that would go quiet in CI is the part that is NOT
the guard.
"""

import pathlib
import shutil
import subprocess

import pytest

_ROOT = pathlib.Path(__file__).resolve().parent.parent

# Every path a worktree symlinks in from the main checkout, per CLAUDE.md's
# five-step preprocessing and the worktree convention.
SYMLINKED = ["ladder/cache", "data/cadec", "data/keywords.csv",
             "data/exclusions.csv", "data/SnomedCT_Release_AU1000036_20260731"]


def _rules():
    text = (_ROOT / ".gitignore").read_text()
    return [ln.strip() for ln in text.splitlines()
            if ln.strip() and not ln.lstrip().startswith("#")]


def test_the_cache_is_ignored_in_symlink_form_as_well_as_directory_form():
    """The regression, asserted against the file and nothing else."""
    rules = _rules()
    assert "ladder/cache/" in rules, "the directory form must stay"
    assert "ladder/cache" in rules, (
        "a worktree SYMLINKS ladder/cache, and git does not match a symlink "
        "against a trailing-slash rule — the bare form is what ignores it")


def _ignored(path: str) -> bool:
    return subprocess.run(["git", "check-ignore", "-q", "--no-index", path],
                          cwd=_ROOT).returncode == 0


@pytest.mark.skipif(shutil.which("git") is None,
                    reason="no git binary — python:*-slim has none, and the "
                           "regression above is asserted without it")
def test_git_itself_ignores_every_path_the_worktree_convention_symlinks():
    # Control first: if check-ignore answered "ignored" to everything, the
    # assertion below would pass while measuring nothing.
    assert not _ignored("README.md"), \
        "check-ignore is not discriminating — the rest of this test is vacuous"

    missed = [p for p in SYMLINKED if not _ignored(p)]
    assert not missed, (
        "these are symlinked into a fresh worktree and git does not ignore "
        f"them in symlink form: {missed}")

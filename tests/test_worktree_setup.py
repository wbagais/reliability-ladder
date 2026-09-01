"""The paths a fresh worktree SYMLINKS must be gitignored as symlinks.

Found 2026-08-31 while setting up a worktree to validate `preflight_rungs`.
`.gitignore` carries `ladder/cache/` with a trailing slash, which matches a
DIRECTORY — and the standing worktree convention does not create a directory,
it creates a symlink to the main checkout's. Git does not treat a symlink as a
directory, so `ladder/cache` showed up as untracked in `git status` and one
`git add -A` away from being committed.

Same shape as the defects this repo keeps finding: the declared rule and the
real situation agree only while nobody exercises the difference.
"""

import pathlib
import subprocess

_ROOT = pathlib.Path(__file__).resolve().parent.parent

# Every path a worktree symlinks in from the main checkout, per CLAUDE.md's
# five-step preprocessing and the worktree convention.
SYMLINKED = ["ladder/cache", "data/cadec", "data/keywords.csv",
             "data/exclusions.csv", "data/SnomedCT_Release_AU1000036_20260731"]


def _ignored(path: str) -> bool:
    return subprocess.run(["git", "check-ignore", "-q", "--no-index", path],
                          cwd=_ROOT).returncode == 0


def test_every_symlinked_path_is_ignored_without_a_trailing_slash():
    missed = [p for p in SYMLINKED if not _ignored(p)]
    assert not missed, (
        "these are symlinked into a fresh worktree and git does not ignore them "
        f"in symlink form: {missed}")

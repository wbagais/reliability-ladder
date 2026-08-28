"""manifest.json — the one file that makes a number reproducible.

Corpus version, vocabulary release, seed, split sizes, gold rule, rung order,
rung parameters. Reproducibility and honesty are the same file: if a setting can
move a published number, it belongs here rather than in a default argument.

Append-only, and edited deliberately — it is the file most likely to be touched
from two directions at once, which makes it the likeliest conflict in the repo.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

DEFAULT_PATH = "manifest.json"


def load_manifest(path: str | os.PathLike = DEFAULT_PATH) -> dict[str, Any]:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(
            f"{p} not found. Create it with `python -m ladder.run init` "
            "(step 0 of docs/cadec-track.md)."
        )
    man = json.loads(p.read_text())
    man.setdefault("rungs", {})
    _resolve_paths(man, p.parent)
    return man


def _resolve_paths(man: dict[str, Any], base: Path) -> None:
    """Manifest paths are relative to the manifest, so a checkout moves cleanly."""
    for section, key in (
        ("corpus", "cadec_root"),
        ("corpus", "root"),          # any non-CADEC adapter
        ("corpus", "splits_dir"),
        ("vocabulary", "snomed_db"),
        ("vocabulary", "snomed_release_dir"),
        ("vocabulary", "meddra_csv"),
        ("output", "dir"),
    ):
        val = man.get(section, {}).get(key)
        if val and not os.path.isabs(val):
            man[section][key] = str((base / val).resolve())


def friendly(fn, *args):
    """Run a CLI entry point, turning a missing prerequisite into one clear line.

    Every one of these failures has an actionable message already — a corpus
    that is not downloaded, a vocabulary index that is not built. A traceback on
    top of it just hides the sentence the reader needs.
    """
    try:
        return fn(*args)
    except FileNotFoundError as exc:
        print(f"\n{exc}\n", file=sys.stderr)
        return 2

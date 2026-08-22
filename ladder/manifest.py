"""manifest.json — the one file that makes a number reproducible.

Corpus version, vocabulary release, seed, split sizes, gold rule, rung order,
rung parameters. Reproducibility and honesty are the same file: if a setting can
move a published number, it belongs here rather than in a default argument.

Append-only, and edited only in a joint block — it is the one file both owners
have a reason to touch, which makes it the likeliest conflict in the repo.
"""

from __future__ import annotations

import json
import os
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
        ("corpus", "splits_dir"),
        ("vocabulary", "snomed_db"),
        ("vocabulary", "snomed_release_dir"),
        ("output", "dir"),
    ):
        val = man.get(section, {}).get(key)
        if val and not os.path.isabs(val):
            man[section][key] = str((base / val).resolve())


def save_manifest(man: dict[str, Any], path: str | os.PathLike = DEFAULT_PATH) -> None:
    Path(path).write_text(json.dumps(man, indent=2) + "\n")

"""Run discovery — the runs list behind every tab.

A run is the family of files the pipeline writes beside each other:
`<id>.records.jsonl`, `<id>.ledger.jsonl`, `<id>.results.csv`,
`<id>.manifest.json`. The dashboard groups them by stem and never invents a
fifth format. Sources are the checkout's own `out/`, the TRACKED `runs/archive/` (the
consolidated re-run's corpus-free four per run, on every clone since
2026-09-07) and the main checkout's `out/archive/` (read-only baselines,
found through the worktree's `.git` file so no absolute path is baked into
the repo).

The saved manifest copy does not record the split, so the split is INFERRED:
the run's doc_ids against the frozen splits in `data/splits/`. A run whose
documents fit no split reports "unknown", never a guess.
"""
from __future__ import annotations

import csv
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

SUFFIXES = {
    "records": ".records.jsonl",
    "ledger": ".ledger.jsonl",
    "results": ".results.csv",
    "manifest": ".manifest.json",
    # Since 2026-09-03 (plan item 12, ladder/trace.py) every run also leaves
    # the per-record, per-rung state table and each rung's aggregate.
    "state": ".state.jsonl",
    "aggregates": ".aggregates.json",
}

#: `<run>.r<N>.records.jsonl` (the record set as rung N left it) and
#: `<run>.r<N>.calls.jsonl` (every model call rung N made). Matched BEFORE the
#: plain suffixes: `rerun-cadec-d0.r3.records.jsonl` ends in `.records.jsonl`
#: too, and the b2-menu archive listed 219 "runs" of which 150 were these.
PER_RUNG = re.compile(r"^(?P<stem>.+)\.r(?P<n>\d+)\.(?P<kind>records|calls)\.jsonl$")


def classify(name: str) -> tuple[str, str] | None:
    """(kind, stem) for an artifact filename, or None for anything else.
    Kinds are the SUFFIXES keys plus `r<N>.records` / `r<N>.calls`."""
    m = PER_RUNG.match(name)
    if m:
        return f"r{m.group('n')}.{m.group('kind')}", m.group("stem")
    for kind, suffix in SUFFIXES.items():
        if name.endswith(suffix):
            return kind, name[: -len(suffix)]
    return None


@dataclass
class RunInfo:
    run_id: str
    dir: Path
    archived: bool  # from the archive: read-only baselines
    files: dict[str, Path] = field(default_factory=dict)
    mtime: float = 0.0


def discover_runs(sources: list[tuple[Path, bool]]) -> dict[str, RunInfo]:
    """{run_key: RunInfo} over (dir, archived) sources.

    Keys are the run id; on a collision across sources the LATER hit is
    qualified as "<parent-dir>/<id>" so both stay addressable and the first
    source (the working checkout) keeps the bare name.
    """
    runs: dict[str, RunInfo] = {}
    for root, archived in sources:
        if not root or not Path(root).is_dir():
            continue
        for path in sorted(Path(root).rglob("*")):
            if not path.is_file():
                continue
            hit = classify(path.name)
            if hit is None:
                continue
            kind, stem = hit
            key = _key_for(stem, path.parent, runs)
            info = runs.get(key)
            if info is None or info.dir != path.parent:
                if info is not None and info.dir != path.parent:
                    key = f"{path.parent.name}/{stem}"
                    info = runs.get(key)
                if info is None:
                    info = RunInfo(run_id=stem, dir=path.parent,
                                   archived=archived)
                    runs[key] = info
            info.files[kind] = path
            info.mtime = max(info.mtime, path.stat().st_mtime)
    return runs


def _key_for(stem: str, parent: Path, runs: dict[str, RunInfo]) -> str:
    existing = runs.get(stem)
    if existing is None or existing.dir == parent:
        return stem
    return f"{parent.name}/{stem}"


def main_checkout_archive(repo_root: Path) -> Path | None:
    """The main checkout's out/archive, reached through the worktree's .git file.

    A linked worktree's `.git` is a FILE reading "gitdir: <main>/.git/worktrees/<x>".
    A normal checkout (`.git` is a directory) has no separate main checkout, so
    the answer is None — its own out/ is already scanned.
    """
    gitfile = Path(repo_root) / ".git"
    if not gitfile.is_file():
        return None
    m = re.match(r"gitdir:\s*(.+)", gitfile.read_text().strip())
    if not m:
        return None
    gitdir = Path(m.group(1))
    # <main>/.git/worktrees/<name> -> <main>
    try:
        main_root = gitdir.parents[2] if gitdir.parent.name == "worktrees" else None
    except IndexError:
        return None
    if main_root is None:
        return None
    archive = main_root / "out" / "archive"
    return archive if archive.is_dir() else None


# --- readers (existing formats only — never a new one) -----------------------


def read_ledger(info: RunInfo) -> list[dict]:
    path = info.files.get("ledger")
    if path is None or not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def read_results(info: RunInfo) -> list[dict]:
    path = info.files.get("results")
    if path is None or not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def read_manifest_copy(info: RunInfo) -> dict | None:
    path = info.files.get("manifest")
    if path is None or not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def run_doc_ids(info: RunInfo) -> set[str]:
    """The documents a run touched, from its own artifacts."""
    docs: set[str] = set()
    path = info.files.get("records")
    if path is not None and path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                docs.add(json.loads(line).get("doc_id"))
    if not docs:
        for row in read_ledger(info):
            d = row.get("doc_id")
            if d and d != "-":
                docs.add(d)
    docs.discard(None)
    return docs


def infer_split(info: RunInfo, splits: dict[str, list[str]]) -> str:
    docs = run_doc_ids(info)
    if not docs:
        return "unknown"
    for name, ids in splits.items():
        if docs <= set(ids):
            return name
    return "unknown"

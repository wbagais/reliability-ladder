"""App state — every read goes through the pipeline's own loaders.

`ladder.corpus.load_corpus` for documents, `ladder.corpus.read_split` for the
frozen splits, `ladder.clean.load_exclusions` for exclusions,
`ladder.run.read_predictions` for records, `ladder.ledger.Ledger.read` for
ledger rows, `ladder.registry.Registry` for the vocabulary. The dashboard
parses nothing itself (governing rule: a lens, never a second accounting
path). Every heavyweight source is OPTIONAL and its absence is a stated
degradation, not an error — CI has no corpus, no index, no cache.
"""
from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from dashboard import runsindex
from dashboard.runsindex import RunInfo

_UNSET = object()


class AppState:
    def __init__(
        self,
        repo_root: Path,
        sources: list[tuple[Path, bool]] | None = None,
        corpus: Any = _UNSET,
        splits: Any = _UNSET,
        exclusion_rows: Any = _UNSET,
        registry: Any = _UNSET,
        manifest: Any = _UNSET,
    ):
        self.repo_root = Path(repo_root)
        if sources is None:
            sources = [(self.repo_root / "out", False)]
            archive = runsindex.main_checkout_archive(self.repo_root)
            local_archive = self.repo_root / "out" / "archive"
            if local_archive.is_dir():
                sources.append((local_archive, True))
            if archive is not None and archive != local_archive:
                sources.append((archive, True))
        self.sources = sources
        self._corpus = corpus
        self._splits = splits
        self._exclusion_rows = exclusion_rows
        self._registry = registry
        self._manifest = manifest
        self._records_cache: dict[tuple, list] = {}
        self._zones_cache: dict[tuple, dict] = {}

    # -- runs -----------------------------------------------------------------

    def runs(self) -> dict[str, RunInfo]:
        return runsindex.discover_runs(self.sources)

    def get_run(self, key: str) -> RunInfo:
        runs = self.runs()
        if key not in runs:
            raise KeyError(key)
        return runs[key]

    def run_split(self, info: RunInfo) -> str:
        return runsindex.infer_split(info, self.splits() or {})

    def records(self, info: RunInfo):
        """Final records, read through `ladder.run.read_predictions`."""
        from ladder.run import read_predictions

        path = info.files.get("records")
        if path is None or not path.exists():
            return []
        key = (str(path), path.stat().st_mtime)
        if key not in self._records_cache:
            split = self.run_split(info)
            splits = self.splits() or {}
            doc_ids = set(splits.get(split) or runsindex.run_doc_ids(info))
            self._records_cache.clear()
            self._records_cache[key] = read_predictions(path, doc_ids)
        return self._records_cache[key]

    def ledger_entries(self, info: RunInfo):
        from ladder.ledger import Ledger

        path = info.files.get("ledger")
        if path is None or not path.exists():
            return []
        return Ledger.read(path)

    # -- shared data ----------------------------------------------------------

    def manifest(self) -> dict:
        if self._manifest is _UNSET:
            try:
                from ladder.manifest import load_manifest

                self._manifest = load_manifest(self.repo_root / "manifest.json")
            except Exception:
                self._manifest = {}
        return self._manifest

    def corpus(self):
        """{doc_id: Document} or None when the licensed corpus is absent."""
        if self._corpus is _UNSET:
            try:
                from ladder.corpus import load_corpus

                root = self.manifest().get("corpus", {}).get("cadec_root")
                self._corpus = load_corpus(root) if root and Path(root).exists() else None
            except Exception:
                self._corpus = None
        return self._corpus

    def splits(self) -> dict[str, list[str]]:
        if self._splits is _UNSET:
            splits = {}
            try:
                from ladder.corpus import read_split

                splits_dir = self.manifest().get("corpus", {}).get(
                    "splits_dir", self.repo_root / "data" / "splits")
                for name in ("dev", "test", "pool"):
                    try:
                        splits[name] = read_split(splits_dir, name)
                    except FileNotFoundError:
                        pass
            except Exception:
                pass
            self._splits = splits
        return self._splits

    def exclusion_rows(self) -> list[dict]:
        if self._exclusion_rows is _UNSET:
            path = self.repo_root / "data" / "exclusions.csv"
            if path.exists():
                with path.open(newline="", encoding="utf-8") as fh:
                    self._exclusion_rows = list(csv.DictReader(fh))
            else:
                self._exclusion_rows = []
        return self._exclusion_rows

    def exclusions(self) -> set[str]:
        """The scoring set, through the pipeline's own loader."""
        from ladder.clean import load_exclusions

        path = self.repo_root / "data" / "exclusions.csv"
        if self._exclusion_rows is not _UNSET:
            return {r["record_id"] for r in self.exclusion_rows()
                    if r.get("record_id")}
        return load_exclusions(path)

    def registry(self):
        """The SNOMED registry, or None (CI, fresh clone) — stated, never faked."""
        if self._registry is _UNSET:
            try:
                from ladder.registry import Registry

                db = self.manifest().get("vocabulary", {}).get(
                    "snomed_db", self.repo_root / "ladder" / "cache" / "snomed.sqlite")
                self._registry = Registry(db) if Path(db).exists() else None
            except Exception:
                self._registry = None
        return self._registry

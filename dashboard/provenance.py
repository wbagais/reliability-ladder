"""C3 — provenance on every number.

Every figure, table and drill-down renders: run id · split · span mode ·
rung-1 backend · manifest hash. The hash is of the run's OWN saved manifest
copy, never the working manifest — the run monitor's baked-in-header defect
(stale models, frozen denominator) is exactly what this replaces. A missing
manifest copy is stated ("absent"), never papered over.
"""
from __future__ import annotations

import hashlib

from dashboard.runsindex import RunInfo, read_manifest_copy


def provenance_for(info: RunInfo, split: str, span_match: str) -> dict:
    man = read_manifest_copy(info)
    path = info.files.get("manifest")
    if path is not None and path.exists():
        digest = hashlib.sha256(path.read_bytes()).hexdigest()[:12]
    else:
        digest = "absent"
    backend = "unknown"
    if man:
        backend = man.get("vocabulary", {}).get("snomed_backend", "unknown")
    return {
        "run_id": info.run_id,
        "split": split,
        "span_match": span_match,
        "backend": backend,
        "manifest_hash": digest,
        "archived": info.archived,
    }

"""R1 — data explorer views. Stats are COMPUTED from the corpus via
`ladder.corpus.load_corpus`; the recorded numbers below are the claims they
are checked against, and a mismatch renders a warning (spec R1 criteria) —
the stats themselves are never hard-coded.

V4 (zone strip on gold) replays the gold standard through rung 1's own code
(`ladder.calibrate.run`) — every rejection there is false by construction.
"""
from __future__ import annotations

from collections import Counter
from typing import Any

from dashboard.state import AppState

#: The repo's RECORDED claims (manifest.json / CLAUDE.md). Used only to warn
#: on mismatch — never displayed as the computed value.
RECORDED_MENTIONS_TOTAL = 9111
RECORDED_CODE_STATUSES = {"active": 928, "retired": 115, "absent": 3}


def stats_payload(state: AppState) -> dict[str, Any] | None:
    corpus = state.corpus()
    if corpus is None:
        return None
    mentions = [m for d in corpus.values() for m in d.mentions]
    reactions = [m for m in mentions if m.entity_type == "reaction"]
    discontinuous = [m for m in reactions if len(m.spans) > 1]
    by_entity = Counter(m.entity_type for m in mentions)
    by_cadec = Counter(m.cadec_type for m in mentions)
    by_kind = Counter(m.gold_kind for m in reactions)
    families = Counter(d.drug_group for d in corpus.values())

    warnings: list[str] = []
    recorded_total = state.manifest().get("corpus", {}).get(
        "n_mentions_total", RECORDED_MENTIONS_TOTAL)
    if len(mentions) != recorded_total:
        warnings.append(
            f"computed {len(mentions)} mentions != recorded {recorded_total} "
            "(manifest.corpus.n_mentions_total) — corpus or parser drifted")

    codes: dict[str, Any] = {"available": False}
    registry = state.registry()
    if registry is not None:
        unique = sorted({str(c) for m in mentions for c in (m.sct or [])})
        status = Counter()
        for code in unique:
            if not registry.exists(code):
                status["absent"] += 1
            elif registry.is_active(code):
                status["active"] += 1
            else:
                status["retired"] += 1
        codes = {"available": True, "unique_codes": len(unique), **status}
        for k, want in RECORDED_CODE_STATUSES.items():
            if status.get(k, 0) != want:
                warnings.append(
                    f"code status {k}: computed {status.get(k, 0)} != recorded "
                    f"{want} — release-dependent, verify before quoting")

    return {
        "n_docs": len(corpus),
        "n_mentions": len(mentions),
        "by_entity_type": dict(by_entity),
        "by_cadec_type": dict(by_cadec),
        "gold_kinds": dict(by_kind),
        "concept_less": by_kind.get("concept_less", 0),
        "post_coordinated": by_kind.get("all_of", 0),
        "disjunctions": by_kind.get("any_of", 0),
        "discontinuous": {
            "reaction_mentions": len(discontinuous),
            "fraction": round(len(discontinuous) / len(reactions), 4)
            if reactions else 0.0,
        },
        "drug_groups": dict(families),
        "codes": codes,
        "warnings": warnings,
    }


def docs_payload(state: AppState, split: str | None, q: str | None,
                 drug: str | None) -> dict[str, Any] | None:
    corpus = state.corpus()
    if corpus is None:
        return None
    splits = state.splits() or {}
    # Default is dev+pool; test is a deliberate selection and gets the
    # spent-split banner (C2 — the split is spent, viewing it is fine).
    names = [split] if split else ["dev", "pool"]
    doc_ids: list[str] = []
    for name in names:
        doc_ids.extend(splits.get(name, []))
    if not splits:
        doc_ids = list(corpus)
    docs = []
    excluded = state.exclusions()
    for d in doc_ids:
        if d not in corpus:
            continue
        if q and q.lower() not in d.lower():
            continue
        doc = corpus[d]
        if drug and doc.drug_group != drug:
            continue
        reactions = [m for m in doc.mentions if m.entity_type == "reaction"]
        docs.append({
            "doc_id": d,
            "drug_group": doc.drug_group,
            "n_mentions": len(doc.mentions),
            "n_reactions": len(reactions),
            "n_discontinuous": sum(1 for m in reactions if len(m.spans) > 1),
            "n_excluded": sum(1 for m in doc.mentions
                              if m.record_id in excluded),
        })
    return {
        "split": split or "dev+pool",
        "spent_split": split == "test",
        "docs": docs,
    }


def doc_payload(state: AppState, doc_id: str) -> dict[str, Any] | None:
    corpus = state.corpus()
    if corpus is None or doc_id not in corpus:
        return None
    doc = corpus[doc_id]
    excluded = state.exclusions()
    exclusion_reasons = {r["record_id"]: r for r in state.exclusion_rows()}
    mentions = []
    for m in doc.mentions:
        row = exclusion_reasons.get(m.record_id)
        mentions.append({
            "record_id": m.record_id,
            "entity_type": m.entity_type,
            "cadec_type": m.cadec_type,
            "text": m.text,  # loopback-only view — scrubbed from exports
            "spans": [list(s) for s in m.spans],
            "discontinuous": len(m.spans) > 1,
            "sct": list(m.sct or []),
            "gold_kind": m.gold_kind,
            # excluded renders as EXCLUDED, never as an error (R1 criteria)
            "excluded": m.record_id in excluded,
            "exclusion_reason": row.get("reason") if row else None,
        })
    return {"doc_id": doc_id, "drug_group": doc.drug_group,
            "text": doc.text, "mentions": mentions}


def zones_payload(state: AppState, split: str) -> dict[str, Any]:
    """V4 — zone occupancy of the gold standard under rung 1, per backend.

    M1 renders the local-rf2 backend only: OLS4 is a network backend and a
    lens must not stall on it. The backend is named in the provenance and the
    caveat states the dependence."""
    corpus = state.corpus()
    registry = state.registry()
    if corpus is None:
        return {"available": False, "reason": "corpus unavailable"}
    if registry is None:
        return {"available": False, "reason": "registry unavailable (no SNOMED index)"}
    key = ("zones", split)
    if key not in state._zones_cache:
        from ladder.calibrate import run as calibrate_run
        from ladder.rungs.r1 import DEFAULTS

        splits = state.splits() or {}
        doc_ids = [d for d in splits.get(split, []) if d in corpus]
        if not doc_ids:
            return {"available": False, "reason": f"split {split!r} empty"}
        params = {**DEFAULTS,
                  **{k: v for k, v in
                     (state.manifest().get("rungs", {}).get("1", {})).items()
                     if k in DEFAULTS}}
        result = calibrate_run(corpus, doc_ids, registry, params)
        state._zones_cache[key] = {
            "available": True,
            "backend": "local-rf2",
            "split": split,
            "n": result.get("n") or sum((result.get("zones") or {}).values()),
            "zones": result.get("zones"),
            "reasons": result.get("reasons"),
            "false_rejection_rate": result.get("false_rejection_rate"),
            "band_rate": result.get("band_rate"),
            "accept_rate": result.get("accept_rate"),
        }
    return state._zones_cache[key]

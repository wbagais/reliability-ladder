"""Rung 1 against the gold standard — the check's own false-rejection floor.

A validation gate is only interesting if it rejects wrong answers and nothing
else. Before any model output exists, you can measure the "nothing else" half
exactly: replay rung 1 over CADEC's own annotations. Every rejection is by
construction a FALSE rejection, because the gold standard is the answer key.

That floor is the number to subtract from the rung 1 rejection rate later, and
it is what decides the three open settings in rungs/r1.py. It needs no model,
no split discipline and no budget, so it runs on the whole corpus.

    python -m ladder.calibrate --split pool
    python -m ladder.calibrate --split all --json out/rung1_floor.json
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

from ladder import corpus as corpus_mod
from ladder.manifest import friendly, load_manifest
from ladder.registry import Registry
from ladder.rungs import r1
from ladder.schema import CONCEPT_LESS, DRUG, REACTION, Record, ZONE_ACCEPT, ZONE_BAND, ZONE_REJECT


def gold_to_record(m: Any) -> Record:
    """A gold mention, dressed as a record so rung 1 can be run on it.

    The first code is used for post-coordinated (`all_of`) gold: rung 1 asks
    whether A code is real and correctly typed, not whether the full
    post-coordinated expression is complete.
    """
    return Record(
        doc_id=m.doc_id,
        entity_type=m.entity_type,
        text=m.text,
        spans=list(m.spans),
        sct=(m.sct[0] if m.sct else CONCEPT_LESS),
        record_id=m.record_id,
        confidence=1.0,
    )


def run(docs, doc_ids, registry, params: dict[str, Any]) -> dict[str, Any]:
    zones = Counter()
    reasons = Counter()
    by_type: dict[str, Counter] = {REACTION: Counter(), DRUG: Counter()}
    examples: dict[str, list] = {}
    inactive = 0
    negated_flagged = 0
    concept_less_zones = Counter()
    n = 0
    for doc_id in doc_ids:
        doc = docs[doc_id]
        for m in doc.mentions:
            rec = gold_to_record(m)
            z, reason, checks = r1.zone(rec, doc.text, registry, params)
            n += 1
            zones[z] += 1
            by_type[m.entity_type][z] += 1
            if checks.get("sct_active") is False:
                inactive += 1
            if checks.get("negated"):
                negated_flagged += 1
            if m.gold_kind == "concept_less":
                concept_less_zones[z] += 1
            if z == ZONE_REJECT:
                reasons[reason] += 1
                examples.setdefault(reason, [])
                if len(examples[reason]) < 6:
                    examples[reason].append(
                        {
                            "record": m.record_id,
                            "text": m.text,
                            "sct": m.sct,
                            "context": _context(doc.text, m.spans),
                            "cue": checks.get("negation_cue"),
                        }
                    )
    return {
        "n_mentions": n,
        "n_docs": len(doc_ids),
        "zones": dict(zones),
        "false_rejection_rate": round(zones[ZONE_REJECT] / n, 5) if n else 0.0,
        "reasons": dict(reasons),
        "accept_rate": round(zones[ZONE_ACCEPT] / n, 5) if n else 0.0,
        "band_rate": round(zones[ZONE_BAND] / n, 5) if n else 0.0,
        "by_entity_type": {k: dict(v) for k, v in by_type.items()},
        "inactive_codes_seen": inactive,
        "negation_flagged": negated_flagged,
        "concept_less_zones": dict(concept_less_zones),
        "examples": examples,
        "params": params,
    }


def _context(text: str, spans, pad: int = 45) -> str:
    a = max(0, min(s for s, _ in spans) - pad)
    b = min(len(text), max(e for _, e in spans) + pad)
    return " ".join(text[a:b].split())


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--manifest", default="manifest.json")
    ap.add_argument("--split", default="all", help="dev | test | pool | all")
    ap.add_argument("--json", help="write the full report here")
    ap.add_argument("--sweep", action="store_true", help="compare the open settings")
    a = ap.parse_args(argv)

    man = load_manifest(a.manifest)
    docs = corpus_mod.load_corpus(man["corpus"]["cadec_root"])
    registry = Registry(man["vocabulary"]["snomed_db"])
    if a.split == "all":
        doc_ids = sorted(docs)
    else:
        doc_ids = corpus_mod.read_split(man["corpus"]["splits_dir"], a.split)

    base = {**r1.DEFAULTS, **man["rungs"].get("1", {})}
    variants = {"manifest": base}
    if a.sweep:
        variants = {
            "manifest (defaults)": base,
            "reject_inactive=True": {**base, "reject_inactive": True},
            "finding_scope=all": {**base, "finding_scope": "all"},
            "lexical_mode=contained": {**base, "lexical_mode": "contained"},
            "negation_action=reject": {**base, "negation_action": "reject"},
            "no negation check": {**base, "check_negation": False},
        }

    out = {}
    for name, params in variants.items():
        out[name] = run(docs, doc_ids, registry, dict(params))

    print(f"corpus: {len(doc_ids)} docs, split={a.split}, release={registry.release}\n")
    for name, r in out.items():
        print(f"--- {name}")
        print(
            f"    mentions {r['n_mentions']:5d}   "
            f"ACCEPT {r['zones'].get(ZONE_ACCEPT,0):5d}  "
            f"BAND {r['zones'].get(ZONE_BAND,0):5d}  "
            f"REJECT {r['zones'].get(ZONE_REJECT,0):5d}   "
            f"false-rejection {r['false_rejection_rate']:.4f}"
        )
        for reason, k in sorted(r["reasons"].items(), key=lambda kv: -kv[1]):
            print(f"        {reason:22s} {k:5d}")
    if a.json:
        Path(a.json).parent.mkdir(parents=True, exist_ok=True)
        Path(a.json).write_text(json.dumps(out, indent=2))
        print(f"\nwrote {a.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(friendly(main))

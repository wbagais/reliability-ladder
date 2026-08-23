"""
split_by_type.py — every pooled rung-1 ratio, re-derived per entity type.

WHY. Drugs are span-checked only, never code-scored: CADEC codes them to AMT.
But every headline ratio in decisions.md pools drugs and reactions into one
denominator. Measured 2026-08-22: concept inactivity is 46.8% for drugs and
6.2% for reactions, and pools to the documented 11%. A drug-weighted average is
being reported as if it described the surface the pipeline grades.

This runs rung 1 over gold — model-free, reproducible — and splits every number.

CHOICES, stated because they move the counts:
  * one Record per gold MENTION, not per code. Multi-code golds (all_of/any_of)
    contribute their first code; the count of those is reported separately.
  * concept_less golds are passed through with whatever the corpus gives, so
    rung 1's own concept_less branch decides — not this script.
"""
import json, pathlib
from collections import Counter, defaultdict

from ladder.registry import Registry
from ladder.rungs import r1
from ladder.schema import Record
from ladder import corpus as C

man = json.loads(pathlib.Path("manifest.json").read_text())
reg = Registry(man["vocabulary"]["snomed_db"])
docs = C.load_corpus(man["corpus"]["cadec_root"])
golds = C.gold_records(docs, list(docs))
print(f"gold mentions: {len(golds)}")

recs, sources, meta = [], {}, Counter()
for i, g in enumerate(golds):
    d = g.to_dict()
    sct = d.get("sct") or []
    if isinstance(sct, str):
        sct = [sct]
    if len(sct) > 1:
        meta["multi_code_mentions"] += 1
    rec = Record(
        doc_id=d["doc_id"],
        entity_type=d.get("entity_type"),
        text=d.get("text", ""),
        spans=[tuple(s) for s in (d.get("spans") or [])],
        sct=(str(sct[0]) if sct else None),
        confidence=1.0,
        record_id=f"{d['doc_id']}#gold{i}",
    )
    rec.checks["gold_kind"] = d.get("gold_kind")
    recs.append(rec)
    sources[d["doc_id"]] = docs[d["doc_id"]].text
print("multi-code mentions (first code used):", meta["multi_code_mentions"])

r1.apply(recs, sources, {"registry": reg})

zones = defaultdict(Counter)
reasons = defaultdict(Counter)
audit = defaultdict(Counter)
kinds = defaultdict(Counter)
for rec in recs:
    t = rec.entity_type or "?"
    zones[t][rec.checks.get("r1_verdict")] += 1
    if rec.checks.get("r1_reason"):
        reasons[t][rec.checks["r1_reason"]] += 1
    for r in (rec.checks.get("r1_audit", {}) or {}).get("reasons", []):
        audit[t][r] += 1
    kinds[t][rec.checks.get("gold_kind")] += 1

types = sorted(zones)
print("\n=== ZONE OCCUPANCY (pooled figure on record: 43.1 / 56.8 / 0.13) ===")
for t in types:
    n = sum(zones[t].values())
    parts = "  ".join(f"{z}={c} ({c/n:.1%})" for z, c in sorted(zones[t].items()))
    print(f"  {t:10} n={n:5}  {parts}")
pool = Counter()
for t in types: pool.update(zones[t])
n = sum(pool.values())
print(f"  {'POOLED':10} n={n:5}  " + "  ".join(f"{z}={c} ({c/n:.1%})" for z, c in sorted(pool.items())))

print("\n=== REJECTION REASONS — verdict (first failure only) ===")
for t in types:
    print(f"  {t:10} {dict(reasons[t]) or '{}'}")

print("\n=== REJECTION REASONS — full audit set (all failures) ===")
for t in types:
    print(f"  {t:10} {dict(audit[t]) or '{}'}")

print("\n=== gold_kind by type ===")
for t in types:
    print(f"  {t:10} {dict(kinds[t])}")

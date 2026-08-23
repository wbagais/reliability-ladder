"""r4_gold_control.py — make rung 4's span channel readable.

The 40-doc rung 4 run judged 96 records, 94 of them REJECT. span_ok 3/96 is
equally consistent with a judge that fails everything and a judge correctly
reading an already-rejected tail. This mixes gold mentions into the judged set
so rung 1 actually splits it, then reports both channels by provenance.

Run from the repo root:
    LADDER_N=0 PYTHONPATH=. python3 ~/Downloads/r4_gold_control.py
"""
import json, pathlib, collections, dataclasses

from ladder.registry import Registry
from ladder.rungs.r0 import run
from ladder.rungs import r1, r4
from ladder import stub_llm as S, corpus as C

man = json.loads(pathlib.Path("manifest.json").read_text())
reg = Registry(man["vocabulary"]["snomed_db"])
items = S.load_items(man["corpus"]["splits_dir"])
src = {i["doc_id"]: i["text"] for i in items}

# ---- the arm the judge already saw -------------------------------------
r0_recs, _ = run(items, "A", S.stub, {"registry": reg, "rung0_offsets": "search"})
for r in r0_recs:
    r.checks["provenance"] = "r0"

# ---- gold mentions, lifted into Records --------------------------------
# Constructed field by field. An earlier version cloned an R0 record with
# dataclasses.replace and inherited its `text` -- the mention surface -- onto
# every gold record, so span grounding failed on all 226 and rung 1 rejected
# the entire control arm. Do not clone Records.
from ladder.rungs.r0 import Record

docs = C.load_corpus(man["corpus"]["cadec_root"])

gold_recs, skipped = [], collections.Counter()
for it in items:
    doc_id = it["doc_id"]
    for g in docs[doc_id].mentions:
        d = g.to_dict()
        if d.get("entity_type") != "reaction":
            continue
        spans = d.get("spans") or []
        codes = [str(c) for c in (d.get("sct") or [])]
        if not spans:
            skipped["no_span"] += 1
            continue
        if d.get("gold_kind") != "single" or len(codes) != 1:
            # all_of / CONCEPT_LESS are not single-code gradable. LIPITOR.511's
            # date defect is NOT caught here -- 20070731 has SCTID shape.
            skipped[str(d.get("gold_kind"))] += 1
            continue
        gold_recs.append(Record(
            doc_id=doc_id,
            entity_type="reaction",
            text=d.get("text", ""),
            spans=[tuple(sp) for sp in spans],
            sct=codes[0],
            meddra=(d.get("meddra") or [None])[0],
            confidence=1.0,
            zone="NEW",
            reason=None,
            record_id=f"{doc_id}#g{d.get('index')}",
            provenance=["gold"],
            checks={"provenance": "gold"},
        ))

print(f"gold records built {len(gold_recs)}   skipped {dict(skipped)}")

# ---- rung 1 over both, so the set splits --------------------------------
# zone() is pure: it returns the verdict and never touches the record, so the
# assignment into checks is ours to make.
both = gold_recs + r0_recs
for r in both:
    verdict, reason, audit = r1.zone(r, src.get(r.doc_id, ""), reg, {"registry": reg})
    r.checks["r1_verdict"] = verdict
    r.checks["r1_reason"] = reason
    r.checks["r1_audit_control"] = audit

print("rung 1 over the mixed set:",
      dict(collections.Counter(r.checks.get("r1_verdict") for r in both)))
print("  gold only:", dict(collections.Counter(
    r.checks.get("r1_verdict") for r in both if r.checks.get("provenance") == "gold")))
print("  r0 only:  ", dict(collections.Counter(
    r.checks.get("r1_verdict") for r in both if r.checks.get("provenance") == "r0")))

_v = collections.Counter(r.checks.get("r1_verdict") for r in both)
if len(_v) < 2 or min(_v.values()) < 0.1 * sum(_v.values()):
    raise SystemExit(
        f"rung 1 did not split the mixed set: {dict(_v)}. Judging it would "
        "reproduce the unreadable number at twice the cost. Stopping."
    )

# ---- one judge pass over the mixture ------------------------------------
both, m = r4.apply(both, src, {"registry": reg,
                               "judge_llm": S.judge("llama3.2:3b"),
                               "extractor_model": S.MODEL,
                               "judge_model": "llama3.2:3b"})
r4.report(m)

# ---- the breakdown r4.report cannot do ----------------------------------
print("\n" + "=" * 58)
print("BY PROVENANCE — the control")
print("=" * 58)
rows = collections.defaultdict(collections.Counter)
for r in both:
    c = r.checks.get("r4") or {}
    prov = r.checks.get("provenance", "?")
    if c.get("span_ok") is None:
        rows[prov]["unparsed"] += 1
        continue
    rows[prov]["judged"] += 1
    rows[prov]["span_ok" if c["span_ok"] else "span_not"] += 1
    rows[prov]["code_ok" if c.get("code_ok") else "code_not"] += 1

for prov in ("gold", "r0"):
    t = rows[prov]
    j = t["judged"] or 1
    print(f"\n  {prov}:  judged {t['judged']}  unparsed {t['unparsed']}")
    print(f"     span ok {t['span_ok']:4}  not {t['span_not']:4}   "
          f"({t['span_ok'] / j:.0%} ok)")
    print(f"     code ok {t['code_ok']:4}  not {t['code_not']:4}   "
          f"({t['code_ok'] / j:.0%} ok)")

print("\n  READ THIS: if span_ok is near 0% on gold too, the judge rejects")
print("  everything and the 3% on r0 output measures nothing. If gold spans")
print("  pass at a materially higher rate, the 3% was a correct read of a")
print("  bad tail and rung 4's span channel is doing real work.")

print("\nby rung 1 verdict:")
vrows = collections.defaultdict(collections.Counter)
for r in both:
    c = r.checks.get("r4") or {}
    if c.get("span_ok") is None:
        continue
    v = r.checks.get("r1_verdict")
    vrows[v]["n"] += 1
    vrows[v]["span_ok"] += bool(c["span_ok"])
    vrows[v]["code_ok"] += bool(c.get("code_ok"))
for v, t in sorted(vrows.items(), key=lambda kv: -kv[1]["n"]):
    print(f"  {str(v):8} n={t['n']:4}  span_ok={t['span_ok']:4}  code_ok={t['code_ok']:4}")

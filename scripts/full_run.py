"""
full_run.py — rung 0, gold scoring, and rung 2, on one set of predictions.

Everything measured before 2026-08-23 was produced on CPU inference. The move to
GPU changed the model's output: 176 mentions became 169, on the same 40 docs,
same model, same greedy decoding with seed 0. Determinism holds WITHIN hardware
(three runs identical) and not ACROSS it. Every CPU-era figure is superseded.

Rung 0 runs ONCE and both the scorer and rung 2 consume the same records, so the
numbers are guaranteed to describe the same run rather than two runs that happen
to agree.

    PYTHONPATH=. python3 full_run.py            # mode A
    PYTHONPATH=. python3 full_run.py --mode B
"""
import json, os, pathlib, subprocess, sys, time
from collections import Counter

from ladder.registry import Registry
from ladder.rungs.r0 import run, report as r0report
from ladder.rungs import r2
from ladder import stub_llm as S, corpus as C
from bench import align

MODE = sys.argv[sys.argv.index("--mode") + 1] if "--mode" in sys.argv else "A"

man = json.loads(pathlib.Path("manifest.json").read_text())
cfg = {"registry": Registry(man["vocabulary"]["snomed_db"]),
       "rung0_offsets": "search", "llm": S.stub}
os.environ.setdefault("LADDER_N", "0")
items = S.load_items(man["corpus"]["splits_dir"])
docs = C.load_corpus(man["corpus"]["cadec_root"])
sources = {i["doc_id"]: i["text"] for i in items}

def gpu():
    try:
        out = subprocess.run(["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
                             capture_output=True, text=True, timeout=5)
        return out.stdout.strip() or "unknown"
    except Exception:
        return "no nvidia-smi (CPU inference)"

backend = gpu()
print(f"compute backend: {backend}")
print(f"documents: {len(items)}\n")

# ---------------------------------------------------------------- rung 0
recs, agg = run(items, MODE, S.stub, cfg)
r0report(MODE, recs, agg)

# ---------------------------------------------------------------- scoring
def score(recs):
    by_doc = {}
    for r in recs:
        if r.spans and r.spans[0][0] >= 0:
            by_doc.setdefault(r.doc_id, []).append(
                {"fragments": [list(s) for s in r.spans], "code": str(r.sct or "")})
    tot, ng, npd = Counter(), 0, 0
    for it in items:
        gold = [{"fragments": [list(s) for s in g.to_dict().get("spans") or []],
                 "sct": [str(c) for c in (g.to_dict().get("sct") or [])],
                 "gold_kind": g.to_dict().get("gold_kind")}
                for g in docs[it["doc_id"]].mentions
                if g.to_dict().get("entity_type") == "reaction"]
        pred = by_doc.get(it["doc_id"], [])
        ng += len(gold); npd += len(pred)
        for k, v in align.score(pred, gold).items():
            if k in ("span_matched", "spurious", "missed", "code_correct",
                     "code_wrong", "matched_ungradable", "gold_gradable"):
                tot[k] += v
    return tot, ng, npd

tot, ng, npd = score(recs)
g = tot["code_correct"] + tot["code_wrong"]
sp = tot["span_matched"] / npd if npd else 0.0
sr = tot["span_matched"] / ng if ng else 0.0
print(f"\n{'=' * 58}\nAGAINST GOLD — reactions only\n{'=' * 58}")
print(f"  golds {ng}   predictions {npd}")
print(f"  SPAN  matched {tot['span_matched']}  spurious {tot['spurious']}  missed {tot['missed']}")
print(f"        P={sp:.4f}  R={sr:.4f}  F1={2*sp*sr/(sp+sr) if sp+sr else 0:.4f}")
print(f"  CODE  correct {tot['code_correct']}  wrong {tot['code_wrong']}  "
      f"ungradable {tot['matched_ungradable']}")
print(f"        accuracy {tot['code_correct']/g if g else None}  over {g} graded")

# ---------------------------------------------------------------- rung 2
recs, m2 = r2.apply(recs, sources, cfg)
r2.report(m2)

tot2, _, npd2 = score(recs)
g2 = tot2["code_correct"] + tot2["code_wrong"]
print(f"\n  after rung 2: code {tot2['code_correct']}/{g2} "
      f"(was {tot['code_correct']}/{g})")

# ---------------------------------------------------------------- provenance
from ladder import provenance as _prov
_stamp = _prov.gather(
    man, split="dev", n_docs=len(items), vocab=cfg["registry"],
    entry_point="scripts/full_run.py",
    models_spec={"extractor": (man.get("model", {}).get("extractor"), S.MODEL)},
    extra={"mode": MODE})
for _w in _prov.warnings(_stamp):
    print(f"  WARNING  {_w}")

out = {
    "provenance": _stamp,
    # kept so anything reading these keys still works
    "mode": MODE, "compute_backend": backend,
    "model": S.MODEL, "documents": len(items),
    "snomed_release": man["vocabulary"]["snomed_release"],
    "corpus_version": man["corpus"]["version"],
    "rung0": {"mentions": len(recs),
              "tokens": agg["tokens_in"] + agg["tokens_out"],
              "latency_p95_s": S.latency_p95()},
    "gold": {"reaction_golds": ng, "predictions": npd,
             "span_precision": round(sp, 4), "span_recall": round(sr, 4),
             "code_correct": tot["code_correct"], "code_graded": g},
    "rung3": {k: v for k, v in m2.items() if k != "t0"},
    "code_after_r3": {"correct": tot2["code_correct"], "graded": g2},
}
pathlib.Path("runs").mkdir(exist_ok=True)
p = pathlib.Path(f"runs/full-{MODE}-{int(time.time())}.json")
p.write_text(json.dumps(out, indent=2) + "\n")
print(f"\nwrote {p}")

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

IT SCORES THROUGH `ladder/score.py`, the same scorer as the ladder (ported
2026-08-31). It used to call the `bench/align.py` scorer, a SECOND one that paired
predictions with gold by character IoU >= 0.5 under bipartite assignment — a
third matching rule, reported under the same words ("precision", "recall") as
the ladder's own. Two definitions of "matched" behind one name is how a number
gets quoted into the wrong table. `bench/` is deleted; this was its only caller.

WHAT IS STILL NOT COMPARABLE: this runs the STUB. `cfg["llm"]` is
`ladder.stub_llm.stub`, so nothing here ever reaches a model, and the CPU/GPU
note above is history rather than a property of what this script now does. It
is a wiring smoke test over the r0 -> gold -> r2 path. The measured ladder is
`ladder/run.py`, and docs/decisions.md is where its numbers live.
"""
import json, os, pathlib, subprocess, sys, time

from ladder.registry import Registry
from ladder.rungs.r0 import run, report as r0report
from ladder.rungs import r2
from ladder import stub_llm as S, corpus as C
from ladder.score import score_run

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
# `score_run` filters to REACTION records and REACTION gold itself, so the
# hand-rolled entity_type filter that used to live here is gone. One behaviour
# changed on purpose: an unlocated prediction (spans (-1, -1), the
# schema-invalid shape) was silently DROPPED here and is a false positive to
# `score_run`. Counting it is the honest reading, and it is what ladder/run.py
# already does.
GOLDS = [g for it in items for g in docs[it["doc_id"]].mentions]


def score(recs):
    return score_run(recs, GOLDS, span_match="exact", vocab=cfg["registry"])


sc = score(recs)
det, cod = sc["detection"], sc["coding"]
print(f"\n{'=' * 58}\nAGAINST GOLD — reactions only\n{'=' * 58}")
print(f"  golds {sc['n_gold']}   predictions {sc['n_pred']}   "
      f"span_match {sc['span_match']}")
print(f"  SPAN  matched {det['n_matched']}  "
      f"spurious {sc['n_pred'] - det['n_matched']}  "
      f"missed {sc['n_gold'] - det['n_matched']}")
print(f"        P={det['precision']:.4f}  R={det['recall']:.4f}  F1={det['f1']:.4f}")
print(f"  CODE  correct {cod['correct']}  incorrect {cod['incorrect']}  "
      f"outdated {cod['outdated']}  abstained {cod['abstained']}")
print(f"        accuracy {cod['accuracy']:.4f}  over {cod['n']} matched")
print(f"  HEADLINE  P={sc['precision']:.4f}  R={sc['recall']:.4f}  F1={sc['f1']:.4f}")

# ---------------------------------------------------------------- rung 2
recs, m2 = r2.apply(recs, sources, cfg)
r2.report(m2)

sc2 = score(recs)
print(f"\n  after rung 2: code {sc2['coding']['correct']}/{sc2['coding']['n']} "
      f"(was {cod['correct']}/{cod['n']})")

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
    # Stamped straight off score_run, with span_match named: a precision with
    # no matcher beside it is the ambiguity this port removed.
    "gold": {"reaction_golds": sc["n_gold"], "predictions": sc["n_pred"],
             "span_match": sc["span_match"],
             "detection_precision": round(det["precision"], 4),
             "detection_recall": round(det["recall"], 4),
             "precision": round(sc["precision"], 4),
             "recall": round(sc["recall"], 4),
             "f1": round(sc["f1"], 4),
             "code_correct": cod["correct"], "code_matched": cod["n"]},
    "rung3": {k: v for k, v in m2.items() if k != "t0"},
    "code_after_r3": {"correct": sc2["coding"]["correct"],
                      "matched": sc2["coding"]["n"]},
}
pathlib.Path("runs").mkdir(exist_ok=True)
p = pathlib.Path(f"runs/full-{MODE}-{int(time.time())}.json")
p.write_text(json.dumps(out, indent=2) + "\n")
print(f"\nwrote {p}")

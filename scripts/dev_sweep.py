"""
dev_sweep.py — rung 0 mode A over the whole dev split, both offset arms.

Two documents is an observation. Forty is a measurement. The offsets flag is
the ablation: identical model output, identical checks, and the question is
whether the two arms still produce different rejection TABLES at scale while
the underlying failure set stays the same.

Writes runs/dev-<arm>-<ts>.json so the numbers survive the terminal.

    PYTHONPATH=. python3 dev_sweep.py
"""
import json, os, pathlib, time
from collections import Counter

from ladder.registry import Registry
from ladder.rung0_ab import run, report
from ladder import stub_llm as S

man = json.loads(pathlib.Path("manifest.json").read_text())
reg = Registry(man["vocabulary"]["snomed_db"])

os.environ.setdefault("LADDER_N", "0")          # 0 = whole split
os.environ.setdefault("LADDER_SPLIT", "dev")
items = S.load_items(man["corpus"]["splits_dir"])
print(f"documents: {len(items)}\n")

pathlib.Path("runs").mkdir(exist_ok=True)
stamp = int(time.time())
summary = {}

for arm in ("model", "search"):
    S.LATENCIES.clear()
    t0 = time.time()
    recs, agg = run(items, "A", S.stub, {"registry": reg, "rung0_offsets": arm})
    out = report(f"A/{arm}", recs, agg)

    how = Counter(r.checks.get("offsets") for r in recs)
    print(f"  offset provenance: {dict(how)}")
    print(f"  latency p95: {S.latency_p95()}s over {len(S.LATENCIES)} calls")
    print(f"  wall: {time.time()-t0:.0f}s\n")

    out.update({
        "arm": arm,
        "documents": len(items),
        "offset_provenance": {str(k): v for k, v in how.items()},
        "latency_p95_s": S.latency_p95(),
        "tokens_per_record": round(out["tokens"] / max(out["n"], 1), 1),
        "model": S.MODEL,
        "snomed_release": man["vocabulary"]["snomed_release"],
        "corpus_version": man["corpus"]["version"],
    })
    summary[arm] = out
    p = pathlib.Path(f"runs/dev-{arm}-{stamp}.json")
    p.write_text(json.dumps(out, indent=2) + "\n")
    print(f"  wrote {p}\n")

# --- the ablation --------------------------------------------------------
m, s = summary["model"], summary["search"]
print("=" * 62)
print("OFFSET ABLATION — same output, same checks, different table?")
print("=" * 62)
print(f"  {'':24s} {'model':>10s} {'search':>10s}")
print(f"  {'mentions':24s} {m['n']:10d} {s['n']:10d}")
print(f"  {'rejected':24s} {m['rejected']:10d} {s['rejected']:10d}")
keys = sorted(set(m['reasons']) | set(s['reasons']))
print("\n  verdict reasons (first failure):")
for k in keys:
    if m['reasons'].get(k) or s['reasons'].get(k):
        print(f"  {k:24s} {m['reasons'].get(k,0):10d} {s['reasons'].get(k,0):10d}")
print("\n  full failure set (every check):")
for k in keys:
    a, b = m['reasons_all'].get(k, 0), s['reasons_all'].get(k, 0)
    if a or b:
        flag = "   <- invariant" if a == b else "   <- MOVED"
        print(f"  {k:24s} {a:10d} {b:10d}{flag}")
print(f"\n  {'cost: tokens/record':24s} {m['tokens_per_record']:10} {s['tokens_per_record']:10}")
print(f"  {'cost: latency p95 (s)':24s} {m['latency_p95_s']:10} {s['latency_p95_s']:10}")
print("\n  If the full set is invariant and the verdict table is not, the flag")
print("  changed what gets REPORTED, not what the model got wrong.")

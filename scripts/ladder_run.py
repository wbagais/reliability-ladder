"""ladder_run.py — the full ladder in specified order [0, 1, 2, 3, 4, 5, 6].

Every rung so far has been measured standalone. This is the first script that
runs them in the order the manifest specifies, which is the only way to see
whether the rungs interact. Per-rung numbers all assume they do not.

Rung 1 runs in OBSERVE mode: it records a verdict and never moves the zone.
Rung 5 pays the coverage cost, last, per docs/wiki/content/r2.md.

    LADDER_N=0 PYTHONPATH=. python3 scripts/ladder_run.py
"""
import json, pathlib, collections, inspect, time

from ladder.registry import Registry
from ladder.rungs.r0 import run
from ladder.rungs import r1, r2, r3, r4, r5
from ladder import stub_llm as S

ORDER = [0, 1, 2, 3, 4, 5, 6]

man = json.loads(pathlib.Path("manifest.json").read_text())
reg = Registry(man["vocabulary"]["snomed_db"])
items = S.load_items(man["corpus"]["splits_dir"])
src = {i["doc_id"]: i["text"] for i in items}

print("rung order:", ORDER)
for name, mod in (("r2", r3), ("r4", r4), ("r3", r5), ("r5", r2)):
    print(f"  {name}.apply{inspect.signature(mod.apply)}")
print()


def call(mod, name, records, cfg):
    """Call rungN.apply, surfacing the real signature if it differs."""
    try:
        out = mod.apply(records, src, cfg)
    except TypeError as e:
        raise SystemExit(
            f"{name}.apply signature mismatch: {e}\n"
            f"  actual: {name}.apply{inspect.signature(mod.apply)}"
        )
    if isinstance(out, tuple):
        return out
    return out, None


def observe(records, label):
    """Rung 1 in observe mode: record the verdict, never move the zone."""
    for rec in records:
        v, why, audit = r1.zone(rec, src.get(rec.doc_id, ""), reg, {"registry": reg})
        rec.checks["r1_verdict"] = v
        rec.checks["r1_reason"] = why
        rec.checks["r1_audit"] = audit
    c = collections.Counter(r.checks["r1_verdict"] for r in records)
    print(f"  r1 observe [{label}]: {dict(c)}")
    return records


def codes(records):
    return sum(1 for r in records if r.sct)


t_start = time.perf_counter()

# ---- 0 -----------------------------------------------------------------
print("=" * 58, "\nRUNG 0 — extract\n", "=" * 58, sep="")
recs, m0 = run(items, "A", S.stub, {"registry": reg, "rung0_offsets": "search"})
print(f"  mentions {len(recs)}   carrying a code {codes(recs)}")

# ---- 1 (observe) -------------------------------------------------------
print("\n" + "=" * 58, "\nRUNG 1 — validate (observe)\n", "=" * 58, sep="")
observe(recs, "after r0")

# ---- 2 -----------------------------------------------------------------
print("\n" + "=" * 58, "\nRUNG 2 — self-correction\n", "=" * 58, sep="")
recs, m2 = call(r2, "r2", recs, {"registry": reg, "llm": S.stub})
if m2 and hasattr(r2, "report"):
    r2.report(m2)
observe(recs, "after r2")
print(f"  carrying a code {codes(recs)}")

# ---- 3 -----------------------------------------------------------------
print("\n" + "=" * 58, "\nRUNG 3 — voting\n", "=" * 58, sep="")
recs, m3 = call(r3, "r3", recs, {"registry": reg, "llm": S.voter(0.7), "k": 3})
if m3:
    r3.report(m3)
observe(recs, "after r3")
print(f"  carrying a code {codes(recs)}")

# ---- 4 -----------------------------------------------------------------
print("\n" + "=" * 58, "\nRUNG 4 — judge\n", "=" * 58, sep="")
recs, m4 = call(r4, "r4", recs, {"registry": reg,
                                 "judge_llm": S.judge("llama3.2:3b"),
                                 "extractor_model": S.MODEL,
                                 "judge_model": "llama3.2:3b"})
if m4:
    r4.report(m4)

# ---- 5 (last) ----------------------------------------------------------
print("\n" + "=" * 58, "\nRUNG 5 — abstention\n", "=" * 58, sep="")
recs, _ = call(r5, "r5", recs, {"registry": reg})
print("  zones:", dict(collections.Counter(r.zone for r in recs)))
print("  reasons:", dict(collections.Counter(r.reason for r in recs).most_common(8)))
withheld = sum(1 for r in recs if "withheld" in r.checks)
print(f"  withheld {withheld} of {len(recs)}   still carrying a code {codes(recs)}")

# ---- 6 -----------------------------------------------------------------
print("\n" + "=" * 58, "\nRUNG 6 — triage desk\n", "=" * 58, sep="")
print(f"  NOT BUILT. Would receive {withheld} withheld records.")
print("  Blocked upstream, not unfinished: rung 0 produced 0 correct codes,")
print("  so every record reaching a reviewer carries a wrong answer or none.")

# ---- summary -----------------------------------------------------------
print("\n" + "=" * 58, "\nEND TO END\n", "=" * 58, sep="")
print(f"  order {ORDER}")
print(f"  records {len(recs)}   published {codes(recs)}   withheld {withheld}")
print(f"  coverage {codes(recs) / len(recs):.3f}")
print(f"  wall clock {time.perf_counter() - t_start:.1f}s")
print("\n  Compare against the standalone runs. Any difference is rung")
print("  interaction, which every per-rung figure so far assumes is zero.")

"""
rung0_ab.py — the rung 0 ablation: does a vocabulary lookup tool help?

THE RULE: one implementation, one flag. Modes A and B share every line except
the tool block. Two implementations would confound tool access with prompting.

    python -m ladder.rung0_ab --mode A       # recall only  (manifest default)
    python -m ladder.rung0_ab --mode B       # search tool
    python -m ladder.rung0_ab --compare      # both, side by side

`rung0_mode` in manifest.json decides which is the headline and which is the
ablation. Whichever you pick changes what every number above it means, so it
lives in the manifest rather than in a flag default.

What this file used to own, and no longer does
-----------------------------------------------
It had its own `Rec` dataclass, its own `rung1()` and its own `REASONS` list.
All three are gone, because a second implementation of the frozen contract is
how a project ends up with two different numbers for the same run — and because
that rung 1 reproduced three faults the measured one had already fixed:

  * it rejected on negation, which costs 427 gold-correct mentions (4.7%):
    CADEC annotates a mention regardless of polarity
  * it rejected any code the hierarchy could not place, which is every RETIRED
    concept — another 413 gold mentions
  * it had two outcomes (REJECT / PASS), so it could not express "plausible but
    unverifiable", which is where 57% of even a perfect answer set lands

Records are `ladder.schema.Record`, validation is `ladder.rungs.r1`, and reason
names come from `ladder.schema.REJECT_REASONS`. See docs/decisions.md.
"""

from __future__ import annotations

import argparse
import json
import sys
import time

from ladder import vocab
from ladder.ledger import Ledger
from ladder.rungs import r1
from ladder.schema import REACTION, REJECT_REASONS, Record, ZONE_ACCEPT, ZONE_BAND, ZONE_REJECT

# ------------------------------------------------------------------ prompts
BASE = """Extract every adverse reaction the reporter describes in the post below.

For each one return:
  span_text  - the reporter's exact words, copied character for character
  start,end  - character offsets of span_text in the post
  code       - the SNOMED CT concept id for that reaction
  confidence - 0.0 to 1.0

Report only reactions the writer actually experienced. Do not report anything
they say they did NOT have.

Return JSON: {"mentions":[{"span_text":..,"start":..,"end":..,"code":..,"confidence":..}]}
"""

TOOL_BLOCK = """
You have a vocabulary search tool. Call it before choosing any code:
    SEARCH("term") -> [{code, label}, ...]
Choose a code from the results. If nothing fits, set code to null.
"""


def build_prompt(mode: str) -> str:
    return BASE + (
        TOOL_BLOCK
        if mode == "B"
        else "\nEmit the SNOMED CT concept id from your own knowledge.\n"
    )


# ------------------------------------------- rung 0 — the only LLM call here
def rung0(doc_id: str, text: str, mode: str, llm) -> tuple[list[Record], dict]:
    """Identical for A and B except that B may call the tool first."""
    meta = {"tool_calls": 0, "tokens_in": 0, "tokens_out": 0}
    raw, usage = llm(build_prompt(mode), text, mode)
    meta["tokens_in"] += usage["in"]
    meta["tokens_out"] += usage["out"]

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        # Never silently repaired: a parse failure is a real reliability cost
        # and rung 0's counter-metric.
        return [], {**meta, "parse_failed": True}

    out = []
    for i, m in enumerate(parsed.get("mentions", [])):
        start, end = m.get("start", -1), m.get("end", -1)
        rec = Record(
            doc_id=doc_id,
            entity_type=REACTION,
            text=m.get("span_text", ""),
            spans=[(start, end)] if isinstance(start, int) and isinstance(end, int) else [],
            sct=(str(m["code"]) if m.get("code") is not None else None),
            confidence=float(m.get("confidence", 0) or 0),
            record_id=f"{doc_id}#{i}",
        )
        rec.checks["rung0_mode"] = mode
        if mode == "B" and rec.text:
            rec.checks["tool_results"] = vocab.search(rec.text, 5)
            meta["tool_calls"] += 1
        out.append(rec)
    return out, meta


def honoured_tool(rec: Record) -> bool | None:
    """Mode B only, and the most interesting check on the ladder.

    The model searched, got candidates back, then emitted a code. Did it emit
    one of them, or override its own lookup with something invented? None when
    no search was made for this record.
    """
    results = rec.checks.get("tool_results")
    if not results:
        return None
    return str(rec.sct) in {str(r["code"]) for r in results}


# ------------------------------------------------------------------ harness
def run(items, mode, llm, cfg=None):
    """Rung 0, then the measured rung 1 — no second validation implementation."""
    cfg = dict(cfg or {})
    recs: list[Record] = []
    agg = {"tokens_in": 0, "tokens_out": 0, "tool_calls": 0, "parse_failed": 0, "t0": time.time()}
    sources = {}
    for it in items:
        got, meta = rung0(it["doc_id"], it["text"], mode, llm)
        for k in ("tokens_in", "tokens_out", "tool_calls"):
            agg[k] += meta.get(k, 0)
        agg["parse_failed"] += int(meta.get("parse_failed", False))
        sources[it["doc_id"]] = it["text"]
        recs += got
    r1.apply(recs, sources, cfg)
    for rec in recs:
        rec.checks["honoured_tool"] = honoured_tool(rec)
    agg["seconds"] = round(time.time() - agg["t0"], 2)
    return recs, agg


def report(mode, recs, agg):
    n = len(recs)
    verdicts = [r.checks.get("r1_verdict") for r in recs]
    rej = [r for r in recs if r.checks.get("r1_verdict") == ZONE_REJECT]
    overrode = sum(1 for r in recs if r.checks.get("honoured_tool") is False)
    print(f"\n{'=' * 58}\nMODE {mode} — {'search tool' if mode == 'B' else 'recall only'}\n{'=' * 58}")
    print(f"  mentions emitted by R0     {n}")
    print(f"  rejected by R1             {len(rej)}  ({(len(rej) / n * 100 if n else 0):.0f}%)")
    print(f"  accepted / band            {verdicts.count(ZONE_ACCEPT)} / {verdicts.count(ZONE_BAND)}")
    reasons = {w: sum(1 for r in rej if r.checks.get("r1_reason") == w) for w in REJECT_REASONS}
    audited = {
        w: sum(1 for r in recs
               if w in (r.checks.get("r1_audit", {}) or {}).get("reasons", []))
        for w in REJECT_REASONS
    }
    masked = sum(max(0, audited[w] - reasons[w]) for w in REJECT_REASONS)
    print("  rejection reasons — verdict (first failure) vs every failure:")
    print(f"     {'':22s} {'verdict':>8s} {'all':>6s}")
    for why in REJECT_REASONS:
        if reasons[why] or audited[why]:
            flag = "  <- hidden by check order" if audited[why] > reasons[why] else ""
            print(f"     {why:22s} {reasons[why]:8d} {audited[why]:6d}{flag}")
    if masked:
        print(f"  failures the verdict table did not show: {masked}")
    unevaluable = {}
    for r in recs:
        for k, v in ((r.checks.get("r1_audit", {}) or {}).get("unevaluable") or {}).items():
            unevaluable[f"{k}: {v}"] = unevaluable.get(f"{k}: {v}", 0) + 1
    for k, v in sorted(unevaluable.items()):
        print(f"  could not be checked: {k}  ({v})")
    if mode == "B":
        print(f"  overrode its own lookup    {overrode}")
    print(
        f"  tokens {agg['tokens_in'] + agg['tokens_out']:6d}"
        f"   tool calls {agg['tool_calls']:3d}"
        f"   JSON failures {agg['parse_failed']}"
        f"   {agg['seconds']}s"
    )
    return {
        "mode": mode,
        "n": n,
        "rejected": len(rej),
        "reasons": reasons,
        "reasons_all": audited,
        "masked": masked,
        "overrode_tool": overrode,
        "tokens": agg["tokens_in"] + agg["tokens_out"],
        "tool_calls": agg["tool_calls"],
    }


def compare(a, b):
    print(f"\n{'=' * 58}\nA vs B — the ablation\n{'=' * 58}")
    print(f"  {'':24s} {'A recall':>10s} {'B tool':>10s}")
    print(
        f"  {'rejection rate':24s} "
        f"{a['rejected'] / max(a['n'], 1) * 100:9.0f}% {b['rejected'] / max(b['n'], 1) * 100:9.0f}%"
    )
    for w in REJECT_REASONS:
        if a["reasons"].get(w) or b["reasons"].get(w):
            print(f"  {w:24s} {a['reasons'].get(w, 0):10d} {b['reasons'].get(w, 0):10d}")
    print(f"  {'overrode its own lookup':24s} {a['overrode_tool']:10d} {b['overrode_tool']:10d}")
    print(f"  {'tokens':24s} {a['tokens']:10d} {b['tokens']:10d}")
    print(f"  {'vocabulary calls':24s} {a['tool_calls']:10d} {b['tool_calls']:10d}")
    print("\n  Read it this way: if B's rejection rate falls but errors reappear as")
    print("  'overrode its own lookup' or as wrong-but-valid codes, the tool MOVED")
    print("  the errors rather than removing them. That is the finding either way.")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--mode", choices=["A", "B"])
    ap.add_argument("--compare", action="store_true")
    ap.add_argument("--manifest", default="manifest.json")
    a = ap.parse_args(argv)

    from ladder.manifest import load_manifest
    from ladder.registry import Registry

    man = load_manifest(a.manifest)
    cfg = dict(man["rungs"].get("1", {}))
    cfg["registry"] = Registry(man["vocabulary"]["snomed_db"])
    cfg["ledger"] = Ledger(f"{man['output']['dir']}/rung0_ab.ledger.jsonl", run_id="rung0_ab")

    try:
        from ladder.stub_llm import load_items, stub
    except ModuleNotFoundError:
        return int(
            bool(
                sys.stderr.write(
                    "ladder/stub_llm.py is not in the repo yet — it is the client this\n"
                    "module runs against. Supply `stub(prompt, text, mode) -> (raw, usage)`\n"
                    "and `load_items(path) -> [{doc_id, text}]`, or drive run() directly.\n"
                )
            )
        )

    items = load_items(man["corpus"]["splits_dir"])
    if a.compare:
        ra, ga = run(items, "A", stub, cfg)
        rb, gb = run(items, "B", stub, cfg)
        compare(report("A", ra, ga), report("B", rb, gb))
    else:
        mode = a.mode or ("B" if man.get("rung0_mode") == "search" else "A")
        report(mode, *run(items, mode, stub, cfg))
    cfg["ledger"].close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

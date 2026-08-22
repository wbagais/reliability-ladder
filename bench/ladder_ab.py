"""
ladder_ab.py — rung 0 (modes A and B) + rung 1, in one file.

THE RULE: one implementation, one flag. Modes A and B share every line except
the tool block. Two implementations would confound tool access with prompting.

    python ladder_ab.py --mode A
    python ladder_ab.py --mode B
    python ladder_ab.py --compare        # both, side by side
"""
from __future__ import annotations
import argparse, json, re, sys, time
from dataclasses import dataclass, field, asdict
from pathlib import Path

from bench import vocab

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
    return BASE + (TOOL_BLOCK if mode == "B" else
                   "\nEmit the SNOMED CT concept id from your own knowledge.\n")


# ------------------------------------------------------------------- record
@dataclass
class Rec:
    doc_id: str
    span_text: str = ""
    start: int = -1
    end: int = -1
    code: str | None = None
    confidence: float = 0.0
    mode: str = "A"
    tool_results: list = field(default_factory=list)
    zone: str = ""
    reason: str = ""
    checks: dict = field(default_factory=dict)


# ------------------------------------------------- rung 0 — the only LLM call
def rung0(doc_id: str, text: str, mode: str, llm) -> tuple[list[Rec], dict]:
    """Identical for A and B except that B may call the tool first."""
    meta = {"tool_calls": 0, "tokens_in": 0, "tokens_out": 0}
    prompt = build_prompt(mode)
    raw, usage = llm(prompt, text, mode)
    meta["tokens_in"] += usage["in"]; meta["tokens_out"] += usage["out"]

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return [], {**meta, "parse_failed": True}     # never silently repaired

    out = []
    for m in parsed.get("mentions", []):
        r = Rec(doc_id=doc_id, span_text=m.get("span_text", ""),
                start=m.get("start", -1), end=m.get("end", -1),
                code=(str(m["code"]) if m.get("code") is not None else None),
                confidence=float(m.get("confidence", 0)), mode=mode)
        if mode == "B" and r.span_text:
            r.tool_results = vocab.search(r.span_text, 5)
            meta["tool_calls"] += 1
        out.append(r)
    return out, meta


# ------------------------------------------------- rung 1 — zero LLM calls
REASONS = ["ungrounded_span", "negated", "no_code", "code_not_found",
           "wrong_semantic_type", "overrode_tool"]

def rung1(r: Rec, source: str) -> Rec:
    c = {}
    c["grounded"] = vocab.grounded(source, (r.start, r.end), r.span_text)
    if not c["grounded"]:
        r.zone, r.reason, r.checks = "REJECT", "ungrounded_span", c
        return r                                   # free — no lookup happens

    c["negated"] = vocab.negated(source, (r.start, r.end))
    if c["negated"]:
        r.zone, r.reason, r.checks = "REJECT", "negated", c
        return r                                   # free — no lookup happens

    if not r.code:
        r.zone, r.reason, r.checks = "REJECT", "no_code", c
        return r

    c["exists"] = vocab.exists(r.code)
    if not c["exists"]:
        r.zone, r.reason, r.checks = "REJECT", "code_not_found", c
        return r

    c["is_finding"] = vocab.is_finding(r.code)
    if not c["is_finding"]:
        r.zone, r.reason, r.checks = "REJECT", "wrong_semantic_type", c
        return r

    # check 7 — mode B only. Did the model honour its own lookup?
    hon = vocab.honoured_tool(r.code, r.tool_results)
    c["honoured_tool"] = hon
    if hon is False:
        r.zone, r.reason, r.checks = "REJECT", "overrode_tool", c
        return r

    c["lexical_overlap"] = round(vocab.lexical_overlap(r.span_text, r.code), 2)
    r.zone, r.reason, r.checks = "PASS", "", c       # PASS is not "correct"
    return r


# ------------------------------------------------------------------ harness
def run(items, mode, llm):
    recs, agg = [], {"tokens_in": 0, "tokens_out": 0, "tool_calls": 0,
                     "parse_failed": 0, "t0": time.time()}
    for it in items:
        got, meta = rung0(it["doc_id"], it["text"], mode, llm)
        for k in ("tokens_in", "tokens_out", "tool_calls"):
            agg[k] += meta.get(k, 0)
        agg["parse_failed"] += int(meta.get("parse_failed", False))
        recs += [rung1(r, it["text"]) for r in got]
    agg["seconds"] = round(time.time() - agg["t0"], 2)
    return recs, agg


def report(mode, recs, agg):
    n = len(recs)
    rej = [r for r in recs if r.zone == "REJECT"]
    print(f"\n{'='*58}\nMODE {mode} — {'search tool' if mode=='B' else 'recall only'}\n{'='*58}")
    print(f"  mentions emitted by R0     {n}")
    print(f"  rejected by R1             {len(rej)}  ({(len(rej)/n*100 if n else 0):.0f}%)")
    print(f"  passed validation          {n-len(rej)}")
    print("  rejection reasons — the number that matters:")
    for why in REASONS:
        k = sum(1 for r in rej if r.reason == why)
        if k: print(f"     {why:22s} {k}")
    print(f"  tokens {agg['tokens_in']+agg['tokens_out']:6d}"
          f"   tool calls {agg['tool_calls']:3d}"
          f"   JSON failures {agg['parse_failed']}"
          f"   {agg['seconds']}s")
    return {"mode": mode, "n": n, "rejected": len(rej),
            "reasons": {w: sum(1 for r in rej if r.reason == w) for w in REASONS},
            "tokens": agg["tokens_in"] + agg["tokens_out"],
            "tool_calls": agg["tool_calls"]}


def compare(a, b):
    print(f"\n{'='*58}\nA vs B — the ablation\n{'='*58}")
    print(f"  {'':24s} {'A recall':>10s} {'B tool':>10s}")
    print(f"  {'rejection rate':24s} "
          f"{a['rejected']/max(a['n'],1)*100:9.0f}% {b['rejected']/max(b['n'],1)*100:9.0f}%")
    for w in REASONS:
        if a["reasons"][w] or b["reasons"][w]:
            print(f"  {w:24s} {a['reasons'][w]:10d} {b['reasons'][w]:10d}")
    print(f"  {'tokens':24s} {a['tokens']:10d} {b['tokens']:10d}")
    print(f"  {'vocabulary calls':24s} {a['tool_calls']:10d} {b['tool_calls']:10d}")
    print("\n  Read it this way: if B's rejection rate falls but errors reappear as")
    print("  'overrode_tool' or as wrong-but-valid codes, the tool MOVED the errors")
    print("  rather than removing them. That is the finding either way.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["A", "B"])
    ap.add_argument("--compare", action="store_true")
    ap.add_argument("--data", default="items.json")
    a = ap.parse_args()
    try:
        from bench.stub_llm import stub, load_items
    except ModuleNotFoundError:
        sys.exit(
            "bench/stub_llm.py is not in the repo yet — it is the fake client this\n"
            "module runs against. Supply `stub(prompt, text, mode) -> (raw, usage)`\n"
            "and `load_items(path) -> [{doc_id, text}]`, or drive run() directly."
        )
    items = load_items(a.data)
    if a.compare:
        ra, ga = run(items, "A", stub); rb, gb = run(items, "B", stub)
        compare(report("A", ra, ga), report("B", rb, gb))
    else:
        m = a.mode or "A"
        report(m, *run(items, m, stub))

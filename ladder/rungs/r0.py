"""Rung 0 — the bare LLM. One call per document. Everything else is measured
against this.

Rung 0 is the one rung handed an EMPTY record list: it receives the split's
`sources` and returns the records every other rung then routes. Rungs 1-6 judge,
correct, vote on and abstain from what this rung produced; none of them can
create a mention.

    raw, usage = cfg["llm"](prompt, source, mode)

The model is never chosen here. `run.py` resolves it once from
`manifest.model.extractor` and injects `cfg["llm"]` — see `ladder.llm.for_rung`.

MODES. Rung 0 has an ablation built in, and the rule is one implementation, one
flag: modes A and B share every line except the tool block, because two
implementations would confound tool access with prompting.

    A  recall only — the model emits a SNOMED code from its own knowledge
    B  search tool — the model is given a vocabulary lookup first

`rung0_mode` in manifest.json decides which is the headline and which is the
ablation. `--compare` at the bottom of this file runs them side by side.

WHAT RUNG 0 IS ACTUALLY ASKED TO DO, and how the four parts fail differently:

    find     which spans are adverse reactions
    quote    the reporter's exact words          — reliable
    locate   character offsets of that quote     — fails at every model size
    code     the SNOMED concept id               — scales with the model

Measured on ARTHROTEC.1, mode A: claude-haiku-4-5 got 2 of 3 codes real and
0 of 3 offsets right; granite4:micro-h got 0 of 2 codes and 0 of 2 offsets, and
0 of 26 codes across ten dev documents. Quoting is near-perfect for both (77%
verbatim over the ten documents) while offset arithmetic fails regardless of
size — which is what `rung0_offsets: "search"` exists to bypass, since a span
the model quoted correctly can be located by string search instead of trusting
its character count.
"""

from __future__ import annotations

import argparse
import json
import time
from typing import Any

from ladder import vocab
from ladder.ledger import Ledger
from ladder.rungs import r1
from ladder.schema import (
    REACTION,
    REJECT_REASONS,
    Record,
    ZONE_ACCEPT,
    ZONE_BAND,
    ZONE_REJECT,
)

RUNG = 0

DEFAULTS: dict[str, Any] = {
    #: "model" trusts the offsets the model emitted; "search" discards them and
    #: locates span_text in the source. See the module docstring.
    "rung0_offsets": "model",
    "rung0_mode": "recall",
}

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


def recover_offsets(span_text: str, source: str, claimed: tuple[int, int]) -> tuple[int, int, str]:
    """Locate span_text in source. Returns (start, end, how).

    Disambiguates repeats by the model's own claim: its arithmetic was wrong but
    its sense of position was roughly right, so the nearest occurrence to the
    claimed start is a better guess than the first one.
    """
    if not span_text:
        return -1, -1, "empty"
    hits, i = [], source.find(span_text)
    while i != -1:
        hits.append(i)
        i = source.find(span_text, i + 1)
    if not hits:
        low = source.lower().find(span_text.lower())
        if low == -1:
            return -1, -1, "not_in_source"
        return low, low + len(span_text), "search_case_insensitive"
    if len(hits) == 1:
        s = hits[0]
        return s, s + len(span_text), "search_unique"
    anchor = claimed[0] if isinstance(claimed[0], int) and claimed[0] >= 0 else 0
    s = min(hits, key=lambda h: abs(h - anchor))
    return s, s + len(span_text), f"search_nearest_of_{len(hits)}"


def rung0(doc_id: str, text: str, mode: str, llm, cfg=None) -> tuple[list[Record], dict]:
    """One document, one model call. Identical for A and B except the tool block."""
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

    offsets_mode = (cfg or {}).get("rung0_offsets", "model")
    out = []
    for i, m in enumerate(parsed.get("mentions", [])):
        start, end = m.get("start", -1), m.get("end", -1)
        how = "model"
        if offsets_mode == "search":
            start, end, how = recover_offsets(m.get("span_text", ""), text, (start, end))
            key = "offsets_" + how.split("_")[0]
            meta[key] = meta.get(key, 0) + 1
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
        rec.checks["offsets"] = how
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


def apply(
    records: list[Record], sources: dict[str, str], cfg: dict[str, Any]
) -> tuple[list[Record], dict]:
    """The rung entry point. `records` is EMPTY — rung 0 builds from `sources`.

    Refuses to run on a non-empty list rather than appending to it: rung 0 twice
    over the same split would double every mention and every number above it.
    """
    cfg = {**DEFAULTS, **(cfg or {})}
    if records:
        raise RuntimeError(
            f"rung 0 was handed {len(records)} existing records. It is the rung "
            "that CREATES them, so running it over a populated set would double "
            "the mention count. Run it first, or not at all."
        )
    llm = cfg.get("llm")
    if llm is None:
        raise RuntimeError(
            "rung 0 has no model. Skipping silently would report an empty "
            "extraction as a result. Set manifest.model.extractor."
        )
    ledger = cfg.get("ledger")
    mode = "B" if cfg.get("rung0_mode") == "search" else "A"

    agg: dict[str, Any] = {
        "documents": 0, "records": 0, "tokens_in": 0, "tokens_out": 0,
        "tool_calls": 0, "parse_failed": 0, "t0": time.time(),
    }
    out: list[Record] = []
    for doc_id, text in sources.items():
        t0 = time.time()
        got, meta = rung0(doc_id, text, mode, llm, cfg)
        elapsed_ms = (time.time() - t0) * 1000
        agg["documents"] += 1
        agg["parse_failed"] += int(meta.get("parse_failed", False))
        for k in ("tokens_in", "tokens_out", "tool_calls"):
            agg[k] += meta.get(k, 0)
        for rec in got:
            rec.checks["honoured_tool"] = honoured_tool(rec)
        # One ledger row per DOCUMENT, not per record: rung 0's unit of cost is
        # the call, and a document that produced no mentions still cost one.
        if ledger:
            ledger.log(
                rung=RUNG,
                doc_id=doc_id,
                record_id=doc_id,
                zone="NEW",
                outcome="parse_failed" if meta.get("parse_failed") else "extracted",
                reason="json_decode" if meta.get("parse_failed") else None,
                tokens_in=meta["tokens_in"],
                tokens_out=meta["tokens_out"],
                api_calls=1,
                latency_ms=elapsed_ms,
                mode=mode,
                mentions=len(got),
            )
        out += got

    agg["records"] = len(out)
    agg["seconds"] = round(time.time() - agg["t0"], 2)
    return out, agg


def report_run(agg: dict) -> None:
    n, docs = agg["records"], agg["documents"]
    print(f"\n{'=' * 58}\nRUNG 0 — bare LLM\n{'=' * 58}")
    print(f"  documents             {docs}")
    print(f"  mentions emitted      {n}  ({n / docs if docs else 0:.1f} per document)")
    print(f"  JSON parse failures   {agg['parse_failed']}")
    print(f"  tokens {agg['tokens_in'] + agg['tokens_out']:6d}   "
          f"tool calls {agg['tool_calls']:3d}   {agg['seconds']}s")


# ============================================================================
# THE ABLATION — does a vocabulary lookup tool help?
#
# Was ladder/rung0_ab.py. Folded in here so the rung and the experiment over it
# cannot drift apart: `run()` calls the same `rung0()` that `apply()` calls, and
# then the ONE measured rung 1, never a second copy of either.
#
#     python -m ladder.rungs.r0 --mode A       # recall only
#     python -m ladder.rungs.r0 --mode B       # search tool
#     python -m ladder.rungs.r0 --compare      # both, side by side
# ============================================================================

# ------------------------------------------------------------------ harness
def run(items, mode, llm, cfg=None):
    """Rung 0, then the measured rung 1 — no second validation implementation."""
    cfg = dict(cfg or {})
    recs: list[Record] = []
    agg = {"tokens_in": 0, "tokens_out": 0, "tool_calls": 0, "parse_failed": 0, "t0": time.time()}
    sources = {}
    for it in items:
        got, meta = rung0(it["doc_id"], it["text"], mode, llm, cfg)
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
    ap = argparse.ArgumentParser(description="rung 0 — the bare LLM, and the tool ablation over it")
    ap.add_argument("--mode", choices=["A", "B"])
    ap.add_argument("--compare", action="store_true")
    ap.add_argument("--manifest", default="manifest.json")
    ap.add_argument(
        "--model",
        help="provider/model from ladder/models.yaml. Defaults to "
        "manifest.model.extractor, then to a local ollama model — a hosted "
        "provider sends CADEC text off the machine and needs LADDER_ALLOW_REMOTE=1",
    )
    a = ap.parse_args(argv)

    from ladder.manifest import load_manifest
    from ladder.registry import Registry

    man = load_manifest(a.manifest)
    cfg = dict(man["rungs"].get("1", {}))
    cfg["registry"] = Registry(man["vocabulary"]["snomed_db"])
    cfg["ledger"] = Ledger(f"{man['output']['dir']}/r0_ab.ledger.jsonl", run_id="r0_ab")

    from ladder.llm import for_rung
    from ladder.stub_llm import load_items

    stub = for_rung(0, man, a.model)
    print(f"[rung0] model={stub.spec} ({stub.role})")

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

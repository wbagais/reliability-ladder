"""Rung 4 — LLM-as-judge. +1 call per record.

A SECOND model scores the record. Not the extractor.

THE MODEL FAMILY RULE IS ENFORCED, NOT ADVISED
----------------------------------------------
A model judging its own output measures self-consistency, not correctness. If
`manifest.model.judge` matches `manifest.model.extractor`, this rung raises
rather than running: a self-judge produces a plausible number that means
something other than what the column heading says, which is the failure mode
this whole project is about.

WHY IT RUNS AFTER VOTING
------------------------
Order is [0, 1, 2, 3, 4, 5, 6]. The judge sees what rung 2 corrected and what
rung 3 voted on, so it grades the best available answer rather than a draft.

Rung 1 runs in `observe` mode precisely so the judge is graded on the FULL
unfiltered set. If rung 1 filtered, rung 4's marginal contribution would not be
attributable to rung 4.

INPUT BOUNDARY — ENFORCED
-------------------------
May read `checks["r1_verdict"]` and `checks["r1_reason"]`. Nothing else.
`checks["meddra_term"]` is derived from the answer key — that table is the
answer key's own code inventory — and a judge shown it is being handed the
answer. Post text comes from `sources[doc_id]`, never from `docs`.

Enforced with the same `ALLOWED_CHECK_KEYS` mechanism as rung 2, because a leak
here produces BETTER numbers rather than an error, and silent improvement is the
hardest kind of bug to notice.

RECORDS, DOES NOT ROUTE
-----------------------
Whether a judgement moves the zone is a manifest choice, and the same argument
applies as for rung 1: a judge that routes confounds every rung above it.
Default is to record into `checks["r4_verdict"]` and let rung 5 act.

HOW YOU WILL KNOW IT WORKS
--------------------------
On the gold control every record is correct, so a judge that rejects any of them
is producing a false rejection — the same error-floor logic rung 1 was tuned
with, and it needs no scorer. Agreement with rung 1 is a sanity check, not a
result: the two should disagree somewhere, or the judge adds nothing.

A judge that only ever agrees is a null result and worth reporting as one.
"""

from __future__ import annotations

import json
import time
from collections import Counter
from typing import Any

from ladder.schema import Record

RUNG = 4
NAME = "llm-as-judge"

DEFAULTS = {
    "temperature": 0,
    "route": False,          # record only; rung 5 acts
    "show_vocabulary_term": False,
}

ALLOWED_CHECK_KEYS = frozenset({"r1_verdict", "r1_reason"})

PROMPT = """You are checking another system's work. It read a patient's post and claimed a specific adverse reaction was reported, with a SNOMED CT code.

The post:
{source}

Its claim:
  reaction: "{text}"  (characters {start}-{end})
  code:     {sct}

Is this claim correct? Judge two things separately:
  span  - is "{text}" really an adverse reaction the writer says they experienced?
  code  - is {sct} the right SNOMED CT concept for it?

Return JSON only:
{{"span_ok":true|false,"code_ok":true|false,"confidence":0.0,"why":"one short sentence"}}
"""


def _guard(rec: Record) -> dict:
    """The record's checks, reduced to what rung 4 may see."""
    return {k: v for k, v in rec.checks.items() if k in ALLOWED_CHECK_KEYS}


def judge(rec: Record, source: str, llm, cfg: dict) -> tuple[dict | None, dict]:
    _guard(rec)          # the boundary is applied before the prompt is built
    s, e = (rec.spans[0] if rec.spans else (-1, -1))
    prompt = PROMPT.format(source=source, text=rec.text, start=s, end=e, sct=rec.sct)
    raw, usage = llm(prompt, source, "judge")
    try:
        m = json.loads(raw)
    except json.JSONDecodeError:
        return None, {**usage, "parse_failed": True}
    return {
        "span_ok": bool(m.get("span_ok")),
        "code_ok": bool(m.get("code_ok")),
        "confidence": float(m.get("confidence", 0) or 0),
        "why": str(m.get("why", ""))[:200],
    }, usage



def _stamp(ledger, rung: int, sizes: dict[str, int]) -> None:
    """Write each denominator's SIZE onto the rows that carry its name.

    Sizes are not known until the loop ends, so rows are written with a name
    only. NOTE: this mutates Ledger.rows in memory; the JSONL line was already
    flushed, so denominator_n is present in `ledger.rows` and NOT in the file.
    Making it durable means buffering per rung, which changes Ledger's
    append-only contract — A's call.
    """
    if not ledger:
        return
    for row in getattr(ledger, "rows", []):
        if row.rung == rung:
            n = sizes.get((row.extra or {}).get("denominator"))
            if n is not None:
                row.extra["denominator_n"] = n

def apply(records: list[Record], sources: dict[str, str], cfg: dict[str, Any]) -> tuple[list[Record], dict]:
    cfg = {**DEFAULTS, **(cfg or {})}
    llm = cfg.get("judge_llm")
    if llm is None:
        raise RuntimeError(
            "rung 4 has no judge model. It must NOT fall back to the extractor: "
            "a model judging its own output measures self-consistency, not "
            "correctness. Pass judge_llm, and record the model in "
            "manifest.model.judge."
        )
    extractor = cfg.get("extractor_model")
    judge_model = cfg.get("judge_model")
    if extractor and judge_model and extractor == judge_model:
        raise RuntimeError(
            f"judge and extractor are both {judge_model!r}. A self-judge "
            "measures self-consistency. Use a different model family and record "
            "both in manifest.model."
        )

    ledger = cfg.get("ledger")
    agg = {"records": 0, "tokens_in": 0, "tokens_out": 0, "parse_failed": 0,
           "verdicts": Counter(), "agree_r1": 0, "disagree_r1": 0,
           # span and code counted APART. Pooling them into pass/fail hides the
           # thing worth knowing: measured 2026-08-23, the judge engages with
           # whether the reaction was really reported and says nothing about
           # whether the code is a real SNOMED concept. A judge with no
           # vocabulary knowledge cannot adjudicate codes, so it grades the half
           # it can grade — and a pooled verdict reports that as a judgement on
           # both.
           "span_ok": 0, "span_bad": 0, "code_ok": 0, "code_bad": 0,
           "r1_verdicts": Counter(), "judged": 0,
           "t0": time.time()}

    for rec in records:
        source = sources.get(rec.doc_id, "")
        agg["records"] += 1
        v, usage = judge(rec, source, llm, cfg)
        agg["tokens_in"] += usage.get("in", 0)
        agg["tokens_out"] += usage.get("out", 0)
        if v is None:
            agg["parse_failed"] += 1
            rec.checks["r4_verdict"] = None
            rec.checks["r4"] = {"outcome": "parse_failed"}
            # A parse failure still cost a call. A rung that logs only its
            # successes reports a cheaper judge than the one that ran.
            if ledger:
                ledger.log(record_id=rec.record_id, doc_id=rec.doc_id, rung=RUNG,
                           zone=rec.zone, reason="parse_failed",
                           outcome="parse_failed", api_calls=1,
                           tokens_in=usage.get("in", 0), tokens_out=usage.get("out", 0),
                           latency_ms=usage.get("seconds", 0.0) * 1000,
                           denominator="r4_offered", evaluable="could_not_run")
            continue

        verdict = "pass" if (v["span_ok"] and v["code_ok"]) else "fail"
        agg["verdicts"][verdict] += 1
        agg["judged"] += 1
        agg["span_ok" if v["span_ok"] else "span_bad"] += 1
        agg["code_ok" if v["code_ok"] else "code_bad"] += 1
        rec.checks["r4_verdict"] = verdict
        rec.checks["r4_confidence"] = v["confidence"]
        rec.checks["r4"] = v

        # Sanity check, not a result. Two checkers that never disagree are one
        # checker paid for twice.
        r1v = rec.checks.get("r1_verdict")
        if r1v is not None:
            agg["r1_verdicts"][r1v] += 1
            r1_pass = r1v in ("ACCEPT", "BAND")
            agg["agree_r1" if r1_pass == (verdict == "pass") else "disagree_r1"] += 1

        if cfg["route"] and verdict == "fail":
            rec.mark(RUNG, "REJECT", None)
        if ledger:
            ledger.log(record_id=rec.record_id, doc_id=rec.doc_id, rung=RUNG, zone=rec.zone,
                         reason=None, outcome="judged", api_calls=1,
                         tokens_in=usage.get("in", 0), tokens_out=usage.get("out", 0),
                         latency_ms=usage.get("seconds", 0.0) * 1000,
                         verdict=verdict,
                         span_ok=v["span_ok"], code_ok=v["code_ok"],
                         denominator="r4_judged", evaluable="pass")

    _stamp(ledger, RUNG, {"r4_judged": agg["judged"],
                          "r4_offered": agg["records"]})
    agg["seconds"] = round(time.time() - agg["t0"], 2)
    agg["verdicts"] = dict(agg["verdicts"])
    agg["r1_verdicts"] = dict(agg["r1_verdicts"])
    return records, agg


def report(agg: dict) -> None:
    n = agg["records"]
    j = agg["judged"]
    print(f"\n{'=' * 58}\nRUNG 4 — LLM-as-judge\n{'=' * 58}")
    print(f"  records offered {n}   judged {j}   "
          f"parse failures {agg['parse_failed']}")
    if not j:
        print("  nothing judged — the judge produced no usable output")
        return
    if agg["parse_failed"]:
        print(f"  NOTE: {agg['parse_failed']}/{n} records have no judgement. "
              "Every rate below is over the {j} that parsed.".format(j=j))

    print("\n  the two questions, counted apart:")
    print(f"     span really a reported reaction   ok {agg['span_ok']:4d}   "
          f"not {agg['span_bad']:4d}")
    print(f"     code right for it                 ok {agg['code_ok']:4d}   "
          f"not {agg['code_bad']:4d}")
    for k, v in sorted(agg["verdicts"].items()):
        print(f"     pooled {k:6s} {v:5d}  ({v / j * 100:.0f}%)")

    # Agreement is only informative when BOTH checkers vary. If rung 1 returned
    # one verdict for every record, "100% agreement" is arithmetic, not a
    # finding — and calling it a null result would be wrong in the opposite
    # direction.
    r1v = agg["r1_verdicts"]
    tot = agg["agree_r1"] + agg["disagree_r1"]
    print(f"\n  rung 1 verdicts on this set: {r1v}")
    if len(r1v) <= 1:
        print("  Rung 1 returned a single verdict for every record, so agreement")
        print("  with it is guaranteed and measures nothing. This comparison")
        print("  needs a set rung 1 splits — the gold control is the one to use.")
    elif tot:
        print(f"  agree {agg['agree_r1']} ({agg['agree_r1']/tot*100:.0f}%)  "
              f"disagree {agg['disagree_r1']}")
        if agg["disagree_r1"] == 0:
            print("  The judge never disagrees with rung 1, on a set where rung 1")
            print("  does vary. Two checkers that always agree are one checker")
            print("  paid for twice — a null result.")
    print(f"\n  tokens {agg['tokens_in'] + agg['tokens_out']:6d}   {agg['seconds']}s")

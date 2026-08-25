"""Rung 2 — self-correction. One model call per correctable failure.

Rung 2 fires ONLY on a rung 1 failure, and states the reason as a FACT:

    "The code 41456009 does not exist in SNOMED CT."

never as a question. A question invites the model to re-derive the answer it
already gave; a fact gives it something it did not have when it answered. This
is the whole mechanism, and it is why rung 2 cannot touch a record that passed
validation — there is no fact to feed back. A record in BAND is unverifiable,
not wrong, and asking a model to "check" it produces churn, not correction.

Runs before rungs 3 and 4 (order 0-1-2-3-4-5-6): correcting before voting means
the vote sees repaired records, and correcting before abstention means rung 5
does not discard something rung 2 would have rescued.

WHAT COUNTS AS A REPAIR, AND WHAT DOES NOT
------------------------------------------
A corrected record is re-validated by `ladder.rungs.r1` — the same measured
implementation, never a second one. Four outcomes, counted separately because
they mean different things:

    rescued        rung 1 rejected it, rung 2 changed it, rung 1 now accepts
                   or bands it. The only outcome that is a win.
    still_failing  changed, and still rejected. Cost paid, nothing bought.
    unchanged      the model returned the same code. Cost paid, nothing moved.
    declined       the model returned null. The record is left UNCHANGED;
                   rung 2 has no authority to withdraw an answer. Rung 5 owns
                   abstention and reads `checks["r2_declined"]`. Counting this
                   as a repair is how a ladder reports a coverage loss as a
                   reliability gain.

`declined` is broken out because it is the failure mode that flatters. Measured
2026-08-22 at rung 0: mode B's rung 1 rejection rate halved purely through 59
null codes, with code accuracy unchanged at zero. The same confound is available
here and must not be allowed to hide inside "rescued".

THE PREDICTION THIS RUNG TESTS
------------------------------
On the dev split, granite4:micro-h produced 0 correct codes out of 203 graded
mentions, and 164 of 176 codes in mode A did not exist at all. If the model has
no SNOMED knowledge, being told a code is wrong cannot produce a right one — it
can only produce a different wrong one. Rung 2's rescue rate should be at or
near zero, and if it is not, the interesting question is where the correct code
came from.

Self-correction can only recover what the model could have got right unaided.
That is a claim rung 2 either confirms or refutes, on measured numbers.
"""

from __future__ import annotations

import json
import time
from typing import Any

from ladder.rungs import r1
from ladder.schema import (
    R_CODE_INACTIVE,
    R_CODE_UNKNOWN,
    R_SPAN_OUT_OF_RANGE,
    R_SPAN_UNGROUNDED,
    R_WRONG_SEMANTIC_TYPE,
    Record,
    ZONE_ACCEPT,
    ZONE_BAND,
    ZONE_REJECT,
)

RUNG = 2
NAME = "self-correction"

DEFAULTS = {
    # Only failures that yield a STATABLE FACT. A reason the model cannot act
    # on produces a re-roll, not a correction.
    "correctable": (R_CODE_UNKNOWN, R_CODE_INACTIVE, R_WRONG_SEMANTIC_TYPE,
                    R_SPAN_UNGROUNDED, R_SPAN_OUT_OF_RANGE),
    "max_attempts": 1,      # one retry. More is a different experiment.
    "allow_withdrawal": True,   # model may return null; always counted apart
}

# The fact, per reason. Present tense, specific, no hedging, no question.
FACTS = {
    R_CODE_UNKNOWN: (
        'The code {sct} does not exist in SNOMED CT. It is not in any release.'
    ),
    R_CODE_INACTIVE: (
        'The code {sct} was retired from SNOMED CT and is no longer active.'
    ),
    R_WRONG_SEMANTIC_TYPE: (
        'The code {sct} exists, but it is not a clinical finding. An adverse '
        'reaction must be coded to a clinical finding.'
    ),
    R_SPAN_UNGROUNDED: (
        'The text "{text}" does not appear at characters {start}-{end} of the '
        'post.'
    ),
    R_SPAN_OUT_OF_RANGE: (
        'The offsets {start}-{end} fall outside the post, which is {n_source} '
        'characters long.'
    ),
}

PROMPT = """One of your answers was checked against SNOMED CT and the source post, and is wrong.

FACT: {fact}

The post:
{source}

Your answer was:
  span_text: {text}
  start,end: {start},{end}
  code:      {sct}

Correct it. If no SNOMED CT code is right for this reaction, set code to null —
do not substitute a code you are unsure of.

Return JSON only: {{"span_text":..,"start":..,"end":..,"code":..,"confidence":..}}
"""


# The spec's input boundary, enforced rather than observed. Rung 2 may read
# r1_verdict and r1_reason from checks and NOTHING else: checks["meddra_term"]
# is derived from the answer key, and a prompt containing it would leak gold
# into every number above this rung.
ALLOWED_CHECK_KEYS = frozenset({"r1_verdict", "r1_reason"})


class _CheckView:
    """checks, with everything rung 2 is not allowed to see removed."""

    def __init__(self, checks: dict):
        self._d = {k: v for k, v in checks.items() if k in ALLOWED_CHECK_KEYS}

    def get(self, k, default=None):
        if k not in ALLOWED_CHECK_KEYS:
            raise KeyError(
                f"rung 2 may not read checks[{k!r}] — see the input boundary in "
                "docs/wiki/content/r3.md. Answer-key-derived fields in a prompt "
                "invalidate every number above this rung."
            )
        return self._d.get(k, default)

    def __getitem__(self, k):
        return self.get(k)


def _verdict(rec: Record) -> tuple[str | None, str | None]:
    """Rung 1's judgement, whether or not rung 1 was gating. Mirrors rung 5."""
    v = rec.checks.get("r1_verdict")
    if v is None:
        v = rec.zone if rec.zone in (ZONE_ACCEPT, ZONE_BAND, ZONE_REJECT) else None
    return v, rec.checks.get("r1_reason")


def build_fact(rec: Record, reason: str, n_source: int = 0) -> str | None:
    tpl = FACTS.get(reason)
    if tpl is None:
        return None
    s, e = (rec.spans[0] if rec.spans else (-1, -1))
    return tpl.format(sct=rec.sct, text=rec.text, start=s, end=e,
                      n_source=n_source)


def correct(rec: Record, source: str, reason: str, llm, cfg: dict) -> tuple[Record | None, dict]:
    """One correction attempt. Returns (candidate, meta). Never mutates rec."""
    meta = {"tokens_in": 0, "tokens_out": 0, "parse_failed": False}
    fact = build_fact(rec, reason, len(source))
    if fact is None:
        return None, {**meta, "skipped": "no fact for this reason"}

    s, e = (rec.spans[0] if rec.spans else (-1, -1))
    prompt = PROMPT.format(fact=fact, source=source, text=rec.text,
                           start=s, end=e, sct=rec.sct)
    raw, usage = llm(prompt, source, "correct")
    meta["tokens_in"] = usage.get("in", 0)
    meta["tokens_out"] = usage.get("out", 0)
    # The caller already priced the call from models.yaml. Dropping it here
    # logged 0.0 for every paid run — invisible locally, where zero is right.
    meta["usd"] = usage.get("usd", 0.0)
    # Latency is one of the three cost measures and is never derived from a
    # total: it is recorded per call so p95 is a real percentile over calls.
    meta["latency_ms"] = usage.get("seconds", 0.0) * 1000

    try:
        m = json.loads(raw)
    except json.JSONDecodeError:
        # Never repaired here either. A parse failure at rung 2 is a real cost.
        return None, {**meta, "parse_failed": True}

    start, end = m.get("start", -1), m.get("end", -1)
    cand = rec.copy(
        text=m.get("span_text", rec.text),
        spans=[(start, end)] if isinstance(start, int) and isinstance(end, int) else [],
        sct=(str(m["code"]) if m.get("code") is not None else None),
        confidence=float(m.get("confidence", 0) or 0),
    )
    return cand, meta



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
    """Correct rung 1's rejections in place, and record what that bought."""
    cfg = {**DEFAULTS, **(cfg or {})}
    llm = cfg.get("llm")
    if llm is None:
        raise RuntimeError(
            "rung 2 has no model. Silently skipping would report zero "
            "corrections as 'self-correction does not help', which is a "
            "different claim from 'self-correction did not run'."
        )
    ledger = cfg.get("ledger")
    agg = {"attempted": 0, "rescued": 0, "still_failing": 0, "reasserted": 0, "unchanged": 0,
           "declined": 0, "parse_failed": 0, "tokens_in": 0, "tokens_out": 0,
           "t0": time.time()}

    for rec in records:
        verdict, reason = _verdict(rec)
        if verdict != ZONE_REJECT or reason not in cfg["correctable"]:
            # Spec: every record gets a row, so the ledger accounts for the
            # full set and "rung 2 did not fire" is distinguishable from
            # "rung 2 was never run".
            agg["unchanged"] += 1
            rec.checks["r2"] = {"outcome": "unchanged", "reason": reason,
                                "why": "not a correctable rung 1 rejection"}
            if ledger:
                ledger.log(record_id=rec.record_id, doc_id=rec.doc_id, rung=RUNG, zone=rec.zone,
                             reason=reason, outcome="unchanged",
                             denominator="r2_offered", evaluable="could_not_run")
            continue
        source = sources.get(rec.doc_id, "")
        agg["attempted"] += 1

        cand, meta = correct(rec, source, reason, llm, cfg)
        agg["tokens_in"] += meta["tokens_in"]
        agg["tokens_out"] += meta["tokens_out"]
        if meta.get("parse_failed"):
            agg["parse_failed"] += 1
            rec.checks["r2"] = {"outcome": "parse_failed", "reason": reason}
            if ledger:
                # Costs tokens, produces no judgement. Without a row the rung's
                # accounting drops it — same shape as rung 3's not_resampled.
                ledger.log(record_id=rec.record_id, doc_id=rec.doc_id, rung=RUNG,
                           zone=rec.zone, reason=reason, outcome="parse_failed",
                           tokens_in=meta["tokens_in"], tokens_out=meta["tokens_out"],
                           usd=meta.get("usd", 0.0),
                           api_calls=1,
                           denominator="r2_attempted", evaluable="could_not_run")
            continue
        if cand is None:
            rec.checks["r2"] = {"outcome": "skipped", "reason": reason,
                                "why": meta.get("skipped")}
            if ledger:
                ledger.log(record_id=rec.record_id, doc_id=rec.doc_id, rung=RUNG,
                           zone=rec.zone, reason=reason, outcome="skipped",
                           tokens_in=meta["tokens_in"], tokens_out=meta["tokens_out"],
                           usd=meta.get("usd", 0.0),
                           api_calls=1,
                           denominator="r2_attempted", evaluable="could_not_run")
            continue

        # The model declined to re-assert its answer. That is EVIDENCE, not an
        # action: rung 5 owns abstention, and a rung 2 that nulls codes itself
        # duplicates rung 5's mechanism at the wrong rung. The record is left
        # exactly as it was — still carrying its code, still rejected by rung 1
        # — and `declined` is written for rung 5 to act on when it runs.
        if cand.sct is None:
            agg["declined"] += 1
            rec.checks["r2"] = {
                "outcome": "declined",
                "reason": reason,
                "was": {"sct": rec.sct, "spans": rec.spans, "text": rec.text},
                "offered": None,
            }
            rec.checks["r2_declined"] = True
            if ledger:
                ledger.log(record_id=rec.record_id, doc_id=rec.doc_id, rung=RUNG,
                             zone=rec.zone, reason=reason, outcome="declined",
                             tokens_in=meta["tokens_in"], tokens_out=meta["tokens_out"],
                             usd=meta.get("usd", 0.0),
                             api_calls=1, latency_ms=meta["latency_ms"],
                             denominator="r2_attempted", evaluable="fail")
            continue

        if str(cand.sct) == str(rec.sct) and cand.spans == rec.spans:
            agg["reasserted"] += 1
            rec.checks["r2"] = {"outcome": "reasserted", "reason": reason}
            if ledger:
                ledger.log(record_id=rec.record_id, doc_id=rec.doc_id, rung=RUNG, zone=rec.zone,
                             reason=reason, outcome="reasserted",
                             tokens_in=meta["tokens_in"], tokens_out=meta["tokens_out"],
                             usd=meta.get("usd", 0.0),
                             api_calls=1, latency_ms=meta["latency_ms"],
                             denominator="r2_attempted", evaluable="fail")
            continue

        # Re-validate with the ONE measured rung 1, never a second copy.
        new_verdict, new_reason, new_checks = r1.zone(
            cand, source, cfg.get("registry"), cfg
        )
        rescued = new_verdict in (ZONE_ACCEPT, ZONE_BAND)
        agg["rescued" if rescued else "still_failing"] += 1
        rec.checks["r2"] = {
            "outcome": "rescued" if rescued else "still_failing",
            "reason": reason,
            "was": {"sct": rec.sct, "spans": rec.spans, "text": rec.text},
            "now": {"sct": cand.sct, "spans": cand.spans, "text": cand.text},
            "new_verdict": new_verdict,
            "new_reason": new_reason,
        }
        if rescued:
            # The correction is adopted; the original is preserved above, never
            # discarded. Constraint 5: withdrawal, never deletion.
            rec.text, rec.spans, rec.sct = cand.text, cand.spans, cand.sct
            rec.confidence = cand.confidence
            rec.checks.update({k: v for k, v in new_checks.items()})
            rec.checks["r1_verdict"] = new_verdict
            rec.checks["r1_reason"] = new_reason
            rec.mark(RUNG, new_verdict, new_reason)
        if ledger:
            ledger.log(record_id=rec.record_id, doc_id=rec.doc_id, rung=RUNG, zone=new_verdict,
                         reason=new_reason,
                         outcome=rec.checks["r2"]["outcome"],
                         tokens_in=meta["tokens_in"], tokens_out=meta["tokens_out"],
                         usd=meta.get("usd", 0.0),
                         api_calls=1, latency_ms=meta["latency_ms"],
                         denominator="r2_attempted",
                         evaluable="pass" if rescued else "fail")

    _stamp(ledger, RUNG, {"r2_offered": len(records),
                          "r2_attempted": agg["attempted"]})
    agg["seconds"] = round(time.time() - agg["t0"], 2)
    return records, agg


def report(agg: dict) -> None:
    n = agg["attempted"]
    print(f"\n{'=' * 58}\nRUNG 2 — self-correction\n{'=' * 58}")
    print(f"  rung 1 rejections offered   {n}")
    if not n:
        print("  nothing to correct — rung 2 did not run")
        return
    for k in ("rescued", "still_failing", "reasserted", "declined", "parse_failed"):
        print(f"     {k:16s} {agg[k]:5d}  ({agg[k] / n * 100:.0f}%)")
    print(f"  tokens {agg['tokens_in'] + agg['tokens_out']:6d}   {agg['seconds']}s")
    print("\n  'declined' means the model offered no replacement. The record is")
    print("  UNCHANGED and still rejected — rung 5 decides whether that becomes")
    print("  an abstention. Counting it as a repair would report a coverage")
    print("  loss as a reliability gain.")

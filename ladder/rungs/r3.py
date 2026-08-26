"""Rung 3 — voting. k calls per record. The most expensive rung.

Sample the extractor k times for the SAME record and take the majority code.

MAJORITY ON THE NORMALISED CODE, NEVER ON THE STRING
----------------------------------------------------
`cramping` and `Muscle cramp` are the same answer. A string vote splits them and
reports disagreement that does not exist. Normalisation goes through the same
registry function rung 1 uses, so the two agree by construction rather than by
two implementations happening to match.

TEMPERATURE 0.7, DELIBERATELY
-----------------------------
The one place this project departs from greedy decoding. Identical samples
cannot vote: at temperature 0 you pay k times for one answer repeated k times.
It lives in `manifest.rungs.5.temperature` rather than a default argument
because it is a deliberate exception, not a tuning knob.

Note what this costs elsewhere. Every other number in this project is
reproducible on fixed hardware because decoding is greedy; rung 3's are not.
A rung 3 result is a sample from a distribution and must be reported with the
seed and the run id, or repeated.

THE SPREAD IS THE ARTEFACT
--------------------------
A 3-0 and a 2-1 are different states that a single winner hides. If the model is
3-0 on almost everything, voting costs 3x and buys nothing — a publishable null
result, and exactly the finding the ladder exists to surface.

TIES
----
A tie is a real outcome, not an error. This implementation leaves the record
UNCHANGED on a tie and records `tie: true`. It does not invent a winner and it
does not withdraw the answer: withdrawal is rung 5's, and a rung that quietly
nulls contested records reports a coverage loss as a reliability gain — the same
confound measured at rung 0 mode B and at rung 2.

WHAT THIS RUNG ASKS
-------------------
k calls per record against one for rung 0. If the marginal errors prevented do
not justify k times the tokens, the honest finding is to stop at a lower rung.
"""

from __future__ import annotations

import json
import time
from collections import Counter
from typing import Any

from ladder.schema import Record

RUNG = 3
NAME = "voting"

DEFAULTS = {
    "k": 3,
    "temperature": 0.7,
    "tie": "unchanged",     # unchanged | first — never "null", see module docstring
}

# NO PROMPT HERE, DELIBERATELY — AND NO PATH EITHER.
#
# The spec says "sample the extractor k times". A rung 3 with its own prompt
# samples a DIFFERENT TASK and reports the result as if it were the extractor's
# variance. Measured 2026-08-23: a bespoke rung 3 prompt that mentioned
# declining produced 39 declines out of 39, against a rung 0 that fabricates a
# code every time. That measured the prompt, not the model.
#
# The same argument applies to the WHOLE pipeline, not just the prompt, and it
# was measured failing (2026-08-25): this rung sampled rung 0's legacy recall
# prompt while the run's codes came from the frozen S2 retrieve-and-pick path,
# and voting over that other distribution overwrote 9 of 32 rung-1-verified-
# ACCEPT codes with memory-recalled hallucinations. So rung 3 now builds rung
# 0's OWN configuration from the manifest (r0.prepare) and draws every sample
# through rung 0's own per-document body (r0.extract_document) — step,
# retriever, few-shot block and trimmer included. The only thing that varies
# across the k draws is the sampling temperature.

def normalise(code: str | None, registry) -> str:
    """One normalisation, shared with rung 1 — never a second implementation.

    A null answer normalises to "" and votes as itself: "no code is right" is a
    position, and three models declining is a 3-0 result, not an absence of one.
    """
    if code is None or str(code).strip() == "":
        return ""
    fn = getattr(registry, "normalise_term", None) or getattr(registry, "normalise", None)
    if fn is None:
        # Codes are already canonical identifiers, so identity is correct here.
        # Recorded rather than assumed: if the registry grows a normaliser and
        # this stays on identity, the two stop agreeing by construction.
        return str(code).strip()
    return str(fn(str(code).strip()))


def rung0_cfg(cfg: dict) -> dict:
    """Rung 0's configuration, rebuilt from the manifest for the sampler.

    Rung 3's own cfg is manifest.rungs.3 — it says nothing about how rung 0
    extracts. The distribution being verified is defined by manifest.rungs.0,
    so that is what the sampler runs. With no manifest in cfg this degrades to
    r0.DEFAULTS, i.e. the legacy recall path — the same fallback rung 0 itself
    has.
    """
    from ladder.rungs import r0

    man = cfg.get("manifest") or {}
    r0cfg = dict((man.get("rungs") or {}).get("0") or {})
    r0cfg.update(registry=cfg.get("registry"), manifest=man)
    return r0.prepare(r0cfg)


def sample_document(doc_id: str, text: str, llm, r0cfg: dict):
    """One extractor sample of a whole document, through rung 0's own
    CONFIGURED path — r0.extract_document, never a private reimplementation."""
    from ladder.rungs.r0 import extract_document
    return extract_document(doc_id, text, llm, r0cfg)


def _overlap(a, b) -> int:
    """Shared characters between two span lists. Overlap is the scorer's own
    convention for 'the same mention', and it is what tolerates the boundary
    shifts sampling produces ("extreme rectal bleed" vs "rectal bleed")."""
    return sum(
        max(0, min(e1, e2) - max(s1, s2)) for s1, e1 in a for s2, e2 in b
    )


def match_votes(recs: list, sample: list) -> dict[str, Any]:
    """Assign each sampled mention to at most one record: best overlap first,
    one-to-one, ties broken by list order so the assignment is deterministic.

    Returns {record_id: sampled Record}. Votes are collected per RECORD
    IDENTITY — the exact (doc_id, spans) key this replaces called every
    shifted boundary a different mention, which cost 206/240 records their
    votes on the 2026-08-25 run. One-to-one matters too: a single sampled
    mention spanning two records must not be counted as two agreeing votes.
    """
    scored = []
    for i, rec in enumerate(recs):
        for j, s in enumerate(sample):
            ov = _overlap(rec.spans, s.spans)
            if ov > 0:
                scored.append((-ov, i, j))
    scored.sort()
    out: dict[str, Any] = {}
    used_rec: set[int] = set()
    used_sample: set[int] = set()
    for _, i, j in scored:
        if i in used_rec or j in used_sample:
            continue
        used_rec.add(i)
        used_sample.add(j)
        out[recs[i].record_id] = sample[j]
    return out



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
    """Vote over k extractor samples. Records the spread; never withdraws.

    Withdrawal is rung 5's. A unanimous vote for "no code" is EVIDENCE that the
    extractor does not stand behind its answer, written to
    `checks["r3_unanimous_none"]` for rung 5 to act on. A rung 3 that nulls the
    record itself makes rung 1's rejection rate collapse without accuracy
    moving — the same confound measured at rung 0 mode B and rung 2.
    """
    cfg = {**DEFAULTS, **(cfg or {})}
    llm = cfg.get("llm")
    if llm is None:
        raise RuntimeError(
            "rung 3 has no model. Skipping silently would report 'voting did "
            "not help', which is a different claim from 'voting did not run'."
        )
    registry = cfg.get("registry")
    k = int(cfg["k"])
    if k < 2:
        raise ValueError(f"k={k} cannot vote. Set rungs.5.k to 2 or more.")
    if float(cfg["temperature"]) == 0.0:
        raise ValueError(
            "rung 3 at temperature 0 pays k times for one answer repeated k "
            "times. Set rungs.5.temperature above 0, or do not run this rung."
        )

    ledger = cfg.get("ledger")
    r0cfg = rung0_cfg(cfg)
    agg = {"records": 0, "calls": 0, "documents": 0,
           "tokens_in": 0, "tokens_out": 0,
           "unanimous": 0, "split": 0, "tie": 0, "changed": 0,
           "unanimous_none": 0, "not_resampled": 0, "parse_failed": 0,
           "spread": Counter(), "t0": time.time()}

    # k samples of each DOCUMENT, each through rung 0's configured path, then
    # each sample's mentions assigned to the run's records by span overlap.
    by_doc: dict[str, list[dict[str, Any]]] = {}
    for doc_id in {r.doc_id for r in records}:
        text = sources.get(doc_id, "")
        recs_here = [r for r in records if r.doc_id == doc_id]
        agg["documents"] += 1
        matches = []
        doc_in = doc_out = doc_calls = 0
        doc_usd = 0.0
        doc_t0 = time.time()
        for _ in range(k):
            got, meta = sample_document(doc_id, text, llm, r0cfg)
            # A sample through S2 is TWO calls (find, then pick). Billing one
            # per sample would report the repaired rung at half its price.
            calls = meta.get("api_calls", 1)
            agg["calls"] += calls
            doc_calls += calls
            doc_in += meta.get("tokens_in", 0)
            doc_out += meta.get("tokens_out", 0)
            # k times the price of one extraction, and paid whether or not a
            # record is re-found below. The caller computed it; dropping it
            # made rung 3 — the most expensive rung — the cheapest on paper.
            doc_usd += meta.get("usd", 0.0)
            agg["tokens_in"] += meta.get("tokens_in", 0)
            agg["tokens_out"] += meta.get("tokens_out", 0)
            agg["usd"] = agg.get("usd", 0.0) + meta.get("usd", 0.0)
            if meta.get("parse_failed"):
                agg["parse_failed"] += 1
            matches.append(match_votes(recs_here, got))
        by_doc[doc_id] = matches
        # The k samples are a DOCUMENT cost, not a record cost, and they are
        # paid whether or not any record is re-found below. Logging them here
        # is what stops a run where nothing matched from reporting rung 3 as
        # free.
        if ledger:
            ledger.log(
                rung=RUNG, doc_id=doc_id, record_id=doc_id, zone="NEW",
                outcome="sampled", api_calls=doc_calls,
                tokens_in=doc_in, tokens_out=doc_out, usd=doc_usd,
                latency_ms=(time.time() - doc_t0) * 1000, k=k,
                denominator="r3_documents", evaluable="pass",
            )

    for rec in records:
        agg["records"] += 1
        votes: Counter = Counter()
        raw: list[str | None] = []
        seen = 0
        for m in by_doc.get(rec.doc_id, []):
            match = m.get(rec.record_id)
            if match is None:
                continue          # this sample did not find this mention
            seen += 1
            raw.append(match.sct)
            votes[normalise(match.sct, registry)] += 1

        if seen == 0:
            # No sample re-found this mention. That is a real outcome — the
            # extractor is unstable on it — and not a vote.
            agg["not_resampled"] += 1
            rec.checks["r3"] = {"k": k, "seen": 0, "outcome": "not_resampled",
                                "was": rec.sct}
            # Still a row. "No sample re-found this mention" is a finding about
            # extractor stability, and a rung that stays silent on it looks like
            # a rung that did nothing.
            if ledger:
                ledger.log(record_id=rec.record_id, doc_id=rec.doc_id, rung=RUNG,
                           zone=rec.zone, reason="not_resampled",
                           outcome="not_resampled", k=k, seen=0,
                           denominator="r3_voted_on",
                           evaluable="could_not_run")
            continue

        ranked = votes.most_common()
        top_n = ranked[0][1]
        winners = [c for c, n in ranked if n == top_n]
        tie = len(winners) > 1
        agg["spread"]["-".join(str(n) for _, n in ranked)] += 1

        if tie:
            agg["tie"] += 1
        elif top_n == seen:
            agg["unanimous"] += 1
        else:
            agg["split"] += 1

        win = None if tie else (winners[0] or None)
        rec.checks["r3_votes"] = dict(votes)
        rec.checks["r3"] = {"k": k, "seen": seen, "tie": tie, "raw": raw,
                            "was": rec.sct, "winner": win}

        if win is None and not tie:
            # Unanimous "no code". Evidence for rung 5, not an action here.
            agg["unanimous_none"] += 1
            rec.checks["r3_unanimous_none"] = True
        elif win is not None and str(win) != str(rec.sct or ""):
            agg["changed"] += 1
            rec.checks["r3"]["changed"] = True
            rec.sct = win
            rec.mark(RUNG, rec.zone, None)

        if ledger:
            ledger.log(record_id=rec.record_id, doc_id=rec.doc_id, rung=RUNG, zone=rec.zone,
                         reason=None, outcome="tie" if tie else "voted",
                         denominator="r3_resampled", evaluable="pass")

    _stamp(ledger, RUNG, {"r3_resampled": agg["records"] - agg["not_resampled"],
                          "r3_voted_on": agg["records"],
                          "r3_documents": agg["documents"]})
    agg["seconds"] = round(time.time() - agg["t0"], 2)
    agg["spread"] = dict(agg["spread"])
    return records, agg


def report(agg: dict) -> None:
    n = agg["records"]
    print(f"\n{'=' * 58}\nRUNG 3 — voting (k={DEFAULTS['k']})\n{'=' * 58}")
    print(f"  records voted on   {n}   calls {agg['calls']}")
    if not n:
        print("  nothing to vote on"); return
    print(f"  documents sampled  {agg['documents']} x k = {agg['calls']} calls")
    for key in ("unanimous", "split", "tie", "changed", "unanimous_none",
                "not_resampled"):
        print(f"     {key:12s} {agg[key]:5d}  ({agg[key] / n * 100:.0f}%)")
    print(f"  vote spread: {agg['spread']}")
    print(f"  tokens {agg['tokens_in'] + agg['tokens_out']:6d}   "
          f"parse failures {agg['parse_failed']}   {agg['seconds']}s")
    print("\n  'unanimous_none' is EVIDENCE for rung 5, not a withdrawal here.")
    if agg["unanimous"] / n > 0.9:
        print("\n  >90% unanimous: voting is paying k times for one answer.")
        print("  That is a null result and worth reporting as one.")

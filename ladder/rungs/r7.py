"""Rung 7 — type compatibility. A second free check, for the corpus where the
first one cannot fire.

WHY THIS IS A RUNG AND NOT A CHECK INSIDE RUNG 1

Two reasons, and the second is the stronger one.

The safe reason: `r1.zone()` produces every published number in the article.
Adding a branch to it means the base arm is only byte-identical to what is
already reported if a test says so. A new rung file is the extension point
`run.py` already documents — "a rung registers itself by existing" — so the
base arm is unchanged BY CONSTRUCTION, and the diff is a manifest key.

The real reason: MEASUREMENT. Folded into rung 1, this check's contribution is
entangled with the lexical check's and no number can separate them. As its own
rung it gets its own ledger rows, its own denominator, and its own rejection
count, so "what did the type check add" is a question the ledger can answer. A
new check that cannot be separately counted is the thing this project keeps
finding.

THE BET THIS RUNG MAKES, stated so it can be falsified

  Type compatibility between a span and a code is a DECIDABLE INVALID STATE.

Rung 1's lexical check asks whether the span's words appear in the code's name.
On FiNER-139 that is a structural zero rather than a low score: spans are
numerals ("47.6") and tags are English phrases
("EffectiveIncomeTaxRateContinuingOperations"), so the token sets are disjoint
by construction and the intersection is empty for EVERY possible run, model and
prompt. ACCEPT 0 of 704, rung 1 rejected 1 record in 704, and rungs 2 and 5 went
quiet with it — four rungs silent because one check had no signal.

But both sides carry a second signal, and neither side's type is a word the
other happens to contain:

    the code's name      ...Percentage  ...Amount  ...Shares  ...Date  ...Term
    the span's context   "1.50 %"   "$ 19.4 million"   "1,350,000 shares"

A percentage tag on a span followed by "shares" is PROVABLY wrong, in exactly
the sense a retired SNOMED code is provably wrong: deterministically, at zero
model cost, without knowing the right answer.

MEASURED ON GOLD BEFORE THIS FILE WAS WRITTEN — scripts/finer_type_check.py,
FiNER test split, 187 gold mentions, no model calls:

    can speak about      87.7% of mentions   (the lexical check: 0%)
    false rejections     1.22%  (2 of 164)   (rung 1 on CADEC: 0.13%)
    menu after the check percent 21 · count 16 · duration 8 · date 1, of 139

The 1.22% was reached the way CADEC's 0.13% was — by measuring against gold
FIRST and fixing the rules rather than the data. The first draft rejected 8.54%
of a perfect answer set. The two disagreements that remain are genuine
annotation quirks (`PublicUtilitiesRequestedRateIncreaseDecrease` carries
`$ 1.1 million`) and cannot be tightened away without fitting to the answer key,
which would make the number meaningless.

WHAT IT DOES NOT DO

It never says an answer is RIGHT. Like every check on rung 1, it can only find a
proof of wrongness — a type that contradicts. A record whose types agree is
returned unchanged with its rung 1 verdict intact, because agreeing on type is
weak evidence and calling it ACCEPT would be the endorsement machine the geo arm
found (2026-09-02): a check that vouches confidently where it knows least.

It is also INERT unless the vocabulary implements `code_type`. SNOMED and
GeoNames do not, so this rung can be left in `rung_order` for every corpus and
will report "could not run" rather than branching on a corpus name — the
pattern that cost the FiNER port sixteen edits.
"""
from __future__ import annotations

import re
import time
from typing import Any

from ladder.schema import (
    R_TYPE_MISMATCH,
    ZONE_ACCEPT,
    ZONE_BAND,
    ZONE_REJECT,
)

RUNG = 7

DEFAULTS = {
    #: Off is not an option here — a rung in rung_order is meant to run. The
    #: arm is enabled by putting 7 in rung_order at all, which is the manifest
    #: key, and leaving it out is the base arm.
    "mode": "gate",
    #: Reject only where BOTH sides typed confidently. A span or a code this
    #: rung cannot type is left alone and counted as could-not-run, never
    #: guessed at: an unconfident check that abstains is usable, and one that
    #: guesses is a source of false rejections.
    "require_both": True,
}

#: A span's type, from the span itself and the characters either side.
#: ORDER IS LOAD-BEARING and each rule below was added because a measured
#: disagreement demanded it. See the module docstring for the 8.54% -> 1.22%
#: path; these five rules ARE that path.
_MONTHS = (r"january|february|march|april|may|june|july|august|september"
           r"|october|november|december")


def span_type(text: str, before: str, after: str) -> str | None:
    """Type a span, or return None rather than guess."""
    t = (text or "").strip()
    a = (after or "")[:24].lower()
    b = (before or "")[-28:].lower()

    if re.match(rf"^({_MONTHS})\b", t.lower()) or re.match(r"^(19|20)\d{2}$", t):
        return "date"
    if re.match(r"^\s*%", after or "") or a[:12].lstrip().startswith("percent"):
        return "percent"
    if re.search(r"\byears?\b|\bmonths?\b|\bdays?\b", a[:14]):
        return "duration"
    # A currency symbol immediately before the span outranks any quantity word
    # after it: "$ 6.1 billion in share repurchases" is money, and the word
    # "share" three tokens later does not make it a count. Measured: this rule
    # alone removed 3 of the 8 disagreements in the first draft.
    if re.search(r"\$\s*$", (before or "")[-4:]):
        return "money"
    # "per share" is a UNIT, not a quantity of shares. "$ 90.07 per share" is a
    # price. Checked before the count rule, which would otherwise claim it.
    if re.search(r"\bper\s+(share|unit)\b", a[:18]):
        return "money"
    if re.search(r"\bshares?\b|\bunits?\b|\bsecurities\b|\bemployees\b"
                 r"|\bsegments\b|\bstores\b|\bproperties\b", a[:22]):
        return "count"
    if re.search(r"\b(million|billion|thousand)\b", a[:16]):
        return "money"
    return None


def _context(rec, source: str) -> tuple[str, str]:
    if not rec.spans or not source:
        return "", ""
    i, j = rec.spans[0]
    return source[max(0, i - 40):i], source[j:j + 40]


def check(rec, source: str, vocab: Any, cfg: dict | None = None) -> tuple[str | None, dict]:
    """The verdict, as a pure function. Returns (reason or None, audit trail).

    Pure so it can be unit-tested against hand-made records and replayed over
    the gold standard to measure its own false-rejection rate — which is how the
    rules above were chosen, and the only reason any of them is trustworthy.
    """
    cfg = {**DEFAULTS, **(cfg or {})}
    checks: dict[str, Any] = {}

    coder = getattr(vocab, "code_type", None)
    if coder is None:
        # Inert by design. SNOMED and GeoNames do not implement code_type, so
        # this rung reports could-not-run rather than branching on a corpus.
        checks["r7_applicable"] = False
        return None, checks
    checks["r7_applicable"] = True

    if not rec.sct:
        checks["r7_span_type"] = None
        return None, checks

    before, after = _context(rec, source)
    st = span_type(rec.text, before, after)
    ct = coder(rec.sct)
    checks["r7_span_type"] = st
    checks["r7_code_type"] = ct

    if st is None or ct is None:
        # Could not run: one side untypeable. Counted, never collapsed into
        # pass — the third outcome is the one nothing else models.
        checks["r7_evaluable"] = False
        return None, checks

    checks["r7_evaluable"] = True
    if st != ct:
        return R_TYPE_MISMATCH, checks
    return None, checks


def apply(records: list, sources: dict[str, str], cfg: dict[str, Any]) -> list:
    ledger = cfg.get("ledger")
    vocab = cfg.get("registry")
    params = {k: v for k, v in cfg.items() if k in DEFAULTS}
    gating = params.get("mode", DEFAULTS["mode"]) == "gate"

    for rec in records:
        t0 = time.perf_counter()
        source = sources.get(rec.doc_id, "")
        reason, checks = check(rec, source, vocab, params)
        rec.checks.update(checks)

        if reason is not None:
            # Rung 2 reads r1_verdict and r1_reason and NOTHING else — that is
            # its enforced input boundary, not a convention. So a rejection
            # here is written into those two fields, which is how this rung
            # hands rung 2 a trigger without rung 2 being taught a new field.
            # Recorded plainly because it looks like a hack and is not: the
            # boundary exists to keep answer-key-derived fields out of a
            # prompt, and a type verdict is not one.
            rec.checks["r1_verdict"] = ZONE_REJECT
            rec.checks["r1_reason"] = reason
            if gating:
                rec.mark(RUNG, ZONE_REJECT, reason)

        if ledger:
            evaluable = checks.get("r7_evaluable")
            ledger.log(
                RUNG,
                rec.doc_id,
                rec.record_id,
                rec.zone,
                "rejected" if (gating and reason) else "judged",
                reason=reason,
                verdict=ZONE_REJECT if reason else None,
                latency_ms=(time.perf_counter() - t0) * 1000,
                denominator="r7_offered",
                evaluable=evaluable,
            )
    return records


def report(records: list) -> str:
    """What this rung did, over the set it could speak about.

    The denominator is stated because a rate over an unnamed set is the defect
    this project documents most often. Records this rung could not type are
    counted separately and never folded into a pass.
    """
    n = len(records)
    applicable = sum(1 for r in records if r.checks.get("r7_applicable"))
    evaluable = sum(1 for r in records if r.checks.get("r7_evaluable"))
    rejected = sum(1 for r in records if r.checks.get("r1_reason") == R_TYPE_MISMATCH)
    if not applicable:
        return (f"rung 7  not applicable — this vocabulary does not implement "
                f"code_type(), so the check is inert over all {n} records")
    lines = [
        f"rung 7  type compatibility, over {n} records",
        f"        typed on both sides   {evaluable:5}  ({evaluable/n:.1%})",
        f"        could not type        {applicable - evaluable:5}  "
        f"({(applicable - evaluable)/n:.1%})  — counted, not passed",
        f"        REJECTED              {rejected:5}  "
        f"({rejected/evaluable if evaluable else 0:.1%} of what it could judge)",
    ]
    return "\n".join(lines)

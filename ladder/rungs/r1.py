"""Rung 1 — the deterministic validation layer. Zero model calls.

Rung 1 JUDGES; whether it also ROUTES is a manifest setting.

    mode: "observe"  (default)  verdicts are recorded and reported; the record's
                                zone is untouched, so rungs 3-6 see the full
                                unfiltered set
    mode: "gate"                the verdict becomes the record's zone, and the
                                rest of the ladder only ever sees what survived

Observe is the default because a filtering rung 1 confounds every rung above it.
If rung 1 removes the records it dislikes, rung 4's judge is graded on a set
rung 1 pre-cleaned, and the marginal contribution of rung 4 is no longer
attributable to rung 4. Keeping rung 1 observational makes every rung a
single-rung ablation on identical input, and rung 1's verdicts stay in the
comparison as their own column. Rung 5, which runs last, is where a rung 1
verdict is finally allowed to cost coverage.

The judgement itself, either way: rung 1 cannot tell you a code is RIGHT — nothing deterministic can, because the
code is not in the source text. It can tell you a code is WRONG, and it does
that for free. Passing validation is not a claim of correctness, which is why
the pass state is split into ACCEPT (the vocabulary uses these very words) and
BAND (plausible, unverifiable by string comparison).

Five checks, in cost order — the free ones fire before any lookup:

    1  schema valid       nothing              malformed output
    2  span grounding     a string compare     fabrication
    3  negation           a cue list           "so far no gastric problems"
    4  code exists        vocabulary lookup    hallucinated codes
    5  semantic type      vocabulary hierarchy a procedure where a finding goes
    6  MedDRA existence   a MedDRA table       a code outside the table
       (then)  lexical match                   ACCEPT vs BAND

Four choices this file makes that the plan left open, each of which moves the
rung 1 rejection rate, and each of which is therefore a manifest setting rather
than a hard-coded opinion. All four were settled by replaying rung 1 over
CADEC's own gold, where every rejection is by construction a FALSE rejection
(`python -m ladder.calibrate --sweep`):

  negation_action (default "flag", NOT "reject")
      The plan gives negation a boxed section and its own rejection reason. On
      the corpus it rejects 427 gold-correct mentions (4.7%), from two
      independent causes. First, CADEC annotates a mention regardless of
      polarity: the plan's own worked example, "so far no gastric problems", is
      annotated in ARTHROTEC.1 as an ADR coded 162076009. Second, NegEx scope
      rules misfire on forum prose — "I can't describe the horrible stomach
      pain", "I can finally clean my house without pain", "doctors deny that
      there is a connection between joint pain ... and Lipitor" all negate
      something other than the mention. So the cue still fires and is still
      logged, because polarity errors are a real safety class, but it flags
      rather than rejects. Set "reject" to reproduce the plan as written.

  reject_inactive (default false)
      115 of the 1,046 SCT codes CADEC uses have been retired from SNOMED since
      2015. Rejecting retired codes would reject 11% of the gold standard's own
      answers and report it as a model error. Inactivity is recorded as an audit
      fact instead.

  finding_scope (default "reaction")
      A drug mention normalises to a product concept, which is not a clinical
      finding. Applying the semantic-type gate to drug records rejects every
      correct drug code.

  semantic type: reject only on a positive "not_finding"
      A retired SNOMED concept has no active is-a rows, so a hierarchy walk
      cannot place it — which is not the same as placing it in the wrong branch.
      Treating "cannot place" as "wrong slot" rejected another 413 gold
      mentions: |Knee pain|, |Bloating symptom|, |Tiredness symptom|, all
      retired, all clinically right. `Registry.finding_status()` returns
      finding / not_finding / unknown and only the middle one rejects.

  meddra_check (default "flag", NOT "reject")
      The only MedDRA table available here is the code list CADEC ships with the
      corpus: 666 codes, every one of which appears in the gold annotations and
      none of which do not (`MeddraTable.leakage()`). As an existence check it
      asks "is this one of the codes the annotators happened to use?", which
      rejects hallucinated codes trivially and rejects real MedDRA codes the
      annotators did not reach for. Both inflate rung 1. So the verdict is
      recorded and counted, and is not a rejection reason. Point `meddra_csv` at
      a subscription release and "reject" becomes honest.

  lexical_mode (default "exact", after measuring the alternative)
      "contained" (span tokens a subset of a vocabulary term's, or vice versa)
      looks obviously right for colloquial text: it accepts "bit drowsy" for
      |Drowsy|, and it lifts the ACCEPT lane from 43.1% to 54.5% of gold. It is
      also how a validation gate starts vouching for wrong answers. Planting a
      near-miss code — a real, active finding sharing its head word with the
      right one, which is the confusion a normalisation model actually makes —
      `contained` puts 19.0% of them in ACCEPT; `exact` puts 0.1% there
      (`python -m ladder.probe --lexical-mode ...`). Eleven points of free
      settlement is not worth a gate that endorses one near-miss in five.
"""

from __future__ import annotations

import time
from typing import Any

from ladder.negation import is_negated
from ladder.schema import (
    CONCEPT_LESS,
    REJECT_REASONS,
    VERDICTS,
    R_CODE_INACTIVE,
    R_CODE_UNKNOWN,
    R_LABEL_MISMATCH,
    R_MEDDRA_UNKNOWN,
    R_NEGATED,
    R_WRONG_SEMANTIC_TYPE,
    REACTION,
    Record,
    ZONE_ACCEPT,
    ZONE_BAND,
    ZONE_REJECT,
)

RUNG = 1
NAME = "deterministic"

DEFAULTS = {
    "mode": "observe",  # "observe" | "gate"
    "reject_inactive": False,
    "meddra_check": "flag",  # "off" | "flag" | "reject"
    "check_negation": True,
    "negation_action": "flag",  # "flag" | "reject"
    "negation_window": 6,
    "finding_check": True,
    "finding_scope": "reaction",  # "reaction" | "all"
    "lexical_mode": "exact",
    # Rung 0's sct_label vs the vocabulary's own words for that code. "flag"
    # like meddra_check and the negation cue, and for the same reason: its
    # false-rejection floor has not been measured, and "rectal bleeding"
    # against |Rectal hemorrhage| is one concept in two wordings.
    "label_check": "flag",  # "off" | "flag" | "reject"
}


def zone(
    rec: Record,
    source: str,
    vocab: Any,
    cfg: dict[str, Any] | None = None,
    meddra: Any = None,
) -> tuple[str, str | None, dict]:
    """The verdict, as one pure function. Returns (verdict, reason, audit trail).

    Returns what rung 1 CONCLUDES — ACCEPT, BAND or REJECT — and never touches
    the record. Whether that verdict becomes the record's zone is `apply`'s
    business, and the manifest's.

    Pure so it can be unit-tested against hand-made records and replayed over
    the gold standard to measure its own false-rejection rate — which is how the
    settings above were chosen.
    """
    cfg = {**DEFAULTS, **(cfg or {})}
    checks: dict[str, Any] = {}

    # 1 + 2 — schema and span grounding. Free, and first.
    ok, reason = rec.valid(source)
    checks["span_grounded"] = ok
    if not ok:
        return ZONE_REJECT, reason, checks

    # 3 — negation. A cue list and a window; still no lookup.
    if cfg["check_negation"]:
        negated, cue = is_negated(source, rec.spans, window=cfg["negation_window"])
        checks["negated"] = negated
        checks["negation_cue"] = cue
        if negated and cfg["negation_action"] == "reject":
            return ZONE_REJECT, R_NEGATED, checks

    # A record that answers CONCEPT_LESS is claiming no code is correct. There
    # is nothing to look up, and rung 1 has no way to contradict it — that is
    # rung 5's and the scorer's business.
    if rec.sct == CONCEPT_LESS:
        checks["concept_less"] = True
        return ZONE_BAND, None, checks

    if not rec.sct:
        checks["no_code"] = True
        return ZONE_BAND, None, checks

    if vocab is None:
        checks["vocab"] = "unavailable"
        if not cfg.get("allow_no_vocab"):
            raise RuntimeError(
                "rung 1 has no vocabulary backend. Returning BAND here would make "
                "'plausible but unverifiable' and 'never checked' the same value, "
                "and nothing above rung 1 could tell them apart. Pass a registry "
                "in cfg, or set allow_no_vocab=True to measure without one."
            )
        return ZONE_BAND, None, checks

    # 4 — does the code exist at all?
    checks["sct_exists"] = vocab.exists(rec.sct)
    if not checks["sct_exists"]:
        return ZONE_REJECT, R_CODE_UNKNOWN, checks

    checks["sct_active"] = vocab.is_active(rec.sct)
    if not checks["sct_active"] and cfg["reject_inactive"]:
        return ZONE_REJECT, R_CODE_INACTIVE, checks

    # 5 — is it in the right slot? Reactions only: a drug normalises to a
    # product concept, which is correctly not a clinical finding.
    status = vocab.finding_status(rec.sct)
    checks["sct_finding_status"] = status
    checks["sct_is_finding"] = status == "finding"
    scope_hit = cfg["finding_scope"] == "all" or rec.entity_type == REACTION
    if cfg["finding_check"] and scope_hit and status == "not_finding":
        return ZONE_REJECT, R_WRONG_SEMANTIC_TYPE, checks

    # 6 — MedDRA, when a table is configured. Recorded either way; a rejection
    # only when the manifest says so, because the available table is derived
    # from the answer key.
    if meddra is not None and cfg["meddra_check"] != "off" and rec.meddra:
        checks["meddra_exists"] = meddra.exists(rec.meddra)
        checks["meddra_term"] = meddra.term(rec.meddra)
        if not checks["meddra_exists"] and cfg["meddra_check"] == "reject":
            return ZONE_REJECT, R_MEDDRA_UNKNOWN, checks
        checks["meddra_lexical_match"] = meddra.lexical_match(
            rec.text, rec.meddra, mode=cfg["lexical_mode"]
        )

    # 7 — the model's OWN label against the code it chose. This catches what
    # exists() cannot: 82249009 is a real, active concept, so every earlier
    # check passes it, and it means |California chicken (organism)|. The model
    # naming the concept turns an unverifiable id into a checkable claim.
    if cfg["label_check"] != "off" and rec.sct_label and rec.sct_label != CONCEPT_LESS:
        checks["label_verified"] = vocab.lexical_match(
            rec.sct_label, rec.sct, mode="contained"
        )
        if not checks["label_verified"] and cfg["label_check"] == "reject":
            return ZONE_REJECT, R_LABEL_MISMATCH, checks

    # Pass. ACCEPT only where the vocabulary uses these very words.
    checks["lexical_match"] = vocab.lexical_match(rec.text, rec.sct, mode=cfg["lexical_mode"])
    if checks["lexical_match"]:
        return ZONE_ACCEPT, None, checks
    checks["reason_band"] = "colloquial_no_lexical_match"
    return ZONE_BAND, None, checks



# ---------------------------------------------------------------- audit pass
def all_reasons(rec, source, vocab, cfg=None, meddra=None) -> dict:
    """Every check, run unconditionally. Does NOT decide the verdict.

    `zone()` short-circuits on the first failure, which is correct for a verdict
    and wrong for a reason table: on model output the cheapest check fires first
    and hides everything above it. Measured 2026-08-22 on 2 dev docs, mode A —
    6/6 records rejected as span_ungrounded, and all 3 distinct codes emitted
    were absent from SNOMED. Not one appeared in the reason table.

    So the table rung 1 reports is a distribution over FIRST failures, weighted
    by check order. On gold the bias is latent (gold spans ground by
    construction); on model output it dominates. A validator tuned on gold can
    carry an ordering bias that only appears once something actually fails.

    Returns reasons (every rejection that applies), unevaluable (checks that
    could not run, and why), and the full check dict. The verdict still comes
    from zone(); this only makes the audit trail complete.
    """
    cfg = {**DEFAULTS, **(cfg or {})}
    reasons: list[str] = []
    unevaluable: dict[str, str] = {}
    checks: dict[str, Any] = {}

    # --- span grounding ----------------------------------------------------
    ok, reason = rec.valid(source)
    checks["span_grounded"] = ok
    if not ok:
        reasons.append(reason)

    # --- negation: needs a grounded span to read a window around -----------
    if cfg["check_negation"]:
        if not ok:
            unevaluable["negation"] = "span not grounded"
        else:
            negated, cue = is_negated(source, rec.spans, window=cfg["negation_window"])
            checks["negated"] = negated
            checks["negation_cue"] = cue
            if negated and cfg["negation_action"] == "reject":
                reasons.append(R_NEGATED)

    # --- code checks: independent of the span. This is the masked branch. ---
    if rec.sct == CONCEPT_LESS:
        checks["concept_less"] = True
    elif not rec.sct:
        checks["no_code"] = True
    elif vocab is None:
        unevaluable["code"] = "vocab unavailable"
    else:
        checks["sct_exists"] = vocab.exists(rec.sct)
        if not checks["sct_exists"]:
            reasons.append(R_CODE_UNKNOWN)
        else:
            checks["sct_active"] = vocab.is_active(rec.sct)
            if not checks["sct_active"] and cfg["reject_inactive"]:
                reasons.append(R_CODE_INACTIVE)

            status = vocab.finding_status(rec.sct)
            checks["sct_finding_status"] = status
            checks["sct_is_finding"] = status == "finding"
            scope_hit = cfg["finding_scope"] == "all" or rec.entity_type == REACTION
            if cfg["finding_check"] and scope_hit and status == "not_finding":
                reasons.append(R_WRONG_SEMANTIC_TYPE)

            checks["lexical_match"] = vocab.lexical_match(
                rec.text, rec.sct, mode=cfg["lexical_mode"]
            )

            # The model's own label against its own code. Run here too, or the
            # reason table hides it behind whichever check fired first.
            if cfg["label_check"] != "off" and rec.sct_label and rec.sct_label != CONCEPT_LESS:
                checks["label_verified"] = vocab.lexical_match(
                    rec.sct_label, rec.sct, mode="contained"
                )
                if not checks["label_verified"] and cfg["label_check"] == "reject":
                    reasons.append(R_LABEL_MISMATCH)

    # --- MedDRA ------------------------------------------------------------
    if meddra is not None and cfg["meddra_check"] != "off" and rec.meddra:
        checks["meddra_exists"] = meddra.exists(rec.meddra)
        checks["meddra_term"] = meddra.term(rec.meddra)
        if not checks["meddra_exists"] and cfg["meddra_check"] == "reject":
            reasons.append(R_MEDDRA_UNKNOWN)

    for r in reasons:
        assert r in REJECT_REASONS, f"undeclared reason {r!r}"

    return {"reasons": reasons, "unevaluable": unevaluable, "checks": checks,
            "n_reasons": len(reasons)}


def apply(records: list[Record], sources: dict[str, str], cfg: dict[str, Any]) -> list[Record]:
    ledger = cfg.get("ledger")
    vocab = cfg.get("registry")
    meddra = cfg.get("meddra")
    params = {k: v for k, v in cfg.items() if k in DEFAULTS}
    gating = params.get("mode", DEFAULTS["mode"]) == "gate"
    for rec in records:
        t0 = time.perf_counter()
        source = sources.get(rec.doc_id, "")
        verdict, reason, checks = zone(rec, source, vocab, params, meddra)
        # The enumerations in schema.py are the contract every rung reads. Assert
        # against them here so adding a reason without declaring it fails loudly
        # in the fixture gate rather than quietly in a results table.
        assert verdict in VERDICTS, f"rung 1 emitted an undeclared verdict {verdict!r}"
        assert reason is None or reason in REJECT_REASONS, (
            f"rung 1 emitted an undeclared reason {reason!r} — add it to "
            "schema.REJECT_REASONS (append, never reorder)"
        )
        rec.checks.update(checks)
        # The verdict always lands on the record — rung 5 reads it, rung 2 needs
        # it to have a fact to feed back, and the report counts it. Only the
        # ZONE is conditional.
        rec.checks["r1_verdict"] = verdict
        rec.checks["r1_reason"] = reason
        rec.checks["r1_audit"] = all_reasons(rec, source, vocab, cfg, meddra)
        if gating:
            rec.mark(RUNG, verdict, reason)
        if ledger:
            ledger.log(
                RUNG,
                rec.doc_id,
                rec.record_id,
                rec.zone,
                "rejected" if (gating and verdict == ZONE_REJECT) else "judged",
                reason=reason,
                verdict=verdict,
                latency_ms=(time.perf_counter() - t0) * 1000,
                denominator="r1_offered",
                # A verdict is not a test that can fail to run: every record
                # gets one. ACCEPT/BAND = the record survives; REJECT = it does
                # not. A check that could not be evaluated is already recorded
                # in r1_audit.unevaluable, and is reported as such.
                evaluable=(
                    "could_not_run"
                    if (rec.checks.get("r1_audit") or {}).get("unevaluable")
                    else "pass" if verdict in (ZONE_ACCEPT, ZONE_BAND) else "fail"
                ),
                mode=params.get("mode", DEFAULTS["mode"]),
                lexical_match=bool(checks.get("lexical_match")),
                sct_active=checks.get("sct_active"),
                negated=checks.get("negated"),
                meddra_exists=checks.get("meddra_exists"),
            )
    return records

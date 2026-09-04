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

THE JUDGE WAS NEVER SHOWN WHAT IT WAS JUDGING (plan item 14, found 2026-09-02,
built 2026-09-03)
-----------------------------------------------------------------------------
Until now `judge()` formatted `source, text, start, end, sct` and nothing
else: the judge was handed `code: 1003722009` — a bare nine-digit number with
no name — and asked "is this the right SNOMED CT concept?". It cannot answer
that, so the pass/fail split it returned measured a question that could not
be answered. On FiNER `rec.sct` IS the tag name, which is the whole reason the
judge engaged there: identifier readability, not context size.

`rungs.4.menu` is `off | ranked | shuffled`. With a menu the judge is shown
what the extractor was shown (`checks["candidates"]`, rendered exactly as
rung 0 rendered it) and what it answered (the pick, as a line), and asked a
third question — `best`: the line it would choose, or null for "the right
answer is not on this list". That last verdict is one the system could not
express: a code failure was ambiguous between a bad pick and a bad menu,
which need opposite fixes.

OFF BY DEFAULT: every published rung 4 figure was produced blind, and the arm
is paired against it (manifest.judgemenu.json / manifest.judgeshuffle.json,
one-key diffs, test-pinned). `shuffled` permutes the menu per record under a
fixed seed, because the slot-0 attractor has been found three times and a
judge shown a ranked list may ratify line 0. Safe here where it was unsafe in
rung 0 (B4, 2026-09-01): the judge sees ONE record per call, so a per-record
permutation cannot alias indices across a batch. A record with no menu (S0,
S1) gets the blind prompt and says so in `checks["r4_menu"] = "none"` — the
arm couples rung 4 to S2, and that is stated rather than hidden.
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
    # NO TEMPERATURE HERE. It used to say `"temperature": 0` and rung 4 called
    # `llm(prompt, "", "judge")` without it — declared, never read, the same
    # defect as manifest.model.temperature one layer down (2026-08-31). It is
    # removed rather than wired: a rung DEFAULT would override the manifest's
    # declaration and put a code default back on top of it. The judge inherits
    # the temperature its Caller was bound at, which is the manifest's.
    "route": False,          # record only; rung 5 acts
    # `show_vocabulary_term: False` stood here from 39a94f0 and was never read.
    # Removed 2026-08-31 with r2's two. What the judge is shown is decided by
    # PROMPT_SLOTS and judge_prompt(), where it is visible.
    # off | ranked | shuffled — see the module docstring. OFF: every published
    # rung 4 number is a blind-judge measurement and the arm is paired on it.
    "menu": "off",
}

MENU_MODES = ("off", "ranked", "shuffled")

# `candidates` and `r0_negated` are rung 0's OWN output — the menu it
# retrieved and the polarity it claimed — not the answer key. `meddra_term`
# stays out for the reason the docstring gives.
ALLOWED_CHECK_KEYS = frozenset({"r1_verdict", "r1_reason", "candidates", "r0_negated"})

# THE SEVENTH PROMPT CONSTANT. The FiNER port (2026-08-29) rendered six rung 0
# prompt constants from `manifest.corpus.prompts` and missed this one, so a
# judge grading an SEC filing was asked whether the text described "a personal
# adverse reaction ... the writer says they experienced", with a "SNOMED CT
# code". The judge is the one rung whose entire job is to read the text, so a
# prompt about the wrong domain does not degrade its verdicts, it invalidates
# them. Same slot mechanism as r0.PROMPT_SLOTS; missing slots fall back to
# CADEC's, so the CADEC arm renders byte-identically to the old constant.
PROMPT_SLOTS = {
    "entity": "adverse reaction",
    "entity_short": "reaction",
    "author": "the writer",
    "source": "the post",
    "source_owner": "a patient's post",
    "claim_object": "code",
    "vocabulary": "SNOMED CT",
    "vocabulary_concept": "SNOMED CT concept",
    "claim_verb": "was reported",
    "span_question": "really an {entity} {author} says they experienced",
    # Rendered only when the record is marked [denied]. Phase B found the pick
    # step declined every denied mention until told a denial is still coded;
    # the judge had no such instruction and was failing spans CADEC marks
    # correct. FiNER never sets r0_negated, so this never renders there.
    "denied_note": (
        "A {entity_short} marked [denied] is one {author} says they did NOT "
        "have. It is still coded: the code names the {entity_short} being "
        "denied, exactly as if it were experienced, and the denial is never a "
        "reason to fail the span or the code."
    ),
}

PROMPT_TEMPLATE = """You are checking another system's work. It read {source_owner} and claimed a specific {entity} {claim_verb}, with a {vocabulary} {claim_object}.

The {source_noun}:
{{source}}

Its claim:
  {entity_short}: "{{text}}"  (characters {{start}}-{{end}})
  code:     {{sct}}

Is this claim correct? Judge two things separately:
  span  - is "{{text}}" {span_question}?
  code  - is {{sct}} the right {vocabulary_concept} for it?

Return JSON only:
{{{{"span_ok":true|false,"code_ok":true|false,"confidence":0.0,"why":"one short sentence"}}}}
"""

#: The menu variant. Same header, same two questions, plus the list the
#: extractor chose from, the line it chose, and a third question. Kept as a
#: SEPARATE template so `menu: off` renders the blind prompt byte-identically
#: — the arm must be paired against exactly what was published.
PROMPT_TEMPLATE_MENU = """You are checking another system's work. It read {source_owner} and claimed a specific {entity} {claim_verb}, with a {vocabulary} {claim_object}.

The {source_noun}:
{{source}}

Its claim:
  {entity_short}: "{{text}}"{{denied}}  (characters {{start}}-{{end}})
  code:     {{sct}}

The system chose that code from this list, which is exactly what it was shown,
after being told:
{{guidance}}
{{menu}}
It chose {{pick}}.
{{denied_note}}
Is this claim correct? Judge three things separately:
  span  - is "{{text}}" {span_question}?
  code  - is {{sct}} the right {vocabulary_concept} for it?
  best  - the number in [brackets] of the line YOU would choose for "{{text}}",
          or null if no line on the list is right for it.

Return JSON only:
{{{{"span_ok":true|false,"code_ok":true|false,"best":<number or null>,"confidence":0.0,"why":"one short sentence"}}}}
"""


def _slots(slots: dict | None) -> dict:
    """The resolved slot table one corpus renders with."""
    given = dict(slots or {})
    s = {**PROMPT_SLOTS, **given}
    if "vocabulary" in given and "vocabulary_concept" not in given:
        s["vocabulary_concept"] = given["vocabulary"]
    if "source" in given and "source_owner" not in given:
        s["source_owner"] = given["source"]
    if "vocabulary" in given and "claim_object" not in given:
        s["claim_object"] = given.get("id_name", "identifier")
    s["span_question"] = s["span_question"].format(**{
        k: v for k, v in s.items() if k != "span_question"})
    s.setdefault("source_noun", s["source"])
    src = s["source"]
    s["source_noun"] = src[4:] if src.startswith("the ") else src
    return s


def judge_prompt_menu(slots: dict | None = None) -> str:
    """The menu-showing judge prompt for one corpus, slots resolved the same
    way as `judge_prompt`; still carrying the record placeholders."""
    return PROMPT_TEMPLATE_MENU.format(**_slots(slots))


def menu_order(rec: Record, mode: str, seed: int = 0) -> list[int]:
    """The display order of `rec.checks["candidates"]`, as indices into it.

    `ranked` is rung 0's order. `shuffled` is a pure function of
    (seed, record_id) through blake2b — NOT `hash()`, which is salted per
    process and would make two runs of one configuration incomparable.
    """
    cands = rec.checks.get("candidates") or []
    order = list(range(len(cands)))
    if mode != "shuffled" or len(order) < 2:
        return order
    import hashlib
    import random

    digest = hashlib.blake2b(f"{seed}:{rec.record_id}".encode("utf-8"),
                             digest_size=8).digest()
    random.Random(int.from_bytes(digest, "big")).shuffle(order)
    return order


def _render_menu(cands: list[dict], order: list[int]) -> tuple[str, dict[str, int]]:
    """The numbered menu in display order, and code -> displayed number."""
    lines = []
    shown: dict[str, int] = {}
    for n, i in enumerate(order):
        c = cands[i]
        lines.append(f'     [{n}] {c.get("fsn") or c.get("label")}')
        if c.get("code") is not None:
            shown.setdefault(str(c["code"]), n)
    return "\n".join(lines), shown


def judge_prompt(slots: dict | None = None) -> str:
    """The judge prompt for one corpus. Missing slots fall back to CADEC's.

    Returns a template still carrying {source}/{text}/{start}/{end}/{sct} for
    `judge()` to fill — the slots name the DOMAIN, the placeholders carry the
    RECORD, and the two substitutions must not be collapsed into one.
    """
    given = dict(slots or {})
    s = {**PROMPT_SLOTS, **given}
    # DERIVED, not defaulted. A corpus that sets `vocabulary` and not
    # `vocabulary_concept` would otherwise keep CADEC's "SNOMED CT concept"
    # and half-port the prompt — the same silent-partial-port defect this
    # whole function exists to fix, one slot down.
    if "vocabulary" in given and "vocabulary_concept" not in given:
        s["vocabulary_concept"] = given["vocabulary"]
    # Same argument for every slot that mentions the corpus in passing. A
    # corpus should have to declare its DOMAIN words, not remember every
    # sentence CADEC happened to phrase around them.
    if "source" in given and "source_owner" not in given:
        s["source_owner"] = given["source"]
    if "vocabulary" in given and "claim_object" not in given:
        # "a US-GAAP XBRL tag code" reads wrong; the vocabulary already says
        # what the identifier is called.
        s["claim_object"] = given.get("id_name", "identifier")
    # the span question is itself a slotted phrase, so it renders first
    s["span_question"] = s["span_question"].format(**{
        k: v for k, v in s.items() if k != "span_question"})
    # "the post" -> "post"; the template says "The {source_noun}:"
    s.setdefault("source_noun", s["source"])
    src = s["source"]
    s["source_noun"] = src[4:] if src.startswith("the ") else src
    return PROMPT_TEMPLATE.format(**s)


PROMPT = judge_prompt(None)


def _guard(rec: Record) -> dict:
    """The record's checks, reduced to what rung 4 may see."""
    return {k: v for k, v in rec.checks.items() if k in ALLOWED_CHECK_KEYS}


def judge(rec: Record, source: str, llm, cfg: dict) -> tuple[dict | None, dict]:
    allowed = _guard(rec)   # the boundary is applied before the prompt is built
    mode = cfg.get("menu", DEFAULTS["menu"])
    if mode not in MENU_MODES:
        raise ValueError(
            f"rungs.4.menu={mode!r} is not one of {MENU_MODES}. A judge shown a "
            "menu nobody defined would grade under a label the article cannot "
            "explain."
        )
    s, e = (rec.spans[0] if rec.spans else (-1, -1))
    cands = allowed.get("candidates") if mode != "off" else None
    order: list[int] = []
    shown: dict[str, int] = {}
    if cands:
        seed = int(((cfg.get("manifest") or {}).get("seed")) or 0)
        order = menu_order(rec, mode, seed=seed)
        menu, shown = _render_menu(cands, order)
        slots = _slots(cfg.get("prompt_slots"))
        denied = bool(allowed.get("r0_negated"))
        if rec.sct is not None and str(rec.sct) in shown:
            n = shown[str(rec.sct)]
            pick = f'line [{n}] {cands[order[n]].get("fsn") or cands[order[n]].get("label")}'
        elif rec.sct is None:
            pick = "no line (it gave no code)"
        else:
            pick = f"a code that is NOT on this list: {rec.sct}"
        # What the extractor was TOLD, not only what it was shown: the pick
        # guidance is where a corpus's coding convention lives (CADEC: the
        # plain concept, severity dropped), and a judge grading without it
        # fails correct picks against a rule it never saw (smoke run,
        # 2026-09-03). Read through rung 0's own slot table so the two
        # rungs cannot drift onto different wordings.
        from ladder.rungs import r0 as _r0
        guidance = "\n".join(
            "  " + line for line in
            _r0.resolve(cfg.get("prompt_slots"))["pick_guidance"].strip().splitlines())
        prompt = judge_prompt_menu(cfg.get("prompt_slots")).format(
            source=source, text=rec.text, start=s, end=e, sct=rec.sct,
            denied=" [denied]" if denied else "",
            guidance=guidance, menu=menu, pick=pick,
            denied_note=(slots["denied_note"].format(**slots) + "\n") if denied else "",
        )
        rec.checks["r4_menu"] = mode
        rec.checks["r4_menu_order"] = order
    else:
        prompt = judge_prompt(cfg.get("prompt_slots")).format(
            source=source, text=rec.text, start=s, end=e, sct=rec.sct)
        # "none": the arm was on and this record had nothing to show — an
        # S0/S1 record, or a menu-less record. Distinct from "off".
        rec.checks["r4_menu"] = "off" if mode == "off" else "none"
    # text="" — the template above already carries the post. Passing `source`
    # here sent every post TWICE (fixed 2026-08-25; Caller appends non-empty
    # text as a POST section). The doubled prompt was invisible with granite
    # and is where BioMistral-7B stops answering.
    raw, usage = llm(prompt, "", "judge")
    try:
        m = json.loads(raw)
    except json.JSONDecodeError:
        return None, {**usage, "parse_failed": True}
    v: dict[str, Any] = {
        "span_ok": bool(m.get("span_ok")),
        "code_ok": bool(m.get("code_ok")),
        "confidence": float(m.get("confidence", 0) or 0),
        "why": str(m.get("why", ""))[:200],
        # None when no menu was shown: "not asked" is not "not in the menu".
        "best": None,
        "best_code": None,
        "menu_missing": None,
    }
    if cands:
        best = m.get("best")
        if best is None or (isinstance(best, str) and best.strip().lower() in ("null", "none")):
            v["menu_missing"] = True
        else:
            try:
                n = int(best)
            except (TypeError, ValueError):
                n = -1
            if 0 <= n < len(order):
                v["best"] = n
                v["best_code"] = str(cands[order[n]].get("code"))
                v["menu_missing"] = False
            else:
                # Never clamped: an index off the list is the judge failing to
                # use the menu, and clamping would report that as a choice.
                v["best_bad"] = best
                v["menu_missing"] = False
    return v, usage



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
           # The menu arm's own counts. `menu_missing` is the verdict the
           # blind judge could not give; `best_is_pick` is how often the
           # judge, shown the list, ratifies the extractor's line.
           "menu": cfg.get("menu", DEFAULTS["menu"]),
           "menu_shown": 0, "menu_missing": 0, "best_is_pick": 0,
           "t0": time.time()}

    for rec in records:
        source = sources.get(rec.doc_id, "")
        agg["records"] += 1
        v, usage = judge(rec, source, llm, cfg)
        agg["tokens_in"] += usage.get("in", 0)
        agg["tokens_out"] += usage.get("out", 0)
        # Priced by the caller from models.yaml. Rung 4's judge is the most
        # likely rung to run on a hosted model, so a dropped price here is the
        # most likely to matter.
        agg["usd"] = agg.get("usd", 0.0) + usage.get("usd", 0.0)
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
                           usd=usage.get("usd", 0.0),
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
        rec.checks["r4_best_code"] = v.get("best_code")
        rec.checks["r4_menu_missing"] = v.get("menu_missing")
        if v.get("menu_missing") is not None:
            agg["menu_shown"] += 1
            if v["menu_missing"]:
                agg["menu_missing"] += 1
            elif v.get("best_code") is not None and str(v["best_code"]) == str(rec.sct):
                agg["best_is_pick"] += 1

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
                         usd=usage.get("usd", 0.0),
                         latency_ms=usage.get("seconds", 0.0) * 1000,
                         verdict=verdict,
                         span_ok=v["span_ok"], code_ok=v["code_ok"],
                         menu=rec.checks.get("r4_menu"),
                         menu_missing=v.get("menu_missing"),
                         best_code=v.get("best_code"),
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
    if agg.get("menu_shown"):
        print(f"\n  menu arm ({agg['menu']}): shown {agg['menu_shown']}   "
              f"'not on this list' {agg['menu_missing']}   "
              f"best = the pick {agg['best_is_pick']}")

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

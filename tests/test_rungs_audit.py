"""The rungs 1-6 audit (2026-08-28).

Rung 0 was audited first; these are the live defects the same treatment found
in the rungs above it. Each test names a defect that was demonstrated on real
run artifacts before it was written.

1. RUNG 3 LEAVES RUNG 1'S VERDICT DESCRIBING A CODE THE RECORD NO LONGER HAS.
   Rung 3 overwrites `rec.sct` on a majority vote and never re-validates, but
   rung 5 routes on `checks["r1_verdict"]`. Demonstrated on the shipped runs:
   phaseD-r3-2 changed 25 codes and phaseF-test-1 changed 30, and every one of
   those records still carried rung 1's verdict on the replaced code.
   LIPITOR.739#0 is the case that reached a user: "Chronic pain" coded
   82423001 |Chronic pain|, ACCEPTed by rung 1 on an exact lexical match, then
   voted 3-0 to 762452003 |Chronic musculoskeletal pain| — which does NOT
   lexically match — and shipped as VERIFIED on the older code's ACCEPT.

2. RUNG 2 RE-VALIDATES ITS OWN REPAIR UNDER `r1.DEFAULTS`, NOT UNDER THE
   MANIFEST'S RUNG 1. `run_ladder` builds each rung's cfg from
   `manifest.rungs[n]` alone, so rung 2's cfg carries none of rung 1's
   settings; passing it to `r1.zone` silently substitutes the defaults. A
   repair can then be counted `rescued` under a rule the rung 1 that rejected
   it does not use.
"""

import json
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

_ROOT = pathlib.Path(__file__).resolve().parent.parent

from ladder.rungs import r1, r2, r3
from ladder.schema import (
    R_CODE_UNKNOWN,
    REACTION,
    Record,
    ZONE_ACCEPT,
    ZONE_BAND,
    ZONE_NEW,
)

#         0        9       17          29
SOURCE = "suffered extreme rectal bleed today"
#                  0         1         2         3
#                  0123456789012345678901234567890
PAIN_SOURCE = "the chronic pain never really stopped"


class FakeVocab:
    """Two codes with different words, so a lexical match can change."""

    TERMS = {
        "82423001": ["Chronic pain"],
        "762452003": ["Chronic musculoskeletal pain"],
        "271782001": ["Rectal bleed"],
    }

    def exists(self, code):
        return str(code) in self.TERMS

    def is_active(self, code):
        return True

    def finding_status(self, code):
        return "finding"

    def terms(self, code):
        return self.TERMS.get(str(code), [])

    def replacements(self, code):
        return []

    def lexical_match(self, text, code, mode="exact"):
        want = (text or "").strip().lower()
        got = [t.strip().lower() for t in self.TERMS.get(str(code), [])]
        if mode == "exact":
            return want in got
        # "contained" is a TOKEN subset either way round, which is what
        # Registry.lexical_match does — not a substring test.
        w = set(want.split())
        return any(w <= set(t.split()) or set(t.split()) <= w for t in got)


def pain_record(**kw):
    base = dict(
        doc_id="D9", entity_type=REACTION, text="chronic pain",
        spans=[(4, 16)], sct="82423001", zone=ZONE_NEW, record_id="D9#0",
    )
    base.update(kw)
    return Record(**base)


# ---------------------------------------------------------------- defect 1
def test_rung_3_leaves_rung_1s_verdict_on_the_code_it_replaced():
    """The defect, reproduced from LIPITOR.739#0. Documents the WRONG state."""
    vocab = FakeVocab()
    rec = pain_record()
    verdict, reason, checks = r1.zone(rec, PAIN_SOURCE, vocab, {})
    rec.checks.update(checks)
    rec.checks["r1_verdict"] = verdict
    rec.checks["r1_reason"] = reason
    assert verdict == ZONE_ACCEPT and checks["lexical_match"] is True

    # rung 3's vote lands, exactly as apply() does it today
    rec.sct = "762452003"

    # the record now carries a verdict about a code it does not have
    assert rec.checks["r1_verdict"] == ZONE_ACCEPT
    assert vocab.lexical_match(rec.text, rec.sct, mode="exact") is False


def test_rung_3_revalidate_arm_refreshes_the_verdict_after_a_change():
    """With the arm on, a changed record is re-judged by the ONE rung 1."""
    vocab = FakeVocab()
    rec = pain_record()
    verdict, reason, checks = r1.zone(rec, PAIN_SOURCE, vocab, {})
    rec.checks.update(checks)
    rec.checks["r1_verdict"], rec.checks["r1_reason"] = verdict, reason

    r3.revalidate(rec, PAIN_SOURCE, "762452003",
                  {"registry": vocab, "revalidate": True, "manifest": {}})

    assert rec.sct == "762452003"
    assert rec.checks["r1_verdict"] == ZONE_BAND, (
        "the new code does not lexically match, so rung 1 bands it"
    )
    assert rec.checks["lexical_match"] is False
    assert rec.checks["r3_revalidated"] is True
    # the superseded verdict is kept, never silently dropped
    assert rec.checks["r3_r1_before"]["r1_verdict"] == ZONE_ACCEPT


def test_rung_3_revalidate_is_off_by_default_and_records_the_staleness():
    """Off by default — but a stale verdict is never left unlabelled."""
    vocab = FakeVocab()
    rec = pain_record()
    verdict, reason, checks = r1.zone(rec, PAIN_SOURCE, vocab, {})
    rec.checks.update(checks)
    rec.checks["r1_verdict"], rec.checks["r1_reason"] = verdict, reason

    r3.revalidate(rec, PAIN_SOURCE, "762452003", {"registry": vocab, "manifest": {}})

    assert rec.sct == "762452003"
    assert rec.checks["r1_verdict"] == ZONE_ACCEPT, "unchanged with the arm off"
    assert rec.checks["r3_r1_stale"] is True, (
        "a verdict about a replaced code must be readable as stale, or a "
        "downstream rung cannot tell it apart from a verdict about this code"
    )
    assert "revalidate" in r3.DEFAULTS and r3.DEFAULTS["revalidate"] is False


def test_rung_3_revalidate_uses_the_manifests_rung_1_settings():
    """The re-judgement is rung 1 AS CONFIGURED, never r1.DEFAULTS."""
    vocab = FakeVocab()
    rec = pain_record()
    man = {"rungs": {"1": {"lexical_mode": "contained"}}}
    r3.revalidate(rec, PAIN_SOURCE, "762452003",
                  {"registry": vocab, "revalidate": True, "manifest": man})
    # under "contained", "chronic pain" IS inside "chronic musculoskeletal pain"
    assert rec.checks["r1_verdict"] == ZONE_ACCEPT
    assert rec.checks["lexical_match"] is True


# ---------------------------------------------------------------- defect 2
def test_rung_2_revalidates_under_the_manifests_rung_1_not_the_defaults():
    """A repair must be judged by the same rung 1 that rejected the original.

    `run_ladder` gives rung 2 only `manifest.rungs.2`, so the cfg it passed to
    `r1.zone` carried no rung 1 settings at all and the defaults silently
    applied. Here the manifest sets `label_check: "reject"`: the model repairs
    a nonexistent code to 271782001 |Rectal bleed| while still claiming the
    label "Chronic pain", which the configured rung 1 rejects and the default
    rung 1 only flags. The SAME repair is a rescue under one and not the other,
    which is the whole point — rung 2 must not get to choose.
    """
    vocab = FakeVocab()

    def run(man):
        rec = Record(doc_id="D9", entity_type=REACTION, text="chronic pain",
                     spans=[(4, 16)], sct="999999999",
                     sct_label="Chronic pain", zone=ZONE_NEW, record_id="D9#0")
        rec.checks["r1_verdict"], rec.checks["r1_reason"] = "REJECT", R_CODE_UNKNOWN

        def llm(prompt, text, mode):
            return (json.dumps({"span_text": "chronic pain", "start": 4,
                                "end": 16, "code": "271782001",
                                "confidence": 0.9}), {})

        _, agg = r2.apply([rec], {"D9": PAIN_SOURCE},
                          {"llm": llm, "registry": vocab, "manifest": man})
        return rec, agg

    rec, agg = run({"rungs": {"1": {"label_check": "reject"}}})
    assert agg["attempted"] == 1
    assert agg["rescued"] == 0 and agg["still_failing"] == 1, (
        "the manifest says a label that does not match its code rejects"
    )
    assert rec.checks["r2"]["new_reason"] == "label_mismatch"

    # and under rung 1's own defaults the very same repair IS a rescue, which
    # is exactly what rung 2 was reporting regardless of the manifest
    _, agg_default = run({"rungs": {"1": {}}})
    assert agg_default["rescued"] == 1


def test_rung_2_is_sent_the_post_exactly_once_still():
    """The Phase C double-post fix, re-asserted from the audit side."""
    vocab = FakeVocab()
    rec = Record(doc_id="D9", entity_type=REACTION, text="chronic pain",
                 spans=[(4, 16)], sct="999999999", zone=ZONE_NEW,
                 record_id="D9#0")
    rec.checks["r1_verdict"], rec.checks["r1_reason"] = "REJECT", R_CODE_UNKNOWN
    seen = {}

    def llm(prompt, text, mode):
        seen["prompt"], seen["text"] = prompt, text
        return (json.dumps({"span_text": "chronic pain", "start": 4, "end": 16,
                            "code": "762452003", "confidence": 0.9}), {})

    r2.apply([rec], {"D9": PAIN_SOURCE},
             {"llm": llm, "registry": vocab, "manifest": {}})
    assert seen["text"] == ""
    assert seen["prompt"].count(PAIN_SOURCE) == 1


# ------------------------------------------- defect 3: rung 4's unported prompt
def test_rung_4_prompt_renders_from_the_corpus_slot_table():
    """Rung 4 is the SEVENTH prompt constant, and it was never ported.

    The FiNER arm rendered six rung 0 prompt constants from
    `manifest.corpus.prompts`, and rung 4 was missed — so a judge grading an
    SEC filing was asked whether the text described "a personal adverse
    reaction ... the writer says they experienced", with a "SNOMED CT code".
    Every FiNER verdict from that prompt is answering a question about the
    wrong domain. The judge is the one rung whose whole job is to read the
    text, so a prompt about the wrong text is not a cosmetic defect.
    """
    from ladder.rungs import r4

    cadec = r4.judge_prompt(None)
    assert "adverse reaction" in cadec, "CADEC wording is the default"
    assert "SNOMED CT" in cadec

    import json as _json
    slots = (_json.load(open(_ROOT / "manifest.finer.json"))
             .get("corpus", {}).get("prompts"))
    finer = r4.judge_prompt(slots)
    assert "reported financial fact" in finer and "US-GAAP XBRL tag" in finer
    # NOT just the two obvious substitutions. Every CADEC-specific word has to
    # be gone, or the prompt has half-ported: the first version of this fix
    # still said "It read a patient's post" and "the filer says they
    # EXPERIENCED", which is the same defect wearing the new mechanism.
    for word in ("adverse", "SNOMED", "patient", "experienced", "post",
                 "reaction"):
        assert word.lower() not in finer.lower(), (
            f"CADEC word {word!r} survived into the FiNER judge prompt:\n{finer}"
        )
    # the format placeholders survive rendering, or judge() cannot fill them
    for f in ("{source}", "{text}", "{start}", "{end}", "{sct}"):
        assert f in finer, f"{f} lost during slot rendering"


def test_rung_4_uses_the_rendered_prompt_when_slots_are_passed():
    """The rendering must reach the actual call, not just exist as a helper."""
    from ladder.rungs import r4
    from ladder.schema import REACTION, Record

    seen = {}

    def llm(prompt, text, mode):
        seen["prompt"] = prompt
        return (json.dumps({"span_ok": True, "code_ok": True,
                            "confidence": 0.9, "why": "ok"}), {})

    rec = Record(doc_id="D1", entity_type=REACTION, text="47.6",
                 spans=[(0, 4)], sct="EffectiveIncomeTaxRate",
                 zone=ZONE_NEW, record_id="D1#0")
    r4.apply([rec], {"D1": "a tax rate of 47.6 percent"},
             {"judge_llm": llm, "prompt_slots": {
                 "entity": "reported financial fact", "entity_short": "fact",
                 "author": "the filer", "source": "the filing excerpt",
                 "vocabulary": "US-GAAP XBRL tag"}})
    assert "adverse reaction" not in seen["prompt"]
    assert "reported financial fact" in seen["prompt"]


# ------------------------- defect 4: CADEC's exclusions applied to every corpus
def test_exclusions_are_corpus_scoped_not_global():
    """`load_exclusions()` reads `data/exclusions.csv` whatever corpus is running.

    Observed on the first FiNER run: `[run] gold exclusions applied: 414 (see
    data/exclusions.csv)` — 414 CADEC record ids, on a corpus whose ids all
    start with FINER. Harmless only because the two id spaces happen not to
    collide; the exclusion list is a claim about ONE answer key ("these gold
    mentions cannot be answered"), and applying it to another corpus's gold is
    a category error that would silently drop mentions the moment an id did
    collide. The manifest already knows which corpus it is.
    """
    from ladder import clean

    man = {"corpus": {"adapter": "finer", "exclusions": None}}
    assert clean.exclusions_for(man) == set(), (
        "a corpus that declares no exclusions file must exclude NOTHING, not "
        "fall back to another corpus's list"
    )


def test_exclusions_for_reads_the_declared_file(tmp_path):
    """A corpus that DOES declare one gets exactly that file."""
    from ladder import clean

    p = tmp_path / "excl.csv"
    p.write_text("record_id,reason\nFINER.test.0001#0,bad span\n", encoding="utf-8")
    man = {"corpus": {"adapter": "finer", "exclusions": str(p)}}
    assert clean.exclusions_for(man) == {"FINER.test.0001#0"}


def test_cadec_still_gets_its_exclusions_by_default():
    """The CADEC arm must not change: no `exclusions` key means its own file."""
    from ladder import clean

    got = clean.exclusions_for({"corpus": {"cadec_root": "data/cadec"}})
    assert len(got) == len(clean.load_exclusions()) > 0


# ---------------- defect 5: a model typo costs the whole run, two hours in
def test_every_model_the_run_needs_is_checked_before_rung_0():
    """Models are resolved lazily per rung, so a bad name surfaces last.

    Measured: the first full FiNER run spent 2,035 s in rung 0 and 5,948 s in
    rung 3 — 133 minutes — and then died at rung 4 because
    `manifest.finer.json` said `ollama/granite4:micro-h` where the installed
    model is `ollama/ibm/granite4:micro-h`. Nothing was wrong with the ladder;
    the run simply learned the name was bad as late as it possibly could.

    Same principle the timeout and the reply-shape repairs already apply: one
    bad thing must cost one thing, not the run.
    """
    from ladder import llm as llm_mod

    man = {"model": {"extractor": "ollama/gpt-oss:20b",
                     "judge": "ollama/nope-not-a-model:1b"}}
    problems = llm_mod.check_models(man, [0, 1, 2, 3, 4], available=[
        "gpt-oss:20b", "ibm/granite4:micro-h"])
    assert problems, "an unavailable judge must be reported"
    joined = " ".join(problems)
    assert "judge" in joined and "nope-not-a-model" in joined
    assert "4" in joined, "the failing rung must be named"


def test_check_models_passes_when_every_name_resolves():
    from ladder import llm as llm_mod

    man = {"model": {"extractor": "ollama/gpt-oss:20b",
                     "judge": "ollama/ibm/granite4:micro-h"}}
    assert llm_mod.check_models(man, [0, 1, 2, 3, 4], available=[
        "gpt-oss:20b", "ibm/granite4:micro-h"]) == []


def test_check_models_only_checks_the_rungs_actually_running():
    """`--rungs 0,1` must not fail on a judge it will never call."""
    from ladder import llm as llm_mod

    man = {"model": {"extractor": "ollama/gpt-oss:20b",
                     "judge": "ollama/nope-not-a-model:1b"}}
    assert llm_mod.check_models(man, [0, 1], available=["gpt-oss:20b"]) == []


def test_both_shipped_manifests_name_models_that_exist():
    """The typo itself, and the reason it survived: only CADEC was ever run."""
    import json

    from ladder import llm as llm_mod

    available = ["gpt-oss:20b", "ibm/granite4:micro-h", "llama3.1:8b",
                 "mistral:7b-instruct", "qwen3:8b", "biomistral:7b-q5_k_m"]
    for name in ("manifest.json", "manifest.finer.json"):
        man = json.load(open(_ROOT / name))
        assert llm_mod.check_models(man, man["rung_order"], available) == [], name


def test_check_models_skips_rungs_disabled_in_the_manifest():
    """A rung switched off in the manifest needs no model, so a missing or
    mistyped name for it must not stop the run — `enabled: false` is already a
    recorded run state, and the preflight has to respect it or it turns a
    deliberate configuration into a hard failure. Caught by
    tests/test_r3_repair.py when the preflight was first wired in."""
    from ladder import llm as llm_mod

    man = {"model": {"extractor": "ollama/gpt-oss:20b"},
           "rungs": {"3": {"enabled": False}, "4": {"enabled": False}}}
    assert llm_mod.check_models(man, [0, 1, 2, 3, 4],
                                available=["gpt-oss:20b"]) == []


# ------- defect 6: the PICK path crashes on a reply shape the FIND path allows
def test_a_bare_list_from_the_pick_call_costs_one_document_not_the_run():
    """`_decide_batch` assumed the pick reply is always {"picks": [...]}.

    Measured: all three granite4:micro-h draws died with
    `AttributeError: 'list' object has no attribute 'get'` at r0.py:1283 —
    the model answered with a bare JSON array, which the FIND path has coerced
    since it was hardened and the PICK path never did. Same rule, same file,
    one call site missed: a reply shape nobody anticipated costs ONE DOCUMENT,
    not the run.
    """
    from ladder.rungs import r0

    meta = {}
    assert r0._as_picks([{"reaction": 0, "choice": 3}], meta) == {
        "picks": [{"reaction": 0, "choice": 3}]}
    assert meta.get("shape_coerced") is True, "the coercion must be COUNTED"

    meta2 = {}
    assert r0._as_picks({"picks": [{"reaction": 1, "choice": 2}]}, meta2) == {
        "picks": [{"reaction": 1, "choice": 2}]}
    assert not meta2.get("shape_coerced"), "the expected shape is not a coercion"

    # a shape that carries no picks is None, never an exception
    assert r0._as_picks(["nope", 3], {}) is None
    assert r0._as_picks("nope", {}) is None
    assert r0._as_picks(None, {}) is None


def test_granite_style_pick_reply_survives_a_real_decide_batch():
    """End to end through _decide_batch, the function that actually crashed."""
    from ladder.rungs import r0
    from ladder.schema import REACTION, Record

    rec = Record(doc_id="D1", entity_type=REACTION, text="rectal bleed",
                 spans=[(17, 29)], sct=None, zone=ZONE_NEW, record_id="D1#0")
    cands = [{"i": 0, "code": "271782001", "label": "rectal bleed",
              "fsn": "rectal bleed", "score": 0.9, "via": "dense"},
             {"i": 1, "code": "999", "label": "something else",
              "fsn": "something else", "score": 0.4, "via": "dense"}]
    meta = {"tokens_in": 0, "tokens_out": 0, "api_calls": 0}

    def llm(prompt, text, mode):
        # a bare array, exactly what granite4:micro-h returned
        return (json.dumps([{"reaction": 0, "choice": 0}]),
                {"in": 1, "out": 1, "usd": 0.0, "seconds": 0.0})

    r0._decide_batch([(rec, cands)], "suffered extreme rectal bleed today",
                     llm, r0.prepare({"llm": llm}), meta, "S2")
    assert rec.sct == "271782001", "the pick must be applied, not dropped"
    assert meta.get("shape_coerced") is True


# ------- defect 7: the declared configuration was not the measured one
MEASURED_R0_ARMS = {
    "rung0_split": True,
    "rung0_drop_ungrounded": True,
    "rung0_drop_fragments": True,
    "rung0_drop_duplicate_spans": True,
    "rung0_cut_rate": 0.06,
}


def test_manifest_declares_every_measured_rung_0_arm_explicitly():
    """`manifest.json` must not rely on a code default for anything measured.

    The five arms below were measured and accepted on 2026-08-27/28, shipped as
    code with `r0.DEFAULTS` off, and never appended to the manifest. So the
    tracked configuration scored exact 0.340 while every number in the decision
    log and the article came from a configuration scoring 0.399 — a 5.9-point
    gap, and two answers to "which configuration produced this number". That is
    the same failure the `manifest.model` note exists for, one layer down.

    Explicitly, not just correctly: a manifest that happens to agree with
    `r0.DEFAULTS` still breaks the moment a default moves, and the default is
    the thing that moved last time.
    """
    import json

    man = json.load(open(_ROOT / "manifest.json"))
    declared = man["rungs"]["0"]
    for arm, want in MEASURED_R0_ARMS.items():
        assert arm in declared, (
            f"{arm} is measured and accepted but absent from manifest.json, so "
            f"the run silently takes r0.DEFAULTS[{arm!r}] instead"
        )
        assert declared[arm] == want, f"{arm}: manifest {declared[arm]!r} != measured {want!r}"


def test_the_measured_arms_are_not_the_code_defaults():
    """If they were, the test above could pass while proving nothing."""
    from ladder.rungs import r0

    differs = [a for a, want in MEASURED_R0_ARMS.items()
               if r0.DEFAULTS.get(a) != want]
    assert differs, (
        "every measured arm now matches r0.DEFAULTS, so the manifest could be "
        "empty and still 'agree' — re-point this test at whatever the declared "
        "configuration actually depends on"
    )


# --------- improvement: date-like spans are never a tagged quantity (FiNER)
def test_drop_datelike_removes_years_and_clock_times_only():
    """A bare year or a clock time is a date, not a reported quantity.

    Measured on the FiNER dev run: of 238 false-positive spans, 22 are 4-digit
    years ("2018", "2011") and 4 are times of day ("2:45 p.m."), and **neither
    class costs a single gold mention** — 0 of 165. A third candidate, "drop
    any span with no digit", was measured and REJECTED: it cuts 14 predictions
    but destroys 7 gold, because FiNER gold spells small counts out ("two" ->
    NumberOfOperatingSegments). Free filters ship; the one with a
    false-rejection cost does not.
    """
    from ladder.rungs import r0
    from ladder.schema import REACTION, Record

    def rec(text, i=0):
        return Record(doc_id="D1", entity_type=REACTION, text=text,
                      spans=[(i, i + len(text))], sct="X", zone=ZONE_NEW,
                      record_id=f"D1#{i}")

    recs = [rec("2018", 0), rec("2:45 p.m.", 10), rec("19.5", 30),
            rec("two", 40), rec("1998", 50), rec("12 months", 60)]
    kept, counts = r0.filter_spans(recs, {"rung0_drop_datelike": True})
    kept_text = [r.text for r in kept]
    assert kept_text == ["19.5", "two", "12 months"], kept_text
    assert counts["dropped_datelike"] == 3

    # off by default, like every other span filter
    kept2, counts2 = r0.filter_spans(recs, {})
    assert len(kept2) == 6 and counts2.get("dropped_datelike", 0) == 0
    assert r0.DEFAULTS["rung0_drop_datelike"] is False


def test_drop_datelike_does_not_touch_a_year_inside_a_longer_span():
    """Only a span that IS a date, never one that merely contains one."""
    from ladder.rungs import r0
    from ladder.schema import REACTION, Record

    recs = [Record(doc_id="D1", entity_type=REACTION, text="2018 revenues",
                   spans=[(0, 13)], sct="X", zone=ZONE_NEW, record_id="D1#0")]
    kept, counts = r0.filter_spans(recs, {"rung0_drop_datelike": True})
    assert len(kept) == 1 and counts["dropped_datelike"] == 0


# ---- merge interaction: a bare array must be wrapped under the RIGHT key
def test_a_bare_array_from_a_pick_call_is_not_wrapped_as_mentions():
    """Two independently-correct fixes that break each other on contact.

    This branch made `_decide_batch` tolerate a bare array (granite answers
    `[{"reaction":0,"choice":3}]`). main added `_unwrap_array` at the TRANSPORT
    layer, which wraps any bare array as `{"mentions": [...]}` — correct for a
    FIND reply and wrong for a PICK one, where `.get("picks")` then returns []
    and the picks are silently dropped. Main's fix turns this branch's crash
    into a silent no-op, which is worse: a crash is visible.

    The wrap therefore has to use the key the CALL expects, and `mode` is in
    scope where it happens.
    """
    from ladder.llm import Caller

    c = Caller.__new__(Caller)
    c.unwrapped = 0
    assert c._unwrap_array('[{"span_text":"x"}]', "find") == '{"mentions": [{"span_text":"x"}]}'
    # the pick call passes f"{step}-pick", which is what production sends
    assert c._unwrap_array('[{"reaction":0,"choice":3}]', "S2-pick") == \
        '{"picks": [{"reaction":0,"choice":3}]}'
    # S0/S1/S2 are extraction steps and take the mentions envelope
    assert c._unwrap_array('[{"a":1}]', "S2").startswith('{"mentions"')
    # anything already an object, or not a list, is untouched
    assert c._unwrap_array('{"picks": []}', "S2-pick") == '{"picks": []}'
    assert c._unwrap_array('[1,2,3]', "S2-pick") == '[1,2,3]'
    assert c.unwrapped == 3


# --- rung 4 wired into rung 5: an off-by-default arm (2026-08-30) -------------
#
# The audit's structural finding was that every deferral in the ladder ends in
# a field nothing reads: rung 2 writes `r2_declined`, rung 3 writes
# `r3_unanimous_none`, rung 4 writes `r4_verdict`, and `r5.decide()` reads none
# of the three. The owner's call on rung 4 was to WIRE IT AS AN ARM and measure
# whether it adds anything, rather than to disable it or leave it a diagnostic.
#
# `abstain_on_judge_fail` defaults to False, so the shipped configuration is
# byte-for-byte the one every published CADEC number was produced under.

from ladder.rungs import r5 as _r5
from ladder.schema import (
    Record as _Record,
    R_JUDGE_FAIL as _R_JUDGE_FAIL,
    ZONE_ABSTAIN as _ABSTAIN,
    ZONE_ACCEPT as _ACCEPT,
    ZONE_BAND as _BAND,
    ZONE_VERIFIED as _VERIFIED,
)


def _jrec(verdict, zone=_ACCEPT, **kw):
    base = dict(doc_id="D1", entity_type="reaction", text="bit drowsy",
                spans=[(9, 19)], sct="271782001")
    base.update(kw)
    r = _Record(**base)
    r.checks["r1_verdict"] = zone
    if verdict is not None:
        r.checks["r4_verdict"] = verdict
    return r


def test_the_judge_arm_is_off_by_default():
    """Every published CADEC number was produced with rung 4 wired to nothing."""
    assert _r5.DEFAULTS["abstain_on_judge_fail"] is False
    r = _jrec("fail")
    assert _r5.decide(r, {})[0] == _VERIFIED


def test_the_judge_arm_abstains_an_accepted_record_the_judge_failed():
    r = _jrec("fail")
    zone, reason = _r5.decide(r, {"abstain_on_judge_fail": True})
    assert (zone, reason) == (_ABSTAIN, _R_JUDGE_FAIL)


def test_the_judge_arm_leaves_a_passed_record_alone():
    r = _jrec("pass")
    assert _r5.decide(r, {"abstain_on_judge_fail": True})[0] == _VERIFIED


def test_a_record_the_judge_never_reached_is_not_abstained_for_it():
    """`r4_verdict` is None on a parse failure and absent when rung 4 did not
    run at all. Neither is evidence against the record, and treating a missing
    judgement as a failed one would abstain the whole run the moment the judge
    was disabled."""
    for r in (_jrec(None), _jrec(None)):
        assert _r5.decide(r, {"abstain_on_judge_fail": True})[0] == _VERIFIED
    r = _jrec("fail")
    r.checks["r4_verdict"] = None
    assert _r5.decide(r, {"abstain_on_judge_fail": True})[0] == _VERIFIED


def test_the_judge_arm_cannot_rescue_a_record_the_free_check_already_withheld():
    """The arm may only SUBTRACT coverage. A BAND record stays abstained and
    keeps its own reason, because `unresolved` is the more specific fact and
    the judge agreeing with it adds nothing."""
    r = _jrec("fail", zone=_BAND)
    zone, reason = _r5.decide(r, {"abstain_on_judge_fail": True})
    assert zone == _ABSTAIN and reason != _R_JUDGE_FAIL
    r2 = _jrec("pass", zone=_BAND)
    assert _r5.decide(r2, {"abstain_on_judge_fail": True})[0] == _ABSTAIN


def test_the_judge_arm_withdraws_the_answer_and_keeps_it(tmp_path):
    from ladder.ledger import Ledger
    r = _jrec("fail")
    ledger = Ledger(tmp_path / "l.jsonl", run_id="t")
    _r5.apply([r], {"D1": "she was bit drowsy"},
              {"ledger": ledger, **_r5.DEFAULTS, "abstain_on_judge_fail": True})
    ledger.close()
    assert r.zone == _ABSTAIN and r.reason == _R_JUDGE_FAIL
    assert r.sct is None
    assert r.checks["withheld"]["sct"] == "271782001"


def test_the_judge_arm_manifest_differs_from_the_shipped_one_by_exactly_one_key():
    """An ablation manifest is only an ablation if it holds everything else fixed.

    The spine ablation on 2026-08-30 nearly shipped a 5.9-point rung 0
    difference charged to the rungs being dropped, because its manifests had
    been written before rung 0 changed. `manifest.judgearm.json` exists to
    isolate ONE flag, so this asserts that it does — key by key, not by
    eyeball.
    """
    import json

    a = json.load(open(_ROOT / "manifest.json"))
    b = json.load(open(_ROOT / "manifest.judgearm.json"))
    b.pop("_judgearm_note", None)

    def walk(x, y, path=""):
        if isinstance(x, dict) and isinstance(y, dict):
            for k in sorted(set(x) | set(y)):
                yield from walk(x.get(k), y.get(k), f"{path}.{k}")
        elif x != y:
            yield path

    assert list(walk(a, b)) == [".rungs.5.abstain_on_judge_fail"]
    assert a["rungs"]["5"]["abstain_on_judge_fail"] is False
    assert b["rungs"]["5"]["abstain_on_judge_fail"] is True


def test_the_shipped_manifest_declares_the_judge_arm_off_explicitly():
    """Same rule as the rung 0 arms: the declared configuration must be the
    measured one, and must not lean on a code default that can move."""
    import json

    from ladder.rungs import r5

    man = json.load(open(_ROOT / "manifest.json"))
    assert man["rungs"]["5"]["abstain_on_judge_fail"] is False
    assert "abstain_on_judge_fail" in r5.DEFAULTS


# --- a refusal is not a JSON failure (2026-08-30) -----------------------------
#
# FiNER's recall gap is 52 gold mentions and 21 of them - 12.7% of the whole
# dev gold - are in ONE document the extractor REFUSED: 2,153 reasoning tokens
# and then "I'm sorry, but I can't provide that." The ledger recorded it as
# `json_decode`, i.e. as a model that cannot emit JSON.
#
# That is the same mislabelling `timed_out` > `truncated` > `json_decode` was
# introduced to stop, one class further out. A refusal is a MODEL POLICY
# decision about the content; a JSON failure is a formatting failure. They cost
# the same record and they mean completely different things, and only one of
# them is fixed by anything to do with schemas or token caps.


def test_a_refusal_is_labelled_refused_not_json_decode():
    from ladder.rungs import r0

    meta = {}
    assert r0._parse("I'm sorry, but I can't provide that.", meta) is None
    assert meta["parse_failed"] is True
    assert meta["refused"] is True


def test_ordinary_malformed_json_is_not_called_a_refusal():
    from ladder.rungs import r0

    meta = {}
    assert r0._parse('{"mentions": [', meta) is None
    assert meta["parse_failed"] is True
    assert not meta.get("refused")


def test_a_valid_reply_that_merely_mentions_sorry_is_not_a_refusal():
    """The detector reads a reply the parser has ALREADY rejected, so a
    well-formed answer quoting a patient saying 'sorry I cannot remember' can
    never reach it. Pinned because a substring test on model output is exactly
    the kind of check that quietly starts firing on real data."""
    from ladder.rungs import r0

    meta = {}
    got = r0._parse('{"mentions": [{"span_text": "sorry I cannot sleep"}]}', meta)
    assert got is not None
    assert not meta.get("refused") and not meta.get("parse_failed")


def test_the_reason_ladder_puts_refused_above_json_decode():
    """Most specific first, the same rule as timed_out > truncated. A refusal
    that a timeout also cut off is still reported as the timeout, because the
    timeout is a property of THIS MACHINE and outranks everything."""
    from ladder.rungs import r0

    assert r0.failure_reason({"parse_failed": True}) == "json_decode"
    assert r0.failure_reason({"parse_failed": True, "refused": True}) == "refused"
    assert r0.failure_reason({"parse_failed": True, "refused": True,
                              "truncated": True}) == "truncated"
    assert r0.failure_reason({"parse_failed": True, "refused": True,
                              "truncated": True, "timed_out": True}) == "timed_out"
    assert r0.failure_reason({}) is None


def test_the_refusal_detector_reads_the_apostrophe_the_model_actually_types():
    """The reply that cost 21 gold mentions is `I’m sorry, but I can’t provide
    that.` with U+2019, not the ASCII apostrophe. A detector written against
    the ASCII form passes its own tests and never fires on the corpus."""
    from ladder.rungs import r0

    meta = {}
    assert r0._parse("I’m sorry, but I can’t provide that.", meta) is None
    assert meta.get("refused") is True
    assert r0.failure_reason(meta) == "refused"

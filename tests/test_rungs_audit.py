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

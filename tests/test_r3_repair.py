"""Phase D — rung 3 repair (2026-08-26).

The 2026-08-25 full-ladder run measured rung 3 as net negative AS BUILT:
206/240 records `not_resampled` because votes were matched on an exact
(doc_id, spans) key that shifts between samples, and — worse — where matching
did succeed, 9 of 32 rung-1-verified-ACCEPT codes were OVERWRITTEN with
memory-recalled hallucinations, because the sampler called the legacy recall
prompt while rung 0's codes came from the frozen S2 retrieve-and-pick path.
Voting over a different answer distribution than the one being verified is
not verification.

Three changes, each demanded by a test here:

1. Rung 3 is disabled in the manifest while broken, and a disabled rung is a
   RECORDED state — "rung 3 did not run" must stay distinguishable from
   "rung 3 found nothing".
2. Votes are matched to a record by span OVERLAP, one sampled mention to at
   most one record — the scorer's own convention for "the same mention".
3. The sampler goes through rung 0's CONFIGURED path per sample — the frozen
   step, retriever, few-shot block and trimmer — so the k votes are drawn
   from the distribution being verified.
"""

import json
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from ladder.schema import REACTION, ZONE_ACCEPT, ZONE_NEW, Record


def rec(**kw):
    base = dict(
        doc_id="D1", entity_type=REACTION, text="rectal bleed",
        spans=[(17, 29)], sct="271782001", zone=ZONE_ACCEPT, record_id="D1#0",
    )
    base.update(kw)
    return Record(**base)


#          0        9       17          29
SOURCE = "suffered extreme rectal bleed today"
SOURCES = {"D1": SOURCE}


# --------------------------------------------------------------------------
# 1. a disabled rung is a recorded state, not a silent skip
# --------------------------------------------------------------------------


def test_a_disabled_rung_is_recorded_not_silently_skipped(tmp_path):
    """`enabled: false` in the manifest must leave a visible trail — an
    aggregate entry and a ledger row — and must not touch the records.
    A silent skip would let "rung 3 was off" be read as "rung 3 found
    nothing", which is a different claim about the same numbers."""
    from ladder.run import run_ladder

    man = {
        "rung_order": [3],
        "rungs": {"3": {"enabled": False, "k": 3, "temperature": 0.7}},
    }
    r = rec()
    result = run_ladder(
        man, "dev", [3], [r], SOURCES, None, tmp_path, "disable-test"
    )

    assert result["aggregates"][3].get("disabled") is True, (
        "a disabled rung left no aggregate entry — indistinguishable from "
        "a rung that ran and found nothing"
    )
    rows = [e for e in result["ledger"].rows if e.rung == 3]
    assert rows and all(e.outcome == "disabled" for e in rows), (
        "a disabled rung wrote no ledger row — the run file cannot show "
        "the rung was off"
    )
    assert 3 not in result["missing_rungs"], (
        "disabled must not be filed as not-implemented"
    )
    assert "r3" not in r.checks and r.sct == "271782001", (
        "a disabled rung touched the records"
    )


# --------------------------------------------------------------------------
# 2. votes are matched by span overlap, not by an exact span key
# --------------------------------------------------------------------------


def legacy_llm(reply: dict):
    """A sampler for the legacy recall path: same reply every draw."""

    def llm(prompt, text, mode):
        return json.dumps(reply), {"in": 10, "out": 10}

    return llm


def test_votes_match_the_same_mention_when_sample_spans_shift():
    """The model quotes "extreme rectal bleed" where the record says
    "rectal bleed" — same mention, shifted boundary. The 2026-08-25 run
    lost 206/240 records to exactly this: an exact (doc_id, spans) key
    called every shifted quote a different mention."""
    from ladder.rungs import r3

    r = rec()
    llm = legacy_llm({"mentions": [{
        "span_text": "extreme rectal bleed", "start": 9, "end": 29,
        "code": "12063002", "confidence": 0.9,
    }]})
    out, agg = r3.apply([r], SOURCES, {"llm": llm, "k": 3})

    assert agg["not_resampled"] == 0, (
        "a shifted span boundary was counted as a mention the samples "
        "never re-found"
    )
    assert r.checks["r3"]["seen"] == 3
    assert r.checks["r3"]["winner"] == "12063002"
    assert r.sct == "12063002", "a 3-0 vote did not change the record"


def test_one_sampled_mention_votes_for_at_most_one_record():
    """Overlap matching must stay one-to-one: a sampled mention spanning two
    records votes for the one it overlaps MOST, never for both — double
    counting would manufacture agreement out of a single draw."""
    from ladder.rungs import r3

    r_bleed = rec()                                          # (17, 29), 12 bytes of overlap
    r_extreme = rec(text="extreme", spans=[(9, 16)],
                    sct="999999999", record_id="D1#1")       # 7 bytes of overlap
    llm = legacy_llm({"mentions": [{
        "span_text": "extreme rectal bleed", "start": 9, "end": 29,
        "code": "12063002", "confidence": 0.9,
    }]})
    out, agg = r3.apply([r_bleed, r_extreme], SOURCES, {"llm": llm, "k": 3})

    assert r_bleed.checks["r3"]["seen"] == 3, "the best-overlap record lost its vote"
    assert r_extreme.checks["r3"]["outcome"] == "not_resampled", (
        "one sampled mention was counted as a vote for two records"
    )
    assert agg["not_resampled"] == 1


# --------------------------------------------------------------------------
# 3. the sampler draws from the distribution being verified
# --------------------------------------------------------------------------


class ShortlistVocab:
    """A registry whose lexical shortlist knows exactly one concept."""

    def shortlist(self, text, k=20):
        return [{"code": "271782001", "label": "Drowsy",
                 "fsn": "Drowsy (finding)"}]


class PathAwareLLM:
    """Answers FIND and PICK; a legacy recall prompt gets an empty reply.

    The pick's chosen code (271782001) appears in NO llm reply — it can only
    reach a record through the retrieved menu, so a winning vote for it is
    proof the sample went through retrieve-and-pick rather than recall.
    """

    def __init__(self):
        self.pick_prompts = 0

    def __call__(self, prompt, text, mode):
        if '"picks"' in prompt:
            self.pick_prompts += 1
            return json.dumps({"picks": [{"reaction": 0, "choice": 0}]}), \
                {"in": 10, "out": 10}
        if '"mentions"' in prompt and "concept name is" in prompt:
            return json.dumps({"mentions": [{
                "span_text": "rectal bleed", "context": "suffered extreme",
                "negated": False, "confidence": 0.9,
            }]}), {"in": 10, "out": 10}
        # The legacy recall prompt. Answering it would let this test pass
        # through the very path the fix removes, so it yields nothing.
        return json.dumps({"mentions": []}), {"in": 10, "out": 10}


def test_sampler_votes_come_from_the_configured_retrieve_and_pick_path(tmp_path):
    """With the manifest frozen to S2, rung 3's samples must run the full
    retrieve-and-pick path. The 2026-08-25 run sampled the legacy recall
    prompt instead, and voting over that OTHER distribution overwrote 9 of
    32 rung-1-verified-ACCEPT codes with hallucinations."""
    from ladder.ledger import Ledger
    from ladder.rungs import r3

    man = {"rungs": {"0": {
        "rung0_step": "S2", "rung0_retrieval": "lexical",
        "rung0_fewshot": False, "rung0_trim": False,
        "rung0_offsets": "search",
    }}}
    llm = PathAwareLLM()
    ledger = Ledger(tmp_path / "l.jsonl", run_id="t")
    r = rec(sct="999999999")
    out, agg = r3.apply([r], SOURCES, {
        "llm": llm, "k": 3, "registry": ShortlistVocab(),
        "manifest": man, "ledger": ledger,
    })
    ledger.close()

    assert llm.pick_prompts == 3, (
        f"expected one PICK call per sample, saw {llm.pick_prompts} — the "
        "sampler is not going through the retrieve-and-pick path"
    )
    assert r.checks["r3"]["winner"] == "271782001", (
        "the winning vote did not come through the retrieved menu"
    )
    assert r.sct == "271782001"
    # The k samples are billed as a DOCUMENT row, and through the S2 path a
    # sample is TWO calls. Billing one per sample would report the repaired
    # rung at half its real price.
    doc_rows = [e for e in ledger.rows if e.rung == 3 and e.outcome == "sampled"]
    assert len(doc_rows) == 1 and doc_rows[0].api_calls == 6
    assert agg["calls"] == 6


# --------------------------------------------------------------------------
# 4. one re-finding is not a majority, and document order is deterministic
# --------------------------------------------------------------------------


def test_a_single_refound_sample_cannot_overwrite_the_record():
    """Measured on the phaseD-r3-1 run: 'pain', vocabulary-verified as
    22253000 |Pain|, was overwritten by 38433004 |Analgesia| — the ABSENCE
    of pain — on a 1-0 'majority' from the only sample that re-found the
    mention. The rung refuses k<2 because one draw cannot vote; the same
    argument applies to one COUNTED vote. The verdict is still recorded —
    withholding the action, not the evidence."""
    from ladder.rungs import r3

    calls = {"n": 0}

    def llm(prompt, text, mode):
        calls["n"] += 1
        if calls["n"] == 1:
            return json.dumps({"mentions": [{
                "span_text": "rectal bleed", "start": 17, "end": 29,
                "code": "38433004", "confidence": 0.9,
            }]}), {"in": 10, "out": 10}
        return json.dumps({"mentions": []}), {"in": 10, "out": 10}

    r = rec()
    out, agg = r3.apply([r], SOURCES, {"llm": llm, "k": 3})

    assert r.checks["r3"]["seen"] == 1
    assert r.checks["r3"]["winner"] == "38433004", "the verdict must still be recorded"
    assert r.sct == "271782001", (
        "a 1-0 'majority' from a single re-finding overwrote the record — "
        "one counted vote is not a vote, by the same argument that refuses k<2"
    )
    assert not r.checks["r3"].get("changed")


def test_documents_are_sampled_in_deterministic_order():
    """Sampling iterated a SET of doc_ids, so the sampler's draw sequence —
    and with it every cache key and every vote — depended on Python's hash
    seed. A rung 3 result must be reproducible from the run id; that needs a
    deterministic document order."""
    from ladder.rungs import r3

    seen_docs = []

    def llm(prompt, text, mode):
        seen_docs.append(text)
        return json.dumps({"mentions": []}), {"in": 10, "out": 10}

    ids = ["Z9", "M4", "A1", "Q7", "B2", "X5"]
    recs = [rec(doc_id=d, record_id=f"{d}#0") for d in ids]
    sources = {d: f"source-{d}" for d in ids}
    r3.apply(recs, sources, {"llm": llm, "k": 2})

    expected = [f"source-{d}" for d in sorted(ids) for _ in range(2)]
    assert seen_docs == expected, (
        f"documents were sampled in {seen_docs!r} — order must be sorted, "
        "not whatever the set iteration happened to produce"
    )

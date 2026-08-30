"""Rung 0's PICK step: coverage of the batch, and the answer it already has.

Two defects, measured on the dev split 2026-08-27 over three independent
draws (docs/decisions.md, same date):

  (1) All of a document's reactions go into ONE pick call, and the reply
      stops enumerating as that call grows — `no_pick` is 0.0% at 4-7
      reactions per call and 8-10% above 8. LIPITOR.761 put 12 reactions in
      and got picks for reactions 0-4, at 344 completion tokens against an
      8000 cap: not truncation, just a reply that ended early. Chunking is
      NOT a retry (a retry inside rung 0 is rung 2) — it is the same single
      pass, batched smaller.

  (2) A record that leaves rung 0 with no code while its own retrieved menu
      sits on it has withheld an answer nobody asked it to withhold.
      Abstention is rung 5's job and rung 5 cannot withdraw what rung 0
      never said.
"""

import json

import pytest

from ladder.rungs import r0
from ladder.schema import CONCEPT_LESS
from tests.test_registry_lookup import reg  # noqa: F401  (fixture)
from tests.test_rung0_steps import SOURCES, FakeDense, FakeLLM, cfg


class ManyDense(FakeDense):
    """A retriever that answers every span, so every mention gets a menu."""

    def search(self, query, k=20):  # pragma: no cover - shape only
        return [
            {"i": 0, "code": "12063002", "label": "rectal bleeding",
             "fsn": "rectal bleeding", "via": "dense", "score": 0.9},
            {"i": 1, "code": "213257006", "label": "generally unwell",
             "fsn": "generally unwell", "via": "dense", "score": 0.8},
        ]


def _find(n):
    return {"mentions": [
        {"span_text": t, "context": c, "negated": False, "confidence": 0.9}
        for t, c in [("extreme rectal bleed", "due"), ("extremely sick", "I was"),
                     ("might not survive", "felt I")][:n]
    ]}


# --- (1) the pick call is chunked --------------------------------------------


def test_the_pick_is_split_into_batches_of_at_most_the_configured_size(reg):  # noqa: F811
    """Three mentions at batch size 2 is TWO pick calls, not one.

    The reply that ends early is a property of a long enumeration, so the
    remedy is a shorter one — measured: no_pick 0.0% at 4-7 reactions.
    """
    llm = FakeLLM(
        _find(3),
        {"picks": [{"reaction": 0, "choice": 0}, {"reaction": 1, "choice": 1}]},
        {"picks": [{"reaction": 0, "choice": 0}]},
    )
    recs, agg = r0.apply(
        [], SOURCES,
        cfg(reg, "S2", llm=llm, dense=ManyDense(), rung0_pick_batch=2),
    )
    assert agg["api_calls"] == 3, "1 find + 2 picks"
    assert [r.sct for r in recs] == ["12063002", "213257006", "12063002"]


def test_each_batch_numbers_its_reactions_from_zero(reg):  # noqa: F811
    """A batch's menu positions are the answer key for THAT batch. If the
    second call kept counting from 2, every pick in it would land on the
    wrong record — the same defect the S1 index test guards."""
    llm = FakeLLM(
        _find(3),
        {"picks": [{"reaction": 0, "choice": 0}, {"reaction": 1, "choice": 0}]},
        {"picks": [{"reaction": 0, "choice": 1}]},
    )
    recs, _ = r0.apply(
        [], SOURCES,
        cfg(reg, "S2", llm=llm, dense=ManyDense(), rung0_pick_batch=2),
    )
    second = llm.prompts[-1]
    assert 'reaction 0:' in second and 'reaction 1:' not in second
    assert recs[2].sct == "213257006", "the third record took the last batch's pick"


def test_one_batch_failing_to_parse_leaves_the_others_intact(reg):  # noqa: F811
    """Batching splits the blast radius: a garbled reply loses its own
    batch, not the document."""
    llm = FakeLLM(
        _find(3),
        {"picks": [{"reaction": 0, "choice": 0}, {"reaction": 1, "choice": 1}]},
        "not json at all",
    )
    recs, agg = r0.apply(
        [], SOURCES,
        cfg(reg, "S2", llm=llm, dense=ManyDense(), rung0_pick_batch=2),
    )
    assert [r.sct for r in recs[:2]] == ["12063002", "213257006"]
    assert recs[2].checks.get("pick_parse_failed") is True


# --- (2) the menu answers when the pick does not -----------------------------


def test_a_record_with_a_menu_never_leaves_rung_0_uncoded(reg):  # noqa: F811
    """The pick reply omits reaction 1 entirely — a GAP, not a decline. The
    menu it was already shown answers instead, and the record says so."""
    llm = FakeLLM(_find(2), {"picks": [{"reaction": 0, "choice": 0}]})
    recs, agg = r0.apply(
        [], SOURCES, cfg(reg, "S2", llm=llm, dense=ManyDense()),
    )
    assert recs[1].sct == "12063002"
    assert recs[1].checks["pick_fallback"] == "gap"
    assert recs[1].checks["no_pick"] is True, "the gap is still recorded"
    assert agg["pick_fallback"] == 1


def test_an_explicit_decline_also_falls_back_and_is_labelled_separately(reg):  # noqa: F811
    """`null` is the model answering "none of THESE" — a different act from
    a gap, and counted separately so the two stay legible."""
    llm = FakeLLM(_find(1), {"picks": [{"reaction": 0, "choice": None}]})
    recs, _ = r0.apply([], SOURCES, cfg(reg, "S2", llm=llm, dense=ManyDense()))
    assert recs[0].sct == "12063002"
    assert recs[0].checks["pick_fallback"] == "decline"
    assert recs[0].checks["declined_shortlist"] is True


def test_no_concept_is_a_positive_claim_and_is_never_overridden(reg):  # noqa: F811
    """CONCEPT_LESS asserts no concept fits — that IS an answer, and the
    scorer grades it against concept-less gold. Only the absence of an
    answer is filled in."""
    llm = FakeLLM(_find(1), {"picks": [{"reaction": 0, "choice": "no_concept"}]})
    recs, _ = r0.apply([], SOURCES, cfg(reg, "S2", llm=llm, dense=ManyDense()))
    assert recs[0].sct == CONCEPT_LESS
    assert "pick_fallback" not in recs[0].checks


def test_the_fallback_can_be_turned_off(reg):  # noqa: F811
    """It is a declared arm, like every other rung 0 choice."""
    llm = FakeLLM(_find(2), {"picks": [{"reaction": 0, "choice": 0}]})
    recs, _ = r0.apply(
        [], SOURCES,
        cfg(reg, "S2", llm=llm, dense=ManyDense(), rung0_pick_fallback=False),
    )
    assert recs[1].sct is None

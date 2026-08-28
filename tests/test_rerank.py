"""The rung 0 RERANK stage — between retrieval and the pick.

Why it exists is a measurement, not a hunch. On dev (2026-08-28, 174 matched
mentions) the pick converts a gold code sitting at menu rank 0 at **94.5%**
and one sitting at rank 1-19 at **42.3%**; retrieval puts gold at rank 0 only
52.3% of the time but has it somewhere in its top 200 for 91.4%. Menu recall
wants a deep k and the pick degrades with one — k=40 was measured 2026-08-24
and made picks worse. A rerank stage is the only way to hold both ends:
retrieve deep, reorder, hand the pick a short menu.

Everything here is an ARM. `rung0_rerank` defaults to None so `manifest.json`
is byte-unchanged and no Phase F number moves.
"""

import json

import pytest

from ladder import rerank
from ladder.rungs import r0
from tests.test_registry_lookup import reg  # noqa: F401  (fixture)
from tests.test_rung0_steps import SOURCES, FakeDense, FakeLLM, cfg


def menu(*pairs):
    """A retrieved menu in retrieval order: (code, label) best first."""
    return [{"i": n, "code": c, "label": l, "fsn": l, "score": 0.9 - 0.01 * n,
             "via": "dense"}
            for n, (c, l) in enumerate(pairs)]


# --- 1. polarity: the failure class the cosine cannot see ---------------------


def test_a_negated_span_is_scored_below_the_positive_ability_concept():
    """The dominant inspectable rank-0 failure on dev is antonym inversion:
    "can't sleep" retrieves |able to sleep| above |insomnia|, "could'nt
    concentrate" retrieves |able to concentrate| above |unable to concentrate|.
    Cosine is close to blind to negation; a cue is not."""
    assert rerank.polarity("can't sleep", "able to sleep") < 0
    assert rerank.polarity("can't sleep", "insomnia") >= 0
    assert rerank.polarity("could'nt concentrate", "unable to concentrate") > 0


def test_unable_is_not_read_as_able():
    """`able` is a substring of `unable`. A naive contains() inverts the very
    case the feature exists for."""
    assert rerank.polarity("could'nt walk", "unable to walk") > 0


def test_a_span_with_no_negation_cue_is_not_scored_either_way():
    """The feature only fires on evidence. A positive span must not be pushed
    toward negative concepts — that would be the same error, mirrored."""
    assert rerank.polarity("severe headache", "able to sleep") == 0
    assert rerank.polarity("severe headache", "headache") == 0


# --- 2. the stage itself ------------------------------------------------------


def test_no_reranker_leaves_the_menu_exactly_as_retrieved():
    """Default OFF. A reranker that ran by accident would move every number
    in the repo without an entry in docs/decisions.md saying so."""
    cands = menu(("1", "able to sleep"), ("2", "insomnia"))
    out, meta = rerank.rerank_menu("can't sleep", cands, {}, {})
    assert [c["code"] for c in out] == ["1", "2"]
    assert meta == {}


def test_the_polarity_reranker_lifts_the_consistent_concept_to_rank_0():
    cands = menu(("1", "able to sleep"), ("2", "insomnia"))
    out, _ = rerank.rerank_menu(
        "can't sleep", cands, {"rung0_rerank": "polarity"}, {})
    assert [c["code"] for c in out] == ["2", "1"]


def test_a_reranked_menu_is_renumbered_from_zero():
    """Menu position is the answer key the pick replies with. A reordered menu
    that kept its retrieval numbers would assign one concept's number to
    another — the same defect the pick batching had to avoid."""
    cands = menu(("1", "able to sleep"), ("2", "insomnia"), ("3", "drowsy"))
    out, _ = rerank.rerank_menu(
        "can't sleep", cands, {"rung0_rerank": "polarity"}, {})
    assert [c["i"] for c in out] == [0, 1, 2]


def test_the_menu_is_truncated_to_the_declared_size():
    """Retrieve deep, hand the pick a short menu. The whole point of the
    stage is that these two numbers differ."""
    cands = menu(*[(str(n), f"concept {n}") for n in range(40)])
    out, _ = rerank.rerank_menu(
        "headache", cands,
        {"rung0_rerank": "polarity", "rung0_rerank_k": 15}, {})
    assert len(out) == 15


def test_the_pre_rerank_order_survives_for_audit():
    """Same posture as `span_untrimmed` and `split_from`: the transformation
    is recorded so the un-reranked number stays recomputable from the run."""
    cands = menu(("1", "able to sleep"), ("2", "insomnia"))
    _, meta = rerank.rerank_menu(
        "can't sleep", cands, {"rung0_rerank": "polarity"}, {})
    assert meta["candidates_preranked"] == ["1", "2"]
    assert meta["rerank_moved"] is True


def test_a_rerank_that_changes_nothing_says_so():
    cands = menu(("2", "insomnia"), ("1", "able to sleep"))
    _, meta = rerank.rerank_menu(
        "can't sleep", cands, {"rung0_rerank": "polarity"}, {})
    assert meta["rerank_moved"] is False


def test_an_undefined_reranker_is_refused():
    """Same stance as rung0_retrieval and rung0_menu_order: a run must not be
    reportable under a label the article cannot explain."""
    with pytest.raises(ValueError, match="rung0_rerank"):
        rerank.rerank_menu("x", menu(("1", "a")), {"rung0_rerank": "nope"}, {})


# --- 3. the LLM reranker, and its bill ----------------------------------------


def test_the_llm_reranker_orders_the_menu_by_the_returned_shortlist():
    llm = FakeLLM({"shortlists": [{"reaction": 0, "concepts": [2, 0]}]})
    pairs = [("can't sleep", menu(("1", "able to sleep"), ("2", "drowsy"),
                                 ("3", "insomnia")))]
    out, meta = rerank.rerank_llm(pairs, "post", llm, {"rung0_rerank_k": 3}, {})
    assert [c["code"] for c in out[0]] == ["3", "1", "2"]


def test_concepts_the_shortlist_omits_are_kept_behind_it():
    """The reranker REORDERS; it never drops a candidate the retriever paid
    for. Truncation is the declared menu size doing that, visibly."""
    llm = FakeLLM({"shortlists": [{"reaction": 0, "concepts": [1]}]})
    pairs = [("x", menu(("1", "a"), ("2", "b"), ("3", "c")))]
    out, _ = rerank.rerank_llm(pairs, "post", llm, {"rung0_rerank_k": 3}, {})
    assert [c["code"] for c in out[0]] == ["2", "1", "3"]


def test_an_out_of_range_number_is_ignored_never_clamped():
    """`_decide_batch`'s stance, for the same reason: clamping would report a
    model that failed to use the menu as a model that used it."""
    llm = FakeLLM({"shortlists": [{"reaction": 0, "concepts": [99, 1]}]})
    pairs = [("x", menu(("1", "a"), ("2", "b")))]
    out, meta = rerank.rerank_llm(pairs, "post", llm, {"rung0_rerank_k": 2}, {})
    assert [c["code"] for c in out[0]] == ["2", "1"]
    assert meta["rerank_bad_index"] == 1


def test_a_reply_that_will_not_parse_leaves_the_menu_in_retrieval_order():
    """A transport failure is not a reranking. Recorded so it lands in the
    cost column and not the accuracy one — the same rule as `timed_out`."""
    llm = FakeLLM("not json at all")
    pairs = [("x", menu(("1", "a"), ("2", "b")))]
    out, meta = rerank.rerank_llm(pairs, "post", llm, {"rung0_rerank_k": 2}, {})
    assert [c["code"] for c in out[0]] == ["1", "2"]
    assert meta["rerank_parse_failed"] is True


def test_the_rerank_call_is_billed_to_the_ledger():
    """Cost is three separate measures and the reranker spends one of them.
    An arm that bought accuracy with calls nobody counted would be a free
    lunch on paper only."""
    llm = FakeLLM({"shortlists": [{"reaction": 0, "concepts": [0]}]})
    meta = {"api_calls": 0, "tokens_in": 0, "tokens_out": 0}
    rerank.rerank_llm([("x", menu(("1", "a")))], "post", llm,
                      {"rung0_rerank_k": 1}, meta)
    assert meta["api_calls"] == 1
    assert meta["tokens_in"] == 10 and meta["tokens_out"] == 5
    assert meta["rerank_calls"] == 1


def test_each_rerank_call_renumbers_its_reactions_from_zero():
    """Batching, with `_decide`'s rule: the reaction number is scoped to the
    call it appears in."""
    llm = FakeLLM({"shortlists": [{"reaction": 0, "concepts": [1]}]},
                  {"shortlists": [{"reaction": 0, "concepts": [1]}]})
    pairs = [("a", menu(("1", "p"), ("2", "q"))),
             ("b", menu(("3", "r"), ("4", "s")))]
    out, meta = rerank.rerank_llm(pairs, "post", llm,
                                  {"rung0_rerank_k": 2, "rung0_rerank_batch": 1},
                                  {})
    assert [c["code"] for c in out[0]] == ["2", "1"]
    assert [c["code"] for c in out[1]] == ["4", "3"]
    assert meta["rerank_calls"] == 2
    assert 'reaction 0:' in llm.prompts[1] and 'reaction 1:' not in llm.prompts[1]


# --- 4. wired into rung 0 -----------------------------------------------------


class DeepDense(FakeDense):
    """Records the k it was asked for — the arm's whole claim is that
    retrieval goes DEEPER than the menu the pick sees."""

    def __init__(self):
        self.asked = []

    def search(self, query, k=20):
        self.asked.append(k)
        return [{"i": n, "code": c, "label": l, "fsn": l, "score": 0.9 - 0.01 * n,
                 "via": "dense"}
                for n, (c, l) in enumerate(
                    [("271782001", "able to sleep"), ("12063002", "insomnia")])]


def _find(*quotes):
    return {"mentions": [
        {"span_text": q, "context": "", "negated": False, "confidence": 0.9}
        for q in quotes
    ]}


def test_the_arm_retrieves_deep_and_hands_the_pick_a_short_menu(reg):  # noqa: F811
    dense = DeepDense()
    llm = FakeLLM(_find("extreme rectal bleed"),
                  {"picks": [{"reaction": 0, "choice": 0}]})
    recs, _ = r0.apply([], SOURCES, cfg(reg, "S2", llm=llm, dense=dense,
                                        rung0_rerank="polarity",
                                        rung0_rerank_deep=50,
                                        rung0_rerank_k=15))
    assert dense.asked == [50]
    assert recs[0].checks["rung0_rerank"] == "polarity"


def test_rung_0_is_unchanged_when_the_arm_is_off(reg):  # noqa: F811
    dense = DeepDense()
    llm = FakeLLM(_find("extreme rectal bleed"),
                  {"picks": [{"reaction": 0, "choice": 0}]})
    recs, _ = r0.apply([], SOURCES, cfg(reg, "S2", llm=llm, dense=dense))
    assert dense.asked == [20]
    assert "rung0_rerank" not in recs[0].checks


def test_the_default_is_off():
    """`manifest.json` is append-only and edited jointly; an arm that
    defaulted on would change every rung above 0 without a manifest diff."""
    assert r0.DEFAULTS["rung0_rerank"] is None
    man = json.load(open("manifest.json"))
    assert "rung0_rerank" not in man["rungs"]["0"]


def test_a_denied_reaction_is_marked_for_the_reranker_too():
    """The pick had to be told, or it reasoned "they did not have it, no
    concept applies" and declined every denied gold mention it was given
    (measured, first negation run). The reranker reads the same menus and
    would make the same mistake."""
    llm = FakeLLM({"shortlists": [{"reaction": 0, "concepts": [0]}]})
    rerank.rerank_llm([("nausea", menu(("1", "a")), True)], "post", llm,
                      {"rung0_rerank_k": 1}, {})
    assert "[denied]" in llm.prompts[0]


def test_the_denial_marker_never_reaches_the_polarity_cue():
    """A `[denied]` marker in the span text would trip the negation cue and
    invert the very concept the pick is being asked to code."""
    cands = menu(("1", "able to sleep"), ("2", "insomnia"))
    out, _ = rerank.rerank_menu("sleepiness", cands,
                                {"rung0_rerank": "polarity"}, {}, denied=True)
    assert [c["code"] for c in out] == ["1", "2"]

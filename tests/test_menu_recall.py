"""The offline menu-recall probe — B2's stop condition.

WHY THIS EXISTS: B2 asks whether a domain-adapted encoder puts gold on S2's
menu more often than `granite-embedding:30m` does. That question is answerable
without a single model call, and the probe that answers it produces an article
number, so it is production code with tests rather than a harness script.

The tests pin the three things a recall number can be silently wrong about:
the DENOMINATOR (which mentions count), the RANK (off-by-one at the k cut) and
the HIT RULE (which of a multi-code mention's answers count).
"""

from __future__ import annotations

import pytest

from ladder.corpus import GOLD_NONE, GoldMention
from ladder.menurecall import (
    paired_recall_bootstrap,
    probe,
    rank_of_gold,
    recall_at,
    scorable_gold,
)


def _m(doc_id, index, entity_type, sct, gold_kind="single", text="rash"):
    return GoldMention(
        doc_id=doc_id, index=index, entity_type=entity_type, cadec_type="ADR",
        text=text, spans=[(0, len(text))], sct=list(sct), gold_kind=gold_kind,
    )


# --- the denominator ---------------------------------------------------------


def test_scorable_gold_keeps_only_coded_reactions_outside_the_exclusions():
    mentions = [
        _m("D", 0, "reaction", ["1"]),                       # kept
        _m("D", 1, "drug", ["2"]),                           # a drug
        _m("D", 2, "reaction", [], gold_kind=GOLD_NONE),     # concept_less
        _m("D", 3, "reaction", ["4"]),                       # excluded
    ]
    got = scorable_gold(mentions, exclusions={"D#3"})
    assert [m.record_id for m in got] == ["D#0"]


def test_scorable_gold_counts_a_multi_code_mention_once():
    mentions = [_m("D", 0, "reaction", ["1", "2"], gold_kind="all_of")]
    assert len(scorable_gold(mentions, exclusions=set())) == 1


# --- the rank ----------------------------------------------------------------


def test_rank_of_gold_is_zero_based_and_takes_the_first_hit():
    hits = [{"code": "9"}, {"code": "1"}, {"code": "1"}]
    assert rank_of_gold(hits, {"1"}) == 1


def test_rank_of_gold_is_none_when_the_menu_misses():
    assert rank_of_gold([{"code": "9"}], {"1"}) is None


def test_rank_of_gold_hits_on_any_gold_code_of_a_multi_code_mention():
    # ANY, not ALL: the menu's job is to make the right answer reachable, and
    # an all_of mention is reachable as soon as one of its codes is on it.
    assert rank_of_gold([{"code": "2"}], {"1", "2"}) == 0


# --- the k cut ---------------------------------------------------------------


def test_recall_at_k_includes_rank_k_minus_one_and_excludes_rank_k():
    # The off-by-one that would inflate every number in the table.
    assert recall_at([0], [1], n=1)[1] == 1.0
    assert recall_at([1], [1], n=1)[1] == 0.0
    assert recall_at([19], [20], n=1)[20] == 1.0
    assert recall_at([20], [20], n=1)[20] == 0.0


def test_recall_at_keeps_misses_in_the_denominator():
    # ranks carries one hit; n says there were four mentions.
    assert recall_at([0], [20], n=4)[20] == 0.25


def test_recall_at_refuses_a_denominator_smaller_than_the_hits():
    with pytest.raises(ValueError):
        recall_at([0, 1], [20], n=1)


# --- the probe ---------------------------------------------------------------


class _FakeIndex:
    """Returns a fixed menu per query text, and counts the searches."""

    def __init__(self, menus):
        self.menus, self.calls = menus, []

    def search(self, text, k=20):
        self.calls.append(text)
        return [{"i": i, "code": c} for i, c in enumerate(self.menus[text][:k])]


def test_probe_reports_recall_over_every_mention_and_dedupes_the_queries():
    idx = _FakeIndex({"rash": ["1", "8"], "ache": ["7"]})
    mentions = [
        _m("D", 0, "reaction", ["1"], text="rash"),
        _m("D", 1, "reaction", ["1"], text="rash"),   # same query, same answer
        _m("D", 2, "reaction", ["5"], text="ache"),   # a miss
    ]
    got = probe(idx, mentions, ks=[1, 20])
    assert got["n"] == 3
    assert got["recall"][1] == pytest.approx(2 / 3)
    assert got["recall"][20] == pytest.approx(2 / 3)
    # Two distinct query strings, so two searches for three mentions.
    assert sorted(idx.calls) == ["ache", "rash"]


def test_probe_dedupe_cannot_merge_two_mentions_with_different_gold():
    # Same text, different answers: dedupe is on the QUERY, never on the pair.
    idx = _FakeIndex({"rash": ["1", "8"]})
    mentions = [
        _m("D", 0, "reaction", ["1"], text="rash"),
        _m("D", 1, "reaction", ["8"], text="rash"),
    ]
    got = probe(idx, mentions, ks=[1, 20])
    assert got["recall"][1] == pytest.approx(0.5)
    assert got["recall"][20] == pytest.approx(1.0)


# --- the paired comparison ---------------------------------------------------


def test_probe_reports_the_rank_of_every_record_including_the_misses():
    idx = _FakeIndex({"rash": ["1"], "ache": ["7"]})
    mentions = [
        _m("D", 0, "reaction", ["1"], text="rash"),
        _m("D", 1, "reaction", ["5"], text="ache"),
    ]
    got = probe(idx, mentions, ks=[1])
    assert got["by_record"] == {"D#0": 0, "D#1": None}


def test_paired_recall_bootstrap_point_is_the_observed_delta_at_k():
    # A beats B on one of four mentions: +0.25 at k=20.
    a = {"D#0": 0, "D#1": 0, "E#0": 19, "E#1": None}
    b = {"D#0": 0, "D#1": 0, "E#0": None, "E#1": None}
    mentions = [_m("D", 0, "reaction", ["1"]), _m("D", 1, "reaction", ["1"]),
                _m("E", 0, "reaction", ["1"]), _m("E", 1, "reaction", ["1"])]
    got = paired_recall_bootstrap(a, b, mentions, k=20, n_boot=200, seed=0)
    assert got["point"] == pytest.approx(0.25)
    assert got["lo"] <= got["point"] <= got["hi"]


def test_paired_recall_bootstrap_resamples_documents_not_mentions():
    # UNEQUAL documents, which is what separates the two resampling units.
    # D holds one mention and no gain; E holds three and all of the gain.
    # Over DOCUMENTS a draw is (D,D), (D,E) or (E,E) -> deltas 0, 0.75, 1.0 at
    # probabilities .25/.5/.25, so the mean is 0.625. Over MENTIONS the delta
    # is (gains drawn)/4 and the mean is 0.75. The mean is the discriminator;
    # lo/hi alone cannot tell the two units apart here.
    a = {"D#0": None, "E#0": 19, "E#1": 19, "E#2": 19}
    b = {"D#0": None, "E#0": None, "E#1": None, "E#2": None}
    mentions = [_m("D", 0, "reaction", ["1"]), _m("E", 0, "reaction", ["1"]),
                _m("E", 1, "reaction", ["1"]), _m("E", 2, "reaction", ["1"])]
    got = paired_recall_bootstrap(a, b, mentions, k=20, n_boot=2000, seed=0)
    assert got["docs"] == 2
    assert got["point"] == pytest.approx(0.75)
    assert got["mean"] == pytest.approx(0.625, abs=0.03)
    assert {round(got["lo"], 4), round(got["hi"], 4)} <= {0.0, 0.75, 1.0}


def test_paired_recall_bootstrap_cuts_at_rank_k_minus_one():
    # The off-by-one, on the paired path this time: rank 20 is the 21st slot
    # and is OUTSIDE the top 20. MUT B survived until this test existed.
    mentions = [_m("D", 0, "reaction", ["1"])]
    b = {"D#0": None}
    inside = paired_recall_bootstrap({"D#0": 19}, b, mentions, k=20, n_boot=10)
    outside = paired_recall_bootstrap({"D#0": 20}, b, mentions, k=20, n_boot=10)
    assert inside["point"] == pytest.approx(1.0)
    assert outside["point"] == pytest.approx(0.0)


def test_paired_recall_bootstrap_is_deterministic_under_a_seed():
    a = {"D#0": 0, "E#0": 19}
    b = {"D#0": 0, "E#0": None}
    mentions = [_m("D", 0, "reaction", ["1"]), _m("E", 0, "reaction", ["1"])]
    kw = dict(k=20, n_boot=200, seed=7)
    assert paired_recall_bootstrap(a, b, mentions, **kw) == paired_recall_bootstrap(
        a, b, mentions, **kw
    )


def test_paired_recall_bootstrap_refuses_arms_scored_on_different_mentions():
    # Two arms that did not answer the same questions cannot be paired.
    a, b = {"D#0": 0}, {"D#1": 0}
    mentions = [_m("D", 0, "reaction", ["1"]), _m("D", 1, "reaction", ["1"])]
    with pytest.raises(ValueError):
        paired_recall_bootstrap(a, b, mentions, k=20, n_boot=10, seed=0)

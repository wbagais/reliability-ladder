"""The coordination splitter — ladder/split.py.

Gold shape, measured on the pool split: a coordination is annotated as
SEVERAL mentions sharing a head, each with discontinuous spans. Rung 0 emits
one contiguous quote and loses all of them (dev 2026-08-27: 0 of 233
predictions discontinuous against 39 of 226 gold).
"""

from ladder.split import split_coordination


def _texts(text, groups):
    return [" … ".join(text[a:b] for a, b in g) for g in groups]


def test_head_final_coordination_shares_the_trailing_head():
    """"muscle and joint pain" is two mentions in gold, not one, and they
    carry DIFFERENT codes (68962001 vs 57676002)."""
    t = "muscle and joint pain"
    got = split_coordination(t, (0, len(t)))
    assert _texts(t, got) == ["muscle … pain", "joint … pain"]


def test_head_initial_coordination_shares_the_leading_head():
    t = "pain in hips and legs"
    got = split_coordination(t, (0, len(t)))
    assert _texts(t, got) == ["pain in … hips", "pain in … legs"]


def test_a_comma_list_yields_one_mention_per_item():
    t = "swelling of face, wrists and thighs"
    got = split_coordination(t, (0, len(t)))
    assert _texts(t, got) == [
        "swelling of … face", "swelling of … wrists", "swelling of … thighs"
    ]


def test_offsets_are_returned_in_the_documents_coordinate_space():
    """The splitter is handed a located span, so it must offset from it —
    returning span-relative positions would unground every split record."""
    t = "muscle and joint pain"
    got = split_coordination(t, (100, 100 + len(t)))
    assert got[0] == [(100, 106), (117, 121)]


def test_a_phrase_with_no_coordinator_is_left_alone():
    for t in ("rectal bleed", "severe muscle pain", "headaches"):
        assert split_coordination(t, (0, len(t))) == []


def test_a_coordination_with_no_shared_head_is_left_alone():
    """"nausea and vomiting" is two whole reactions, not one head shared two
    ways. Splitting it would invent a discontinuity gold does not have — and
    the two contiguous mentions are FIND's job, not the splitter's."""
    t = "nausea and vomiting"
    assert split_coordination(t, (0, len(t))) == []


def test_filler_words_do_not_count_as_a_head():
    """"pain in my legs and my arms" — "my" must not become the shared head."""
    t = "pain in my legs and my arms"
    got = split_coordination(t, (0, len(t)))
    assert _texts(t, got) == ["pain in … my legs", "pain in … my arms"]


# --- wired into rung 0 --------------------------------------------------------
#
# BEFORE retrieval, so each half gets its own menu and its own pick: gold gives
# "muscle … pain" and "joint … pain" different codes, and a split applied after
# the pick would copy one code onto both.

import json  # noqa: E402

from ladder.rungs import r0  # noqa: E402
from tests.test_registry_lookup import reg  # noqa: F401,E402  (fixture)
from tests.test_rung0_steps import FakeDense, FakeLLM, cfg  # noqa: E402

SRC = {"D1": "I get terrible muscle and joint pain every day.\n"}
FIND1 = {"mentions": [{"span_text": "muscle and joint pain", "context": "terrible",
                       "negated": False, "confidence": 0.9}]}


class TwoDense(FakeDense):
    def search(self, query, k=20):
        code = "68962001" if "muscle" in query.lower() else "57676002"
        label = "muscle pain" if code == "68962001" else "joint pain"
        return [{"i": 0, "code": code, "label": label, "fsn": label,
                 "via": "dense", "score": 0.9}]


def test_rung_0_splits_a_coordination_into_discontinuous_records(reg):  # noqa: F811
    llm = FakeLLM(FIND1, {"picks": [{"reaction": 0, "choice": 0},
                                    {"reaction": 1, "choice": 0}]})
    recs, agg = r0.apply(
        [], SRC, cfg(reg, "S2", llm=llm, dense=TwoDense(), rung0_split=True),
    )
    assert len(recs) == 2
    assert all(len(r.spans) == 2 for r in recs), "both records are discontinuous"
    assert agg["split"] == 1, "one quote became two mentions"


def test_each_split_half_is_retrieved_and_coded_separately(reg):  # noqa: F811
    """The whole reason the split precedes retrieval."""
    llm = FakeLLM(FIND1, {"picks": [{"reaction": 0, "choice": 0},
                                    {"reaction": 1, "choice": 0}]})
    recs, _ = r0.apply(
        [], SRC, cfg(reg, "S2", llm=llm, dense=TwoDense(), rung0_split=True),
    )
    assert sorted(r.sct for r in recs) == ["57676002", "68962001"]


def test_the_original_quote_survives_on_every_split_record(reg):  # noqa: F811
    """Same posture as span_untrimmed: the transformation is auditable and
    the untransformed number recomputable from disk."""
    llm = FakeLLM(FIND1, {"picks": [{"reaction": 0, "choice": 0},
                                    {"reaction": 1, "choice": 0}]})
    recs, _ = r0.apply(
        [], SRC, cfg(reg, "S2", llm=llm, dense=TwoDense(), rung0_split=True),
    )
    assert all(r.checks["split_from"] == "muscle and joint pain" for r in recs)


def test_the_split_is_off_by_default(reg):  # noqa: F811
    """A declared arm, like every other rung 0 choice."""
    llm = FakeLLM(FIND1, {"picks": [{"reaction": 0, "choice": 0}]})
    recs, _ = r0.apply([], SRC, cfg(reg, "S2", llm=llm, dense=TwoDense()))
    assert len(recs) == 1 and len(recs[0].spans) == 1

"""The span trimmer — Phase B(d), 2026-08-25.

Measured on the enhanced S2 dev run: detection F1 is 0.429 exact against
0.765 overlap — 34 points of pure boundary convention. The model finds the
mention and quotes MORE of the sentence than gold keeps ("extreme rectal
bleed" where gold says "rectal bleed" is the canonical case, but articles,
possessives and verbs are the volume).

The trimmer LEARNS the convention instead of hand-writing it, because the
hand-written rule was already tried and rejected — gold KEEPS a leading
intensifier 3x more often than it drops one (2026-08-25), so "trim the
intensifier" breaks more than it fixes. The learning signal is the corpus's
own boundary behaviour: for each token, how often does gold leave it
immediately OUTSIDE a span versus keep it as the span's FIRST (or LAST)
token? A token gold near-always leaves outside is trimmable; "severe" is not.

POOL ONLY. Rules learned from dev or test gold would tune the measurement on
itself; pool is disjoint from both by construction and is never scored. The
same wall as rung0_fewshot_docs, enforced the same way.
"""

import pytest

from ladder.trim import SpanTrimmer, boundary_counts


def d(text, *mentions):
    """(text, spans) with the spans located by search — offsets by hand are
    how the corpus's own 4 quoted-text exclusions happened."""
    spans = []
    for m in mentions:
        i = text.index(m)
        spans.append((i, i + len(m)))
    return (text, spans)


# A synthetic corpus with an unambiguous convention: "my"/"the" always sit
# outside the span, "severe" is kept inside, "." always trails outside.
DOCS = [
    d("I got my headache.", "headache"),
    d("my nausea would not stop.", "nausea"),
    d("the cramps came back. my fatigue too.", "cramps", "fatigue"),
    d("the severe leg pain was awful.", "severe leg pain"),
    d("felt the dizziness.", "dizziness"),
]


@pytest.fixture()
def trimmer():
    return SpanTrimmer.learn(DOCS, min_evidence=2, outside_ratio=0.9)


def test_boundary_counts_separate_outside_from_first():
    counts = boundary_counts(DOCS)
    assert counts["before"]["my"] == 3
    assert counts["first"].get("my", 0) == 0
    assert counts["first"]["severe"] == 1
    assert counts["after"]["."] == 2
    assert counts["last"].get(".", 0) == 0


def test_learns_that_articles_lead_outside_the_span(trimmer):
    assert "my" in trimmer.lead_drop
    assert "the" in trimmer.lead_drop


def test_does_not_learn_to_trim_what_gold_keeps(trimmer):
    """"severe" opens a gold span — the intensifier rejection, now learned
    from data instead of legislated."""
    assert "severe" not in trimmer.lead_drop


def test_trailing_sentence_punctuation_is_trimmable(trimmer):
    assert "." in trimmer.trail_drop


def test_trim_drops_a_leading_learned_token(trimmer):
    text, (start, end) = trimmer.trim("my headache", (100, 111))
    assert text == "headache"
    assert (start, end) == (103, 111)


def test_trim_walks_multiple_leading_tokens(trimmer):
    text, (start, end) = trimmer.trim("the my headache", (0, 15))
    assert text == "headache"
    assert (start, end) == (7, 15)


def test_trim_drops_a_trailing_learned_token(trimmer):
    text, (start, end) = trimmer.trim("headache.", (20, 29))
    assert text == "headache"
    assert (start, end) == (20, 28)


def test_trim_keeps_kept_conventions(trimmer):
    text, span = trimmer.trim("severe leg pain", (10, 25))
    assert text == "severe leg pain"
    assert span == (10, 25)


def test_trim_never_empties_a_span(trimmer):
    """A span that is all trimmable tokens is left alone — an empty mention
    is not a boundary correction."""
    text, span = trimmer.trim("my the", (5, 11))
    assert text == "my the"
    assert span == (5, 11)


def test_trim_is_a_noop_below_the_evidence_floor():
    """One sighting is an anecdote, not a convention."""
    t = SpanTrimmer.learn(DOCS[:1], min_evidence=5, outside_ratio=0.9)
    assert t.trim("my headache", (0, 11)) == ("my headache", (0, 11))


def test_pool_trimmer_refuses_non_pool_learning():
    """Same wall as rung0_fewshot_docs: rules learned from a scored split
    would tune the measurement on itself."""
    from ladder.trim import pool_trimmer

    with pytest.raises(ValueError, match="pool"):
        pool_trimmer({"corpus": {"splits_dir": "data/splits",
                                 "cadec_root": "unused"}},
                     split="dev", loader=lambda root: {})


# --- the interior clause cut -------------------------------------------------
#
# Measured on the baseline dev records before wiring: 46 of the 70 boundary
# mismatches are pred ⊃ gold, and the volume is trailing CLAUSES ("pain that
# wakes me up", "neck pain while turning head"), which no edge-token rule
# reaches. The signal is interior: inside_rate(w) = occurrences of w inside
# pool gold spans / all occurrences of w in pool text. Tokens gold near-never
# keeps inside a span ("that", "when", drug names, dosages) mark where the
# span should stop. Thresholds are deliberately tight — the looser sweep
# points bought exact F1 by damaging overlap and were rejected.

CUT_DOCS = [
    d("headache that would not stop that day.", "headache"),
    d("nausea that came back when I walked.", "nausea"),
    d("the cramps hurt when I sat.", "cramps"),
]


@pytest.fixture()
def cut_trimmer():
    return SpanTrimmer.learn(CUT_DOCS, min_evidence=2, outside_ratio=0.9,
                             cut_min_total=2, cut_max_rate=0.0)


def test_learns_interior_cut_tokens(cut_trimmer):
    assert "that" in cut_trimmer.cut_drop
    assert "when" in cut_trimmer.cut_drop
    assert "headache" not in cut_trimmer.cut_drop


def test_cut_truncates_at_the_first_cut_token(cut_trimmer):
    text, span = cut_trimmer.trim("headache that would not stop", (10, 38))
    assert text == "headache"
    assert span == (10, 18)


def test_cut_never_fires_on_the_first_token(cut_trimmer):
    """A span STARTING with a cut token is not a clause tail — cutting at
    position 0 would empty it."""
    text, _ = cut_trimmer.trim("that headache", (0, 13))
    assert "headache" in text


def test_cut_and_edge_trim_compose(trimmer, cut_trimmer):
    t = SpanTrimmer(lead_drop=trimmer.lead_drop,
                    trail_drop=trimmer.trail_drop,
                    cut_drop=cut_trimmer.cut_drop)
    text, span = t.trim("my headache that would not stop", (0, 31))
    assert text == "headache"
    assert span == (3, 11)


def test_a_trimmer_without_cut_rules_still_works(trimmer):
    """cut_drop defaults empty — the edge-only trimmer is the same object."""
    text, span = trimmer.trim("headache that would not stop", (0, 28))
    assert text == "headache that would not stop"


# --- the interior cut, and what the splitter makes safe (2026-08-27) ----------
#
# The cut threshold was frozen at inside_rate <= 0.02 over >= 50 sightings on
# the Phase B measurement, where looser points bought exact F1 by cutting
# spans out of their overlap matches. Measured on pool 2026-08-27, the tokens
# that open the trailing clauses rung 0 still keeps sit just ABOVE it:
#
#     so 0.053   with 0.054   has 0.043   while 0.030   went 0.025   and 0.049
#
# One of those is not like the others. Cutting at "and" truncates a
# COORDINATION, which since ladder/split.py is a mention boundary rather than
# a clause boundary — so a looser rate is only safe if coordinators are held
# out of the cut set explicitly.


def test_coordinators_are_never_cut_tokens_however_loose_the_rate():
    """"muscle and joint pain" must reach the splitter whole."""
    docs = [("muscle and joint pain " * 60, [])]
    t = SpanTrimmer.learn(docs, cut_min_total=1, cut_max_rate=1.0)
    for w in ("and", "or", ",", "&"):
        assert w not in t.cut_drop


def test_the_cut_rate_is_configurable_and_defaults_to_the_frozen_value():
    """The frozen value stays the default; the arm moves it. "so" sits at
    inside_rate 0.05 on pool — above 0.02, below 0.055."""
    from ladder import trim

    assert trim.DEFAULT_CUT_MAX_RATE == 0.02
    # 60 occurrences of "so", 3 of them inside a gold span -> rate 0.05
    text = ("so ache. " * 3) + ("pain so bad. " * 57)
    spans = [(m, m + 2) for m in range(0, 27, 9)]
    docs = [(text, spans)]
    assert "so" in SpanTrimmer.learn(docs, cut_min_total=10, cut_max_rate=0.055).cut_drop
    assert "so" not in SpanTrimmer.learn(docs, cut_min_total=10, cut_max_rate=0.02).cut_drop


def test_pool_trimmer_passes_the_thresholds_through(monkeypatch):
    """The arm has to reach the rules, or the manifest setting is decoration."""
    from ladder import trim
    from ladder.corpus import Document

    seen = {}
    real = SpanTrimmer.learn

    def spy(docs, **kw):
        seen.update(kw)
        return real(docs, **kw)

    monkeypatch.setattr(trim.SpanTrimmer, "learn", staticmethod(spy))

    class AnyDoc(dict):
        def __getitem__(self, k):
            return Document(doc_id=k, drug_group="X", text="pain", mentions=[])

    man = {"corpus": {"splits_dir": "data/splits", "cadec_root": "unused"}}
    trim.pool_trimmer(man, loader=lambda root: AnyDoc(), cut_max_rate=0.055)
    assert seen["cut_max_rate"] == 0.055

"""Tests for ladder.checks.gate — the ceiling, and every threshold both ways.

WHAT THESE PIN DOWN

`gatecheck`'s value is one number: the most the free check could endorse on a
corpus, computed from gold with no model. It was validated against five arms
that were later run on a rented card —

    FiNER      predicted 0.0%    measured 0.0% on four models
    LINNAEUS   predicted 4.8%    measured 12.5% on one, 0 on three
    PsyTAR     predicted 24.3%   measured 18.6-31.0%
    BC5CDR     predicted 35.8%   measured 7.0-21.8%
    geo        predicted 40.9%   measured 20.3-63.6%

— and every measured value sits at or below its prediction, which is what a
ceiling must do. These tests hold the arithmetic that produces it, and exercise
each drafting threshold on both sides of its boundary. A threshold that is never
crossed in a test is a number nobody has checked.
"""
from __future__ import annotations

import pathlib
import sys
import types

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from ladder.checks import Arm
from ladder.checks import gate

from test_crosscheck import Doc, Mention, Vocab, arm   # noqa: E402


class Terms:
    """A vocabulary whose names are given per code, so a test can construct an
    exact overlap stratum."""
    def __init__(self, mapping):
        self.mapping = mapping

    def exists(self, c):
        return str(c) in self.mapping

    def terms(self, c):
        return self.mapping.get(str(c), [])


def corpus(pairs):
    """pairs: (surface form, canonical name). One document, one mention each."""
    docs, mapping = {}, {}
    mentions = []
    for i, (text, name) in enumerate(pairs):
        code = str(i)
        mapping[code] = [name]
        mentions.append(Mention(text, [code]))
    docs["D"] = Doc(mentions)
    return arm(docs=docs, registry=Terms(mapping))


# ── the stratum, and the ceiling that follows ────────────────────────
def test_identical_surface_and_name_is_the_ceiling():
    p = gate.profile(corpus([("Tremor", "Tremor"), ("Nausea", "Nausea")]))
    assert p["lane_ceiling"] == 1.0
    assert p["strata"]["identical"] == 1.0


def test_no_shared_token_is_a_zero_ceiling():
    """FiNER: the spans are numerals and the tags are English phrases, so the
    two share no token by construction — on any run, with any model, forever."""
    p = gate.profile(corpus([("47.6", "EffectiveIncomeTaxRate"),
                             ("19.5", "Revenues")]))
    assert p["lane_ceiling"] == 0.0
    assert p["strata"]["none"] == 1.0


def test_vernacular_against_latin_is_no_overlap():
    """LINNAEUS: 'mice' shares nothing with 'Mus musculus', and no model can
    fix that — it is a property of the vocabulary against the corpus."""
    p = gate.profile(corpus([("mice", "Mus musculus"), ("yeast", "Saccharomyces")]))
    assert p["lane_ceiling"] == 0.0
    assert len(p["no_overlap_examples"]) == 2


def test_subset_and_partial_are_not_the_ceiling():
    """Only IDENTICAL counts. A span contained in a longer name has not been
    endorsed by an exact check."""
    p = gate.profile(corpus([("Tremor", "Tremor"),
                             ("bone", "low bone turnover"),
                             ("renal pain", "renal failure")]))
    assert p["lane_ceiling"] == pytest.approx(1 / 3)
    assert p["strata"]["subset"] == pytest.approx(1 / 3)
    assert p["strata"]["partial"] == pytest.approx(1 / 3)


def test_codes_absent_from_the_vocabulary_leave_the_denominator():
    """An id the index does not hold is a record outside the denominator, not a
    wrong answer. PsyTAR maps to SNOMEDCT_US against an AU index and 0.1% were
    absent; folding those in would have made it look worse for a reason
    unrelated to the check."""
    a = corpus([("Tremor", "Tremor")])
    a.docs["D"].mentions.append(Mention("ghost", ["nope"]))
    p = gate.profile(a)
    assert p["vocab_absent"] == pytest.approx(0.5)
    assert p["lane_ceiling"] == 1.0        # over the USABLE half, not all of it


def test_no_vocabulary_means_no_ceiling_at_all():
    """The CLI refuses in this case rather than printing a profile that reads
    like a complete assessment."""
    p = gate.profile(arm(registry=None))
    assert "lane_ceiling" not in p


# ── the profile's own measurements ───────────────────────────────────
def test_multi_token_and_capitalisation_are_counted():
    a = corpus([("weight gain", "x"), ("Tremor", "y"), ("nausea", "z")])
    p = gate.profile(a)
    assert p["multi_token"] == pytest.approx(1 / 3)
    assert p["capitalised"] == pytest.approx(1 / 3)


def test_repeats_are_counted_as_a_share_of_mentions():
    a = corpus([("nausea", "x"), ("nausea", "y"), ("tremor", "z")])
    assert gate.profile(a)["repeated"] == pytest.approx(2 / 3)


# ── every drafting threshold, both sides ─────────────────────────────
def base(**over):
    p = {"multi_token": 0.2, "dotted": 0.0, "capitalised": 0.7,
         "leading_article": 0.0, "discontinuous": 0.0, "repeated": 0.1,
         "commonest": ["a", "b", "c", "d", "e"], "multi_examples": ["a b"],
         "len_median": 8, "len_p95": 14}
    p.update(over)
    return p


def test_phrase_rule_fires_only_above_its_threshold():
    assert "A PHRASE" in gate.draft_rules(base(multi_token=0.40), "disease")
    assert "A PHRASE" not in gate.draft_rules(base(multi_token=0.30), "disease")


def test_single_word_rule_fires_only_below_its_threshold():
    assert "SINGLE WORD" in gate.draft_rules(base(multi_token=0.10), "place")
    assert "SINGLE WORD" not in gate.draft_rules(base(multi_token=0.20), "place")


def test_case_rule_flips_at_both_ends():
    """LINNAEUS is 34.3% capitalised and LGL is 100%. The same measurement
    produces opposite advice, which is the point of measuring it."""
    assert "NOT A CUE" in gate.draft_rules(base(capitalised=0.34), "organism")
    assert "NOT A CUE" not in gate.draft_rules(base(capitalised=0.70), "organism")
    assert "capitalised" in gate.draft_rules(base(capitalised=0.99), "place")


def test_abbreviation_rule_fires_on_dotted_forms():
    """LINNAEUS is 18.0% dotted — 'C. elegans', 'E. coli' — five times the geo
    rate."""
    assert "ABBREVIATED" in gate.draft_rules(base(dotted=0.18), "organism")
    assert "ABBREVIATED" not in gate.draft_rules(base(dotted=0.03), "place")


def test_repeat_rule_fires_when_forms_recur():
    assert "EVERY TIME" in gate.draft_rules(base(repeated=0.87), "place")
    assert "EVERY TIME" not in gate.draft_rules(base(repeated=0.10), "place")


def test_discontinuous_rule_fires_on_split_mentions():
    """PsyTAR is 6.5% discontinuous; the geo corpora are 0%."""
    assert "TWO PIECES" in gate.draft_rules(base(discontinuous=0.065), "reaction")
    assert "TWO PIECES" not in gate.draft_rules(base(discontinuous=0.0), "reaction")


def test_no_overlap_examples_raise_a_review_flag_and_not_a_rule():
    """The tool shows the pattern and refuses to write the rule. 'mice' ->
    'Mus musculus' needs a judgement about what the corpus means."""
    rules = gate.draft_rules(
        base(no_overlap_examples=[("mice", "Mus musculus")]), "organism")
    assert "[REVIEW]" in rules and "mice" in rules


# ── what it will not decide ──────────────────────────────────────────
def test_a_thin_ceiling_needs_a_signature():
    """FiNER's zero is structural and LINNAEUS's 4.8% was a build choice. From
    here they look identical, and guessing would invent the more interesting
    of two answers."""
    out = gate.unsigned(arm(), {"lane_ceiling": 0.048}, "")
    assert any("FINDING or a BUG" in u for u in out)


def test_an_undeclared_entity_needs_a_signature():
    assert any("what IS this corpus about" in u
               for u in gate.unsigned(arm(), {"lane_ceiling": 0.5}, ""))


def test_an_adapter_with_several_types_needs_a_signature():
    a = arm(mod=types.SimpleNamespace(TYPES=("Chemical", "Disease")))
    assert any("which entity type to score" in u
               for u in gate.unsigned(a, {"lane_ceiling": 0.5}, ""))


def test_a_review_flag_needs_a_signature():
    assert any("no-overlap rule" in u
               for u in gate.unsigned(arm(), {"lane_ceiling": 0.5}, "[REVIEW] x"))


# ── the sniffable declarations ───────────────────────────────────────
def test_gate_codes_come_from_this_corpus_gold():
    """Not from CADEC's. A gate on another vocabulary's codes passes or fails
    for reasons unrelated to the arm it is guarding."""
    s = gate.sniffable(corpus([("Tremor", "Tremor")]))
    assert s["vocabulary.gate.real"] == "0"
    assert s["vocabulary.gate.fake"] != s["vocabulary.gate.real"]


def test_split_sizes_scale_to_a_small_corpus():
    """LINNAEUS has 95 documents and the inherited 40+60 left no pool. The
    sizes are read off the corpus rather than inherited."""
    small = arm(docs={f"D{i}": Doc([Mention("x", ["111"])]) for i in range(95)})
    s = gate.sniffable(small)
    assert s["corpus.n_dev_docs"] + s["corpus.n_test_docs"] < 95

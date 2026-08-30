"""Three span filters, all learned or checkable WITHOUT gold.

Measured on dev 2026-08-28, stacked, against the four-fix arm: exact F1
0.386 -> 0.399, paired bootstrap +0.0133 [+0.0033, +0.0214]. Each is cheap
and none of them can invent a mention — they only decline to emit one.
"""

import json

import pytest

from ladder.rungs import r0
from tests.test_registry_lookup import reg  # noqa: F401  (fixture)
from tests.test_rung0_steps import SOURCES, FakeDense, FakeLLM, cfg


class Dense(FakeDense):
    def search(self, query, k=20):  # pragma: no cover - shape only
        return [{"i": 0, "code": "12063002", "label": "rectal bleeding",
                 "fsn": "rectal bleeding", "via": "dense", "score": 0.9}]


def _find(*quotes):
    return {"mentions": [
        {"span_text": q, "context": "", "negated": False, "confidence": 0.9}
        for q in quotes
    ]}


def _run(reg, *quotes, **kw):  # noqa: F811
    llm = FakeLLM(_find(*quotes),
                  {"picks": [{"reaction": i, "choice": 0} for i in range(len(quotes))]})
    return r0.apply([], SOURCES, cfg(reg, "S2", llm=llm, dense=Dense(), **kw))


# --- 1. the quote is not in the post -----------------------------------------


def test_a_quote_that_is_not_in_the_post_is_not_emitted(reg):  # noqa: F811
    """`locate()` returns (-1, -1) when the model paraphrased instead of
    quoting. Measured on dev: 11 such records, 0 of them matched any gold
    mention — they are false positives by construction, and the check needs
    no answer key, only the post."""
    recs, agg = _run(reg, "extreme rectal bleed", "a phrase never written",
                     rung0_drop_ungrounded=True)
    assert [r.text for r in recs] == ["extreme rectal bleed"]
    assert agg["dropped_ungrounded"] == 1


def test_ungrounded_spans_are_kept_when_the_filter_is_off(reg):  # noqa: F811
    """Default OFF: it changes what rung 0 emits, so it is a declared arm."""
    recs, _ = _run(reg, "extreme rectal bleed", "a phrase never written")
    assert len(recs) == 2
    assert recs[1].spans == [(-1, -1)]


# --- 2. function-word fragments ----------------------------------------------


def test_a_span_of_only_function_words_is_not_a_mention(reg):  # noqa: F811
    """'because', 'This', 'No' were emitted as reactions on dev. A span with
    no content word cannot name a clinical concept, whatever the menu says."""
    recs, agg = _run(reg, "extreme rectal bleed", "because",
                     rung0_drop_fragments=True)
    assert [r.text for r in recs] == ["extreme rectal bleed"]
    assert agg["dropped_fragment"] == 1


def test_a_single_content_word_is_kept(reg):  # noqa: F811
    """14 of 45 unproposed gold mentions on dev are single words ('sore',
    'painful', 'tingly'). The filter must never reach them."""
    recs, _ = _run(reg, "sick", rung0_drop_fragments=True)
    assert [r.text for r in recs] == ["sick"]


# --- 3. the same span twice ---------------------------------------------------


def test_the_same_span_is_emitted_once(reg):  # noqa: F811
    """Gold is claimed one-to-one, so a second record on the same characters
    can only ever be a false positive. NOT a merge of overlapping spans —
    that was measured and LOST (-0.008), because the coordination splitter
    emits several records sharing a head span BY DESIGN."""
    recs, agg = _run(reg, "extreme rectal bleed", "extreme rectal bleed",
                     rung0_drop_duplicate_spans=True)
    assert len(recs) == 1
    assert agg["dropped_duplicate"] == 1


def test_two_different_spans_are_both_kept(reg):  # noqa: F811
    recs, _ = _run(reg, "extreme rectal bleed", "extremely sick",
                   rung0_drop_duplicate_spans=True)
    assert len(recs) == 2


def test_the_splitter_output_survives_the_duplicate_filter(reg):  # noqa: F811
    """The splitter's records are discontinuous and distinct; only an exact
    span-key repeat is a duplicate."""
    from ladder.schema import Record, REACTION

    a = Record(doc_id="D1", entity_type=REACTION, text="joint pain",
               spans=[(0, 5), (12, 16)], sct=None, sct_label=None, meddra=None,
               confidence=1.0, zone="NEW", reason=None, provenance=[], checks={})
    b = Record(doc_id="D1", entity_type=REACTION, text="muscle pain",
               spans=[(6, 11), (12, 16)], sct=None, sct_label=None, meddra=None,
               confidence=1.0, zone="NEW", reason=None, provenance=[], checks={})
    kept, counts = r0.filter_spans([a, b], {"rung0_drop_duplicate_spans": True})
    assert len(kept) == 2

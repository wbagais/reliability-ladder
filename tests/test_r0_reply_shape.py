"""Rung 0's tolerance of reply SHAPE, and the crash it used to cause
(2026-08-28, open-weight extractor comparison).

`llama3.1:8b` answers the FIND prompt with a bare JSON array of mention
objects instead of the requested {"mentions": [...]} wrapper. Two separate
faults fell out of that, and they need different treatment.

1. IT CRASHED THE RUN. `_step_pick` did `parsed.get("mentions", [])` on
   whatever `_parse` returned, so a list raised AttributeError and killed a
   40-document run on document 3. This repo's stated rule is that one bad
   document costs ONE RECORD, not the run — the same argument that made the
   call timeout return an empty response instead of raising. An unexpected
   reply SHAPE is exactly that case, and it must be counted as a parse
   failure for its document and nothing more.

2. THE SHAPE ITSELF. The content is unambiguously what was asked for; only
   the wrapper is missing. Refusing it would score formatting luck rather
   than capability, and the incumbent model emits the wrapper because the
   prompt was tuned against it. So a bare list of mention objects is
   accepted — and COUNTED in meta["shape_coerced"], so the accommodation
   appears in the results table as a per-model compliance cost.

WHERE THE LINE IS, stated so the parser does not keep loosening until every
model passes: we accept a reply whose CONTENT is unambiguously the requested
content, and we count every accommodation. We do not invent missing fields,
guess codes, or repair content. A bare list of mention objects qualifies; a
list of bare strings does not, because "which field is this" would be a
guess.
"""

import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from ladder.rungs import r0
from tests.test_registry_lookup import reg  # noqa: F401  (fixture)


def test_a_bare_list_of_mentions_is_accepted_and_counted():
    meta = {}
    got = r0._normalise_reply([{"span_text": "nausea", "negated": False}], meta)
    assert got == {"mentions": [{"span_text": "nausea", "negated": False}]}
    assert meta["shape_coerced"] is True, "the accommodation must be counted"


def test_the_requested_shape_is_untouched_and_not_counted():
    meta = {}
    payload = {"mentions": [{"span_text": "nausea"}]}
    assert r0._normalise_reply(payload, meta) == payload
    assert "shape_coerced" not in meta


def test_a_list_of_bare_strings_is_refused():
    """Content is NOT unambiguous — which field would 'nausea' be?"""
    meta = {}
    assert r0._normalise_reply(["nausea", "headache"], meta) is None


def test_an_empty_list_is_the_requested_shape_with_no_mentions():
    meta = {}
    assert r0._normalise_reply([], meta) == {"mentions": []}


def test_a_scalar_reply_is_refused_not_crashed():
    meta = {}
    assert r0._normalise_reply(42, meta) is None
    assert r0._normalise_reply("nausea", meta) is None


def test_an_unexpected_shape_costs_one_document_not_the_run(reg):  # noqa: F811
    """The regression that killed a 40-document sweep on document 3."""
    calls = {"n": 0}

    def llm(prompt, text, mode):
        calls["n"] += 1
        return ('["nausea", "headache"]', {"in": 10, "out": 5})

    cfg = r0.prepare({"rung0_step": "S2", "llm": llm, "registry": reg})
    got, meta = r0.run_step("D1", "I had nausea", "S2", llm, cfg)

    assert got == [], "no records, because the reply could not be read"
    assert meta["parse_failed"] is True, "counted as a parse failure"
    assert calls["n"] == 1, "and NOT retried — a retry inside rung 0 is rung 2"

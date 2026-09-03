"""The guard that lets rung 2's prompt be slotted without moving CADEC.

`r2.PROMPT` is the string every published CADEC correction was produced with.
Slotting it introduces a way for that wording to change by accident, so the
constant is KEPT in the file and this test asserts the slotted renderer
reproduces it byte for byte. If the two ever diverge, every rung-2 number in
the article was produced by a prompt that no longer exists.

Same method scripts/port_prompt_constants.py used for rung 0's six constants
during the FiNER port, and for the same reason: a prompt change is invisible in
a diff of results, and visible only here.
"""
from __future__ import annotations

import pytest

from ladder.rungs import r2
from ladder.schema import R_TYPE_MISMATCH


def test_default_rendering_is_byte_identical_to_the_published_constant():
    """The load-bearing test. Nothing else protects CADEC's rung 2 numbers."""
    assert r2.prompt() == r2.PROMPT, (
        "the slotted prompt no longer reproduces r2.PROMPT — every published "
        "CADEC rung-2 number was produced with the constant, so a divergence "
        "here means they cannot be reproduced"
    )


def test_none_slots_and_empty_slots_agree():
    assert r2.prompt(None) == r2.prompt({})


def test_a_none_value_falls_back_rather_than_rendering_none():
    """A slot present-but-null must not put the word None into a prompt.

    r0.resolve has the same rule. Recorded as a test because the failure is
    silent: the prompt still renders, still parses, and is simply wrong.
    """
    assert r2.prompt({"vocabulary": None}) == r2.PROMPT


def test_slots_actually_replace_the_cadec_wording():
    out = r2.prompt({
        "vocabulary": "US-GAAP XBRL",
        "source_ref": "the filing excerpt",
        "source_head": "The excerpt",
        "id_name": "tag",
        "entity_short": "figure",
    })
    assert "SNOMED CT" not in out, "the whole point is that SNOMED is not named"
    assert "reaction" not in out
    assert "US-GAAP XBRL" in out and "the filing excerpt" in out


def test_format_placeholders_survive_slotting():
    """The renderer returns a template; .format() still has to work on it."""
    out = r2.prompt().format(fact="F", source="S", text="T", start=1, end=2, sct="C")
    for value in ("F", "S", "T", "C"):
        assert value in out
    assert "{" not in out.replace('{"span_text"', ""), "an unfilled placeholder survived"


# ── the new reason ──────────────────────────────────────────────────────
def test_type_mismatch_has_a_fact():
    """A reason with no fact is skipped by build_fact and silently does nothing."""
    assert R_TYPE_MISMATCH in r2.FACTS


def test_type_mismatch_is_correctable():
    assert R_TYPE_MISMATCH in r2.DEFAULTS["correctable"]


def test_the_fact_names_both_types():
    """'The type check disagreed' is not a fact a model can act on."""
    tpl = r2.FACTS[R_TYPE_MISMATCH]
    assert "{span_type}" in tpl and "{code_type}" in tpl


def test_cadec_reasons_are_untouched():
    """The five original reasons keep their facts and their order.

    correctable is a tuple and the article's rung-2 numbers were produced with
    those five. Appending is safe; reordering or dropping is not.
    """
    from ladder.schema import (R_CODE_INACTIVE, R_CODE_UNKNOWN,
                               R_SPAN_OUT_OF_RANGE, R_SPAN_UNGROUNDED,
                               R_WRONG_SEMANTIC_TYPE)
    original = (R_CODE_UNKNOWN, R_CODE_INACTIVE, R_WRONG_SEMANTIC_TYPE,
                R_SPAN_UNGROUNDED, R_SPAN_OUT_OF_RANGE)
    assert r2.DEFAULTS["correctable"][:5] == original
    for reason in original:
        assert reason in r2.FACTS

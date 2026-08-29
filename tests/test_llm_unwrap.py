"""A counted repair for JSON wrapped in prose (2026-08-28, open-model study).

WHY THIS EXISTS, AND WHY IT IS NOT CHEATING.

The open-weight extractor comparison found that `llama3.1:8b` answers the
rung 0 FIND prompt CORRECTLY and still scored zero:

    Here are the adverse reactions extracted from the post:

    ```
    {"mentions": [{"span_text": "extreme rectal bleed", ...}, ...]}
    ```

    Note that "extremely sick" and "might not survive" are not specific medical

The JSON is right and the mentions are the right mentions. `_unfence` uses an
anchored match, so a fence with prose before it is not a fence, and the reply
was counted as a parse failure. Scoring that as a model failure would measure
WHICH MODEL THE HARNESS WAS BUILT AROUND, not which model can do the task —
gpt-oss:20b emits bare JSON because the prompts were tuned against it.

So this is the same class as `_unfence` and `_reclose`, and it follows their
rules exactly: it fires only when the reply does not already parse, it never
fabricates, it is applied identically to every model, and it is COUNTED — the
count is the model's chattiness, reported as a compliance cost rather than
hidden inside a zero.
"""

import json
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from ladder.llm import Caller


class _Bare(Caller):
    """A Caller with no network and no provider lookup — repairs only."""

    def __init__(self):
        self.spec = "test/none"
        self.role = "extractor"
        self.latencies = []
        self.fenced = 0
        self.unclosed = 0
        self.prosed = 0


LLAMA = (
    'Here are the adverse reactions extracted from the post:\n\n'
    '```\n'
    '{\n  "mentions": [\n'
    '    {"span_text": "extreme rectal bleed", "negated": false},\n'
    '    {"span_text": "extremely sick", "negated": false}\n'
    '  ]\n}\n'
    '```\n\n'
    'Note that "extremely sick" is not a specific medical'
)


def test_prose_wrapped_json_is_recovered_and_counted():
    c = _Bare()
    got = c._unwrap(LLAMA)
    parsed = json.loads(got)
    assert [m["span_text"] for m in parsed["mentions"]] == [
        "extreme rectal bleed", "extremely sick"]
    assert c.prosed == 1, "the repair must be counted, never silent"


def test_valid_json_is_untouched_and_not_counted():
    c = _Bare()
    raw = '{"mentions": []}'
    assert c._unwrap(raw) == raw
    assert c.prosed == 0


def test_a_reply_with_no_json_is_returned_unchanged():
    c = _Bare()
    raw = "I could not find any adverse reactions in this post."
    assert c._unwrap(raw) == raw
    assert c.prosed == 0


def test_it_never_fabricates_from_unparseable_braces():
    """Braces that do not parse must stay a parse failure."""
    c = _Bare()
    raw = "The set { was opened but never closed properly }"
    assert c._unwrap(raw) == raw
    assert c.prosed == 0


def test_an_empty_object_is_not_a_repair():
    """Mirrors _reclose's rule: ' {' must not become a fabricated {}."""
    c = _Bare()
    raw = "no reactions here: {}"
    assert c._unwrap(raw) == raw
    assert c.prosed == 0


def test_a_json_array_wrapped_in_prose_is_recovered():
    c = _Bare()
    raw = 'Sure! Here you go:\n[{"span_text": "nausea"}]\nHope that helps.'
    assert json.loads(c._unwrap(raw)) == [{"span_text": "nausea"}]
    assert c.prosed == 1


def test_prose_repair_runs_in_the_call_path_after_unfence():
    """The three repairs compose, and each keeps its own counter."""
    c = _Bare()
    got = c._reclose(c._unwrap(c._unfence(LLAMA)))
    assert json.loads(got)["mentions"]
    assert (c.fenced, c.prosed, c.unclosed) == (0, 1, 0), (
        "an anchored fence match does not fire on a fence preceded by prose; "
        "the prose repair is what recovers this reply"
    )

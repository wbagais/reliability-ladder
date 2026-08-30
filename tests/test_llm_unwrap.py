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

    #: Repair counters, read off ladder/llm.py rather than listed by hand.
    #: This stub broke on the merge that added `preambled`, and a hand-kept
    #: list breaks again on the next counter someone adds.
    _COUNTERS = tuple(sorted({
        ln.split("self.", 1)[1].split(" =")[0]
        for ln in (pathlib.Path(__file__).resolve().parent.parent
                   / "ladder" / "llm.py").read_text().splitlines()
        if ln.strip().startswith("self.") and ln.strip().endswith("= 0")
    }))

    def __init__(self):
        self.spec = "test/none"
        self.role = "extractor"
        self.latencies = []
        for name in self._COUNTERS:
            setattr(self, name, 0)


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
    # CHANGED BY THE 2026-08-30 MERGE, and the change is correct. main
    # extended _unfence with a NON-ANCHORED fence search (counted in
    # `preambled`), which recovers this reply before the prose repair is
    # reached — measured there on FiNER, where llama3.1:8b put a sentence
    # before the fence on 60 of 60 documents. Two independent fixes for the
    # same failure, and the earlier one in the chain wins. The prose repair is
    # NOT redundant: it is the only thing that handles prose around
    # UNFENCED JSON, which the next test pins.
    assert (c.fenced, c.preambled, c.prosed, c.unclosed) == (1, 1, 0, 0), (
        "the loose fence search now recovers a fence preceded by prose"
    )


def test_the_prose_repair_still_earns_its_place_on_unfenced_json():
    """What the loose fence CANNOT do: prose around JSON with no fence at all.

    Without this case the prose repair would be dead code after the merge, and
    a repair nothing exercises is one nobody has shown to work.
    """
    c = _Bare()
    raw = ('Sure! Here is what I found in the post:\n'
           '{"mentions": [{"span_text": "rectal bleed", "negated": false}]}\n'
           'Let me know if you need anything else.')
    got = c._reclose(c._unwrap(c._unfence(raw)))
    assert json.loads(got)["mentions"][0]["span_text"] == "rectal bleed"
    assert (c.fenced, c.preambled, c.prosed) == (0, 0, 1), (
        "no fence to find, so only the prose repair can recover this"
    )

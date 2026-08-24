"""The `usd` column — the one cost measure nothing was writing.

`ladder/llm.py:Caller.__call__` already computes the dollar cost of every call
from `models.yaml`'s per-Mtok rates, and returns it in `usage["usd"]`. Every
rung dropped it on the floor, so the ledger's `usd` was a column of zeroes and
`Ledger.totals()["usd"]` was 0.0 for a paid run.

Local runs are free, which is why this survived: the number was right by
accident for the default configuration and wrong for every configuration the
study would actually need it in — a hosted judge, or the Sonnet 5 comparison
these steps were measured against.

FOUR RUNGS, NOT ONE. Fixing rung 0 alone would leave `totals()["usd"]`
reporting rung 0's spend as the run's spend, which is a worse number than a
zero: a zero is visibly absent, a partial total reads as a total.

Cost is still THREE separate measures — tokens, latency p95, records routed to
a person — and `usd` is carried alongside them, never fused into them. See
ladder/ledger.py.
"""

import json

import pytest

from ladder.ledger import Ledger
from ladder.schema import CONCEPT_LESS, REACTION, Record, ZONE_BAND, ZONE_REJECT

SOURCE = "I feel a bit drowsy & have a little blurred vision.\n"
SOURCES = {"D1": SOURCE}

#: What the caller hands back. The rate is real (models.yaml carries per-Mtok
#: figures); the figure here is a fixture.
USAGE = {"in": 1000, "out": 200, "seconds": 0.5, "model": "test/model",
         "cached": False, "usd": 0.0125}


class PricedLLM:
    """A caller that reports a cost, as every hosted provider's does."""

    def __init__(self, *replies):
        self.replies = list(replies)

    def __call__(self, prompt, text, mode, **kw):
        raw = self.replies.pop(0) if self.replies else "{}"
        if not isinstance(raw, str):
            raw = json.dumps(raw)
        return raw, dict(USAGE)

    def sampler(self, temperature):
        return self


@pytest.fixture
def ledger(tmp_path):
    return Ledger(tmp_path / "usd.jsonl", run_id="usd")


def rows_of(ledger, rung):
    """Read back from DISK: a field in memory but not in the file is a field
    that does not exist for anyone reading the results later."""
    ledger.flush()
    import pathlib

    return [
        json.loads(line)
        for line in pathlib.Path(ledger.path).read_text().splitlines()
        if line.strip() and json.loads(line)["rung"] == rung
    ]


# --- rung 0 ------------------------------------------------------------------


def test_rung_0_logs_the_cost_the_caller_computed(ledger):
    from tests.test_registry_lookup import CONCEPTS  # noqa: F401
    from ladder.keywords import KeywordTable
    from ladder.rungs import r0

    llm = PricedLLM({"mentions": [{"span_text": "bit drowsy", "context": "feel a",
                                   "sct_label": ["Drowsy"], "confidence": 0.9}]})
    cfg = {
        "rung0_step": "S1",
        "registry": object(),
        "llm": llm,
        "ledger": ledger,
        "keywords": KeywordTable.from_mapping({"drowsy": ["271782001"]}),
    }
    r0.apply([], SOURCES, cfg)
    rows = rows_of(ledger, 0)
    assert rows and rows[0]["usd"] == pytest.approx(USAGE["usd"])


def test_rung_0_totals_are_not_zero_for_a_paid_run(ledger):
    from ladder.keywords import KeywordTable
    from ladder.rungs import r0

    llm = PricedLLM({"mentions": []}, {"mentions": []})
    cfg = {
        "rung0_step": "S1", "registry": object(), "llm": llm, "ledger": ledger,
        "keywords": KeywordTable.from_mapping({"drowsy": ["271782001"]}),
    }
    r0.apply([], {"D1": SOURCE, "D2": SOURCE}, cfg)
    assert ledger.totals()["usd"] == pytest.approx(2 * USAGE["usd"])


def test_a_free_local_run_still_logs_zero(ledger):
    """The bug hid because zero was RIGHT for a local model. It must stay
    right — a caller reporting no cost is not a caller reporting nothing."""
    from ladder.keywords import KeywordTable
    from ladder.rungs import r0

    class FreeLLM(PricedLLM):
        def __call__(self, prompt, text, mode, **kw):
            raw, usage = super().__call__(prompt, text, mode, **kw)
            return raw, {**usage, "usd": 0.0}

    cfg = {
        "rung0_step": "S1", "registry": object(), "llm": FreeLLM({"mentions": []}),
        "ledger": ledger,
        "keywords": KeywordTable.from_mapping({"drowsy": ["271782001"]}),
    }
    r0.apply([], SOURCES, cfg)
    assert ledger.totals()["usd"] == 0.0


def test_a_caller_that_reports_no_cost_does_not_break_the_run(ledger):
    """`usage` has no `usd` key at all — an older caller, or a stub."""
    from ladder.keywords import KeywordTable
    from ladder.rungs import r0

    class Bare(PricedLLM):
        def __call__(self, prompt, text, mode, **kw):
            return json.dumps({"mentions": []}), {"in": 1, "out": 1}

    cfg = {
        "rung0_step": "S1", "registry": object(), "llm": Bare(), "ledger": ledger,
        "keywords": KeywordTable.from_mapping({"drowsy": ["271782001"]}),
    }
    r0.apply([], SOURCES, cfg)
    assert rows_of(ledger, 0)[0]["usd"] == 0.0


# --- the paid rungs above it -------------------------------------------------


def rec(**kw):
    base = dict(doc_id="D1", entity_type=REACTION, text="bit drowsy",
                spans=[(9, 19)], sct="271782001", zone=ZONE_BAND)
    base.update(kw)
    return Record(**base)


class StubVocab:
    def exists(self, code):
        return code == "271782001"

    def is_active(self, code):
        return True

    def finding_status(self, code):
        return "finding"

    def is_finding(self, code):
        return True

    def terms(self, code):
        return ["Drowsy"]

    def replacements(self, code):
        return []

    def lexical_match(self, text, code, mode="exact"):
        return False

    def shortlist(self, text, k=20):
        return []


def test_rung_2_logs_the_cost(ledger):
    from ladder.rungs import r2

    r = rec(sct="999999999", zone=ZONE_REJECT)
    r.checks.update(r1_verdict="REJECT", r1_reason="code_unknown")
    llm = PricedLLM({"span_text": "bit drowsy", "sct_label": ["Drowsy"],
                     "sct_code": "271782001", "confidence": 0.5})
    r2.apply([r], SOURCES, {"llm": llm, "ledger": ledger, "registry": StubVocab()})
    rows = rows_of(ledger, 2)
    assert rows and any(x["usd"] for x in rows), "rung 2 logged no cost"


def test_rung_4_logs_the_cost(ledger):
    from ladder.rungs import r4

    llm = PricedLLM({"verdict": "agree", "reason": "fine"})
    r4.apply([rec()], SOURCES, {
        "judge_llm": llm, "ledger": ledger, "registry": StubVocab(),
        "extractor_model": "test/extractor", "judge_model": "test/judge",
    })
    rows = rows_of(ledger, 4)
    assert rows and any(x["usd"] for x in rows), "rung 4 logged no cost"


def test_rung_3_logs_the_cost_of_its_k_sampling_calls(ledger):
    """Rung 3 bills the k calls as a DOCUMENT row, paid whether or not a
    record is re-found. That is exactly the row that must carry a price."""
    from ladder.rungs import r3

    llm = PricedLLM(*[{"mentions": []}] * 3)
    r3.apply([rec()], SOURCES, {"llm": llm, "ledger": ledger, "k": 3,
                                "registry": StubVocab()})
    rows = rows_of(ledger, 3)
    doc_rows = [x for x in rows if x["outcome"] == "sampled"]
    assert doc_rows and any(x["usd"] for x in doc_rows), "rung 3 logged no cost"

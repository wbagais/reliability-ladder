"""Does `scripts/preflight_rungs.py` actually PREDICT which rungs paid?

The tool landed on 2026-08-31 and the article's central recommendation rests on
it: every layer has a precondition, and all of them are measurable before the
layer is built. A tool that has never been shown to make the right call is a
proposal, not an instrument — so this file is the validation, and the answer key
is what each rung actually did, recorded in `docs/decisions.md`.

Every case below is a MEASURED historical situation, not an invented one, and
each asserts the call the tool makes on it:

  wiring      the three orphaned verdict fields found by hand on 2026-08-28
  rung 1      FiNER's ACCEPT 0 of 704, against CADEC's lane that fires
  rungs 2/5   rung 1's own false-positive rate, at 9.3% and after the repair
  rung 5      rung 0's confidence, which is {1.0, 0.99} and nothing else
  rung 3      voting could not re-find 206 of 240 mentions on CADEC

The corpus is deliberately NOT loaded. These run from a clean checkout with no
CADEC, no FiNER and no model, because a precondition check you cannot rerun is
in the same position as the rungs it is meant to catch.
"""

import pathlib
import types

import pytest

_ROOT = pathlib.Path(__file__).resolve().parent.parent


def _preflight():
    """Load the script from SOURCE, with no bytecode cache in the path.

    The obvious `spec_from_file_location` + `exec_module` writes
    `scripts/__pycache__/preflight_rungs.*.pyc` and will serve it back. Caught
    the only way it ever is — by mutating a threshold in the script and finding
    that the test still passed, three times over, against code that had not
    been re-read. Same defect as the LLM cache key that survived a parameter
    change: a cache that outlives the thing it keys on turns a test into a
    recording. `compile` + `exec` never touches disk.
    """
    src = (_ROOT / "scripts" / "preflight_rungs.py").read_text()
    mod = types.ModuleType("preflight_rungs_under_test")
    mod.__file__ = str(_ROOT / "scripts" / "preflight_rungs.py")
    exec(compile(src, mod.__file__, "exec"), mod.__dict__)
    return mod


pf = _preflight()


class Mention:
    """The only two attributes the checks touch on a gold record."""

    def __init__(self, text, sct):
        self.text, self.sct = text, sct


class Vocab:
    """A vocabulary whose two answers are supplied by the test."""

    def __init__(self, matches=(), missing=()):
        self._matches, self._missing = set(matches), set(missing)

    def lexical_match(self, text, code, mode="exact"):
        return (text, code) in self._matches

    def exists(self, code):
        return code not in self._missing


MAN = {"rungs": {"1": {"lexical_mode": "exact"}}}


# --- wiring: the free check, and the one that found the most ----------------
#
# 2026-08-28, by hand: rung 2 wrote r2_declined, rung 3 wrote r3_unanimous_none
# and rung 4 wrote r4_verdict, and the refusal step read none of the three. Run
# against `ladder/` as it stood at 9bb98c9^ — the commit before rung 4 got its
# reader — check_readers names those three and nothing else, over 55 diagnostic
# fields it correctly leaves alone. That is the empirical validation; this test
# pins the mechanism so it cannot rot.


def test_a_verdict_nothing_reads_is_reported_and_a_diagnostic_is_not(tmp_path):
    pkg = tmp_path / "ladder"
    pkg.mkdir()
    (pkg / "r2.py").write_text(
        'def go(rec):\n'
        '    rec.checks["r2_declined"] = True\n'
        '    rec.checks["candidates"] = []\n')
    (pkg / "r5.py").write_text(
        'def go(rec):\n'
        '    if rec.checks.get("r1_verdict") == "REJECT":\n'
        '        pass\n')
    (pkg / "r1.py").write_text('def go(rec):\n    rec.checks["r1_verdict"] = "BAND"\n')

    verdicts, diagnostics = pf.check_readers(pkg)
    orphans = {f for f, r in verdicts.items() if not r["read"]}

    assert orphans == {"r2_declined"}, "the verdict nothing reads must be named"
    assert "r1_verdict" in verdicts and not orphans & {"r1_verdict"}, \
        "a verdict another module reads is wired, not orphaned"
    assert "candidates" in diagnostics, \
        "a diagnostic field is written for the ledger and must not be reported as an orphan"


# --- rung 1: the ACCEPT lane, and the corpus where it cannot fire -----------
#
# FiNER shipped NOTHING: ACCEPT 0 / BAND 350 / REJECT 1, coverage 1.0 -> 0.0,
# every record routed to a person. The cause is structural — the span is "47.6"
# and the code is a US-GAAP tag name, so they share no tokens by construction —
# and it is visible on GOLD, before a model runs. This is the call the article
# says one query would have made.


def test_the_accept_lane_is_refused_where_span_and_code_share_no_language():
    gold = [Mention("47.6", ["Revenues"]),
            Mention("19.5", ["AccrualForEnvironmentalLossContingencies"]),
            Mention("0.375", ["EffectiveIncomeTaxRateContinuingOperations"])]
    c = pf.check_accept_lane(MAN, gold, Vocab(matches=()))
    assert c.verdict == pf.DONT
    assert "0 of 3" in c.evidence
    # DON'T is not enough: "cannot fire on a perfect answer set" and "fires, but
    # too thinly" are different findings and only the first is FiNER's.
    assert "PERFECT answer set" in c.because


def test_the_accept_lane_is_built_where_the_words_are_shared():
    gold = [Mention("nausea", ["422587007"]), Mention("drowsy", ["271782001"]),
            Mention("extreme rectal bleed", ["12063002"])]
    vocab = Vocab(matches={("nausea", "422587007"), ("drowsy", "271782001")})
    c = pf.check_accept_lane(MAN, gold, vocab)
    assert c.verdict == pf.BUILD


def test_a_lane_too_thin_to_carry_a_system_is_refused_as_well():
    gold = [Mention(f"m{i}", [str(i)]) for i in range(100)]
    c = pf.check_accept_lane(MAN, gold, Vocab(matches={("m0", "0")}))
    assert c.verdict == pf.DONT, "1% of a perfect answer set is not a lane"
    assert "too thin" in c.because, "a thin lane is a different finding from an absent one"


# --- rungs 2 and 5: the rejection rate, measured on gold -------------------
#
# Replaying rung 1 over the answer key took its false-positive rate from 9.3%
# to 0.13%, because every rejection there is false by construction. The check
# must refuse the layer at the first number and allow it at the second — a rung
# 2 built on the 9.3% gate would have spent most of its calls "correcting"
# answers that were already right.


def test_a_gate_that_rejects_9_percent_of_a_perfect_answer_set_is_refused():
    gold = [Mention(f"m{i}", [str(i)]) for i in range(1000)]
    c = pf.check_reject_lane(MAN, gold, Vocab(missing={str(i) for i in range(93)}))
    assert c.verdict == pf.DONT
    assert "FALSE positive" in c.evidence


def test_the_same_gate_after_the_repair_is_allowed():
    gold = [Mention(f"m{i}", [str(i)]) for i in range(1000)]
    c = pf.check_reject_lane(MAN, gold, Vocab(missing={"0"}))
    assert c.verdict == pf.BUILD


# --- rung 5: the dead dial -------------------------------------------------
#
# rung 0's confidence over a dev split is {1.0: 204, 0.99: 44} and nothing
# else, so rung 5's tau cannot separate records and the planned sweep was
# cancelled rather than run over a constant.


def test_the_recorded_confidence_distribution_kills_the_threshold():
    recs = [{"confidence": 1.0}] * 204 + [{"confidence": 0.99}] * 44
    c = pf.check_tau(MAN, recs)
    assert c.verdict == pf.DONT
    assert "2 distinct value(s) over 248 records" in c.evidence


def test_a_confidence_field_that_varies_keeps_the_threshold():
    recs = [{"confidence": v} for v in (1.0, 0.9, 0.8, 0.7, 0.6)] * 10
    assert pf.check_tau(MAN, recs).verdict == pf.BUILD


# --- rung 3: nothing to vote on -------------------------------------------
#
# Voting matches records by (doc_id, spans). Before the Phase D repair it could
# not re-find 206 of 240 mentions on CADEC, so the rung reported not_resampled
# rather than a disagreement. The check draws three samples and asks whether
# the keys align at all.


def _fake_draws(monkeypatch, per_draw):
    """Make r0 return a supplied span set per draw, with no model anywhere."""
    calls = {"n": 0}

    class Rec:
        def __init__(self, spans):
            self.spans = spans

    class Caller:
        def sampler(self, t):
            return self

    def extract_document(doc_id, text, sampler, cfg):
        spans = per_draw[calls["n"] // 1 % len(per_draw)]
        calls["n"] += 1
        return [Rec([s]) for s in spans], {}

    import ladder.llm as llm_mod
    from ladder.rungs import r0
    monkeypatch.setattr(llm_mod, "for_rung", lambda rung, man: Caller())
    monkeypatch.setattr(r0, "prepare", lambda cfg: cfg)
    monkeypatch.setattr(r0, "extract_document", extract_document)
    monkeypatch.setattr(pf, "vocab_for", lambda man: None)


class Doc:
    text = "irrelevant"


def test_draws_that_quote_different_phrasings_have_nothing_to_vote_on(monkeypatch):
    # three draws, one document, almost no overlap — the recorded CADEC shape
    _fake_draws(monkeypatch, [[(0, 5)], [(0, 9)], [(2, 9)]])
    c = pf.check_resample(MAN, {"D1": Doc()}, ["D1"], 1)
    assert c.verdict == pf.DONT
    assert "Jaccard" in c.evidence


def test_draws_that_agree_on_the_spans_make_a_vote_well_defined(monkeypatch):
    _fake_draws(monkeypatch, [[(0, 5), (7, 9)]])
    c = pf.check_resample(MAN, {"D1": Doc()}, ["D1"], 1)
    assert c.verdict == pf.BUILD


def test_partial_agreement_is_neither_verdict_and_must_say_so(monkeypatch):
    # Two draws find three spans, the third finds two: a vote engages on the
    # shared subset and reports not_resampled on the rest. That third state has
    # to be recorded, or the rung's rate is computed over a set nobody named.
    _fake_draws(monkeypatch, [[(0, 5), (7, 9), (11, 14)],
                              [(0, 5), (7, 9), (11, 14)],
                              [(0, 5), (7, 9)]])
    c = pf.check_resample(MAN, {"D1": Doc()}, ["D1"], 1)
    assert c.verdict == pf.UNKNOWN
    assert "not_resampled" in c.because

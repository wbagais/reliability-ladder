"""Tests for rung 7 — type compatibility. Written BEFORE the wiring, per
CLAUDE.md, and every one of them was watched to fail first.

The reason that discipline matters here specifically: rung 7 exists to give
FiNER a rejection class it has never had, and a rejection class feeds rung 2,
which feeds rung 5. A check that rejects wrongly does not merely produce a bad
number — it wakes three rungs and gives them false work. The false-rejection
tests below are therefore the load-bearing ones, and the CADEC isolation tests
are the ones that protect what is already published.
"""
from __future__ import annotations

import json
import pathlib

import pytest

from ladder.rungs import r7
from ladder.schema import R_TYPE_MISMATCH, REJECT_REASONS


# ── the contract ────────────────────────────────────────────────────────
def test_reason_is_declared():
    """An undeclared reason fails loudly at rung 1's assert, not quietly here."""
    assert R_TYPE_MISMATCH in REJECT_REASONS


def test_rung_number_is_seven():
    assert r7.RUNG == 7


# ── span typing, each case from a measured disagreement ─────────────────
@pytest.mark.parametrize("text,before,after,want", [
    # the plain cases
    ("1.50", "with a floor of ", " % ) plus 2.80", "percent"),
    ("19.4", "net proceeds of $ ", " million . As of", "money"),
    ("1,350,000", "we sold ", " shares for net", "count"),
    ("January 9 , 2023", "The SRT Loan matures on ", " . The Company", "date"),
    ("6.8", "of approximately ", " years . 11 Table", "duration"),

    # A currency symbol immediately before outranks a quantity word after.
    # "$ 6.1 billion in share repurchases" is money; the word "share" three
    # tokens later does not make it a count. This rule removed 3 of the first
    # draft's 8 disagreements.
    ("6.1", "Directors has authorized $ ", " billion in share repurc", "money"),

    # "per share" is a UNIT, not a quantity of shares.
    ("90.07", "at an average price of $ ", " per share , excluding", "money"),

    # And it abstains rather than guessing.
    ("42", "the number ", " appears here", None),
])
def test_span_type(text, before, after, want):
    assert r7.span_type(text, before, after) == want


# ── the false-rejection rate, on gold, which is the whole argument ──────
def test_false_rejection_rate_on_gold_is_under_two_percent():
    """Every disagreement with gold is a FALSE rejection by construction.

    Measured 2026-09-02: 2 of 164 typed mentions = 1.22%, against rung 1's
    0.13% on CADEC. The threshold here is 2%, not 1.22%, so the test does not
    pin the exact figure — a rule change that moves it slightly should not go
    red, but one that breaks the check should.
    """
    pytest.importorskip("ladder.corpus_finer")
    from ladder.corpus_finer import load_corpus, read_split
    from ladder.vocab_finer import load as load_vocab

    man_path = pathlib.Path("manifest.finer.json")
    if not man_path.is_file():
        pytest.skip("FiNER manifest not present")
    man = json.loads(man_path.read_text())
    root = man["corpus"]["root"]
    if not pathlib.Path(root).is_dir():
        pytest.skip("FiNER data not present")

    sampling = {k: v for k, v in (man["corpus"].get("sampling") or {}).items()
                if not k.startswith("_")}
    docs = load_corpus(root, **sampling)
    ids = read_split(man["corpus"]["splits_dir"], "test")
    vocab = load_vocab(root)

    typed = wrong = 0
    for d in ids:
        text = docs[d].text
        for m in docs[d].mentions:
            i, j = m.spans[0]
            st = r7.span_type(m.text, text[max(0, i - 40):i], text[j:j + 40])
            ct = vocab.code_type(m.sct[0]) if m.sct else None
            if st is None or ct is None:
                continue
            typed += 1
            wrong += (st != ct)

    assert typed > 100, f"only {typed} mentions typeable — coverage collapsed"
    rate = wrong / typed
    assert rate < 0.02, (
        f"false-rejection rate {rate:.2%} ({wrong}/{typed}) — a check that "
        f"rejects a perfect answer set this often is worse than no check")


def test_coverage_on_gold_is_substantial():
    """A precise check that fires on 3% of records is not worth wiring in.

    Measured: 87.7% of FiNER test mentions are typed on both sides, against the
    lexical check's 0%.
    """
    pytest.importorskip("ladder.corpus_finer")
    from ladder.corpus_finer import load_corpus, read_split
    from ladder.vocab_finer import load as load_vocab

    man_path = pathlib.Path("manifest.finer.json")
    if not man_path.is_file():
        pytest.skip("FiNER manifest not present")
    man = json.loads(man_path.read_text())
    root = man["corpus"]["root"]
    if not pathlib.Path(root).is_dir():
        pytest.skip("FiNER data not present")

    sampling = {k: v for k, v in (man["corpus"].get("sampling") or {}).items()
                if not k.startswith("_")}
    docs = load_corpus(root, **sampling)
    ids = read_split(man["corpus"]["splits_dir"], "test")
    vocab = load_vocab(root)

    n = typed = 0
    for d in ids:
        text = docs[d].text
        for m in docs[d].mentions:
            n += 1
            i, j = m.spans[0]
            st = r7.span_type(m.text, text[max(0, i - 40):i], text[j:j + 40])
            ct = vocab.code_type(m.sct[0]) if m.sct else None
            typed += (st is not None and ct is not None)
    assert typed / n > 0.75, f"coverage {typed/n:.1%} — too thin to be worth a rung"


# ── isolation: CADEC cannot move ────────────────────────────────────────
class _Rec:
    def __init__(self, sct=None, text="", spans=None):
        self.sct = sct
        self.text = text
        self.spans = spans or [(0, len(text))]
        self.checks = {}
        self.zone = None
        self.doc_id = "D"
        self.record_id = "D#0"

    def mark(self, *a, **k):
        self.marked = a


class _NoTypeVocab:
    """A vocabulary with no code_type — SNOMED and GeoNames both look like this."""

    def exists(self, code):
        return True


def test_inert_without_code_type():
    """The rung must be a no-op on a vocabulary that cannot type its codes.

    This is what lets rung 7 sit in rung_order for every corpus without
    branching on a corpus name — the pattern that cost the FiNER port sixteen
    one-line edits.
    """
    rec = _Rec(sct="271782001", text="drowsy")
    reason, checks = r7.check(rec, "I felt drowsy", _NoTypeVocab())
    assert reason is None
    assert checks["r7_applicable"] is False
    assert "r7_span_type" not in checks


def test_untypeable_side_is_could_not_run_not_a_pass():
    """The third outcome, which nothing else models.

    A record this rung cannot type is NOT the same as one it judged and passed,
    and collapsing the two would make the rejection rate a rate over an unnamed
    set — the defect this project documents most often.
    """
    class V:
        def code_type(self, code):
            return None

    rec = _Rec(sct="SomeTag", text="42")
    reason, checks = r7.check(rec, "the number 42 appears here", V())
    assert reason is None
    assert checks["r7_evaluable"] is False


def test_rejects_only_on_contradiction():
    class V:
        def code_type(self, code):
            return "count" if "Shares" in code else "percent"

    text = "we sold 1,350,000 shares for net proceeds"
    rec = _Rec(sct="EffectiveIncomeTaxRate", text="1,350,000", spans=[(8, 17)])
    reason, checks = r7.check(rec, text, V())
    assert reason == R_TYPE_MISMATCH
    assert checks["r7_span_type"] == "count"
    assert checks["r7_code_type"] == "percent"

    rec2 = _Rec(sct="StockIssuedSharesNewIssues", text="1,350,000", spans=[(8, 17)])
    reason2, _ = r7.check(rec2, text, V())
    assert reason2 is None, "agreeing types must not be rejected"


def test_agreement_is_not_promoted_to_accept():
    """Agreeing on type is weak evidence and must not become an endorsement.

    The geo arm (2026-09-02) measured what happens when a check vouches
    confidently where it knows least: rung 1's ACCEPT lane on a gazetteer was
    WORSE than its BAND lane on all three models. This rung can only reject.
    """
    class V:
        def code_type(self, code):
            return "money"

    rec = _Rec(sct="ProceedsFromIssuance", text="19.4", spans=[(20, 24)])
    rec.checks["r1_verdict"] = "BAND"
    reason, _ = r7.check(rec, "net proceeds of $ 19.4 million . As", V())
    assert reason is None
    assert rec.checks["r1_verdict"] == "BAND", "rung 7 must not upgrade a verdict"

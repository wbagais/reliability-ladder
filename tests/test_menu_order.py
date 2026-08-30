"""Ordering the FiNER menu by the words AROUND the number (2026-08-30).

FiNER's menu is the whole 139-tag vocabulary, on the sound argument that a bare
number carries no terms to rank on. But the SENTENCE does, and CADEC already
measured that the order of a menu is load-bearing: alphabetising the pick menu
cost 10-12 points of coding accuracy at byte-identical detection, because the
pick anchors on early slots. FiNER's full menu has no meaningful order at all
and is seven times longer than the CADEC menu (k=40) that already measured
WORSE than k=20.

So this reorders and drops NOTHING: menu recall stays 1.000 by construction and
the only thing under test is whether best-first order is worth anything when
the query is context rather than the span.

Offline probe before a line of this was written (out/harness/finerctx.py, 165
dev gold mentions, granite-embedding:30m over de-camel-cased tag names):
median rank of the correct tag 7 of 139, recall@1 0.242, @10 0.558, @20 0.685.
Real signal, and not nearly enough to justify TRUNCATING the menu to 20.
"""

import pytest

from ladder.menuorder import context_ranked, tag_words


def test_tag_words_splits_the_camel_case_an_embedder_has_never_seen():
    assert tag_words("DebtInstrumentInterestRateStatedPercentage") == (
        "debt instrument interest rate stated percentage")
    assert tag_words("us-gaap:NumberOfReportableSegments") == (
        "number of reportable segments")
    assert tag_words("ConcentrationRiskPercentage1") == (
        "concentration risk percentage 1")


def stub_embed(texts):
    """A one-dimensional embedder: the score IS how many query words the tag
    shares with the text, so the expected order is computable by hand."""
    out = []
    for t in texts:
        out.append([float(len(set(t.split()) & {"interest", "rate", "debt"}))])
    return out


CANDS = [
    {"i": 0, "code": "us-gaap:NumberOfReportableSegments", "label": "x", "via": "full"},
    {"i": 1, "code": "us-gaap:DebtInstrumentInterestRateStatedPercentage",
     "label": "y", "via": "full"},
    {"i": 2, "code": "us-gaap:PaymentsOfDividends", "label": "z", "via": "full"},
]


def test_context_ranking_puts_the_contextually_closest_tag_first():
    out = context_ranked(CANDS, "the debt instrument bore interest at a rate of",
                         stub_embed)
    assert out[0]["code"] == "us-gaap:DebtInstrumentInterestRateStatedPercentage"


def test_context_ranking_drops_nothing_and_renumbers():
    out = context_ranked(CANDS, "interest rate", stub_embed)
    assert len(out) == len(CANDS)
    assert {c["code"] for c in out} == {c["code"] for c in CANDS}
    assert [c["i"] for c in out] == [0, 1, 2], "the pick indexes the menu it is shown"


def test_ranking_is_stable_for_ties_so_a_run_reproduces():
    tied = [{"i": n, "code": f"us-gaap:PaymentsOfDividends{n}"} for n in range(5)]
    a = context_ranked(tied, "nothing in common", stub_embed)
    b = context_ranked(tied, "nothing in common", stub_embed)
    assert [c["code"] for c in a] == [c["code"] for c in b]
    assert [c["code"] for c in a] == [c["code"] for c in tied]


def test_no_context_returns_the_menu_untouched():
    """An ordering failure must cost ORDER, never the run: a mention with no
    usable context still gets the full menu, in the order it came in."""
    assert context_ranked(CANDS, "", stub_embed) == CANDS
    assert context_ranked(CANDS, None, stub_embed) == CANDS


def test_an_embedder_that_fails_costs_the_order_and_not_the_document():
    def boom(_texts):
        raise RuntimeError("ollama is not running")

    assert context_ranked(CANDS, "interest rate", boom) == CANDS


def test_an_empty_menu_is_not_an_error():
    assert context_ranked([], "interest rate", stub_embed) == []


# --- wired into rung 0 as an off-by-default arm ------------------------------


def test_the_arm_is_off_in_both_shipped_manifests():
    import json
    import pathlib

    root = pathlib.Path(__file__).resolve().parents[1]
    for name in ("manifest.json", "manifest.finer.json"):
        man = json.load(open(root / name))
        assert man["rungs"]["0"].get("rung0_menu_order", "score") == "score", (
            f"{name} must ship the measured menu order, not the new arm")


def test_context_is_a_declared_menu_order():
    from ladder.rungs import r0

    assert "context" in r0.MENU_ORDERS
    assert r0.DEFAULTS["rung0_menu_order"] == "score"


def test_an_undeclared_menu_order_still_raises():
    from ladder.rungs import r0

    with pytest.raises(ValueError):
        r0._order_menu([{"i": 0, "code": "us-gaap:X"}], "best")


def test_context_order_without_an_embedder_leaves_the_menu_alone():
    """`_order_menu` is called per mention inside the document loop. If the
    context arm is on but nothing supplied an embedder, the menu must come back
    in retrieval order rather than the call raising halfway through a run."""
    from ladder.rungs import r0

    cands = [{"i": 0, "code": "us-gaap:A"}, {"i": 1, "code": "us-gaap:B"}]
    assert r0._order_menu(cands, "context") == cands


def test_the_pick_menu_is_context_ordered_when_the_arm_is_on():
    from ladder.rungs import r0

    cands = [{"i": 0, "code": "us-gaap:PaymentsOfDividends"},
             {"i": 1, "code": "us-gaap:DebtInstrumentInterestRateStatedPercentage"}]
    out = r0._order_menu(cands, "context", context="interest rate on the debt",
                         embed=stub_embed)
    assert out[0]["code"] == "us-gaap:DebtInstrumentInterestRateStatedPercentage"
    assert [c["i"] for c in out] == [0, 1]


def test_the_span_context_window_comes_from_the_source_not_the_span():
    """The whole premise is that the SPAN carries no query and the sentence
    does, so the window must be read off the document."""
    from ladder.rungs import r0

    src = "A" * 200 + "the conversion price of 11.16 per share" + "B" * 200
    a = src.index("11.16")
    assert "conversion price" in r0._span_context(src, [(a, a + 5)], window=40)
    assert r0._span_context(src, [(-1, -1)], window=40) == ""
    assert r0._span_context("", [(0, 1)], window=40) == ""


def test_prepare_supplies_a_memoised_embedder_only_when_the_arm_is_on():
    """139 tag names re-embedded once per mention would be ~40,000 embedding
    calls for a 292-mention run, to compute the same 139 vectors every time.
    The context changes per mention; the menu does not."""
    from ladder.rungs import r0

    calls = []

    def counting(texts):
        calls.append(list(texts))
        return [[float(len(t))] for t in texts]

    off = r0.prepare({"rung0_step": None, "manifest": {}, "rung0_trim": False})
    assert off.get("menu_embedder") is None

    cfg = r0.prepare({"rung0_step": None, "manifest": {}, "rung0_trim": False,
                      "rung0_menu_order": "context", "embedder": counting})
    e = cfg["menu_embedder"]
    assert e(["debt instrument", "interest rate"]) == [[15.0], [13.0]]
    assert e(["interest rate", "debt instrument"]) == [[13.0], [15.0]]
    assert calls == [["debt instrument", "interest rate"]], (
        "the second call re-embedded text it had already seen")


def test_prepare_does_not_reach_for_ollama_when_the_arm_is_off():
    """An import or a connection attempt at prepare() time would make every
    CADEC run depend on an embedding server it never uses."""
    from ladder.rungs import r0

    def boom(_texts):
        raise AssertionError("the embedder must not be called")

    cfg = r0.prepare({"rung0_step": None, "manifest": {}, "rung0_trim": False,
                      "embedder": boom})
    assert "menu_embedder" not in cfg or cfg["menu_embedder"] is None


def test_the_ctxmenu_manifest_differs_by_exactly_the_menu_order():
    """Same rule as manifest.judgearm.json: an arm manifest that drifts from
    its base is two experiments wearing one name."""
    import json
    import pathlib

    root = pathlib.Path(__file__).resolve().parents[1]
    a = json.load(open(root / "manifest.finer.json"))
    b = json.load(open(root / "manifest.finer.ctxmenu.json"))
    b.pop("_ctxmenu_note", None)
    b["rungs"]["0"].pop("rung0_menu_order_note", None)

    def walk(x, y, path=""):
        if isinstance(x, dict) and isinstance(y, dict):
            for k in sorted(set(x) | set(y)):
                yield from walk(x.get(k), y.get(k), f"{path}.{k}")
        elif x != y:
            yield path

    assert list(walk(a, b)) == [".rungs.0.rung0_menu_order"]
    assert b["rungs"]["0"]["rung0_menu_order"] == "context"

"""The InfoQ figures read their numbers from the tracked report, not from
literals typed in by hand.

Until 2026-09-07 `docs/figures/make_infoq_figs.py` carried the dial and the
shipped-set figure as hard-coded tuples, computed by a scratch script that no
longer exists. Nothing could regenerate them from a clean machine and nothing
could say whether the article's table and the figure disagreed. Now the figure
script loads `runs/archive/consolidated-2026-09-03/rerun/cadec.json`, whose
`shipping_rules` section `ladder.analysis.shipping_rules` writes, and these
tests keep it that way.
"""

import json
import pathlib

ROOT = pathlib.Path(__file__).parent.parent
REPORT = ROOT / "runs" / "archive" / "consolidated-2026-09-03" / "rerun" / "cadec.json"
FIGS = ROOT / "docs" / "figures" / "make_infoq_figs.py"

RULES = ["everything", "everything_after_r3", "accept", "accept_contained",
         "r3_unanimous", "r3_two_agree", "r4_blind_pass", "r4_menu_pass"]


def test_the_tracked_report_carries_the_shipping_rules_for_every_draw_and_their_mean():
    report = json.loads(REPORT.read_text())
    for name, d in report["draws"].items():
        assert [r["rule"] for r in d["shipping_rules"]] == RULES, name
        for r in d["shipping_rules"]:
            assert r["ships"] + r["to_person"] == d["final"]["n"], (name, r["rule"])
            assert r["correct"] + r["span_only"] + r["code_only"] + r["neither"] == r["ships"]
    assert [r["rule"] for r in report["shipping_rules_mean"]] == RULES


def test_the_first_draw_reproduces_the_published_shipped_set_figure():
    """The numbers on docs/figures/infoq-fig5-shipped.png as published on
    2026-09-04, now from the module rather than a scratch script."""
    d0 = {r["rule"]: r for r in json.loads(REPORT.read_text())["draws"]["rerun-cadec-d0"]["shipping_rules"]}
    row = lambda r: (r["correct"], r["span_only"], r["code_only"], r["neither"], r["to_person"], r["person_correct"], round(r["f1"], 3))
    assert row(d0["everything_after_r3"]) == (88, 28, 23, 91, 0, 0, 0.397)
    assert row(d0["accept"]) == (39, 2, 0, 12, 177, 49, 0.283)
    assert row(d0["accept_contained"]) == (53, 5, 8, 25, 139, 35, 0.34)
    assert row(d0["r3_unanimous"]) == (51, 13, 15, 29, 122, 37, 0.315)  # all three samples agree
    assert row(d0["r3_two_agree"]) == (77, 22, 21, 65, 45, 11, 0.387)
    assert row(d0["r4_blind_pass"]) == (63, 16, 15, 42, 94, 25, 0.357)
    assert row(d0["r4_menu_pass"]) == (74, 9, 14, 39, 94, 14, 0.42)


def test_the_figure_script_reads_the_report_and_carries_no_hand_typed_counts():
    src = FIGS.read_text()
    assert "consolidated-2026-09-03/rerun/cadec.json" in src
    assert "shipping_rules" in src
    for literal in ("88, 28, 23, 91", "39, 2, 0, 12", "100, 0.39, 155000", "22, 0.77, 0"):
        assert literal not in src, f"hand-typed data still in the figure script: {literal}"


def test_the_shipped_set_figure_does_not_restate_the_table():
    """The article's table already carries ships and F1 per rule as three-run
    means. The figure is the first run alone, so a per-row 'ships N · F1 x'
    annotation duplicated the table with different numbers (230 against 233,
    0.397 against 0.405) and left the reader to reconcile them. The figure
    keeps only what the table cannot show, the withheld records and how many
    of them were correct, and says 'first run' in its title."""
    src = FIGS.read_text()
    assert 'f"ships {ships}' not in src
    assert "F1 {f:.3f}" not in src
    assert 'set_title("What ships under each rule, first run' in src

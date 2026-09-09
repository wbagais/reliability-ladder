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
HERE_FIGS = ROOT / "docs" / "figures"
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
    """The article's prose (once a table) carries ships and F1 per rule. The
    figure is the first run alone, so a per-row 'ships N · F1 x' annotation
    once duplicated the table with different numbers (230 against 233, 0.397
    against 0.405) and left the reader to reconcile them. The figure keeps
    only what the prose cannot show, the withheld records and how many of
    them were correct, and says 'first run' in its title."""
    src = FIGS.read_text()
    assert 'f"ships {ships}' not in src
    assert "F1 {f:.3f}" not in src
    assert 'set_title("What ships under each rule, first run' in src


def test_the_article_dial_prose_is_the_first_run_like_the_figure_above_it():
    """The dial table was removed on 2026-09-08 at the reviewers' request (two
    comments: "very hard to read this table, delete it; if it has important
    information highlight it in the text"). The prose under Figure 2 now
    carries the three rows a reader needs, and it must stay on the figure's
    own basis, the first run, read from the report rather than typed in:
    ship everything, the run's ACCEPT setting, and the menu-shown judge."""
    art = (ROOT / "docs" / "article-infoq-CADEC.md").read_text()
    assert "| ship only when" not in art, "the dial table is back; the reviewers asked for prose"
    d0 = {r["rule"]: r for r in json.loads(REPORT.read_text())["draws"]["rerun-cadec-d0"]["shipping_rules"]}
    n = json.loads(REPORT.read_text())["draws"]["rerun-cadec-d0"]["final"]["n"]
    every, acc, judge = d0["everything_after_r3"], d0["accept"], d0["r4_menu_pass"]
    sec = art.split("## One dial, not a staircase", 1)[1].split("\n## ", 1)[0]
    # 2026-09-08, owner: the prose should carry relationships, not restate the
    # figure's rows. Five numbers remain because each anchors a lesson: the
    # ceiling, the trade behind the free check, and the one rule that beats
    # shipping everything on F1.
    for needle in (
        f"the {every['correct']} right answers the extractor found",
        f"removes {(every['ships'] - every['correct']) - (acc['ships'] - acc['correct'])} errors",
        f"{every['correct'] - acc['correct']} right answers",
        f"{acc['to_person']} records for a person",
        f"{judge['f1']:.3f} against {every['f1']:.3f}",
    ):
        assert needle in sec, f"the dial prose no longer carries the first run's number: {needle!r}"


def test_the_funnel_figure_names_the_model_it_measures():
    """A reviewer read Figure 3 as a comparison between models ("add the model
    name, add the original model to compare"). It is one model's funnel, and
    the figure now says which."""
    dot = (HERE_FIGS / "infoq-fig3-funnel.dot").read_text()
    assert "gpt-oss:20b" in dot


def test_the_variants_figure_reads_the_three_step_reports():
    """The three-variant table under "We chose this shape" was replaced by a
    chart on 2026-09-08 (reviewer: "hard to read"). The chart reads F1,
    tokens and parse failures per run from the three tracked reports —
    cadec-s0 (recall the code), cadec-s1 (name the concept), cadec (pick
    from a menu) — and this pins the values it must show."""
    src = FIGS.read_text()
    for name in ("\"cadec-s0\"", "\"cadec-s1\""):
        assert name in src, f"the figure script does not read {name}"
    assert "infoq-fig7-variants" in src
    assert (HERE_FIGS / "infoq-fig7-variants.png").is_file()
    rerun = ROOT / "runs" / "archive" / "consolidated-2026-09-03" / "rerun"
    seen = {}
    for stem in ("cadec-s0", "cadec-s1", "cadec"):
        draws = json.loads((rerun / f"{stem}.json").read_text())["draws"]
        seen[stem] = [(d["rung0"]["exact"]["f1"],
                       d["aggregates"]["0"]["tokens_in"] + d["aggregates"]["0"]["tokens_out"],
                       d["aggregates"]["0"]["parse_failed"]) for d in draws.values()]
    assert [round(f, 3) for f, _, _ in seen["cadec-s0"]] == [0.03, 0.03, 0.024]
    assert [round(f, 3) for f, _, _ in seen["cadec-s1"]] == [0.252, 0.253, 0.276]
    assert [round(f, 3) for f, _, _ in seen["cadec"]] == [0.393, 0.393, 0.434]
    assert [p for _, _, p in seen["cadec-s0"]] == [3, 3, 3]
    assert all(141_000 <= t <= 148_000 for _, t, _ in seen["cadec-s0"])
    assert all(81_000 <= t <= 83_000 for _, t, _ in seen["cadec-s1"])
    assert all(155_000 <= t <= 162_000 for _, t, _ in seen["cadec"])
    art = (ROOT / "docs" / "article-infoq-CADEC.md").read_text()
    assert "infoq-fig7-variants.png" in art
    assert "| **recall the code** |" not in art, "the three-variant table is back"


def test_the_funnel_chart_reads_the_error_budget_from_the_report():
    """Figure 4 was a hand-written Graphviz table (infoq-fig3-funnel.dot) that
    a reviewer found unclear (2026-09-08). It is a chart now, drawn by the
    figure script from the first draw's `budget` block: the four stages of the
    funnel and the losses between them, with the finding loss split into
    never-touched (missed under overlap matching) and wrong-boundary (matched
    under overlap but not exact). The table carried 43 / 67 for that split,
    typed in from an earlier analysis; the report says 48 / 62."""
    src = FIGS.read_text()
    assert "infoq-fig8-funnel" in src and '["budget"]' in src
    assert (HERE_FIGS / "infoq-fig8-funnel.png").is_file()
    d0 = json.loads(REPORT.read_text())["draws"]["rerun-cadec-d0"]["budget"]
    ex, ov = d0["exact"], d0["overlap"]
    assert (ex["n_gold"], ex["matched"], ex["on_menu"], ex["correct"]) == (226, 116, 108, 87)
    assert ex["n_gold"] - ex["matched"] == 110 == ov["missed"] + (ov["matched"] - ex["matched"])
    assert (ov["missed"], ov["matched"] - ex["matched"]) == (48, 62)
    art = (ROOT / "docs" / "article-infoq-CADEC.md").read_text()
    assert "infoq-fig8-funnel.png" in art and "infoq-fig3-funnel.png" not in art


def test_the_matrix_chart_reads_the_tracked_matrix_and_the_cadec_report():
    """"Does it hold beyond CADEC?" is a chart now (Figure 5, 2026-09-08): every
    corpus x model cell of the tracked matrix.csv on two axes — how often the
    free check's ACCEPT lane fires (`occupancy`) and how often what lands there
    is right (`correctness`) — with CADEC's three draws from the report as the
    reference. The matrix carries FOUR model families (qwen3 never produced a
    scorable cell, per scripts/score_matrix.py), so the section says four."""
    import csv
    src = FIGS.read_text()
    assert "infoq-fig9-matrix" in src and "matrix.csv" in src and '["lanes"]' in src
    assert (HERE_FIGS / "infoq-fig9-matrix.png").is_file()
    rows = list(csv.DictReader((ROOT / "matrix.csv").open()))
    assert len(rows) == 28 and len({r["model"] for r in rows}) == 4
    corpora = {r["corpus"] for r in rows}
    assert corpora == {"bc5cdr", "finer", "geo", "lgl", "linnaeus", "psytar", "trnews"}
    clinical = [r for r in rows if r["corpus"] in ("psytar", "bc5cdr")]
    gaz = [r for r in rows if r["corpus"] in ("geo", "lgl", "trnews")]
    assert all(0.07 <= float(r["occupancy"]) <= 0.32 and float(r["correctness"]) >= 0.80 for r in clinical)
    assert all(0.20 <= float(r["occupancy"]) <= 0.75 and float(r["correctness"]) <= 0.26 for r in gaz)
    assert all(float(r["occupancy"]) == 0.0 for r in rows if r["corpus"] == "finer")
    # Removed from the article at the owner's request (2026-09-08): the section
    # is about whether each lesson holds, not about performance. The chart is
    # kept in the script and README as the repository's view of the matrix.
    art = (ROOT / "docs" / "article-infoq-CADEC.md").read_text()
    sec = art.split("## Does it hold beyond CADEC?", 1)[1].split("\n## ", 1)[0]
    assert "infoq-fig9-matrix.png" not in art and "Figure 5" not in art
    assert "five model families" not in sec and "four model families" in sec

"""Figures for docs/article-infoq-CADEC.md.

Two of the three are Graphviz tables in the house style of fig7-pipeline-cadec
(infoq-fig1-ladder.dot, infoq-fig3-funnel.dot); this script renders them with
`dot` and draws the third, the dial, with Matplotlib in the same palette.

Every number is read from the tracked report
runs/archive/consolidated-2026-09-03/rerun/cadec.json — the `shipping_rules`
section per draw and `shipping_rules_mean` over the three draws, written by
scripts/rerun_analysis.py from ladder.analysis.shipping_rules. Nothing is typed
in here except labels, colours and label positions. Run from anywhere:

    .venv/bin/python docs/figures/make_infoq_figs.py

Needs matplotlib and the `dot` binary (Graphviz); see docs/figures/README.md.
"""
import json
import subprocess
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).resolve().parent
REPORT = HERE.parent.parent / "runs" / "archive" / "consolidated-2026-09-03" / "rerun" / "cadec.json"
report = json.loads(REPORT.read_text())
MEAN = {r["rule"]: r for r in report["shipping_rules_mean"]}
FIRST = {r["rule"]: r for r in report["draws"]["rerun-cadec-d0"]["shipping_rules"]}
N_FIRST = report["draws"]["rerun-cadec-d0"]["final"]["n"]
# tokens the extractor alone spends per run (rung 0), mean over the draws
R0_TOKENS = sum(d["cost"]["0"]["tokens"] for d in report["draws"].values()) / len(report["draws"])

# House palette, from fig7-pipeline-cadec.dot
MODEL = "#0c6469"   # teal  - a language model runs here
FREE = "#3a464c"    # grey  - deterministic, no model (darkened 2026-09-08 for print)
INK = "#121a1e"
RULE = "#c8d1d5"
plt.rcParams.update({"font.family": ["Helvetica", "Arial", "DejaVu Sans"],
                     "font.size": 12, "axes.edgecolor": FREE, "text.color": INK,
                     "axes.labelcolor": INK, "xtick.color": INK, "ytick.color": INK})

# ---------- Graphviz tables ----------
for name in ("infoq-fig1-ladder", "infoq-fig3-funnel", "infoq-fig4-flow", "fig7-pipeline-cadec", "infoq-fig6-pipeline-flow"):
    subprocess.run(["dot", "-Tpng", "-Gdpi=200", str(HERE / f"{name}.dot"),
                    "-o", str(HERE / f"{name}.png")], check=True)

# ---------- the dial ----------
# rule -> label, colour, label position (x, y, ha). The numbers — share shipped,
# accuracy of what ships, extra tokens — are the three-draw means from the report.
DIAL = [
    ("everything_after_r3", "ship everything\n(extractor alone, {r0k}k)", MODEL, (97, 0.32, "right")),
    ("accept", "vocabulary match, strict\n(shipped)", FREE, (27, 0.825, "left")),
    ("accept_contained", "vocabulary match, loose\n(contained)", FREE, (44, 0.685, "left")),
    ("r3_unanimous", "vote: all 3 agree\n(voting)", MODEL, (44, 0.545, "right")),
    ("r3_two_agree", "vote: 2 of 3 agree\n(voting)", MODEL, (88, 0.515, "left")),
    ("r4_blind_pass", "blind judge passes\n(judge)", MODEL, (49, 0.425, "right")),
    ("r4_menu_pass", "menu-shown judge passes\n(judge)", MODEL, (64, 0.625, "left")),
]
n_mean = MEAN["everything"]["ships"]
rows = [(label.format(r0k=round(R0_TOKENS / 1000)), 100 * MEAN[rule]["ships"] / n_mean,
         MEAN[rule]["accuracy"], MEAN[rule]["extra_tokens"], col, pos)
        for rule, label, col, pos in DIAL]
fig, ax = plt.subplots(figsize=(8.0, 5.8))
for name, ships, acc, tok, col, (lx, ly, ha) in rows:
    size = 60 + tok / 1500
    ax.scatter(ships, acc, s=size, color=col, alpha=0.9, edgecolor="white", linewidth=1.5, zorder=3)
    if name.startswith("ship everything"):
        lab = f"{name}\nno extra tokens"
    else:
        lab = f"{name}\n{tok/1000:.0f}k tokens" if tok else f"{name}\n0 tokens"
    ax.annotate(lab, (ships, acc), xytext=(lx, ly), fontsize=8.5, ha=ha, va="center", color=INK,
                arrowprops=dict(arrowstyle="-", color=RULE, lw=0.8, shrinkB=6), zorder=2)
# iso-yield curves: yield = share shipped x accuracy of what ships
x = np.linspace(12, 104, 300)
for y in [0.25, 0.35]:
    ax.plot(x, y / (x / 100), ls=":", color=RULE, lw=1, zorder=1)
ax.set_xlim(10, 110)
ax.set_ylim(0.27, 0.9)
ax.set_xlabel("share of records shipped (%)")
ax.set_ylabel("accuracy of what ships")
ax.set_title("Every layer's verdict is a setting of one dial. Dotted curves: constant yield (0.25, 0.35).",
             fontsize=11, loc="left", color=INK)
ax.spines[["top", "right"]].set_visible(False)
ax.grid(alpha=0.25, color=RULE)
h = [plt.Line2D([], [], marker="o", ls="", color=MODEL, ms=9),
     plt.Line2D([], [], marker="o", ls="", color=FREE, ms=9)]
ax.legend(h, ["a model decides", "no model: deterministic"], loc="upper right", frameon=False, fontsize=9)
plt.tight_layout()
plt.savefig(HERE / "infoq-fig2-dial.png", dpi=200)
plt.close()
print("ok")

# ---------- the shipped set under each rule ----------
# rerun-cadec-d0 (the first run), each rule's row from the report: what ships,
# split four ways by the state file's exact and overlap outcomes (right code on
# the exact span / exact span, wrong code / right code, boundary off / neither),
# what goes to a person and how many of those were right, and F1 span-exact on
# the shipped subset against the 226 annotated mentions. The article's table
# gives the three-run means from the same section.
GREEN, GREEN_LT, TEAL_LT, WRONG, PERSON, PERSON_EDGE = "#2d6a4f", "#a9cfb6", "#bfdfe1", "#c8d1d5", "#fdf0c8", "#946c00"
SHIPPED = [
    ("everything_after_r3", "ship everything\n(the extractor's answer)"),
    ("accept", "vocabulary check says ACCEPT\n(the run's setting)"),
    ("accept_contained", "loose vocabulary check says ACCEPT"),
    ("r3_unanimous", "all 3 voting samples agree"),
    ("r3_two_agree", "2 of 3 voting samples agree"),
    ("r4_blind_pass", "blind judge passes"),
    ("r4_menu_pass", "menu-shown judge passes"),
]
rules = [  # name, both right, span only, code only, neither, to a person, (correct among them), F1
    (label, FIRST[rule]["correct"], FIRST[rule]["span_only"], FIRST[rule]["code_only"], FIRST[rule]["neither"],
     FIRST[rule]["to_person"], FIRST[rule]["person_correct"], FIRST[rule]["f1"])
    for rule, label in SHIPPED
]
fig, ax = plt.subplots(figsize=(10.4, 5.6))
ys = np.arange(len(rules))[::-1]
for y, (name, c, s, k, w, p, pc, f) in zip(ys, rules):
    left = 0
    for val, col, edge in ((c, GREEN, GREEN), (s, GREEN_LT, GREEN_LT), (k, TEAL_LT, TEAL_LT), (w, WRONG, WRONG), (p, PERSON, PERSON_EDGE)):
        if val:
            ax.barh(y, val, left=left, color=col, edgecolor=edge, linewidth=0.8, height=0.62, zorder=3)
            if val >= 12:
                ax.text(left + val / 2, y, str(val), ha="center", va="center", fontsize=10.5,
                        color="white" if col == GREEN else INK, zorder=4)
            left += val
    # Only what the table cannot show: the withheld records and how many of
    # them were correct. Ships and F1 per rule are the table's, as three-run
    # means; printing the first run's beside them was the same row twice with
    # different numbers.
    if p:
        ax.text(N_FIRST + 3, y, f"{p} to a person, {pc} correct", va="center", fontsize=10, color=FREE)
# reference lines: the most any rule ships with the right code on the exact span,
# and the most it ships on an exact span at all (right or wrong code)
best_code = max(r[1] for r in rules); best_span = max(r[1] + r[2] for r in rules)
for x, lab, ha, dx in ((best_code, f"most right code, exact span · {best_code}", "right", -1.5),
                       (best_span, f"{best_span} · most exact span, any code", "left", 1.5)):
    ax.axvline(x, ls=":", color="#b3bec3", lw=1, zorder=2)
    ax.text(x + dx, len(rules) - 0.4, lab, fontsize=9.5, color=FREE, va="bottom", ha=ha)
ax.set_ylim(-0.6, len(rules) + 0.15)
ax.set_yticks(ys); ax.set_yticklabels([r[0] for r in rules], fontsize=11)
ax.set_xlim(0, N_FIRST); ax.set_xticks([0, 50, 100, 150, 200, N_FIRST])
ax.set_xlabel(f"records, first run ({N_FIRST})")
for sp in ("top", "right"): ax.spines[sp].set_visible(False)
ax.tick_params(axis="y", length=0)
from matplotlib.patches import Patch
ax.legend(handles=[Patch(color=GREEN, label="ships · right code, exact span"),
                   Patch(color=GREEN_LT, label="ships · exact span, wrong code"),
                   Patch(color=TEAL_LT, label="ships · right code, boundary off"),
                   Patch(color=WRONG, label="ships · neither"),
                   Patch(facecolor=PERSON, edgecolor=PERSON_EDGE, label="to a person")],
          loc="lower center", bbox_to_anchor=(0.42, -0.5), ncol=3, frameon=False, fontsize=10)
ax.set_title("What ships under each rule, first run, and what a person receives", loc="left", fontsize=13, pad=10)
plt.tight_layout()
plt.savefig(HERE / "infoq-fig5-shipped.png", dpi=200, bbox_inches="tight")
print("ok shipped")

# ---------- the three ways to get a code (Figure 4) ----------
# One dot per cold run: F1 span-exact of the extractor alone under each of the
# three rung-0 steps, read from the three tracked reports. Tokens per run and
# parse failures come from the same reports' rung-0 aggregates. Replaces the
# three-column table under "We chose this shape" (2026-09-08).
STEPS = [
    ("cadec-s0", "recall the code", "the model writes the code\nfrom memory"),
    ("cadec-s1", "name the concept", "the model names it;\na lookup finds the code"),
    ("cadec", "pick from a menu", "the model picks a line;\na lookup finds the code"),
]
rows = []
for stem, title, how in STEPS:
    draws = json.loads((REPORT.parent / f"{stem}.json").read_text())["draws"]
    f1 = [d["rung0"]["exact"]["f1"] for d in draws.values()]
    toks = [d["aggregates"]["0"]["tokens_in"] + d["aggregates"]["0"]["tokens_out"] for d in draws.values()]
    fails = [d["aggregates"]["0"]["parse_failed"] for d in draws.values()]
    docs = draws[next(iter(draws))]["aggregates"]["0"]["documents"]
    rows.append((title, how, f1, toks, fails, docs))

fig, ax = plt.subplots(figsize=(10.2, 5.2))
xs = np.arange(len(rows))
for x, (title, how, f1, toks, fails, docs) in zip(xs, rows):
    shipped = title == "pick from a menu"
    col = MODEL if shipped else FREE
    for i, v in enumerate(f1):
        ax.plot(x + (i - 1) * 0.12, v, "o", ms=11, color=col, zorder=3)
    ax.plot([x - 0.22, x + 0.22], [np.median(f1)] * 2, color=col, lw=1.2, zorder=2)
    lo, hi = min(f1), max(f1)
    ax.text(x + 0.3, np.median(f1), f"{lo:.2f}–{hi:.2f}" if hi - lo >= 0.005 else f"{lo:.2f}",
            va="center", ha="left", fontsize=11, color=INK)
    tk = f"{min(toks)//1000:,}k" if max(toks) - min(toks) < 2000 else f"{min(toks)//1000:,}k–{max(toks)//1000:,}k"
    if len(set(fails)) == 1:
        pf = f"{fails[0]} of {docs} replies unparseable, every run" if fails[0] else "every reply parsed"
    else:
        pf = "unparseable replies: " + " · ".join(str(p) for p in fails)
    ax.text(x, -0.30, f"{tk} tokens per run\n{pf}",
            ha="center", va="top", fontsize=9.5, color=FREE, transform=ax.get_xaxis_transform())
ax.set_xticks(xs)
ax.set_xticklabels([f"{t}{'  (shipped)' if t == 'pick from a menu' else ''}\n{h}" for t, h, *_ in rows], fontsize=10.5)
ax.set_xlim(-0.6, len(rows) - 0.3)
ax.set_ylim(0, 0.5); ax.set_yticks([0, 0.1, 0.2, 0.3, 0.4, 0.5])
ax.set_ylabel("F1, span-exact (0 to 1), one dot per cold run", fontsize=10.5)
for sp in ("top", "right"): ax.spines[sp].set_visible(False)
ax.grid(axis="y", alpha=0.25, color=RULE)
ax.tick_params(axis="x", length=0, pad=8)
ax.set_title("Three ways to get the code, 40 development documents, three cold runs each", loc="left", fontsize=12, pad=10)
plt.subplots_adjust(bottom=0.40)
plt.savefig(HERE / "infoq-fig7-variants.png", dpi=200, bbox_inches="tight")
print("ok variants")

# ---------- the funnel (Figure 4) ----------
# Where the first draw's annotated mentions go, from the report's `budget`
# block: found on the exact span, right concept on the menu, right line
# picked. The finding loss splits into never touched (missed under overlap
# matching) and wrong boundary (matched under overlap but not exact).
# Replaces the hand-written infoq-fig3-funnel.dot table (2026-09-08).
bud = report["draws"]["rerun-cadec-d0"]["budget"]
ex, ov = bud["exact"], bud["overlap"]
stages = [
    ("annotated mentions", ex["n_gold"], FREE, ""),
    ("quoted on the exact span", ex["matched"], MODEL, "1 · FIND, model"),
    ("right concept on the 20-line menu", ex["on_menu"], FREE, "RETRIEVE, no model"),
    ("right line picked", ex["correct"], MODEL, "2 · PICK, model"),
]
losses = [
    f"−{ex['n_gold'] - ex['matched']} not quoted as annotated:\n{ov['missed']} never touched, {ov['matched'] - ex['matched']} wrong boundary",
    f"−{ex['matched'] - ex['on_menu']} right concept not retrieved",
    f"−{ex['on_menu'] - ex['correct']} wrong line chosen",
]
fig, ax = plt.subplots(figsize=(10.2, 4.9))
ys = np.arange(len(stages))[::-1]
for y, (label, n, col, who) in zip(ys, stages):
    ax.barh(y, n, color=col, height=0.58, zorder=3, alpha=0.9 if col == MODEL else 0.75)
    ax.text(n + 3, y, str(n), va="center", ha="left", fontsize=13, color=INK, fontweight="bold")
    ax.text(-4, y, label + (f"\n{who}" if who else ""), va="center", ha="right", fontsize=11,
            color=col if who else INK)
for i, text in enumerate(losses):
    y_top, y_bot = ys[i], ys[i + 1]
    n_top, n_bot = stages[i][1], stages[i + 1][1]
    ax.annotate("", xy=(n_bot, y_bot + 0.32), xytext=(n_top, y_top - 0.32),
                arrowprops=dict(arrowstyle="-", color="#946c00", lw=1.2, ls=":"), zorder=2)
    ax.text(max(n_top, n_bot) + 3, (y_top + y_bot) / 2, text, va="center", ha="left", fontsize=10,
            color="#7a5800")
ax.set_xlim(0, ex["n_gold"] * 1.55); ax.set_ylim(-0.7, len(stages) - 0.3)
ax.set_yticks([]); ax.set_xticks([])
for sp in ax.spines.values(): sp.set_visible(False)
plt.subplots_adjust(left=0.30, top=0.84)
fig.text(0.5, 0.95, f"One extractor, gpt-oss:20b, first run: of {ex['n_gold']} annotated mentions, how many each stage keeps\n"
         f"each bar is what the stage above passed on; the dotted steps are the losses; {ex['correct']} answered right",
         ha="center", va="top", fontsize=12, color=INK)
plt.savefig(HERE / "infoq-fig8-funnel.png", dpi=200, bbox_inches="tight")
print("ok funnel")

# ---------- the free check across corpora (Figure 5) ----------
# Every corpus x model cell of the tracked matrix.csv (scripts/score_matrix.py
# over runs/archive/matrix-2026-09-07/) on two axes: how often the ACCEPT lane
# fires and how often what lands there is right. CADEC's three draws come from
# the report's `lanes` block (ACCEPT n / final n, ACCEPT correct_pct) as the
# reference point; it ran on different hardware and is drawn hollow.
import csv
MATRIX = HERE.parent.parent / "matrix.csv"
cells = list(csv.DictReader(MATRIX.open()))
FAMILY = {  # corpus -> (label, vocabulary family)
    "psytar": ("PsyTAR", "clinical"), "bc5cdr": ("BC5CDR", "clinical"),
    "geo": ("GeoWebNews", "gazetteer"), "lgl": ("LGL", "gazetteer"), "trnews": ("TR-News", "gazetteer"),
    "linnaeus": ("LINNAEUS", "taxonomy"), "finer": ("FiNER-139", "tags"),
}
FAM_COL = {"clinical": "#2d6a4f", "gazetteer": "#946c00", "taxonomy": FREE, "tags": "#a33333"}
fig, ax = plt.subplots(figsize=(9.6, 6.0))
seen = set()
for c in cells:
    label, fam = FAMILY[c["corpus"]]
    x = 100 * float(c["occupancy"]); y = 100 * float(c["correctness"]) if c["correctness"] else 0.0
    if c["corpus"] == "finer" or (c["corpus"] == "linnaeus" and c["accept"] == "0"):
        y = 0.0  # the lane never fired: nothing to be right about
    ax.plot(x, y, "o", ms=10, color=FAM_COL[fam], alpha=0.85, zorder=3,
            label=f"{fam} vocabulary" if fam not in seen else None)
    seen.add(fam)
cadec = [(100 * d["lanes"]["ACCEPT"]["n"] / d["final"]["n"], d["lanes"]["ACCEPT"]["correct_pct"])
         for d in report["draws"].values()]
for i, (x, y) in enumerate(cadec):
    ax.plot(x, y, "o", ms=11, mfc="white", mec="#2d6a4f", mew=2, zorder=4,
            label="CADEC, three runs (reference: different hardware)" if i == 0 else None)
# one label per corpus, placed by hand beside its cells (positions only; no data)
LABEL_AT = {"psytar": (32.5, 83), "bc5cdr": (6, 102.5), "geo": (46.5, 26.5), "lgl": (65.5, 29.5),
            "trnews": (63, 5), "linnaeus": (13.5, 74.5)}
for corpus, (x, y) in LABEL_AT.items():
    label, fam = FAMILY[corpus]
    ax.text(x, y, label, fontsize=10.5, color=FAM_COL[fam], fontweight="bold")
ax.text(25.5, 73, "CADEC", fontsize=10.5, color="#2d6a4f", fontweight="bold")
never = sum(1 for c in cells if c["accept"] == "0")
ax.annotate(f"lane never fired: FiNER-139 on every model,\nLINNAEUS on 3 of 4 ({never} cells at the origin)",
            xy=(0, 0), xytext=(4, 8), fontsize=9.5, color=FREE,
            arrowprops=dict(arrowstyle="-", color=FREE, lw=0.8))
ax.set_xlim(-3, 80); ax.set_ylim(-4, 104)
ax.set_xlabel("how often the free check says ACCEPT (percent of records)", fontsize=11)
ax.set_ylabel("how often an ACCEPT is right (percent)", fontsize=11)
for sp in ("top", "right"): ax.spines[sp].set_visible(False)
ax.grid(alpha=0.25, color=RULE)
ax.legend(loc="center right", frameon=False, fontsize=9.5, bbox_to_anchor=(1.0, 0.55))
ax.set_title("The free check on seven corpora and four model families, one run per cell:\nclinical vocabularies give a small lane that is right, gazetteers a large lane that is wrong",
             loc="left", fontsize=11.5, pad=10)
plt.tight_layout()
plt.savefig(HERE / "infoq-fig9-matrix.png", dpi=200, bbox_inches="tight")
print("ok matrix")

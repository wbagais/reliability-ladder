"""Figures for docs/article-infoq-CADEC.md.

Two of the three are Graphviz tables in the house style of fig7-pipeline-cadec
(infoq-fig1-ladder.dot, infoq-fig3-funnel.dot); this script renders them with
`dot` and draws the third, the dial, with Matplotlib in the same palette.

Every number is from the base run rerun-cadec-d0/d1/d2 (2026-09-03) as quoted
in docs/article-v3-CADEC.md; means over the three draws. Run from anywhere:

    .venv/bin/python docs/figures/make_infoq_figs.py
"""
import subprocess
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).resolve().parent

# House palette, from fig7-pipeline-cadec.dot
MODEL = "#0c6469"   # teal  - a language model runs here
FREE = "#5a6b73"    # grey  - deterministic, no model
INK = "#121a1e"
RULE = "#c8d1d5"
plt.rcParams.update({"font.family": ["Helvetica", "Arial", "DejaVu Sans"],
                     "font.size": 10, "axes.edgecolor": FREE, "text.color": INK,
                     "axes.labelcolor": INK, "xtick.color": INK, "ytick.color": INK})

# ---------- Graphviz tables ----------
for name in ("infoq-fig1-ladder", "infoq-fig3-funnel", "infoq-fig4-flow"):
    subprocess.run(["dot", "-Tpng", "-Gdpi=200", str(HERE / f"{name}.dot"),
                    "-o", str(HERE / f"{name}.png")], check=True)

# ---------- the dial ----------
# name, ships %, accuracy of what ships, tokens per run, colour, label position (x, y, ha)
rows = [
    ("ship everything\n(extractor alone, 155k)", 100, 0.39, 155000, MODEL, (97, 0.32, "right")),
    ("vocabulary match, strict\n(shipped)", 22, 0.77, 0, FREE, (27, 0.825, "left")),
    ("vocabulary match, loose\n(contained)", 39, 0.61, 0, FREE, (44, 0.685, "left")),
    ("vote: all 3 agree\n(voting)", 50, 0.50, 420000, MODEL, (44, 0.545, "right")),
    ("vote: 2 of 3 agree\n(voting)", 80, 0.43, 420000, MODEL, (88, 0.515, "left")),
    ("blind judge passes\n(judge)", 59, 0.47, 84000, MODEL, (49, 0.425, "right")),
    ("menu-shown judge passes\n(judge)", 61, 0.54, 84000, MODEL, (64, 0.625, "left")),
]
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
# rerun-cadec-d0 (first run), records as they stood after voting (88 correct of
# 230). For each "ship only when…" rule: what ships, split four ways by the state
# file's exact and overlap outcomes — right code on the exact span / exact span,
# wrong or no code / right code, boundary off (exact-unmatched, overlap-correct) /
# neither — and what goes to a person. F1 is span-exact on the shipped subset
# against 226 annotated mentions. Counts from scratchpad bars2.py over the archive;
# the article's table gives three-run means. Runs 1 and 2 differ by a few records.
GREEN, GREEN_LT, TEAL_LT, WRONG, PERSON, PERSON_EDGE = "#2d6a4f", "#a9cfb6", "#bfdfe1", "#c8d1d5", "#fdf0c8", "#946c00"
rules = [  # name, both right, span only, code only, neither, to a person, (correct among them), F1
    ("ship everything\n(the extractor's answer)", 88, 28, 23, 91, 0, 0, 0.397),
    ("vocabulary check says ACCEPT\n(the run's setting)", 39, 2, 0, 12, 177, 49, 0.283),
    ("loose vocabulary check says ACCEPT", 53, 5, 8, 25, 139, 35, 0.340),
    ("all 3 voting samples agree", 51, 13, 15, 29, 122, 37, 0.315),
    ("2 of 3 voting samples agree", 77, 22, 21, 65, 45, 11, 0.387),
    ("blind judge passes", 63, 16, 15, 42, 94, 25, 0.357),
    ("menu-shown judge passes", 74, 9, 14, 39, 94, 14, 0.420),
]
fig, ax = plt.subplots(figsize=(8.6, 4.8))
ys = np.arange(len(rules))[::-1]
for y, (name, c, s, k, w, p, pc, f) in zip(ys, rules):
    left = 0
    for val, col, edge in ((c, GREEN, GREEN), (s, GREEN_LT, GREEN_LT), (k, TEAL_LT, TEAL_LT), (w, WRONG, WRONG), (p, PERSON, PERSON_EDGE)):
        if val:
            ax.barh(y, val, left=left, color=col, edgecolor=edge, linewidth=0.8, height=0.62, zorder=3)
            if val >= 12:
                ax.text(left + val / 2, y, str(val), ha="center", va="center", fontsize=8,
                        color="white" if col == GREEN else INK, zorder=4)
            left += val
    ships = c + s + k + w
    ax.text(233, y, f"ships {ships} · F1 {f:.3f}" + (f" · {p} to a person, {pc} correct" if p else ""),
            va="center", fontsize=8, color=FREE)
# reference lines: the most any rule ships with the right code on the exact span,
# and the most it ships on an exact span at all (right or wrong code)
best_code = max(r[1] for r in rules); best_span = max(r[1] + r[2] for r in rules)
for x, lab, ha, dx in ((best_code, f"most right code, exact span · {best_code}", "right", -1.5),
                       (best_span, f"{best_span} · most exact span, any code", "left", 1.5)):
    ax.axvline(x, ls=":", color="#b3bec3", lw=1, zorder=2)
    ax.text(x + dx, len(rules) - 0.4, lab, fontsize=7.5, color=FREE, va="bottom", ha=ha)
ax.set_ylim(-0.6, len(rules) + 0.15)
ax.set_yticks(ys); ax.set_yticklabels([r[0] for r in rules], fontsize=8.5)
ax.set_xlim(0, 230); ax.set_xticks([0, 50, 100, 150, 200, 230])
ax.set_xlabel("records, first run (230)")
for sp in ("top", "right"): ax.spines[sp].set_visible(False)
ax.tick_params(axis="y", length=0)
from matplotlib.patches import Patch
ax.legend(handles=[Patch(color=GREEN, label="ships · right code, exact span"),
                   Patch(color=GREEN_LT, label="ships · exact span, wrong code"),
                   Patch(color=TEAL_LT, label="ships · right code, boundary off"),
                   Patch(color=WRONG, label="ships · neither"),
                   Patch(facecolor=PERSON, edgecolor=PERSON_EDGE, label="to a person")],
          loc="lower center", bbox_to_anchor=(0.42, -0.5), ncol=3, frameon=False, fontsize=8)
ax.set_title("What ships under each rule, and what a person receives", loc="left", fontsize=10, pad=10)
plt.tight_layout()
plt.savefig(HERE / "infoq-fig5-shipped.png", dpi=200, bbox_inches="tight")
print("ok shipped")

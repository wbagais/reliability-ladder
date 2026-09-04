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
for name in ("infoq-fig1-ladder", "infoq-fig3-funnel"):
    subprocess.run(["dot", "-Tpng", "-Gdpi=200", str(HERE / f"{name}.dot"),
                    "-o", str(HERE / f"{name}.png")], check=True)

# ---------- the dial ----------
# name, ships %, accuracy of what ships, tokens per run, colour, label position (x, y, ha)
rows = [
    ("ship everything\n(rung 0)", 100, 0.39, 155000, MODEL, (97, 0.32, "right")),
    ("vocabulary match, strict\n(rung 1, shipped)", 22, 0.77, 0, FREE, (27, 0.825, "left")),
    ("vocabulary match, loose\n(rung 1, contained)", 39, 0.61, 0, FREE, (44, 0.685, "left")),
    ("vote: all agree\n(rung 3)", 61, 0.49, 420000, MODEL, (66, 0.465, "left")),
    ("vote: two agree\n(rung 3)", 80, 0.43, 420000, MODEL, (88, 0.515, "left")),
    ("blind judge passes\n(rung 4)", 59, 0.47, 84000, MODEL, (49, 0.425, "right")),
    ("menu-shown judge passes\n(rung 4)", 61, 0.54, 84000, MODEL, (64, 0.625, "left")),
]
fig, ax = plt.subplots(figsize=(8.0, 5.8))
for name, ships, acc, tok, col, (lx, ly, ha) in rows:
    size = 60 + tok / 1500
    ax.scatter(ships, acc, s=size, color=col, alpha=0.9, edgecolor="white", linewidth=1.5, zorder=3)
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

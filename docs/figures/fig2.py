import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import PercentFormatter

layers = ["bare\nmodel", "checks", "self-\ncorrect", "vote", "judge", "refuse"]
acc = [0.371, 0.371, 0.371, 0.367, 0.367, 0.808]
cov = [1.00, 1.00, 1.00, 1.00, 1.00, 0.21]
tok = [164897, 0, 548, 425355, 92687, 0]

fig, (ax, bx) = plt.subplots(
    2, 1, figsize=(11, 7.2), sharex=True,
    gridspec_kw={"height_ratios": [2.1, 1], "hspace": 0.12})

x = range(len(layers))

ax.plot(x, acc, marker="o", ms=8, lw=2.4, color="#2d6a4f", label="accuracy on answered records", zorder=3)
ax.plot(x, cov, marker="s", ms=7, lw=2.2, color="#a33333", ls="--", label="coverage (share still answered)", zorder=3)

ax.annotate("flat across four layers — two of them paid",
            xy=(2, 0.371), xytext=(0.35, 0.235), fontsize=10.5, color="#333",
            arrowprops=dict(arrowstyle="-", color="#999", lw=1))
ax.annotate("accuracy rises only by\nanswering 79% less often",
            xy=(5, 0.808), xytext=(3.15, 0.885), fontsize=10.5, color="#2d6a4f",
            arrowprops=dict(arrowstyle="->", color="#2d6a4f", lw=1.4))
ax.annotate("voting moves it\nbackwards", xy=(3, 0.367), xytext=(2.55, 0.50),
            fontsize=10, color="#a33333",
            arrowprops=dict(arrowstyle="->", color="#a33333", lw=1.2))

ax.set_ylim(0.15, 1.06)
ax.yaxis.set_major_formatter(PercentFormatter(1.0, decimals=0))
ax.set_ylabel("accuracy · coverage", fontsize=11)
ax.legend(loc="center left", frameon=False, fontsize=10.5)
ax.grid(axis="y", color="#e8e8e8", lw=0.9)
ax.set_axisbelow(True)
for s in ("top", "right"):
    ax.spines[s].set_visible(False)
ax.spines["left"].set_color("#bbb")
ax.spines["bottom"].set_color("#bbb")

colors = ["#bbbbbb", "#2d6a4f", "#e0b84a", "#c8892a", "#e0b84a", "#2d6a4f"]
bars = bx.bar(x, [t / 1000 for t in tok], color=colors, width=0.55)
for i, t in enumerate(tok):
    lbl = "0" if t == 0 else f"{t:,}"
    bx.text(i, t / 1000 + 12, lbl, ha="center", fontsize=9.5,
            color="#2d6a4f" if t == 0 else "#444")
bx.set_ylabel("tokens (thousands)", fontsize=11)
bx.set_ylim(0, 500)
bx.set_xticks(list(x))
bx.set_xticklabels(layers, fontsize=10.5)
bx.grid(axis="y", color="#e8e8e8", lw=0.9)
bx.set_axisbelow(True)
for s in ("top", "right"):
    bx.spines[s].set_visible(False)
bx.spines["left"].set_color("#bbb")
bx.spines["bottom"].set_color("#bbb")

fig.savefig("fig2-flat.png", dpi=150, bbox_inches="tight", facecolor="white")
print("written")

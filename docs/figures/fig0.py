import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Circle, FancyBboxPatch

GREEN, AMBER, GREY, RED = "#2d9e5f", "#e8b13a", "#c9c9c9", "#c94f4f"

# rung 0..6 : (label, colour, note)
RUNGS = [
    ("0  extract",      GREY,  ""),
    ("1  check",        GREEN, "free · 85% lane"),
    ("2  self-correct", GREY,  "never had a trigger"),
    ("3  vote",         AMBER, "no consistent sign"),
    ("4  judge",        AMBER, "read by nothing \u00b7 provisional"),
    ("5  refuse",       GREEN, "63 -> 4 err / 100"),
    ("6  person",       GREY,  "196 of 248"),
]

fig, ax = plt.subplots(figsize=(11.2, 5.0))
ax.set_xlim(0, 11.2); ax.set_ylim(0, 5.0); ax.axis("off")
fig.patch.set_facecolor("white")

def bead(x, y, r, c, edge="#00000022"):
    ax.add_patch(Circle((x, y), r, facecolor=c, edgecolor=edge, lw=1.2, zorder=3))
    # the hole, which is what makes a pony bead read as a bead
    ax.add_patch(Circle((x, y), r * 0.34, facecolor="white", edgecolor="#00000018",
                        lw=0.8, zorder=4))
    # highlight
    ax.add_patch(Circle((x - r*0.32, y + r*0.34), r * 0.20, facecolor="#ffffff88",
                        edgecolor="none", zorder=5))

# ---- the ladder: two green stiles, seven coloured rungs ----------------
x0, x1 = 6.05, 8.05
y_bot, y_top = 0.55, 4.55
n = len(RUNGS)
ys = [y_bot + i * (y_top - y_bot) / (n - 1) for i in range(n)]
R = 0.235

for i, (label, colour, note) in enumerate(RUNGS):
    y = ys[i]
    # stiles
    bead(x0, y, R, GREEN)
    bead(x1, y, R, GREEN)
    # rung — three beads across, coloured by what the layer bought
    for k, xf in enumerate((0.30, 0.5, 0.70)):
        bead(x0 + (x1 - x0) * xf, y, R * 0.92, colour)
    # label
    ax.text(x1 + 0.40, y, label, fontsize=11.5, va="center", ha="left",
            color="#333333", fontfamily="DejaVu Sans")
    if note:
        ax.text(x1 + 2.15, y, note, fontsize=9.5, va="center", ha="left",
                color="#888888", fontfamily="DejaVu Sans", style="italic")

# ---- the letter beads --------------------------------------------------
import matplotlib.transforms as mtrans

def letter_bead(x, y, ch, face="#fdfdfd", ink="#333333", size=0.28, rot=0):
    tr = mtrans.Affine2D().rotate_deg_around(x, y, rot) + ax.transData
    ax.add_patch(FancyBboxPatch((x - size, y - size), 2*size, 2*size,
                                boxstyle="round,pad=0.02,rounding_size=0.10",
                                facecolor=face, edgecolor="#00000030", lw=1.2,
                                zorder=3, transform=tr))
    ax.text(x, y, ch, fontsize=14, ha="center", va="center", color=ink,
            fontweight="bold", zorder=4, rotation=rot, fontfamily="DejaVu Sans")

INK = ["#c0392b", "#2d9e5f", "#2471a3", "#e8b13a", "#8e44ad", "#16a085",
       "#d35400", "#2d6a4f", "#c0392b", "#2471a3", "#8e44ad"]

JIT = [3, -4, 2, -2, 5, -3, 1, -5, 3, -1, 4]
for i, ch in enumerate("AI"):
    letter_bead(0.70 + i*0.62, 3.72 + (0.04 if i else 0), ch,
                ink="#333333", rot=-6 + i*9)

word = "RELIABILITY"
for i, ch in enumerate(word):
    letter_bead(0.58 + i*0.47, 2.92 + (0.03 if i % 2 else -0.02), ch,
                ink=INK[i % len(INK)], rot=JIT[i % len(JIT)])

ax.text(0.50, 2.10, "measured rung by rung", fontsize=13, color="#777777",
        fontfamily="DejaVu Sans", style="italic")

# small key
kx, ky = 0.60, 1.42
for c, t in ((GREEN, "paid for itself"), (AMBER, "cost, changed nothing"),
             (GREY, "no measured effect")):
    bead(kx, ky, 0.16, c)
    ax.text(kx + 0.30, ky, t, fontsize=10, va="center", color="#777777",
            fontfamily="DejaVu Sans")
    ky -= 0.40

fig.savefig("fig0-hero.png", dpi=150, bbox_inches="tight", facecolor="white")
print("written")

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mp
import numpy as np

GREEN, AMBER, RED, GREY, BLUE = "#2d6a4f", "#c8892a", "#a33333", "#8a8a8a", "#3b6ea5"
LGREEN, LAMBER, LRED, LGREY = "#e3f0e6", "#fdf0c8", "#fbe4e4", "#f2f2f2"
plt.rcParams["font.family"] = "DejaVu Sans"


# ─────────────────────────────────────────────────────────── FIGURE A
# Three corpora, one pipeline. Extends Wejdan's CADEC/FiNER table.
def fig_a():
    rows = [
        ("INPUT", "one forum post",
         "10 sentences of an SEC filing", "one news article", None),
        ("1 · FIND\nmodel", 'quote the reaction\n→ "bit drowsy"',
         'quote the bare number\n→ "47.6"', 'quote the place\n→ "Brooklyn"', "model"),
        ("RETRIEVE\nno model", "embed the span, 20 nearest\n→ menu holds the answer 87%",
         "no such step — 139 tags\nfit in the prompt, always complete",
         "Jaccard over 13.4M names\n→ menu holds the answer 42.5%", None),
        ("2 · PICK\nmodel", "choose a line number\n→ 0 (of 20)",
         "choose a line number\n→ 41 (of 139)",
         "choose a line number\n→ 0 (of 20)", "model"),
        ("RESOLVE\nno model", "look the line up\n→ 271782001 |Drowsy|",
         "read the line — the tag\nname IS the answer",
         "look the line up\n→ 2173872 |Brooklyn|", None),
        ("rung 1 says", "ACCEPT 42%\nthe lane is 80–89% correct",
         "ACCEPT 0%\nspan and code share no token",
         "ACCEPT 46%\nbut the lane is WORSE than BAND", "out"),
    ]
    heads = [("CADEC", "129,675 concepts"), ("FiNER-139", "139 tags"),
             ("GeoWebNews", "13,463,738 places")]

    fig, ax = plt.subplots(figsize=(14.4, 7.4))
    ax.set_xlim(0, 14.4); ax.set_ylim(0, 7.4); ax.axis("off")
    fig.patch.set_facecolor("white")

    x0, cw, lw = 0.30, 3.98, 2.10
    y = 6.35
    for i, (h, sub) in enumerate(heads):
        cx = x0 + lw + i * cw + cw / 2
        ax.text(cx, y + 0.42, h, ha="center", fontsize=14, fontweight="bold")
        ax.text(cx, y + 0.16, sub, ha="center", fontsize=10, color=GREY)

    for r, (label, a, b, c, kind) in enumerate(rows):
        h = 0.92 if r else 0.62
        y -= h
        face = {"model": "#eef6f6", "out": LGREEN}.get(kind, "#fbfbfb")
        edge = {"model": "#3d8a8a", "out": GREEN}.get(kind, "#cccccc")
        ax.add_patch(mp.Rectangle((x0, y), lw, h, facecolor="#f0f0f0",
                                  edgecolor="#cccccc", lw=0.8))
        ax.text(x0 + lw - 0.12, y + h / 2, label, ha="right", va="center",
                fontsize=10.5, fontweight="bold", color="#444", linespacing=1.4)
        for i, txt in enumerate((a, b, c)):
            cx = x0 + lw + i * cw
            ax.add_patch(mp.Rectangle((cx, y), cw, h, facecolor=face,
                                      edgecolor=edge, lw=1.0))
            col = GREY if "no such step" in txt else "#222"
            st = "italic" if "no such step" in txt else "normal"
            ax.text(cx + 0.16, y + h / 2, txt, ha="left", va="center",
                    fontsize=10.2, color=col, style=st, linespacing=1.45)

    ax.text(x0, 0.42, "Two model calls, and neither ever sees a code: the menu carries labels only "
                      "and the answer is a position in a list.",
            fontsize=10.5, color=GREY)
    ax.text(x0, 0.16, "Everything outside the two teal rows is deterministic. "
                      "The bottom row is where the three corpora stop agreeing.",
            fontsize=10.5, color=GREY)
    fig.savefig("figA-three-corpora.png", dpi=150, bbox_inches="tight", facecolor="white")
    print("figA")


# ─────────────────────────────────────────────────────────── FIGURE B
# Where the gold goes, three corpora side by side.
def fig_b():
    """Where the gold goes, three corpora side by side.

    Drawn as a funnel rather than paired bars: each stage's bar is the SURVIVORS,
    width proportional to the original gold count, with the loss written beside
    it. An earlier version drew survivors and losses as adjacent boxes and they
    collided whenever the loss was large — which is exactly the case the figure
    exists to show.
    """
    data = [
        ("CADEC · dev, 40 docs", 226, [
            ("span found", 126, "never proposed", 100),
            ("answer on the menu", 114, "menu missed it", 12),
            ("CORRECT", 93, "picked another line", 21)]),
        ("FiNER-139 · test, 60 docs", 187, [
            ("span found", 115, "never proposed", 72),
            ("answer on the menu", 115, "the menu IS the whole\nvocabulary — it cannot miss", 0),
            ("CORRECT", 44, "picked another tag", 71)]),
        ("GeoWebNews · test, 60 docs", 636, [
            ("span found", 321, "never proposed", 315),
            ("answer on the menu", 136, "menu missed it", 185),
            ("CORRECT", 70, "picked another line", 66)]),
    ]

    fig, axes = plt.subplots(1, 3, figsize=(15.5, 6.2))
    fig.subplots_adjust(bottom=0.16, top=0.86, wspace=0.18)
    fig.patch.set_facecolor("white")

    for ax, (title, total, steps) in zip(axes, data):
        ax.set_xlim(0, 10); ax.set_ylim(0, 10); ax.axis("off")
        ax.text(0.4, 9.5, title, fontsize=12.5, fontweight="bold")
        ax.text(0.4, 9.0, f"{total} gold mentions", fontsize=10.5, color=GREY)

        # the full-width bar the funnel narrows from
        ax.add_patch(mp.Rectangle((0.4, 7.9), 9.0, 0.42,
                     facecolor="#e8e8e8", edgecolor="none"))
        ax.text(9.3, 8.11, f"{total}", ha="right", va="center",
                fontsize=10, color="#666")

        y = 6.5
        for lbl, keep, lose_lbl, lose in steps:
            w = 9.0 * keep / total
            # The stage name sits ABOVE the bar, not inside it. A short bar and
            # a long label collide, and the shortest bars are exactly the ones
            # this figure is about.
            ax.text(0.4, y + 0.68, lbl, fontsize=10.5, fontweight="bold", color="#123")
            ax.add_patch(mp.Rectangle((0.4, y), max(w, 0.25), 0.5,
                         facecolor=LGREEN, edgecolor=GREEN, lw=1.5))
            ax.text(0.4 + max(w, 0.25) + 0.18, y + 0.25, f"{keep}",
                    va="center", fontsize=11.5, fontweight="bold", color=GREEN)
            if lose:
                ax.text(0.4, y - 0.22, f"−{lose}  {lose_lbl}", va="top",
                        fontsize=9.5, color=RED, linespacing=1.35)
            else:
                ax.text(0.4, y - 0.22, lose_lbl, va="top", fontsize=9.5,
                        color=GREY, style="italic", linespacing=1.35)
            y -= 2.15

        pct = steps[-1][1] / total
        col = GREEN if pct > .35 else AMBER if pct > .15 else RED
        ax.text(0.4, 0.45, f"{pct:.0%}", fontsize=27, fontweight="bold", color=col)
        ax.text(2.6, 0.90, "of gold answered", fontsize=11, color="#444")
        ax.text(2.6, 0.50, "correctly", fontsize=11, color="#444")

    fig.text(0.09, 0.055,
             "Each bar is the survivors, to scale against that corpus's own gold count. "
             "FiNER cannot lose anything at retrieval because its 139 tags ARE the menu; it loses at the pick instead.",
             fontsize=9.5, color=GREY)
    fig.text(0.09, 0.02,
             "GeoWebNews's menu figure is recall@20 within 10 km over a 200-mention sample, and its low score prices "
             "OUR retriever — lexical, not dense — not the ladder.",
             fontsize=9.5, color=GREY)
    fig.savefig("figB-cascades.png", dpi=150, facecolor="white")
    print("figB")


# ─────────────────────────────────────────────────────────── FIGURE C
# The new finding: the ACCEPT lane inverts on a gazetteer.
def fig_c():
    corpora = ["CADEC\n(five models)", "GeoWebNews\ngpt-oss:20b",
               "GeoWebNews\nllama3.1:8b", "GeoWebNews\nmistral:7b"]
    accept = [0.846, 0.206, 0.134, 0.214]
    band = [0.359, 0.250, 0.330, 0.370]

    fig, ax = plt.subplots(figsize=(11.4, 6.6))
    fig.subplots_adjust(bottom=0.30)
    fig.patch.set_facecolor("white")
    x = np.arange(len(corpora)); w = 0.33
    ax.bar(x - w/2, accept, w, label="ACCEPT — the vocabulary uses these very words",
           color=GREEN, edgecolor="none")
    ax.bar(x + w/2, band, w, label="BAND — plausible, unverifiable",
           color=AMBER, edgecolor="none")
    for i, (a, b) in enumerate(zip(accept, band)):
        ax.text(i - w/2, a + .015, f"{a:.3f}", ha="center", fontsize=10.5, color=GREEN)
        ax.text(i + w/2, b + .015, f"{b:.3f}", ha="center", fontsize=10.5, color=AMBER)

    ax.axvspan(0.5, 3.5, color="#fbe4e4", alpha=.35, zorder=0)
    ax.text(2, .78, "the ordering reverses", ha="center", fontsize=13,
            color=RED, fontweight="bold")
    ax.text(2, .72, "on every model", ha="center", fontsize=13, color=RED,
            fontweight="bold")

    ax.set_xticks(x); ax.set_xticklabels(corpora, fontsize=11)
    ax.set_ylabel("share of records in the lane that are CORRECT", fontsize=11)
    ax.set_ylim(0, .95)
    ax.legend(frameon=False, fontsize=10.5, loc="upper right")
    ax.grid(axis="y", color="#eee", lw=.9); ax.set_axisbelow(True)
    for s in ("top", "right"): ax.spines[s].set_visible(False)
    ax.spines["left"].set_color("#ccc"); ax.spines["bottom"].set_color("#ccc")
    ax.set_title("Rung 1's free check endorses most confidently where it knows least",
                 fontsize=13.5, pad=16, loc="left")
    fig.text(.09, 0.015,
             "ACCEPT means the vocabulary uses the extracted words. On SNOMED that is evidence — little other than "
             "|Chronic pain| is called \"chronic pain\".\nOn a gazetteer it is nearly worthless: \"London\" matching an "
             "entry named \"London\" says nothing about WHICH London, and 1,117 of 2,399\ngold mentions carry a name "
             "more than one entry holds. Correctness is within 10 km of the annotators' coordinates.",
             fontsize=9.5, color=GREY, linespacing=1.6)
    fig.savefig("figC-accept-inversion.png", dpi=150, facecolor="white")
    print("figC")


# ─────────────────────────────────────────────────────────── FIGURE D
# The arm's primary result: the overlap gradient, three models, one corpus.
def fig_d():
    strata = ["identical\n\"Washington Square\"\n→ Washington Square",
              "subset\n\"Britain\"\n→ United Kingdom of…",
              "partial", "no shared token\n\"French\"\n→ Republic of France"]
    share = [40.5, 24.8, 4.9, 29.9]
    models = {"gpt-oss:20b": [.305, .158, .143, .070],
              "llama3.1:8b": [.274, .204, .182, .079],
              "mistral:7b-instruct": [.309, .140, .143, .150]}
    cols = {"gpt-oss:20b": GREEN, "llama3.1:8b": BLUE, "mistral:7b-instruct": AMBER}

    fig, (ax, bx) = plt.subplots(2, 1, figsize=(11.4, 8.4), sharex=True,
                                 gridspec_kw={"height_ratios": [3, 1], "hspace": .12})
    fig.subplots_adjust(bottom=0.24)
    fig.patch.set_facecolor("white")
    x = np.arange(4)
    # Labels are offset per series and alternate above/below, because the three
    # lines converge at the identical and no-overlap strata and a centred label
    # sits on top of its neighbour.
    off = {"gpt-oss:20b": (-0.13, 1), "llama3.1:8b": (0.0, -1),
           "mistral:7b-instruct": (0.13, 1)}
    for name, vals in models.items():
        ax.plot(x, vals, marker="o", ms=9, lw=2.4, color=cols[name], label=name)
        dx, up = off[name]
        # Only the endpoints are labelled. The middle two strata are where the
        # three lines converge, and a label there sits on its neighbour; the
        # finding is the DROP from first to last, so those are the numbers that
        # have to be readable.
        for i in (0, 3):
            ax.text(i + dx, vals[i] + up * .016, f"{vals[i]:.3f}", ha="center",
                    va="bottom" if up > 0 else "top",
                    fontsize=10, color=cols[name], fontweight="bold")

    ax.annotate("", xy=(3, .05), xytext=(0, .33),
                arrowprops=dict(arrowstyle="->", color="#bbb", lw=1.4,
                                connectionstyle="arc3,rad=0.12"))
    ax.text(1.5, .268, "roughly 4x", fontsize=12, color="#888", style="italic")
    ax.set_ylabel("correct within 10 km", fontsize=11)
    ax.set_ylim(0, .37)
    ax.legend(frameon=False, fontsize=10.5)
    ax.grid(axis="y", color="#eee", lw=.9); ax.set_axisbelow(True)
    for s in ("top", "right"): ax.spines[s].set_visible(False)
    ax.spines["left"].set_color("#ccc"); ax.spines["bottom"].set_color("#ccc")
    ax.set_title("Correctness falls with lexical overlap — one corpus, one prompt, three models",
                 fontsize=13.5, pad=16, loc="left")

    bx.bar(x, share, .55, color="#d8d8d8", edgecolor="none")
    for i, s in enumerate(share):
        bx.text(i, s + 1, f"{s}%", ha="center", fontsize=10, color=GREY)
    bx.set_ylabel("share of gold", fontsize=10.5)
    bx.set_ylim(0, 52)
    bx.set_xticks(x); bx.set_xticklabels(strata, fontsize=10, linespacing=1.5)
    bx.grid(axis="y", color="#eee", lw=.9); bx.set_axisbelow(True)
    for s in ("top", "right"): bx.spines[s].set_visible(False)
    bx.spines["left"].set_color("#ccc"); bx.spines["bottom"].set_color("#ccc")

    fig.text(.09, 0.015,
             "The axis CADEC and FiNER could only bracket, measured WITHIN one corpus with the model held constant. "
             "Those two arms are one point each,\nso the axis was confounded with task, vocabulary and prompt. Here all "
             "four regimes occur together and the gradient survives all three models.",
             fontsize=9.5, color=GREY, linespacing=1.6)
    fig.savefig("figD-overlap-gradient.png", dpi=150, facecolor="white")
    print("figD")


fig_a(); fig_b(); fig_c(); fig_d()


# ─────────────────────────────────────────────────────────── FIGURE E
# The caveat that stops a wrong reading of the geo numbers.
def fig_e():
    """How often the right answer is on the 20-line menu at all.

    The single most important caveat in the geo arm, and it was a line of text
    in figure B. Without it, geo's 0.218 reads as "the ladder does not travel";
    with it, the model is picking from a list that does not hold the answer more
    than half the time.
    """
    labels = ["CADEC\ndense retrieval\nover 129,675 concepts",
              "FiNER-139\nno retrieval —\nthe 139 tags ARE the menu",
              "GeoWebNews\nLEXICAL retrieval\nover 13,463,738 places"]
    recall = [0.870, 1.000, 0.425]
    scored = [0.410, 0.235, 0.218]
    cols = [GREEN, GREEN, RED]

    fig, ax = plt.subplots(figsize=(12.2, 6.6))
    fig.subplots_adjust(bottom=0.30, top=0.86)
    fig.patch.set_facecolor("white")

    x = np.arange(3)
    ax.bar(x, [1.0]*3, .52, color="#f0f0f0", edgecolor="none")
    ax.bar(x, recall, .52, color=[c for c in cols], edgecolor="none", alpha=.85)
    ax.bar(x, scored, .52, color="#ffffff", edgecolor="none", alpha=.0)

    for i, (r, s) in enumerate(zip(recall, scored)):
        ax.text(i, r + .022, f"{r:.1%}", ha="center", fontsize=14,
                fontweight="bold", color=cols[i])
        ax.plot([i-.26, i+.26], [s, s], color="#333", lw=2.2, zorder=5)
        # Right-hand labels run off the axis on the last bar, so the text goes
        # inside the bar there.
        if i < 2:
            ax.text(i + .30, s, f"{s:.1%} answered correctly", va="center",
                    fontsize=10, color="#333")
        else:
            ax.text(i, s - .05, f"{s:.1%}", ha="center", va="top",
                    fontsize=11, color="#fff", fontweight="bold")
            ax.text(i, s - .115, "answered correctly", ha="center", va="top",
                    fontsize=9.5, color="#fff")

    ax.annotate("", xy=(2, .425), xytext=(2, 1.0),
                arrowprops=dict(arrowstyle="<->", color=RED, lw=1.8))
    ax.text(1.60, .90, "57% of the time\nthe answer was\nnever offered",
            fontsize=11, color=RED, linespacing=1.5, fontweight="bold", ha="right")

    ax.set_xticks(x); ax.set_xticklabels(labels, fontsize=10.5, linespacing=1.6)
    ax.set_ylabel("share of gold mentions whose answer is on the 20-line menu", fontsize=11)
    ax.set_ylim(0, 1.16)
    ax.set_yticks([0, .25, .5, .75, 1.0])
    ax.set_yticklabels(["0%", "25%", "50%", "75%", "100%"])
    ax.grid(axis="y", color="#eee", lw=.9); ax.set_axisbelow(True)
    for sd in ("top", "right"): ax.spines[sd].set_visible(False)
    ax.spines["left"].set_color("#ccc"); ax.spines["bottom"].set_color("#ccc")
    ax.set_title("A model cannot pick an answer it was never shown",
                 fontsize=14, pad=18, loc="left")

    fig.text(.09, .015,
             "The system retrieves 20 candidates, then the model picks one line. This is how often the right answer was "
             "among those 20 — the black rule is how often\nthe system got it right. GeoWebNews uses LEXICAL retrieval "
             "because the dense retriever is built over a SNOMED-derived table that does not exist for a\ngazetteer; on "
             "CADEC that same substitution was measured to cost 21 points of recall. So the geo score prices OUR "
             "RETRIEVER, not the ladder.",
             fontsize=9.5, color=GREY, linespacing=1.6)
    fig.savefig("figE-menu-ceiling.png", dpi=150, facecolor="white")
    print("figE")


fig_e()

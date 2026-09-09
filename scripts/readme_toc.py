#!/usr/bin/env python3
"""
readme_toc.py — what the study FOUND, before what it is; and a contents list
that regenerates instead of rotting.

THREE PROBLEMS THIS FIXES

**1 · The README says what the project is and never what it found.** A reader
arriving from the article gets the hero, the task description, a deployment
warning, and then the three checks — several screens before a single measured
number. The findings are the reason to read on and they are currently below the
fold.

**2 · Eighteen sections and no contents.** Long enough to need one, and a
hand-written list goes stale the first time a heading changes. This one is
generated from the `##` headings themselves and can be re-run after any edit.

**3 · "Three corpora, and only two of them are yours to run"** is still the
title of a section a reader meets long before *Five more corpora*. Someone who
stops reading there concludes the study covers three corpora. It gets a forward
pointer in its first line.

    python3 scripts/readme_toc.py --dry-run
    python3 scripts/readme_toc.py          # re-run after any heading change
"""
from __future__ import annotations

import argparse
import pathlib
import re
import sys

TOC_START = "<!-- toc:start -->"
TOC_END = "<!-- toc:end -->"

FINDINGS = """
## What it found

| | |
|---|---|
| **measured** | 7 corpora · 5 model families (4B–20B) · ~50 cells · development and held-out splits |
| **the free check** *(0 tokens)* | endorses a small lane that is **76–100%** right on clinical vocabularies, a large one that is **7–26%** right on gazetteers. The bands do not overlap, and reach runs opposite to accuracy |
| **the paid layers** *(~500k tokens)* | self-correction, sampled voting and a second-model judge routed **zero** records on PsyTAR across three draws — coverage identical to the free layers alone |
| **reproducible** | every cell published as scoreable output, scoring identically from this repository alone |

**The one-line version.** Reliability layers do not make a model more accurate.
They tell you which answers to trust — and the layer that does it best costs
nothing, while the three that cost tokens changed almost no answer.

**What surprised us.** The check that reaches furthest is the one to trust
least, and the split is not about medicine: three ontologies behave alike and
three corpora built on one gazetteer behave alike, in opposite directions. What
the clinical vocabularies share is that the term and the writing are drawn from
overlapping registers — *weight gain* is both what a patient writes and what the
ontology calls it; *Britain* against *United Kingdom of Great Britain and
Northern Ireland* is not.

Full table: [**Five more corpora**](#five-more-corpora-as-additional-tests) ·
every correction, dated: [**the decision log**](docs/decisions.md)

"""


def slug(heading: str) -> str:
    """GitHub's anchor rule: lowercase, drop anything but word chars, spaces and
    hyphens, then spaces to hyphens. Generated rather than written by hand
    because a hand-written anchor breaks silently on the first retitle."""
    s = heading.strip().lower()
    s = re.sub(r"[^\w\s-]", "", s)
    return re.sub(r"\s+", "-", s).strip("-")


def build_toc(text: str) -> str:
    rows = []
    for line in text.split("\n"):
        if line.startswith("## "):
            h = line[3:].strip()
            # Skip "Contents" itself, and the findings block that sits
            # directly above it — a contents list whose first entry is
            # the section immediately preceding it reads as an error.
            if h.lower().startswith(("contents", "what it found")):
                continue
            rows.append(f"- [{h}](#{slug(h)})")
    return (f"{TOC_START}\n\n## Contents\n\n" + "\n".join(rows)
            + f"\n\n{TOC_END}\n")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    p = pathlib.Path("README.md")
    if not p.is_file():
        sys.exit("README.md not found — run from the repository root")
    s = p.read_text()
    changed = []

    # ── findings, immediately after the deployment warning ───────────
    anchor = ("> takes a corpus split identifier, never a string.\n")
    if "## What it found" in s:
        changed.append("findings block already present")
    elif anchor in s:
        s = s.replace(anchor, anchor + FINDINGS, 1)
        changed.append("findings block added after the deployment note")
    else:
        print("  MISSED  could not place the findings block — anchor moved")
        return 1

    # ── the forward pointer on the three-corpora section ─────────────
    old = "## Three corpora, and only two of them are yours to run\n\n*This is the article's scope."
    new = ("## Three corpora, and only two of them are yours to run\n\n"
           "*This is the article's scope. Six more were measured and are in "
           "[Five more corpora](#five-more-corpora-as-additional-tests) below —"
           " do not stop here and conclude the study covers three.")
    if old in s:
        s = s.replace(old, new, 1)
        changed.append("forward pointer on the three-corpora heading")
    elif "do not stop here and conclude" in s:
        changed.append("forward pointer already present")

    # ── the contents, generated ──────────────────────────────────────
    toc = build_toc(s)
    if TOC_START in s:
        s = re.sub(re.escape(TOC_START) + r".*?" + re.escape(TOC_END) + r"\n",
                   toc, s, flags=re.S)
        changed.append("contents regenerated")
    else:
        # after the findings, before the first real section
        first = s.index("\n## ", s.index("## What it found") + 10)
        s = s[:first + 1] + toc + "\n" + s[first + 1:]
        changed.append(f"contents added ({toc.count(chr(10) + '- ')} sections)")

    for c in changed:
        print(f"  ok      {c}")
    if a.dry_run:
        print("\n  --dry-run: nothing written\n")
        return 0
    p.write_text(s)
    print(f"\n  wrote README.md\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

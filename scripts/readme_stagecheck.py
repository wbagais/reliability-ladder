#!/usr/bin/env python3
"""
readme_stagecheck.py — give the three checks, and stagecheck in particular, a
place in the README that matches what they are.

WHY

`stagecheck` currently appears as one row of a table at line 577 of a 590-line
README, under a heading a reader reaches only by scrolling past the entire
study. It is the one artefact here that someone else could install and use
tomorrow: its own repository, 43 tests, no dependencies, MIT, and a mark drawn
for it. As a project submission that placement loses it.

And the link is wrong — it points at `gitlab.com/pushpdeep/stagecheck` while
the repository is on **github.com**. A dead link on the one installable thing.

WHAT THIS CHANGES

  1. the broken GitLab URL -> the GitHub one, everywhere it appears
  2. a nav link in the header, beside the article and the decision log
  3. a short section high in the README — right after the ladder table — that
     says the study produced three tools and shows stagecheck's mark
  4. the existing section near the bottom rewritten as the detail, with the
     lockup, the two fields, and what each tool is for
  5. the mark copied into docs/assets/ rather than hot-linked, because a raw
     link to another repository breaks the moment that repository moves

    python3 scripts/readme_stagecheck.py --dry-run
    python3 scripts/readme_stagecheck.py
"""
from __future__ import annotations

import argparse
import pathlib
import shutil
import sys

REPO = "https://github.com/pushpdeep/stagecheck"
SRC_ASSETS = pathlib.Path.home() / "Documents/stagecheck/assets"
DEST_ASSETS = pathlib.Path("docs/assets")
MARKS = ["lockup-once.svg", "mark.svg"]

EDITS: list[tuple[str, str, str]] = []


def edit(why: str, old: str, new: str) -> None:
    EDITS.append((why, old, new))


# ── 1 · the broken link ──────────────────────────────────────────────
edit("the stagecheck link points at GitLab; the repository is on GitHub",
     "https://gitlab.com/pushpdeep/stagecheck",
     REPO)

# ── 2 · a nav link in the header ─────────────────────────────────────
edit("stagecheck reachable from the top of the page, not only by scrolling",
     """  <a href="docs/article-v3.md">the article</a> ·
  <a href="docs/decisions.md">the decision log</a> ·
  <a href="docs/figures/">figure sources</a>""",
     """  <a href="docs/article-v3.md">the article</a> ·
  <a href="docs/decisions.md">the decision log</a> ·
  <a href="#three-checks-this-study-produced">the three checks</a> ·
  <a href="docs/figures/">figure sources</a>""")

# ── 3 · the short section, high up ───────────────────────────────────
EARLY = """## Three checks this study produced

<p align="center">
  <img src="docs/assets/lockup-once.svg" width="260"
       alt="stagecheck — a ledger spine with three rows: judged, failed, and a hatched row for records that could not be judged.">
</p>

<p align="center"><i>Every stage makes a bet. This one makes you say what it is.</i></p>

Measuring seven layers on seven corpora produced one lesson that outlived the
measurements: **a load-bearing fact recorded in one place cannot be checked, and
will eventually be wrong without saying so.** Every defect caught early here was
caught by comparing two independent records of one fact. Every defect that
reached a rented GPU was a fact written down once and never read back.

Three small tools came out of that, each answering a different question at a
different moment:

| tool | the question | when |
|---|---|---|
| [`gatecheck`](scripts/gatecheck.py) | should this corpus be run at all? | before booking a card |
| [`crosscheck`](scripts/crosscheck.py) | is it wired as it is declared? | the first line of every run |
| **[`stagecheck`](GITHUB_URL)** | **did the run mean anything?** | **after** |

**[`stagecheck`](GITHUB_URL) is a separate, installable package** — its own
repository, 43 tests, no dependencies, MIT — and the only one of the three that
knows nothing about corpora, deliberately. It records the two things a pipeline
usually does not: **the bet a stage makes**, and **the records it could not
judge**. A stage that judged 40 of 100 records and reports 95% accuracy has
reported a rate over an unnamed set; stagecheck refuses to let that go
unrecorded.

The other two are described [further down](#the-three-checks-in-detail).

"""
edit("a section high in the README, before the ladder's own detail",
     "## The ladder\n",
     EARLY.replace("GITHUB_URL", REPO) + "## The ladder\n")

# ── 4 · the section at the bottom, as the detail ─────────────────────
DETAIL = """## The three checks, in detail

Three questions at three moments. Two live in this repository; one is its own.

| tool | question | when | knows about corpora |
|---|---|---|---|
| [`gatecheck`](scripts/gatecheck.py) | should I run this? | before booking a card | yes |
| [`crosscheck`](scripts/crosscheck.py) | is it what I declared? | first line of every run | yes |
| [`stagecheck`](GITHUB_URL) | did the run mean anything? | after | **no, deliberately** |

### stagecheck

<p align="center">
  <a href="GITHUB_URL">
    <img src="docs/assets/lockup-once.svg" width="300"
         alt="stagecheck — a ledger spine with three rows: judged, failed, and a hatched row for records that could not be judged.">
  </a>
</p>

**GITHUB_URL** — 43 tests, no dependencies, MIT.

A ledger for pipeline stages that records **two fields nothing else does**: what
the stage was betting on, and how many records it could not judge. The second is
the one that matters. A rate computed over the records a stage *could* judge,
reported as though it covered all of them, is the defect this whole study kept
finding — and it is invisible in every metric that reports a percentage without
its denominator.

It knows nothing about corpora, vocabularies or language models, and it should
not. That is what makes it usable outside this study.

### gatecheck

Reads a corpus's answer key and predicts what the free check *could* endorse —
before any GPU time. On FiNER-139 it reports **0.0%** and says the arm cannot
produce a lane however good the model is, which is a full GPU arm's finding
available for nothing. On LINNAEUS it reports **4.8%** and flags it thin.

Both warnings fire on exactly the two arms that wasted the most card time before
the tool existed.

### crosscheck

Reads every declared fact back from an independent source: the rendered prompt
against the declared entity, the few-shot ids against the split the guard
actually reads, the split ids against the corpus the adapter loads, each named
model against what is installed.

Nine checks, and every one is a defect that reached a rented card first. It
found a live one within an hour of being written — a manifest whose task
description rendered as *"the abstract describes the abstract describes"*,
written an hour after the identical bug had been found, diagnosed and explained
elsewhere. Care did not prevent the repeat; a second reading of the same fact
did.

**52 tests between the two**, each written from a real defect and each made to
fail on that defect before being confirmed to pass on the fix.

"""
edit("the lower section rewritten as the detail, with the mark and the fields",
     "## The three checks\n",
     DETAIL.replace("GITHUB_URL", REPO) + "<!-- old section follows -->\n")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    p = pathlib.Path("README.md")
    if not p.is_file():
        sys.exit("README.md not found — run from the repository root")
    s = p.read_text()

    # the mark, copied rather than hot-linked
    missing = []
    for m in MARKS:
        src = SRC_ASSETS / m
        if not src.is_file():
            missing.append(str(src))
            continue
        print(f"  asset   {m}  ->  {DEST_ASSETS/m}")
        if not a.dry_run:
            DEST_ASSETS.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, DEST_ASSETS / m)
    if missing:
        print(f"  ! not found: {', '.join(missing)}")
        print(f"    the image will 404 until it is copied in")

    applied = missed = 0
    for why, old, new in EDITS:
        n = s.count(old)
        if n >= 1:
            s = s.replace(old, new)
            applied += 1
            print(f"  ok      {why}" + (f"  ({n} places)" if n > 1 else ""))
        else:
            missed += 1
            print(f"  MISSED  {why}\n          anchor: {old[:60]!r}")

    print(f"\n  {applied} applied, {missed} missed")
    if a.dry_run:
        print("  --dry-run: nothing written\n")
        return 0
    if missed:
        # A half-edited README describes the repository half-correctly, and
        # nothing in it says which half.
        print("  REFUSING to write a partially-edited README.\n")
        return 1
    p.write_text(s)
    print("  wrote README.md\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

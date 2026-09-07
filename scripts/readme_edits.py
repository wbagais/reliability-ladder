#!/usr/bin/env python3
"""
readme_edits.py — bring the README up to 2026-09-07 without changing its scope.

WHAT CHANGES AND WHAT DOES NOT

The article is a 2,849-word InfoQ piece on CADEC and FiNER, and that is the
right editorial call — seven corpora would double its length and blur the
argument. So the README's HEADLINE SCOPE stays exactly as it is: two corpora,
the same table, the same framing.

What changes is everything below that:

  1. a leftover instruction-to-self at the very top, and a duplicated title
  2. CADEC's 42.4% -> 32% dev / 38% corpus-wide, retracted by the 2026-09-04
     gold replay when it was re-run on the base run's own denominator
  3. "Every number in this repo is measured on CADEC v2" — no longer true
  4. `gatecheck` and `crosscheck` added to the quick start, as step ZERO,
     because that is where they belong in the method rather than as a
     side project
  5. a new section: five more corpora, as ADDITIONAL TESTS, clearly marked
     beyond the article's scope
  6. a new section: the three checks, honest about their maturity —
     stagecheck is published with 43 tests, the other two are one evening
     old with known false positives

Nothing is removed. All seven manifests, adapters, results and decision entries
stay where they are; the README simply stops claiming the repo is smaller than
it is.

    python3 scripts/readme_edits.py --dry-run
    python3 scripts/readme_edits.py
"""
from __future__ import annotations

import argparse
import pathlib
import sys

EDITS: list[tuple[str, str, str]] = []


def edit(why: str, old: str, new: str) -> None:
    EDITS.append((why, old, new))


# ── 1 · the leftover note and the duplicated title ───────────────────
edit("a paste instruction left at the top of the file",
     "<!-- Paste at the very top of README.md, above the existing title. -->\n"
     "<!-- Requires docs/figures/fig0-hero.png, which is already in the repo. -->\n\n",
     "")
edit("two titles, one centred and one plain",
     "---\n# The Reliability Ladder\n\n",
     "---\n\n")

# ── 2 · the retracted number ─────────────────────────────────────────
edit("CADEC's lane was retracted from 43% to 32% dev / 38% corpus-wide by the "
     "2026-09-04 gold replay, re-run on the base run's own denominator",
     "| **CADEC v2** | patient forum posts | SNOMED CT, 129,675 concepts | "
     "**non-transferable** — you need your own copy | 42.4% |",
     "| **CADEC v2** | patient forum posts | SNOMED CT, 129,675 concepts | "
     "**non-transferable** — you need your own copy | 32% |")

edit("the corpus count in the section heading",
     "## Three corpora, and only two of them are yours to run",
     "## Three corpora, and only two of them are yours to run\n\n"
     "*This is the article's scope. Five more were added between 2026-09-01 and\n"
     "2026-09-07 and are summarised further down — they test whether the claims\n"
     "below hold anywhere else.*")

# ── 3 · the CADEC-only claim ─────────────────────────────────────────
edit("the repo is no longer CADEC-only",
     "Every number in this repo is measured on CADEC v2.",
     "The numbers in the sections above are measured on CADEC v2 and FiNER-139. "
     "Five further corpora were added in September 2026 and are listed under "
     "*Five more corpora* below.")

# ── 4 · the two checks, as step zero of the quick start ──────────────
edit("gatecheck and crosscheck belong in the quick start, not in a footnote: "
     "they are the first two commands anyone runs",
     "**Start here.** CADEC cannot be redistributed, so that arm is not reproducible\n"
     "from a clean checkout by anyone but you. The FiNER arm is.",
     """**Start here.** CADEC cannot be redistributed, so that arm is not reproducible
from a clean checkout by anyone but you. The FiNER arm is, and so are five of the
six corpora added since.

**Step zero, before any GPU time.** Two checks, a second each, no model calls:

```bash
PYTHONPATH=. python3 scripts/gatecheck.py  --manifest manifest.finer.json
PYTHONPATH=. python3 scripts/crosscheck.py --manifest manifest.finer.json
```

`gatecheck` predicts the free check's ceiling from gold alone. On FiNER it
reports **0.0%** and refuses to recommend the arm — the spans are numerals and
the tags are English phrases, so the check cannot fire however good the model
is. That is a full GPU arm's finding, available before booking one.

`crosscheck` reads every declared fact back from an independent source: the
rendered prompt against the declared entity, the few-shot ids against the pool
split the guard actually reads, the split ids against the corpus the adapter
loads, and each named model against what ollama has. Every check in it is a
defect that reached a rented card first.""")


# ── 5 · five more corpora, as additional tests ───────────────────────
MORE = """
## Five more corpora, as additional tests

*Beyond the article's scope, and the reason to trust what is above it.* Between
2026-09-01 and 2026-09-07 the two claims — that the free check is worth its
nothing, and that the paid layers are not worth their tokens — were re-run on
five further corpora across four model families.

| corpus | domain | vocabulary | licence | lane fires | of that, correct |
|---|---|---|---|---|---|
| **CADEC v2** | patient forum posts | SNOMED CT | non-transferable | 32% | 76–82% |
| **PsyTAR** | patient drug reviews | SNOMED CT | **CC BY 4.0** | 19–31% | **80–90%** |
| **BC5CDR** | biomedical abstracts | MeSH | free mirror | 7–22% | **93–100%** |
| **GeoWebNews** | news geography | GeoNames | GPL-3.0 | 20–64% | 11–26% |
| **LGL** | local news | GeoNames | GPL-3.0 | 30–74% | 10–22% |
| **TR-News** | news geography | GeoNames | GPL-3.0 | 37–72% | 10–17% |
| **LINNAEUS** | research papers | NCBI Taxonomy | CC-BY | 0–13% | 80% *(n=5)* |
| **FiNER-139** | SEC filings | 139 XBRL tags | CC-BY-SA-4.0 | **0.0%** | — |

Ranges are across `gpt-oss:20b`, `llama3.1:8b`, `mistral:7b-instruct` and
`ibm/granite4:micro-h` — 4B to 20B — one draw each on the dev split, rungs 0–1.
Three draws were measured byte-identical on three corpora, so a single draw is a
measurement rather than a sample. **CADEC's row is a reference and not a row of
the same table:** it was produced on different hardware, and floating point
differs between a CPU-split model and a GPU-resident one.

**The split is the finding, and it is not about medicine.** Clinical
vocabularies give a SMALL lane that is RIGHT; gazetteers give a LARGE lane that
is WRONG. Read as ACCEPT's accuracy over the accuracy of what the check
*declined* to endorse — whether the lane sorted anything at all — the clinical
corpora separate **2.0–3.8×** and TR-News separates **0.6–0.9×**. There the free
check is worse than not checking.

**And the paid layers still do not pay.** The full ladder on PsyTAR, three
draws: self-correction, sampled voting and the LLM judge each routed **zero**
records, and coverage was identical to rungs 0–1 alone. That was a one-corpus
claim before 2026-09-07.

Everything is in [`docs/decisions.md`](docs/decisions.md), dated, including the
corrections — twelve matrix cells that ran with the wrong corpus's prompt, and
five that ran a different model than their directory name claimed.

## The three checks

Three questions at three moments. Two live here; one is its own repo.

| tool | question | when | knows about corpora |
|---|---|---|---|
| [`gatecheck`](scripts/gatecheck.py) | should I run this? | before booking a card | yes |
| [`crosscheck`](scripts/crosscheck.py) | is it what I declared? | first line of every run | yes |
| [`stagecheck`](https://gitlab.com/pushpdeep/stagecheck) | did the run mean anything? | after | **no, deliberately** |

**`stagecheck` is the mature one** — its own repository, 43 tests, no
dependencies, MIT. It records the two things a pipeline usually does not: the
bet a stage makes, and the records it could not judge.

**`gatecheck` and `crosscheck` are one evening old** and have known false
positives; they are in `scripts/` rather than packaged, and the boundary between
them and `stagecheck` is described in
[`docs/three-checks.md`](docs/three-checks.md).

The principle they share came out of a week of failures that all looked the
same: **a load-bearing fact recorded once cannot be checked, and will eventually
be wrong silently.** Everything that caught a real defect compared two
independent records of one fact. Everything that got through was recorded once.
"""

edit("a section for the additional corpora and one for the three checks, "
     "placed before the licence",
     "## Licence",
     MORE.strip() + "\n\n## Licence")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--file", default="README.md")
    a = ap.parse_args()

    p = pathlib.Path(a.file)
    if not p.is_file():
        sys.exit(f"{a.file} not found")
    s = p.read_text()
    applied = missed = 0

    for why, old, new in EDITS:
        n = s.count(old)
        if n == 1:
            s = s.replace(old, new, 1)
            applied += 1
            print(f"  ok      {why}")
        elif n == 0:
            missed += 1
            print(f"  MISSED  {why}")
            print(f"          anchor not found: {old[:70]!r}")
        else:
            missed += 1
            print(f"  MISSED  {why}")
            print(f"          anchor appears {n} times, needs to be unique")

    print(f"\n  {applied} applied, {missed} missed")
    if a.dry_run:
        print("  --dry-run: nothing written\n")
        return 0
    if missed:
        # A partial README edit is worse than none: it leaves a document that
        # half-describes the repo, and nothing says which half.
        print("  REFUSING to write a partially-edited README. Fix the anchors "
              "above and re-run.\n")
        return 1
    p.write_text(s)
    print(f"  wrote {a.file}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

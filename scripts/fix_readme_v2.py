#!/usr/bin/env python3
"""
fix_readme_v2.py — four things the README gets wrong, one of them factually.

A predecessor, scripts/fix_readme.py, brought this file up to date on
2026-08-23. Eleven days and two corpora later it is stale again, and one of the
four is not staleness but an error:

1 . THE RUNG TABLE IS PRE-RENUMBER. It lists rung 2 as abstention, 3 as
    self-correction, 5 as voting. The renumber landed 2026-08-23 and every other
    file in the repository uses 2=self-correct, 3=voting, 4=judge, 5=abstention.
    The README has been describing a ladder that has not existed for eleven days.

2 . ONE CORPUS. Two more have been ported since, and they are the reason the
    article can say anything about generalisation at all.

3 . A STRANGER CANNOT RUN ANYTHING. Every instruction assumes CADEC, which is
    non-transferable. FiNER is CC-BY-SA and GeoWebNews is GPL-3.0 — both
    redistributable, neither mentioned. A reproducible path that requires a
    licence nobody can grant you is not one.

4 . THE HEADLINE RESULTS ARE THE FIRST DEV RUN. 169 mentions, F1 0.543, 0 of 105
    codes — superseded by the frozen test split and by two further corpora.

Listed rather than silently left unfixed: the Status block, the repo map (ten
modules newer than it), and the rung-1 costs section, which predates the second
and third corpora.

    python3 scripts/fix_readme_v2.py
"""
import pathlib
import sys

P = pathlib.Path("README.md")

OLD_TABLE = """| Rung | Layer | Mechanism | Extra cost | Owner |
|---|---|---|---|---|
| 0 | bare LLM | one call, JSON, temp 0; emits a code with or without a lookup tool (`rung0_mode`) | 1 call/item | B |
| 1 | deterministic | schema \u00b7 span grounding \u00b7 negation \u00b7 code exists \u00b7 semantic type \u00b7 MedDRA | **none** | A |
| 2 | abstention | decline anything still unresolved, or below \u03c4 | none | A |
| 3 | self-correction | one bounded retry, fired **only by a rung 1 failure**, reason stated as fact | +1 call | B |
| 4 | LLM-as-judge | second model, **different family**, scores the record | +1 call | B |
| 5 | voting | k samples, majority on the **normalised code**, never the string | k calls | B |
| 6 | human-in-the-loop | a person settles it \u2014 simulated, or timed | human minutes | joint |"""

NEW_TABLE = """| Rung | Layer | Mechanism | Extra cost | What it bought |
|---|---|---|---|---|
| 0 | bare LLM | retrieve candidates, then pick a line number \u2014 two calls, and neither ever sees a code | 2 calls/item | the input to everything above |
| 1 | deterministic | schema \u00b7 span grounding \u00b7 negation \u00b7 code exists \u00b7 semantic type \u00b7 lexical match | **none** | the one layer that paid \u2014 80\u201389% correct in its ACCEPT lane across five model families |
| 2 | self-correction | one bounded retry, fired **only by a rung 1 rejection**, the reason stated as a fact | +1 call | **nothing.** 0 rescued of 158 on CADEC, 0 of 918 on FiNER |
| 3 | voting | k samples, majority on the **normalised code**, never the string | k calls | +5 on the tuning set, **0 out of sample**, for 425,355 tokens |
| 4 | LLM-as-judge | second model, **different family**, scores the record | +1 call | separates 1.23\u00d7 held out, against the free check\u2019s 2.36\u20136.12\u00d7 |
| 5 | abstention | decline anything rung 1 could not corroborate | none | errors 62.9 \u2192 4.0 per 100, at 79 reviews per 100 |
| 6 | human-in-the-loop | a person settles it \u2014 timed, not simulated | human minutes | the only settling authority, and the cost nothing else prices |

Rung ID equals execution position. **This numbering changed on 2026-08-23**, and
decision-log entries before that date use the old order (2=abstention,
3=self-correction, 5=voting) \u2014 the mapping is in `docs/decisions.md`."""

CORPORA = """## Three corpora, and only two of them are yours to run

Deliberately different in the one respect that decides whether the free check can
work at all \u2014 whether the extracted span and the code\u2019s own name are drawn from
the same language.

| corpus | domain | vocabulary | licence | free check fires |
|---|---|---|---|---|
| **CADEC v2** | patient forum posts | SNOMED CT, 129,675 concepts | **non-transferable** \u2014 you need your own copy | 42.4% |
| **FiNER-139** | SEC filings | 139 XBRL tags | CC-BY-SA-4.0, redistributable | **0.0%** |
| **GeoWebNews** | news geography | GeoNames, 13.4M places | GPL-3.0, redistributable | 39.8% |

FiNER\u2019s zero is structural rather than a low score: the spans are numerals
(`47.6`) and the tags are English phrases
(`EffectiveIncomeTaxRateContinuingOperations`), so the two share no token by
construction \u2014 on any run, with any model, forever.

## Run it yourself, without a licence

**Start here.** CADEC cannot be redistributed, so that arm is not reproducible
from a clean checkout by anyone but you. The FiNER arm is.

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt pytest
```

```bash
mkdir -p data/finer && cd data/finer
curl -LO https://huggingface.co/datasets/nlpaueb/finer-139/resolve/main/finer139.zip
unzip -q finer139.zip -d extracted && cd ../..
python -m ladder.run init --manifest manifest.finer.json
```

The free half needs no model and takes seconds:

```bash
PYTHONPATH=. python3 scripts/preflight_rungs.py --manifest manifest.finer.json --static
PYTHONPATH=. python3 scripts/relations_report.py --manifest manifest.finer.json
```

That second command is the shortest route to the central finding. It reports
that the lexical check has **no signal at all** here, and that a
type-compatibility check has 87.7% \u2014 a layer reported dead means *this check
found no signal*, never *this corpus has none*.

For the model half you need [ollama](https://ollama.com) and ~14 GB of VRAM:

```bash
ollama pull gpt-oss:20b && ollama pull ibm/granite4:micro-h
PYTHONPATH=. python3 -m ladder.run --manifest manifest.finer.json ladder \\
    --split test --limit 3 --plain
```

Drop `--limit 3` for the full split \u2014 60 documents, roughly 25 minutes on a
48 GB card, several hours on a laptop.

### Reproduce the article\u2019s findings

Five of them, from gold and source, with no model calls:

```bash
PYTHONPATH=. python3 scripts/reproduce.py
```

### The GeoWebNews arm

```bash
git clone --depth 1 https://github.com/milangritta/Pragmatic-Guide-to-Geoparsing-Evaluation /tmp/gwn
mkdir -p data/gwn && cp -r /tmp/gwn/data/Geocoding data/gwn/
curl -O https://download.geonames.org/export/dump/allCountries.zip && unzip -q allCountries.zip
python3 scripts/build_geo_index.py --dump allCountries.txt --out ladder/cache/geonames.sqlite
PYTHONPATH=. python3 -m ladder.run --manifest manifest.geo.json init
```

The index is 13.4M rows and takes about a minute. **This arm uses lexical
retrieval where CADEC uses dense** \u2014 no embedded keyword table exists for a
gazetteer \u2014 and on CADEC that substitution cost 21 points of recall@20. No
absolute score from the geo arm is comparable with CADEC\u2019s.

## Quick start"""

NEW_HEAD = """## What the full ladder measured

> **These are the FIRST dev-split figures, from 2026-08-20, and they are
> superseded.** Kept because the decision log refers to them. The shipped numbers
> are on the frozen test split \u2014 exact F1 0.204, coding accuracy 0.392, rung 5
> dropping errors from 59.6 to 3.8 per 100 at 77.1 reviews per 100 \u2014 and the
> cross-corpus results are in [docs/article-v3.md](docs/article-v3.md).

Dev split, 40 documents,"""


def main() -> int:
    s = P.read_text()
    if "FiNER-139" in s:
        print("already applied"); return 0
    n = 0

    if OLD_TABLE in s:
        s = s.replace(OLD_TABLE, NEW_TABLE, 1); n += 1
        print("  + rung table corrected \u2014 it was pre-renumber")
    else:
        print("  ! rung table not matched; fix it by hand", file=sys.stderr)

    if "## Quick start" in s:
        s = s.replace("## Quick start", CORPORA, 1); n += 1
        print("  + three corpora, and a path a stranger can run")

    old_head = "## What the full ladder measured\n\nDev split, 40 documents,"
    if old_head in s:
        s = s.replace(old_head, NEW_HEAD, 1); n += 1
        print("  + stale headline table marked superseded")

    if "Four preprocessing steps, in order." in s:
        s = s.replace("Four preprocessing steps, in order.",
                      "Five preprocessing steps, in order.", 1); n += 1
        print("  + preprocessing: four -> five")

    if '<a href="docs/article-v2.md">the article</a>' in s:
        s = s.replace('<a href="docs/article-v2.md">the article</a>',
                      '<a href="docs/article-v3.md">the article</a>', 1); n += 1
        print("  + article link -> v3")

    P.write_text(s)
    print(f"\n{n} change(s). Still stale and NOT fixed: the Status block, the repo")
    print("map (ten modules newer than it), and the rung-1 costs section, which")
    print("predates the second and third corpora.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

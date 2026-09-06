#!/usr/bin/env python3
"""
matrix_plan.py — what has been run, what has not, and what the rest would cost.

WHY A PLANNER AND NOT JUST A RUNNER

"All models on all corpora" is 5 models x 8 corpora x 3 draws = 120 runs. At the
rate the PsyTAR arm measured on a rented RTX 6000 Ada — 40 documents through the
full ladder in about 8 minutes — that is on the order of **16 hours and $25**,
and a third of it is re-running cells that already exist.

So this reports the matrix first. Three states per cell:

    DONE        results on disk, with the draw count
    READY       manifest and splits exist; only GPU time is missing
    BLOCKED     something has to be built first, and what

NO RUNG CHANGES ARE NEEDED FOR ANY OF THIS. A model sweep varies
`manifest.model.extractor` and nothing else — which is precisely what
`manifest_diff.py` is for, and every generated manifest is checked against its
base before it runs. A cell that differs in more than the model is not a cell in
this matrix.

WHAT IT WILL NOT DO

It will not silently fill BLOCKED cells. Three corpora (LGL, TR-News, LINNAEUS)
have gold-side numbers and no manifest, splits or retrieval configuration;
BC5CDR has an adapter and no MeSH index. Building those is real work with real
choices — which split, which retrieval mode, which name set — and a planner that
guessed them would be manufacturing an experiment rather than running one.

    PYTHONPATH=. python3 scripts/matrix_plan.py
    PYTHONPATH=. python3 scripts/matrix_plan.py --rate 1.57
"""
from __future__ import annotations

import argparse
import glob
import json
import pathlib
import sys
from collections import defaultdict

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

#: The five families the CADEC sweep used. Their spread in headline F1 is what
#: makes "the lane is 80-89% regardless of model" a claim about the check
#: rather than about one model.
MODELS = [
    ("gpt-oss:20b",         "ollama/gpt-oss:20b"),
    ("llama3.1:8b",         "ollama/llama3.1:8b"),
    ("mistral:7b-instruct", "ollama/mistral:7b-instruct"),
    ("granite4:micro-h",    "ollama/ibm/granite4:micro-h"),
    ("qwen3:4b",            "ollama/qwen3:4b"),
]

#: corpus -> (manifest, output-prefix, what is missing if anything)
CORPORA = [
    ("CADEC",      "manifest.json",              "out/", ""),
    ("FiNER-139",  "manifest.finer.json",        "out/finer", ""),
    ("GeoWebNews", "manifest.geo.json",          "out/geo", ""),
    ("PsyTAR",     "manifest.psytar.json",       "out/psytar", ""),
    ("LGL",        "manifest.lgl.json",          "out/lgl",
     "no manifest, no frozen splits — and it shares GeoWebNews's gazetteer, so "
     "it inherits the lexical-retrieval deviation"),
    ("TR-News",    "manifest.trnews.json",       "out/trnews",
     "no manifest, no frozen splits; 116 of 1,275 spans do not land"),
    ("LINNAEUS",   "manifest.linnaeus.json",     "out/linnaeus",
     "no manifest; and it has TWO vocabularies (scientific-only and all-names) "
     "whose choice moves the endorsable stratum 5.4% -> 35.4%, so a model arm "
     "must declare which"),
    ("BC5CDR",     "manifest.bc5cdr.json",       "out/bc5cdr",
     "MeSH index not built; two entity types, and the arm must pick one"),
]


def completed() -> dict:
    """Every finished run, keyed by (corpus, extractor), read from the MANIFEST
    each run saved beside its results.

    Not from directory names. Those are `finer`, `finer-llama`, `geo-gptoss`,
    `psytar-d0` — three conventions across four corpora, and a glob over them
    reported CADEC's five-family sweep as unrun, which would have paid to redo
    work that already exists. **A directory name says what somebody intended;
    the manifest beside the results says what ran.**
    """
    done = defaultdict(set)
    for f in glob.glob("out/**/*.manifest.json", recursive=True) + \
             glob.glob("runs/**/*.manifest.json", recursive=True):
        try:
            m = json.loads(pathlib.Path(f).read_text())
        except Exception:
            continue
        corpus = (m.get("corpus") or {}).get("name") or "?"
        model = (m.get("model") or {}).get("extractor") or "?"
        done[(corpus, model)].add(pathlib.Path(f).parent.name + "/" + pathlib.Path(f).name)
    return done


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rate", type=float, default=1.57, help="$/hour")
    ap.add_argument("--draws", type=int, default=3)
    ap.add_argument("--minutes-per-draw", type=float, default=8.0,
                    help="measured: PsyTAR, 40 documents, full ladder, RTX 6000 Ada")
    a = ap.parse_args()

    print(f"\n  the matrix · {len(MODELS)} models x {len(CORPORA)} corpora "
          f"x {a.draws} draws\n")
    w = max(len(c[0]) for c in CORPORA)
    print(f"  {'corpus':<{w}} " + " ".join(f"{m[:9]:>10}" for m, _ in MODELS))
    print("  " + "-" * (w + 11 * len(MODELS)))

    done_map = completed()
    todo, blocked = [], []
    for name, manifest, prefix, missing in CORPORA:
        row, ready = [], pathlib.Path(manifest).is_file() and not missing
        for mk, spec in MODELS:
            if not ready:
                row.append(f"{'—':>10}")
                continue
            n = len(done_map.get((name, spec), set()))
            if n >= a.draws:
                row.append(f"{'done':>10}")
            else:
                row.append(f"{str(a.draws - n) + ' runs':>10}")
                todo.append((name, manifest, mk, a.draws - n))
        print(f"  {name:<{w}} " + " ".join(row))
        if missing:
            blocked.append((name, missing))

    print()
    if blocked:
        print("  BLOCKED — these need building before any model can run on them\n")
        for name, why in blocked:
            print(f"    {name}")
            for line in _wrap(why, 68):
                print(f"        {line}")
        print()

    runs = sum(n for *_, n in todo)
    mins = runs * a.minutes_per_draw
    print(f"  READY AND NOT RUN: {runs} run(s) · {mins/60:.1f} h · "
          f"${mins/60*a.rate:.2f} at ${a.rate:.2f}/h")
    if todo:
        by_corpus = defaultdict(int)
        for name, _, _, n in todo:
            by_corpus[name] += n
        for name, n in sorted(by_corpus.items(), key=lambda x: -x[1]):
            print(f"      {name:<{w}} {n:3} run(s)")

    print()
    print("  Costed from a measurement, not from arithmetic: 40 documents through")
    print("  the full ladder took 8 minutes on the rented card. Corpora with more")
    print("  documents scale accordingly, and rung 3 dominates — dropping to")
    print("  --rungs 0-1 removes roughly three quarters of it and answers every")
    print("  question about the free check's lane.")
    print()
    return 0


def _wrap(s: str, n: int):
    out, line = [], ""
    for word in s.split():
        if len(line) + len(word) + 1 > n:
            out.append(line); line = word
        else:
            line = f"{line} {word}".strip()
    if line:
        out.append(line)
    return out


if __name__ == "__main__":
    raise SystemExit(main())

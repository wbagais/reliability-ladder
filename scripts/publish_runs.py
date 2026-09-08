#!/usr/bin/env python3
"""
publish_runs.py — make every cell re-scoreable by both owners, without
redistributing a corpus that cannot be redistributed.

THE PROBLEM

`out/` and `runs/*` are gitignored, and the reason is in `.gitignore` itself:
*"a worked example is a corpus quotation"*. A records file carries `text` and
`context` — sentences lifted from the source — and CADEC's CSIRO licence is
**non-transferable**. A copy received through this repository is not licensed,
however the recipient uses it.

The cost of that rule is that only one machine can re-score a run, and both
owners want to analyse the same cells.

THE SPLIT

Scoring needs `doc_id`, `spans`, `sct` and the rung verdicts. It does NOT need
`text` or `context` — those are for reading a record, which is diagnosis rather
than scoring. So:

    results.csv, aggregates.json, cell.manifest.json   every corpus, as they are
    records.jsonl STRIPPED of text/context             every corpus, incl. CADEC
    records.jsonl in full                              the six that permit it
    *.calls.jsonl (raw model output)                    never — bulky, and it is
                                                        the model quoting the
                                                        corpus back verbatim

Six of seven corpora permit redistribution: PsyTAR is CC BY 4.0, LINNAEUS
CC-BY, FiNER-139 CC-BY-SA-4.0, GeoWebNews / LGL / TR-News GPL-3.0, BC5CDR a
public mirror. Only CADEC does not.

WHAT YOU LOSE ON CADEC

You can re-score every cell and see every verdict. You cannot read what the
model actually said, which is the difference between *"this cell scores 76%"*
and *"this cell scores 76% because it wrote 'stomach pain' where gold says
'abdominal pain'"*. The second needs the licensed local copy, which both owners
already have.

    python3 scripts/publish_runs.py --dry-run
    python3 scripts/publish_runs.py
    python3 scripts/publish_runs.py --check      # verify nothing leaked
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import shutil
import sys

SRC_DIRS = ["out/matrix", "out/matrix-test", "out/overnight"]
# runs/archive/, following the convention runs/archive/README.md already sets:
# tracked, documented, and "ledger rows, provenance and aggregate blocks only.
# No corpus text." Two publishing schemes in one repo would be worse than
# either, and the other owner's came first.
DEST = pathlib.Path("runs/archive/matrix-2026-09-07")

#: Fields that quote the corpus. Removed from every published record, for every
#: corpus — not only CADEC. Uniform because a rule with an exception is a rule
#: somebody applies wrongly, and the stripped file scores identically.
QUOTING_FIELDS = ("text", "context", "span_untrimmed", "source", "sentence",
                  "snippet", "passage",
                  # `candidates` is the shortlist rung 0 retrieved — 3,095 of a
                  # 4,111-byte record, 75% of every published file. It carries
                  # SNOMED concept LABELS, which is a vocabulary licence
                  # question rather than a corpus one and was not considered
                  # when this list was written. Scoring never reads it.
                  "candidates",
                  # The per-rung audit trace. Diagnostic, not scoreable.
                  "r1_audit")

#: Corpora whose licence permits redistribution, so their FULL records may be
#: published alongside the stripped ones.
REDISTRIBUTABLE = {
    "psytar": "CC BY 4.0",
    "linnaeus": "CC-BY (LINNAEUS manual-corpus-species-1.0)",
    "finer": "CC-BY-SA-4.0",
    "geo": "GPL-3.0 (Gritta et al.)",
    "lgl": "GPL-3.0 (Gritta et al.)",
    "trnews": "GPL-3.0 (Gritta et al.)",
    "bc5cdr": "public mirror of BioCreative V CDR",
}
#: And the one that does not. Matched against the cell directory name.
NON_TRANSFERABLE = {"cadec": "CSIRO Data Licence — non-transferable"}

RECORDS_NOT_WORTH_SHIPPING = {"finer"}

SMALL = (".results.csv", ".aggregates.json", "cell.manifest.json", ".manifest.json")


def corpus_of(cell: str) -> str:
    """`psytar-gpt-oss_20b-d0` -> `psytar`. The cell directory names the corpus
    first, and `run_matrix.sh` has written them that way since the matrix
    began."""
    return cell.split("-", 1)[0].lower()


def strip_record(line: str) -> str | None:
    """One records line with every quoting field removed.

    Returns None for a line that cannot be parsed, rather than passing it
    through: an unparseable line might contain anything, and the point of this
    function is that its output is known.
    """
    try:
        r = json.loads(line)
    except Exception:
        return None
    def clean(o):
        if isinstance(o, dict):
            return {k: clean(v) for k, v in o.items() if k not in QUOTING_FIELDS}
        if isinstance(o, list):
            return [clean(v) for v in o]
        return o
    return json.dumps(clean(r), separators=(",", ":"))


def publish(dry: bool) -> int:
    if DEST.exists() and not dry:
        shutil.rmtree(DEST)
    stats = {"cells": 0, "small": 0, "stripped": 0, "full": 0, "skipped": 0}
    manifest_rows = []

    for src in SRC_DIRS:
        root = pathlib.Path(src)
        if not root.is_dir():
            continue
        for cell in sorted(p for p in root.rglob("*") if p.is_dir()):
            files = list(cell.glob("*"))
            # ONE RUN PER CELL. A cell re-run after a fix holds both, and only
            # the newest was ever scored — `score_matrix.py` reported the
            # PREVIOUS run's numbers for a day because its glob took the first
            # match. Publishing both would ship the same ambiguity.
            recs = [f for f in files if f.name.endswith(".records.jsonl")
                    and not re.search(r"\.r\d+\.records\.jsonl$", f.name)]
            if len(recs) > 1:
                newest = max(recs, key=lambda f: f.stat().st_mtime)
                stem = newest.name.replace(".records.jsonl", "")
                files = [f for f in files
                         if not f.name.endswith(".records.jsonl")
                         or f.name.startswith(stem)]
            if not any(f.name.endswith(".results.csv") for f in files):
                continue
            corpus = corpus_of(cell.name)
            free = corpus in REDISTRIBUTABLE
            out = DEST / cell.relative_to("out")
            stats["cells"] += 1
            manifest_rows.append({
                "cell": str(cell.relative_to("out")),
                "corpus": corpus,
                "records": ("none — the finding is in results.csv"
                            if corpus in RECORDS_NOT_WORTH_SHIPPING
                            else "stripped"),   # every corpus, one rule
                "licence": REDISTRIBUTABLE.get(corpus,
                          NON_TRANSFERABLE.get(corpus, "unknown — treated as non-transferable")),
            })
            if not dry:
                out.mkdir(parents=True, exist_ok=True)

            for f in files:
                if f.is_dir():
                    continue
                if f.name.endswith(SMALL):
                    stats["small"] += 1
                    if not dry:
                        shutil.copy2(f, out / f.name)
                elif re.search(r"\.r\d+\.records\.jsonl$", f.name):
                    # PER-RUNG SNAPSHOTS. `.r1.records.jsonl` is byte-identical
                    # to the final `.records.jsonl` on every cell measured, and
                    # a cell ships up to seven of them. Publishing all of them
                    # made the directory 289 MB for 59 cells, which is a repo
                    # nobody wants to clone. The final file scores identically.
                    stats["skipped"] += 1
                elif f.name.endswith(".records.jsonl"):
                    # STRIPPED FOR EVERY CORPUS. Six of the seven permit
                    # redistribution and their full records would be more
                    # useful — see "Publishing full records" in
                    # docs/TODO-provenance.md, kept as a deliberate deferral
                    # rather than an oversight. One rule wins here because the
                    # conditional version ("full text unless CADEC") is the
                    # kind that gets applied wrongly later.
                    if corpus in RECORDS_NOT_WORTH_SHIPPING:
                        # FiNER's entire result is 0.0% ACCEPT on five model
                        # families, and that lives in results.csv. Its records
                        # are 691 extractions of SEC filing prose with nothing
                        # in the lane to re-score — 44 MB of the 97 published,
                        # for a corpus nobody will re-examine. The finding is
                        # fully reproducible without them.
                        stats["skipped"] += 1
                    else:
                        stats["stripped"] += 1
                        if not dry:
                            kept = []
                            for line in f.read_text().splitlines():
                                c = strip_record(line)
                                if c:
                                    kept.append(c)
                            (out / f.name.replace(".records.jsonl",
                                                  ".records.stripped.jsonl")
                             # "\n".join + "\n" leaves a trailing blank
                             # line, and json.loads raises on it. A published
                             # file the repo's own scorer cannot read is not
                             # published.
                             ).write_text("".join(l + "\n" for l in kept))
                else:
                    # .calls.jsonl, .ledger.jsonl, .state.jsonl — the model
                    # quoting the corpus back verbatim, and bulky. Never
                    # published, for any corpus.
                    stats["skipped"] += 1

    print(f"\n  {stats['cells']} cells")
    print(f"      {stats['small']:4} small files copied (results, aggregates, manifests)")
    print(f"      {stats['full']:4} records files copied in full")
    print(f"      {stats['stripped']:4} records files stripped of quoting fields")
    print(f"      {stats['skipped']:4} files skipped (calls, ledger, state)")

    by = {}
    for r in manifest_rows:
        by.setdefault((r["corpus"], r["records"]), 0)
        by[(r["corpus"], r["records"])] += 1
    print(f"\n  {'corpus':12} {'records':10} cells   licence")
    for (c, kind), n in sorted(by.items()):
        lic = REDISTRIBUTABLE.get(c, NON_TRANSFERABLE.get(c, "unknown"))
        print(f"  {c:12} {kind:10} {n:5}   {lic}")

    if not dry:
        (DEST / "PUBLISHED.md").write_text(_readme(manifest_rows, stats))
        print(f"\n  wrote {DEST}/ and {DEST}/PUBLISHED.md")
    else:
        print("\n  --dry-run: nothing written")
    print()
    return 0


def _readme(rows, stats) -> str:
    free = sorted({r["corpus"] for r in rows if r["records"] == "full"})
    strip = sorted({r["corpus"] for r in rows if r["records"] == "stripped"})
    return f"""# Published run outputs

{stats['cells']} cells, enough for either owner to re-score every one.

## What is here

| file | contents |
|---|---|
| `*.results.csv` | the per-rung table each run printed |
| `*.aggregates.json` | token counts, latencies, per-rung tallies |
| `cell.manifest.json` | the configuration the cell actually ran under |
| `*.records.jsonl` | full records — {', '.join(free) or 'none'} |
| `*.records.stripped.jsonl` | records without `text` or `context` — {', '.join(strip) or 'none'} |

## Why some are stripped

Scoring needs `doc_id`, `spans`, `sct` and the rung verdicts. It does not need
the quoted sentence. So a stripped file **scores identically** to a full one —
`scripts/score_matrix.py` reads the same fields from either.

CADEC's CSIRO licence is non-transferable: a copy received through this
repository would not be licensed, whatever the recipient's use. Its records are
therefore published without the quoted text. Every other corpus here permits
redistribution and is published in full.

## What you cannot do with a stripped file

Read what the model wrote. That is diagnosis rather than scoring — the
difference between *"this cell scores 76%"* and *"it scores 76% because it
wrote 'stomach pain' where gold says 'abdominal pain'"*. For that, use the
licensed local copy.

## Never published, for any corpus

`*.calls.jsonl`, `*.ledger.jsonl` and `*.state.jsonl`. They carry the model
quoting the corpus back verbatim, and they are the bulk of a run.
"""


def check() -> int:
    """Verify no published file carries a quoting field. Cheap, and the whole
    point: a strip that is not verified is a strip nobody has checked."""
    if not DEST.is_dir():
        sys.exit(f"{DEST} does not exist — run without --check first")
    bad = 0
    pat = re.compile(r'"(' + "|".join(QUOTING_FIELDS) + r')"\s*:')
    for f in DEST.rglob("*.stripped.jsonl"):
        for i, line in enumerate(f.read_text().splitlines(), 1):
            if pat.search(line):
                print(f"  ! {f}:{i} still carries a quoting field")
                bad += 1
                break
    n = len(list(DEST.rglob("*.stripped.jsonl")))
    print(f"\n  checked {n} stripped file(s), {bad} still carrying quoted text\n")
    return 1 if bad else 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--check", action="store_true",
                    help="verify no published file carries a quoting field")
    a = ap.parse_args()
    raise SystemExit(check() if a.check else publish(a.dry_run))

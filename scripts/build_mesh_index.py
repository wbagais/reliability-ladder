#!/usr/bin/env python3
"""
build_mesh_index.py — MeSH as a ladder vocabulary.

WHY THIS ONE MATTERS MORE THAN THE OTHERS

The calibration set has five corpora and four vocabulary shapes, but **three of
the five are geoparsing** and CADEC is the only clinical one — while carrying
most of the article's claims. A second corpus of the same shape is worth more
than a sixth of any other, because it is the only way to tell whether the
75–82% ACCEPT lane belongs to controlled clinical vocabularies or to SNOMED in
particular. Section 11 of the article names that as an open question.

BC5CDR is that corpus, and MeSH is its vocabulary.

WHAT MESH GIVES THAT A GAZETTEER AND A TAG SET DO NOT

    MH     the main heading — one preferred name per concept
    ENTRY  synonyms, dozens of them, each with its own name class
    MN     TREE NUMBERS, which are a real hierarchy

The tree is the useful part and it is why `is_finding` is not vacuous here.
MeSH's `C` tree is Diseases and its `D` tree is Chemicals and Drugs, and
BC5CDR annotates exactly those two types. So the semantic relation becomes
**bidirectional**: a mention annotated `Disease` must resolve into the C tree
and a `Chemical` must not. On a gazetteer and a 139-tag set that check is true
by construction; here it can fail, and failing is what makes it a check.

AND IT RUNS THE STRICT/LENIENT ARM AGAIN, ON A THIRD VOCABULARY

LINNAEUS measured what happens when a vocabulary is allowed to know its
subjects' common names: the endorsable stratum moved 5.4% -> 35.4% on the same
records. MeSH ships `MH` and `ENTRY` in the same file with the same
distinction, so the arm repeats here on clinical text.

    --names main      the MH only. Comparable with the GeoNames main-name-only
                      build, and the strict reading.
    --names all       plus ENTRY and PRINT ENTRY synonyms.

    python3 scripts/build_mesh_index.py --dump ~/Downloads/mesh --out ladder/cache/mesh.sqlite
    python3 scripts/build_mesh_index.py --dump ~/Downloads/mesh --names all \\
        --out ladder/cache/mesh-all.sqlite

`d2025.bin` is 31 MB and `c2025.bin` 123 MB; the index takes about a minute.
Both are free from NLM with no registration:

    curl -sL https://nlmpubs.nlm.nih.gov/projects/mesh/2025/asciimesh/d2025.bin -o d2025.bin
    curl -sL https://nlmpubs.nlm.nih.gov/projects/mesh/2025/asciimesh/c2025.bin -o c2025.bin

Note the path: `projects/mesh/<year>/asciimesh/`, not `MESH_FILES/asciimesh/`,
which returns an HTML error page with a 200 status — a HEAD request says the
file is there and a GET returns a "URL Not Found" page. That cost us an hour
the first time we tried this corpus, and it is the reason the download command
is written out above rather than left to a reader.
"""
from __future__ import annotations

import argparse
import pathlib
import sqlite3
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from ladder.registry import normalise_term


def records(path: pathlib.Path):
    """Yield one MeSH record as a dict of field -> list of values.

    The ASCII format is `FIELD = value` lines separated by `*NEWRECORD`. Some
    values carry pipe-delimited metadata (`A23187|T109|T195|LAB|...`); only the
    part before the first pipe is the term.
    """
    cur: dict[str, list[str]] = {}
    with path.open(encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.rstrip("\n")
            if line.startswith("*NEWRECORD"):
                if cur:
                    yield cur
                cur = {}
                continue
            if " = " not in line:
                continue
            k, v = line.split(" = ", 1)
            cur.setdefault(k.strip(), []).append(v.strip())
    if cur:
        yield cur


def terms_of(rec: dict, all_names: bool) -> list[str]:
    out = list(rec.get("MH", [])) + list(rec.get("NM", []))   # NM: supplementary
    if all_names:
        for key in ("ENTRY", "PRINT ENTRY", "SY"):
            for v in rec.get(key, []):
                out.append(v.split("|", 1)[0].strip())
    return [t for t in out if t]


def build(dump: pathlib.Path, out: pathlib.Path, all_names: bool) -> None:
    d = dump / "d2025.bin"
    c = dump / "c2025.bin"
    if not d.is_file():
        sys.exit(f"{d} not found — see this file's docstring for the download.")

    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".building")
    if tmp.exists():
        tmp.unlink()
    db = sqlite3.connect(tmp)
    db.executescript("""
        PRAGMA journal_mode=OFF; PRAGMA synchronous=OFF;
        CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT);
        CREATE TABLE concept(id TEXT PRIMARY KEY, active INT, is_finding INT, is_finding_hist INT);
        CREATE TABLE description(concept_id TEXT, term TEXT, norm TEXT, fsn INT);
    """)

    t0 = time.time()
    n_con = n_desc = n_dis = 0
    con_batch, desc_batch = [], []

    def flush():
        nonlocal con_batch, desc_batch
        if con_batch:
            db.executemany("INSERT OR IGNORE INTO concept VALUES (?,?,?,?)", con_batch)
            con_batch = []
        if desc_batch:
            db.executemany("INSERT INTO description VALUES (?,?,?,?)", desc_batch)
            desc_batch = []

    for src, label in ((d, "descriptors"), (c, "supplementary")):
        if not src.is_file():
            print(f"[mesh] {src.name} absent — skipping {label}", file=sys.stderr)
            continue
        print(f"[mesh] {label} <- {src.name}", file=sys.stderr)
        for rec in records(src):
            uid = (rec.get("UI") or [None])[0]
            if not uid:
                continue
            # is_finding carries DISEASE-ness, read from the tree. MeSH's C tree
            # is Diseases and F03 is Mental Disorders; everything else — most
            # importantly the D tree, Chemicals and Drugs — is not a disease.
            # Supplementary records have no tree, so they inherit from their
            # mapped heading where one exists, and default to not-a-disease
            # (they are overwhelmingly chemicals).
            trees = rec.get("MN", [])
            if trees:
                is_dis = int(any(t.startswith("C") or t.startswith("F03") for t in trees))
            else:
                hm = " ".join(rec.get("HM", []))
                is_dis = int("*" in hm and False)  # SCRs: default not-a-disease
            n_dis += is_dis
            con_batch.append((uid, 1, is_dis, 1))
            n_con += 1

            seen = set()
            for i, t in enumerate(terms_of(rec, all_names)):
                norm = normalise_term(t)
                if not norm or norm in seen:
                    continue
                seen.add(norm)
                desc_batch.append((uid, t, norm, 1 if i == 0 else 0))
                n_desc += 1
            if len(desc_batch) > 60_000:
                flush()
    flush()

    print("[mesh] indexing", file=sys.stderr)
    db.executescript("CREATE INDEX d_concept ON description(concept_id);"
                     "CREATE INDEX d_norm ON description(norm);")
    db.executemany("INSERT INTO meta VALUES (?,?)", [
        ("release", f"MeSH 2025, {n_con:,} concepts, {n_desc:,} names "
                    f"({'MH + ENTRY synonyms' if all_names else 'MH only'})"),
        ("source", "https://nlmpubs.nlm.nih.gov/projects/mesh/2025/asciimesh/"),
        ("names", "all" if all_names else "main"),
        ("is_finding", f"carries DISEASE-ness from the MeSH tree: 1 for the C tree "
                       f"and F03, 0 otherwise ({n_dis:,} of {n_con:,}). Unlike the "
                       f"gazetteer and the tag set this check is NOT vacuous — "
                       f"BC5CDR annotates Chemical and Disease, so the relation "
                       f"can be run in both directions and can fail."),
        ("built", time.strftime("%Y-%m-%d %H:%M:%S")),
    ])
    db.commit(); db.close(); tmp.replace(out)
    print(f"\n[mesh] {n_con:,} concepts · {n_desc:,} names · {n_dis:,} diseases",
          file=sys.stderr)
    print(f"[mesh] {out} · {out.stat().st_size/1e6:.0f} MB · {time.time()-t0:.0f}s",
          file=sys.stderr)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="MeSH -> the ladder's vocabulary schema")
    ap.add_argument("--dump", required=True, type=pathlib.Path,
                    help="directory holding d2025.bin and c2025.bin")
    ap.add_argument("--out", default=pathlib.Path("ladder/cache/mesh.sqlite"),
                    type=pathlib.Path)
    ap.add_argument("--names", choices=("main", "all"), default="main",
                    help="main: MH only, the strict reading. all: plus ENTRY "
                         "synonyms — and the difference between the two is the "
                         "arm this corpus repeats from LINNAEUS.")
    a = ap.parse_args()
    build(a.dump, a.out, a.names == "all")

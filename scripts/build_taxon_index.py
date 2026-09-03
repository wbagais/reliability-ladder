#!/usr/bin/env python3
"""
build_taxon_index.py — NCBI Taxonomy as a ladder vocabulary.

WHY THIS CORPUS, AND WHY IT IS THE MOST INFORMATIVE OF THE FIVE

The calibration set had three vocabulary shapes — a clinical ontology, a flat
139-tag set, a gazetteer — and three of the five corpora were geoparsing. A
threshold exercised on three corpora of one kind is not calibrated.

Species normalisation is a third mechanism for the no-overlap stratum, and it is
unlike the other two. Geography's is demonyms and abbreviations (`French` for
`Republic of France`); FiNER's is a numeral against an English phrase. Here it is
**vernacular against scientific nomenclature**: LINNAEUS annotates `patients`,
`human`, `mice`, `mouse`, `yeast` to *Homo sapiens*, *Mus musculus*,
*Saccharomyces cerevisiae*. Measured on its 4,259 mentions, the eight commonest
surface forms are all common nouns.

AND IT ANSWERS A QUESTION THE GEO ARM COULD ONLY DEFER

`names.dmp` gives every name a taxon is known by, with a NAME CLASS on each:

    4932 | baker's yeast   | genbank common name
    4932 | brewer's yeast  | common name
    4932 | Candida robusta | synonym
    4932 | Saccharomyces cerevisiae | scientific name

The GeoNames build faced the same choice — main name only, or alternates too —
and took main-name-only for comparability with CADEC, leaving the other arm
unmeasured. Here both are one flag, and the corpus is built out of exactly the
mentions that distinguish them. `--names scientific` is the strict reading;
`--names all` includes common names and synonyms, and the difference between the
two IS the measurement.

    python3 scripts/build_taxon_index.py --dump ~/Downloads/linn --out ladder/cache/taxonomy.sqlite
    python3 scripts/build_taxon_index.py --dump ~/Downloads/linn --names all \\
        --out ladder/cache/taxonomy-all.sqlite

`names.dmp` is ~312 MB and `nodes.dmp` ~230 MB; the index is a few hundred MB
and takes a couple of minutes.
"""
from __future__ import annotations

import argparse
import pathlib
import sqlite3
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from ladder.registry import normalise_term

#: Which `name class` values count as a term for this taxon.
STRICT = {"scientific name"}
ALL = {"scientific name", "genbank common name", "common name", "synonym",
       "equivalent name", "genbank synonym"}

#: Ranks that behave like the ladder's `is_finding` — the KIND of thing a
#: species annotation should resolve to. A mention resolving to a kingdom or a
#: superphylum is not wrong exactly, but it is not a species, and rung 1's
#: semantic check exists to notice that difference.
SPECIES_LIKE = {"species", "subspecies", "strain", "no rank", "varietas",
                "forma", "species group", "species subgroup"}


def _rows(path: pathlib.Path):
    """The `.dmp` format: fields separated by `\\t|\\t`, lines ending `\\t|`."""
    with path.open(encoding="utf-8", errors="replace") as fh:
        for line in fh:
            yield [c.strip() for c in line.rstrip("\n").rstrip("|").split("\t|")]


def build(dump: pathlib.Path, out: pathlib.Path, classes: set[str]) -> None:
    names_f, nodes_f = dump / "names.dmp", dump / "nodes.dmp"
    for f in (names_f, nodes_f):
        if not f.is_file():
            sys.exit(f"{f} not found. Download and extract:\n"
                     "    curl -sL https://ftp.ncbi.nlm.nih.gov/pub/taxonomy/"
                     "taxdump.tar.gz -o taxdump.tar.gz\n"
                     "    tar xzf taxdump.tar.gz names.dmp nodes.dmp")

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
    print(f"[taxon] ranks <- {nodes_f.name}", file=sys.stderr)
    ranks: dict[str, str] = {}
    for f in _rows(nodes_f):
        if len(f) >= 3:
            ranks[f[0]] = f[2]

    # is_finding carries RANK here, the way it carries the SNOMED hierarchy on
    # CADEC and is vacuously 1 on a gazetteer and a tag set. This is the first
    # non-clinical vocabulary in the set where rung 1's semantic check has
    # anything real to check.
    concepts = [(tid, 1, 1 if rank in SPECIES_LIKE else 0, 1)
                for tid, rank in ranks.items()]
    db.executemany("INSERT OR IGNORE INTO concept VALUES (?,?,?,?)", concepts)

    print(f"[taxon] names <- {names_f.name}  ({len(classes)} name class(es))",
          file=sys.stderr)
    batch, kept, seen = [], 0, 0
    for f in _rows(names_f):
        if len(f) < 4:
            continue
        seen += 1
        tid, name, cls = f[0], f[1], f[3]
        if cls not in classes:
            continue
        norm = normalise_term(name)
        if not norm:
            continue
        batch.append((tid, name, norm, 1 if cls == "scientific name" else 0))
        kept += 1
        if len(batch) >= 50_000:
            db.executemany("INSERT INTO description VALUES (?,?,?,?)", batch)
            batch.clear()
    if batch:
        db.executemany("INSERT INTO description VALUES (?,?,?,?)", batch)

    print("[taxon] indexing", file=sys.stderr)
    db.executescript("CREATE INDEX d_concept ON description(concept_id);"
                     "CREATE INDEX d_norm ON description(norm);")

    species = sum(1 for _, _, f, _ in concepts if f)
    db.executemany("INSERT INTO meta VALUES (?,?)", [
        ("release", f"NCBI Taxonomy, {len(concepts):,} taxa, "
                    f"{kept:,} names ({'all classes' if len(classes) > 1 else 'scientific only'})"),
        ("source", "https://ftp.ncbi.nlm.nih.gov/pub/taxonomy/taxdump.tar.gz"),
        ("name_classes", ", ".join(sorted(classes))),
        ("is_finding", "carries RANK: 1 for species-like ranks "
                       f"({species:,} of {len(concepts):,}), 0 otherwise. Unlike "
                       "the gazetteer and the tag set, this check is NOT vacuous "
                       "here — a mention resolving to a kingdom is not a species."),
        ("built", time.strftime("%Y-%m-%d %H:%M:%S")),
    ])
    db.commit(); db.close(); tmp.replace(out)

    mb = out.stat().st_size / 1e6
    print(f"\n[taxon] {len(concepts):,} taxa · {kept:,} names kept of {seen:,} "
          f"· {species:,} species-like", file=sys.stderr)
    print(f"[taxon] {out} · {mb:.0f} MB · {time.time()-t0:.0f}s", file=sys.stderr)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="NCBI Taxonomy -> the ladder's vocabulary schema")
    ap.add_argument("--dump", required=True, type=pathlib.Path,
                    help="directory holding names.dmp and nodes.dmp")
    ap.add_argument("--out", default=pathlib.Path("ladder/cache/taxonomy.sqlite"),
                    type=pathlib.Path)
    ap.add_argument("--names", choices=("scientific", "all"), default="scientific",
                    help="scientific: the strict reading, comparable with the "
                         "GeoNames main-name-only build. all: common names and "
                         "synonyms too — and the difference between the two is "
                         "the measurement this corpus exists to make.")
    a = ap.parse_args()
    build(a.dump, a.out, STRICT if a.names == "scientific" else ALL)

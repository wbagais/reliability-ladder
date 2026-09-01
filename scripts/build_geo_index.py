#!/usr/bin/env python3
"""
build_geo_index.py — GeoNames as a ladder vocabulary, in SNOMED's schema.

WHY THERE IS NO vocab_geo.py

`ladder/registry.py` turned out to be generic. Its two tables —
`concept(id, active, is_finding, is_finding_hist)` and
`description(concept_id, term, norm, fsn)` — carry nothing SNOMED-specific, so a
GeoNames index written into the same shape is read by the SAME `Registry` class
with the same `exists`, `terms`, `preferred`, `lexical_match`, `search`,
`codes_for_term` and `shortlist`.

That matters for more than convenience. The third corpus must be measured by the
same check as the first, or the comparison is between two implementations rather
than between two vocabularies. Reusing `Registry` makes that structural instead
of merely intended.

THE DECISIONS BAKED IN HERE, all recorded before any measurement

1. FULL `allCountries`, 13,463,962 rows. Not a curated subset.
   Measured gold coverage on GeoWebNews's 575 distinct canonical names:

       cities15000                        37.4%
       + countryInfo + admin1 + admin2    55.5%
       allCountries                       98.1%   <- this one

   No curated cut reaches usable coverage, because the gold contains oceans,
   mountain ranges, stadiums, airports and buildings alongside cities —
   `Atlantic Ocean`, `Appalachian Mountains`, `Anfield`, `Bank of England`,
   `Amsterdam Airport Schiphol`. A vocabulary that cannot contain 45% of the
   answer key puts a ceiling under every downstream number, and the ceiling
   would be ours rather than the task's.

   The size is also the point. 13.4M entries against SNOMED's 129,675 makes
   retrieval a genuinely harder search, so an ACCEPT lane that survives it is
   better evidence than one that does not have to.

2. MAIN NAME ONLY — GeoNames column 2 — not the alternate-names list.
   The alternates hold demonyms and exonyms ("French", "USA", "Moskva"), and
   including them would lift the ACCEPT rate substantially. That is a real
   experimental arm and it is deliberately NOT this one: CADEC compares against
   a concept's own terms, so the strict reading keeps the three corpora
   comparable. Run alternates as arm 2 and report both.

3. `is_finding` is 1 for every row, and `active` likewise.
   GeoNames is flat and has no retirement, so both checks are vacuously true —
   exactly as on FiNER. Stated rather than faked: two of rung 1's three free
   checks cannot fire here, and only `exists` and `lexical_match` do real work.

USAGE

    python3 scripts/build_geo_index.py \
        --dump ~/Downloads/allCountries.txt \
        --out  ladder/cache/geonames.sqlite

Takes a few minutes and about 1.5 GB of input. The output is read-only
afterwards, like the SNOMED index, and is gitignored.
"""
from __future__ import annotations

import argparse
import pathlib
import sqlite3
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from ladder.registry import normalise_term  # the SAME normaliser CADEC uses

# GeoNames dump columns, from the format described at
# https://download.geonames.org/export/dump/ — readme.txt
COL_ID, COL_NAME, COL_ASCII, COL_ALT = 0, 1, 2, 3
COL_FEATURE_CLASS, COL_FEATURE_CODE = 6, 7


def build(dump: pathlib.Path, out: pathlib.Path, batch: int = 50_000) -> None:
    if not dump.is_file():
        sys.exit(f"{dump} not found. Download and unzip:\n"
                 "    curl -O https://download.geonames.org/export/dump/allCountries.zip")

    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".building")
    if tmp.exists():
        tmp.unlink()

    db = sqlite3.connect(tmp)
    db.executescript(
        """
        PRAGMA journal_mode=OFF; PRAGMA synchronous=OFF;
        CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT);
        CREATE TABLE concept(id TEXT PRIMARY KEY, active INT, is_finding INT, is_finding_hist INT);
        CREATE TABLE description(concept_id TEXT, term TEXT, norm TEXT, fsn INT);
        """
    )

    t0 = time.time()
    concepts, descriptions = [], []
    rows = kept = skipped_blank = 0

    print(f"[geo] reading {dump.name}", file=sys.stderr)
    with dump.open(encoding="utf-8", errors="replace") as fh:
        for line in fh:
            rows += 1
            f = line.rstrip("\n").split("\t")
            if len(f) <= COL_FEATURE_CODE:
                continue
            gid, name = f[COL_ID].strip(), f[COL_NAME].strip()
            if not gid or not name:
                skipped_blank += 1
                continue
            norm = normalise_term(name)
            if not norm:
                # A name that normalises to nothing cannot be matched or
                # retrieved, so it would sit in the index as a permanent miss.
                skipped_blank += 1
                continue

            # active and is_finding are 1 for every row. GeoNames has no
            # retirement and no semantic hierarchy, so rung 1's is_active and
            # is_finding checks are VACUOUS here — the same shape as FiNER, and
            # worth knowing before either number is quoted.
            concepts.append((gid, 1, 1, 1))
            descriptions.append((gid, name, norm, 1))
            kept += 1

            if len(concepts) >= batch:
                db.executemany("INSERT OR IGNORE INTO concept VALUES (?,?,?,?)", concepts)
                db.executemany("INSERT INTO description VALUES (?,?,?,?)", descriptions)
                concepts.clear(); descriptions.clear()
                if rows % 1_000_000 == 0:
                    print(f"[geo]   {rows:,} rows", file=sys.stderr)

    if concepts:
        db.executemany("INSERT OR IGNORE INTO concept VALUES (?,?,?,?)", concepts)
        db.executemany("INSERT INTO description VALUES (?,?,?,?)", descriptions)

    print("[geo] indexing", file=sys.stderr)
    db.executescript(
        "CREATE INDEX d_concept ON description(concept_id);"
        "CREATE INDEX d_norm ON description(norm);"
    )

    db.executemany(
        "INSERT INTO meta VALUES (?,?)",
        [("release", f"GeoNames allCountries, main name only, {kept:,} places"),
         ("source", "https://download.geonames.org/export/dump/allCountries.zip"),
         ("names", "MAIN NAME ONLY — alternate names deliberately excluded, see the "
                   "module docstring. Demonyms and exonyms are ~30% of GeoWebNews gold "
                   "and live in the alternates; including them is a separate arm."),
         ("gold_coverage", "98.1% of GeoWebNews's 575 distinct canonical names "
                           "(cities15000 alone reaches 37.4%)"),
         ("vacuous_checks", "is_active and is_finding are 1 for every row — GeoNames "
                            "has no retirement and no hierarchy, so two of rung 1's "
                            "three free checks cannot fire"),
         ("built", time.strftime("%Y-%m-%d %H:%M:%S"))])
    db.commit()
    db.close()
    tmp.replace(out)

    mb = out.stat().st_size / 1e6
    print(f"\n[geo] {kept:,} places from {rows:,} rows "
          f"({skipped_blank:,} skipped: blank or unnormalisable)", file=sys.stderr)
    print(f"[geo] {out} · {mb:.0f} MB · {time.time()-t0:.0f}s", file=sys.stderr)
    print(f"\nCheck it with the SAME class CADEC uses:\n"
          f"    PYTHONPATH=. python3 -c \"from ladder.registry import Registry; "
          f"r=Registry('{out}'); print(r.release); "
          f"print(r.search('Paris', 3)); print(r.lexical_match('Paris', "
          f"r.codes_for_term('Paris')[0]))\"", file=sys.stderr)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="GeoNames -> the ladder's vocabulary schema")
    ap.add_argument("--dump", required=True, type=pathlib.Path,
                    help="allCountries.txt from the GeoNames dump")
    ap.add_argument("--out", default=pathlib.Path("ladder/cache/geonames.sqlite"),
                    type=pathlib.Path)
    a = ap.parse_args()
    build(a.dump, a.out)

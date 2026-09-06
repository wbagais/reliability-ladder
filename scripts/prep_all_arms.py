#!/usr/bin/env python3
"""
prep_all_arms.py — the four blocked corpora, with every choice stated.

WHAT THIS UNBLOCKS

LGL, TR-News, LINNAEUS and BC5CDR have gold-side numbers and no model arm,
because each needs four things that do not exist yet: a vocabulary index, a
manifest, frozen splits, and a declared retrieval mode. This builds all four,
and it writes each decision into the manifest rather than making it silently.

THE DECISIONS, MADE HERE AND ON THE RECORD

**Retrieval mode.** CADEC and PsyTAR use DENSE retrieval, because a keyword
embedding index exists over SNOMED. The other four have no such index and use
LEXICAL. That is not a detail: on CADEC the same substitution was measured to
cost about 21 points of recall@20, so **no absolute score from a lexical-arm
corpus is comparable with a dense-arm one.** The matrix is uniform in models
and not in retrieval, and any table built from it must say so.

**LINNAEUS's vocabulary.** It has two, and the choice moves the endorsable
stratum 5.4% -> 35.4% on identical records: scientific names only, or plus the
common names and synonyms NCBI ships. The arm runs SCIENTIFIC-ONLY, matching
the main-name-only GeoNames build, so the two lexical arms are read the same
way. The all-names figure stays a gold-side measurement, and the gap between
them is already recorded.

**BC5CDR's entity.** It annotates Chemical and Disease. The arm runs DISEASE,
as the closer analogue of CADEC's reactions and of PsyTAR's ADRs. Chemicals are
the larger class and a separate arm.

**Splits.** LGL, TR-News and LINNAEUS get seeded random splits by the same rule
the geo arm used. BC5CDR ships its own train/dev/test and keeps them — a corpus
that has a standard split and is given a new one stops being comparable with
everything published on it.

    python3 scripts/prep_all_arms.py --dry-run     # see the decisions
    python3 scripts/prep_all_arms.py               # write manifests + splits
    python3 scripts/prep_all_arms.py --indexes     # also build MeSH + taxonomy
"""
from __future__ import annotations

import argparse
import json
import pathlib
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

BASE = pathlib.Path("manifest.json")

ARMS = {
    "manifest.lgl.json": {
        "name": "LGL",
        "corpus": {
            "name": "LGL", "adapter": "geoxml", "corpus": "lgl",
            "root": "data/gwn/Corpora", "splits_dir": "data/lgl/splits",
        },
        "vocab": "ladder/cache/geonames.sqlite",
        "retrieval": "lexical",
        "why": ("588 news articles, GeoNames-linked, gold carries the geonameid "
                "so there is no resolution step to get wrong — unlike GeoWebNews, "
                "whose name-and-coordinates format forced a lookup that picked a "
                "Brooklyn in South Africa."),
    },
    "manifest.trnews.json": {
        "name": "TR-News",
        "corpus": {
            "name": "TR-News", "adapter": "geoxml", "corpus": "trnews",
            "root": "data/gwn/Corpora", "splits_dir": "data/trnews/splits",
        },
        "vocab": "ladder/cache/geonames.sqlite",
        "retrieval": "lexical",
        "why": ("118 articles. 116 of its 1,275 spans do not land and are "
                "dropped with a reason; every rate here is over the remainder."),
    },
    "manifest.linnaeus.json": {
        "name": "LINNAEUS",
        "corpus": {
            "name": "LINNAEUS", "adapter": "linnaeus",
            "root": "data/linnaeus/manual-corpus-species-1.0",
            "splits_dir": "data/linnaeus/splits",
        },
        "vocab": "ladder/cache/taxonomy.sqlite",
        "retrieval": "lexical",
        "why": ("Species mentions against NCBI Taxonomy, SCIENTIFIC NAMES ONLY. "
                "The all-names build moves the endorsable stratum 5.4% -> 35.4% "
                "on these same records; scientific-only is chosen to match the "
                "main-name-only GeoNames build so the lexical arms read alike."),
    },
    "manifest.bc5cdr.json": {
        "name": "BC5CDR",
        "corpus": {
            "name": "BC5CDR", "adapter": "bc5cdr", "entity": "Disease",
            "root": "data/bc5cdr/CDR.Corpus.v010516",
            "splits_dir": "data/bc5cdr/splits",
        },
        "vocab": "ladder/cache/mesh.sqlite",
        "retrieval": "lexical",
        "why": ("1,500 abstracts, MeSH-linked, and the corpus KEEPS ITS OWN "
                "train/dev/test — a corpus with a standard split that is given a "
                "new one stops being comparable with everything published on it. "
                "Entity: Disease, the closer analogue of CADEC's reactions."),
    },
}


def build_indexes(dry: bool) -> None:
    jobs = [
        ("ladder/cache/mesh.sqlite",
         ["python3", "scripts/build_mesh_index.py", "--dump", "data/mesh",
          "--out", "ladder/cache/mesh.sqlite"],
         "MeSH 2025 descriptors + supplementary"),
        ("ladder/cache/taxonomy.sqlite",
         ["python3", "scripts/build_taxon_index.py", "--dump", "data/taxonomy",
          "--out", "ladder/cache/taxonomy.sqlite"],
         "NCBI Taxonomy, scientific names only"),
    ]
    for out, cmd, what in jobs:
        if pathlib.Path(out).is_file():
            print(f"  {out} exists — skipping")
            continue
        print(f"  building {out}  ({what})")
        if dry:
            print(f"      {' '.join(cmd)}")
            continue
        subprocess.run(cmd, check=False)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--indexes", action="store_true",
                    help="also build the MeSH and taxonomy indexes")
    a = ap.parse_args()

    if not BASE.is_file():
        sys.exit("manifest.json not found — run from the repo root")
    base = json.loads(BASE.read_text())

    if a.indexes:
        print("\n  INDEXES\n")
        build_indexes(a.dry_run)

    print("\n  MANIFESTS — each derived from manifest.json, corpus + vocabulary only\n")
    for path, spec in ARMS.items():
        man = json.loads(BASE.read_text())
        man["corpus"] = dict(spec["corpus"])
        man["corpus"]["_why"] = spec["why"]
        man.setdefault("vocabulary", {})["snomed_db"] = spec["vocab"]
        man["vocabulary"]["_backend_note"] = (
            f"{spec['vocab']} — NOT SNOMED. The schema is the same and the "
            "content is not, so a code from this arm means nothing in another.")
        man.setdefault("rungs", {}).setdefault("0", {})["rung0_retrieval"] = spec["retrieval"]
        man["rungs"]["0"]["_rung0_retrieval_note"] = (
            "LEXICAL. No embedding index exists over this vocabulary, and "
            "building one is a separate arm. On CADEC the same substitution was "
            "measured to cost ~21 points of recall@20, so no absolute score here "
            "is comparable with a dense-retrieval corpus."
            if spec["retrieval"] == "lexical" else "dense, as CADEC")
        # The few-shot ids are CADEC's and do not exist here. Cleared rather
        # than guessed: run.py's pool-split guard refuses to start without
        # valid ones, which is the behaviour that caught this on PsyTAR.
        man["rungs"]["0"].pop("rung0_fewshot_docs", None)
        man["output"] = {"dir": f"out/{spec['name'].lower().replace('-', '')}"}
        man["_arm"] = (f"{spec['name']} — one variable against manifest.json: the "
                       f"corpus and the vocabulary it requires. Model, rungs and "
                       f"every rung parameter are unchanged.")
        print(f"  {path}")
        print(f"      {spec['name']:11} vocab {spec['vocab']}")
        print(f"      retrieval {spec['retrieval']}")
        for line in _wrap(spec["why"], 66):
            print(f"      {line}")
        print()
        if not a.dry_run:
            pathlib.Path(path).write_text(json.dumps(man, indent=2) + "\n")

    if a.dry_run:
        print("  --dry-run: nothing written.\n")
        return 0

    print("  NEXT — freeze the splits, then prove each arm is one variable:\n")
    for path, spec in ARMS.items():
        if spec["name"] != "BC5CDR":
            print(f"    PYTHONPATH=. python3 -m ladder.run --manifest {path} init")
    print()
    for path in ARMS:
        print(f"    PYTHONPATH=. python3 scripts/manifest_diff.py manifest.json "
              f"{path} --declared corpus vocabulary rung0_retrieval")
    print()
    print("  Then pick two pool documents per corpus for the few-shot block —")
    print("  by a rule stated BEFORE looking, as PsyTAR's were: the first two")
    print("  pool documents in split order with at least two mentions.\n")
    return 0


def _wrap(s: str, n: int):
    out, line = [], ""
    for w in s.split():
        if len(line) + len(w) + 1 > n:
            out.append(line); line = w
        else:
            line = f"{line} {w}".strip()
    if line:
        out.append(line)
    return out


if __name__ == "__main__":
    raise SystemExit(main())

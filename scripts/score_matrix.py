#!/usr/bin/env python3
"""
score_matrix.py — the free check across six corpora and three models.

WHAT THE MATRIX IS FOR

Two quantities, and they are different questions:

    lane OCCUPANCY     what share of records REACH the ACCEPT lane
    lane CORRECTNESS   what share of what lands there IS RIGHT

CADEC gives 42.4% and 75-82%. PsyTAR, the only matched comparison in the set,
gives 24.7% and 80.9% — the reach moved and the precision did not. This asks
whether that holds across five more corpora and three model families.

WHAT IS NOT UNIFORM, AND MUST TRAVEL WITH EVERY NUMBER BELOW

**Retrieval.** CADEC and PsyTAR retrieve DENSELY over an embedding index built
from SNOMED. The other four retrieve LEXICALLY, because no such index exists for
a gazetteer, a taxonomy, a flat tag set or MeSH. On CADEC that substitution was
measured to cost about 21 points of recall@20, so a lexical-arm occupancy is not
comparable with a dense-arm one. The column is printed for exactly this reason.

**Split size.** LINNAEUS runs 25 dev documents, not 40: it has 95 in total and
40+60 leaves nothing in the pool.

**Draws.** One per cell, not three. Three draws were measured bit-identical on
GeoWebNews and PsyTAR at temperature 0, so a third demonstration buys nothing —
but that is an inference from two corpora and is stated rather than assumed.

**Models.** Three, not five. `qwen3:4b` had no entry in models.yaml and fell
back to a 2,000-token budget it spends thinking, returning empty content — the
file's own comment describes that failure for `qwen3:8b`. `granite4:micro-h`
returns mentions as STRINGS where every other model returns objects. Both are
findings about the harness and neither is a column of numbers.

    PYTHONPATH=. python3 scripts/score_matrix.py
    PYTHONPATH=. python3 scripts/score_matrix.py --csv matrix.csv
"""
from __future__ import annotations

import argparse
import csv
import glob
import json
import pathlib
import re
import sys
from collections import defaultdict

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

#: corpus -> (manifest, retrieval mode, split, documents)
KNOWN = {
    "finer":    ("manifest.finer.json",    "dense*", "dev", 40),
    "geo":      ("manifest.geo.json",      "lexical", "dev", 40),
    "psytar":   ("manifest.psytar.json",   "dense",  "dev", 40),
    "lgl":      ("manifest.lgl.json",      "lexical", "dev", 40),
    "trnews":   ("manifest.trnews.json",   "lexical", "dev", 40),
    "linnaeus": ("manifest.linnaeus.json", "lexical", "dev", 25),
    "bc5cdr":   ("manifest.bc5cdr.json",   "lexical", "dev", 40),
}
#: For reference only, from runs on another machine. NOT produced by this matrix
#: and not comparable with it cell for cell — different hardware, and
#: floating-point differs between a CPU-split model and a GPU one.
CADEC = ("CADEC", "dense", 0.424, (0.75, 0.82))


def shipped(rec: dict):
    ch = rec.get("checks") or {}
    code = rec.get("sct") or (ch.get("withheld") or {}).get("sct")
    if isinstance(code, (list, tuple)):
        code = code[0] if code else None
    return code


def gold_for(manifest: str, split: str):
    from ladder.run import _corpus_for, _corpus_opts, _corpus_root
    m = json.loads(pathlib.Path(manifest).read_text())
    mod = _corpus_for(m)
    docs = mod.load_corpus(_corpus_root(m), **_corpus_opts(m))
    sd = pathlib.Path(m["corpus"]["splits_dir"]) / f"{split}.json"
    ids = json.loads(sd.read_text()) if sd.is_file() else []
    ids = ids if isinstance(ids, list) else ids.get("doc_ids", [])
    return {(mm.doc_id, mm.spans[0][0]): mm.sct
            for d in ids if d in docs for mm in docs[d].mentions}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default="out/matrix")
    ap.add_argument("--csv")
    a = ap.parse_args()

    cells = {}
    for d in sorted(glob.glob(f"{a.dir}/*/")):
        name = pathlib.Path(d.rstrip("/")).name
        m = re.match(r"(.+?)-(.+)-d(\d+)$", name)
        if not m:
            continue
        corpus, model, draw = m.groups()
        recs = [f for f in glob.glob(f"{d}*.records.jsonl")
                if not re.search(r"\.r\d+\.records\.jsonl$", f)]
        if recs:
            # The NEWEST run in the cell. A cell re-run after a fix holds both
            # files, and `recs[0]` is the older one — which silently scored the
            # pre-fix records and reported this morning's numbers as tonight's.
            cells[(corpus, model)] = max(recs, key=lambda f: pathlib.Path(f).stat().st_mtime)

    if not cells:
        sys.exit(f"no cells in {a.dir}")

    golds = {}
    rows = []
    for (corpus, model), f in sorted(cells.items()):
        if corpus not in KNOWN:
            continue
        manifest, retrieval, split, ndocs = KNOWN[corpus]
        if corpus not in golds:
            golds[corpus] = gold_for(manifest, split)
        gold = golds[corpus]

        lanes = defaultdict(lambda: {"n": 0, "scored": 0, "ok": 0})
        total = 0
        for line in open(f):
            r = json.loads(line)
            if not r.get("spans"):
                continue
            total += 1
            v = (r.get("checks") or {}).get("r1_verdict") or "—"
            L = lanes[v]
            L["n"] += 1
            g = gold.get((r["doc_id"], r["spans"][0][0]))
            if g is None:
                continue
            L["scored"] += 1
            L["ok"] += shipped(r) in g

        acc, band = lanes.get("ACCEPT", {}), lanes.get("BAND", {})
        rows.append({
            "corpus": corpus, "model": model, "retrieval": retrieval,
            "docs": ndocs, "records": total,
            "accept": acc.get("n", 0),
            "occupancy": acc.get("n", 0) / total if total else 0.0,
            "acc_scored": acc.get("scored", 0),
            "correctness": (acc.get("ok", 0) / acc["scored"]) if acc.get("scored") else None,
            "band_correctness": (band.get("ok", 0) / band["scored"]) if band.get("scored") else None,
        })

    w = max(len(r["corpus"]) for r in rows)
    print(f"\n  the free check across {len({r['corpus'] for r in rows})} corpora "
          f"x {len({r['model'] for r in rows})} models · one draw · rungs 0-1\n")
    print(f"  {'corpus':<{w}} {'model':<20} {'retr':<8} {'recs':>5} "
          f"{'ACCEPT':>7} {'occ':>7} {'scored':>7} {'correct':>8} {'BAND':>7}")
    print("  " + "-" * (w + 74))
    last = None
    for r in sorted(rows, key=lambda x: (x["corpus"], x["model"])):
        if last and r["corpus"] != last:
            print()
        last = r["corpus"]
        c = "—" if r["correctness"] is None else f"{r['correctness']:.1%}"
        b = "—" if r["band_correctness"] is None else f"{r['band_correctness']:.1%}"
        print(f"  {r['corpus']:<{w}} {r['model']:<20} {r['retrieval']:<8} "
              f"{r['records']:5} {r['accept']:7} {r['occupancy']:6.1%} "
              f"{r['acc_scored']:7} {c:>8} {b:>7}")

    print()
    print(f"  For reference, from runs on ANOTHER MACHINE and not part of this")
    print(f"  matrix: CADEC, dense retrieval, occupancy {CADEC[2]:.1%}, "
          f"correctness {CADEC[3][0]:.0%}-{CADEC[3][1]:.0%}.")
    print(f"  Not comparable cell for cell — floating point differs between a")
    print(f"  CPU-split model and a GPU one, so those are two experiments.")
    print()
    print("  `retr` is the column to read before comparing any two rows. A")
    print("  lexical arm and a dense arm differ by about 21 points of recall@20")
    print("  on CADEC, which is larger than most differences in this table.")
    print("  * FiNER has no retrieval at all: its 139 tags ARE the menu.")
    print()

    if a.csv:
        with open(a.csv, "w", newline="") as fh:
            wr = csv.DictWriter(fh, fieldnames=list(rows[0]))
            wr.writeheader(); wr.writerows(rows)
        print(f"  wrote {a.csv}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

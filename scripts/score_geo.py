#!/usr/bin/env python3
"""
score_geo.py — the GeoWebNews arm, scored against the answer key's own coordinates.

WHY THIS EXISTS RATHER THAN score_run

The ladder scores by comparing a predicted identifier against a gold identifier.
That works where the answer key gives one. GeoWebNews does not: gwn_full.txt
carries the canonical NAME and a LATITUDE and LONGITUDE, and no geonameid at
all.

`corpus_geo.resolve_ids` filled that gap by taking `codes_for_term(name)[0]` —
the first GeoNames row with a matching name. That is arbitrary, and it is wrong
often enough to invalidate a headline: 1,117 of 2,399 gold mentions have a name
that more than one GeoNames entry holds, and the id it happened to choose for
`Brooklyn` is a Brooklyn in South Africa. Scored against that, 97 of the first
run's 240 "wrong" answers carried a label IDENTICAL to gold's.

So this scorer ignores the invented ids and uses what the annotators actually
provided. The standard geoparsing metric is distance: an answer is correct if
the place it names is within a threshold of the coordinates the annotators
recorded. 10 km is the conventional cut and 161 km appears in the literature as
a looser one; both are reported here, because a single threshold hides whether
a system is picking the wrong suburb or the wrong continent.

WHAT IT REPORTS, and why each column is there

  per model, per draw     the three draws are identical on this corpus, which is
                          itself a result and is checked rather than assumed
  the ACCEPT lane         the arm's whole reason for existing. If rung 1's free
                          check identifies a subset that is ~85% correct on
                          CADEC, does it do so here?
  by overlap stratum      identical / subset / partial / none, carried on
                          GoldMention.cadec_type. The stratum is the independent
                          variable and the mechanism is only visible per-stratum.
  median error in km      the number that says WHAT KIND of wrong an answer is.
                          A 5 km miss is the wrong suburb; a 3,000 km miss is a
                          same-named place on another continent, which is a
                          disambiguation failure and not a retrieval one.
  menu ceiling            whether the correct place was on the candidate menu at
                          all. Without this, a low score cannot be attributed:
                          the model may be choosing badly, or may never have
                          been offered the right answer. Measured on CADEC as
                          86.1% recall@20 and it is the single most important
                          control here.

    PYTHONPATH=. python3 scripts/score_geo.py
    PYTHONPATH=. python3 scripts/score_geo.py --dump ~/Downloads/allCountries.txt
"""
from __future__ import annotations

import argparse
import collections
import glob
import json
import math
import os
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from ladder.corpus_geo import load_corpus, read_split, overlap_stratum
from ladder.registry import Registry

NEAR_KM = 10.0      # the conventional geoparsing cut
FAR_KM = 161.0      # the looser one that appears in the literature


def haversine(a, b) -> float:
    R, p = 6371.0, math.pi / 180
    dphi, dlam = (b[0] - a[0]) * p, (b[1] - a[1]) * p
    h = (math.sin(dphi / 2) ** 2
         + math.cos(a[0] * p) * math.cos(b[0] * p) * math.sin(dlam / 2) ** 2)
    return 2 * R * math.asin(math.sqrt(h))


def gold_coordinates(root: str, split_ids: set[str]) -> dict:
    """(doc_id, start) -> (lat, lon, surface, canonical). Straight from the key."""
    out = {}
    path = pathlib.Path(root) / "gwn_full.txt"
    for i, line in enumerate(path.read_text(encoding="utf-8").splitlines()):
        doc_id = f"GWN.{i:03d}"
        if doc_id not in split_ids:
            continue
        for m in line.strip().split("||"):
            f = m.split(",,")
            if len(f) < 6:
                continue
            try:
                out[(doc_id, int(f[4]))] = (float(f[2]), float(f[3]),
                                            f[1].strip(), f[0].strip())
            except ValueError:
                continue
    return out


def predicted_code(rec: dict):
    """The code, including one rung 5 withdrew.

    Abstention moves the answer to checks.withheld, so reading `sct` alone
    scores the system's SHIPPING decision rather than its ANSWER. Both are worth
    knowing and they are different questions; this scorer asks the second.
    """
    return rec.get("sct") or ((rec.get("checks") or {}).get("withheld") or {}).get("sct")


def load_geonames_coords(dump: str, wanted: set[str]) -> dict:
    """geonameid -> (lat, lon), for the ids that were actually predicted.

    A single pass over 13.4M rows, filtered to what is needed. Loading the whole
    file would be 1.6 GB of dictionary for a few hundred lookups.
    """
    coords = {}
    if not os.path.isfile(dump):
        print(f"  ! {dump} not found — distance scoring unavailable.\n"
              f"    curl -O https://download.geonames.org/export/dump/allCountries.zip",
              file=sys.stderr)
        return coords
    with open(dump, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            f = line.split("\t")
            if f[0] in wanted:
                try:
                    coords[f[0]] = (float(f[4]), float(f[5]))
                except (ValueError, IndexError):
                    pass
    return coords


def menu_ceiling(gold, registry, dump_coords, k=20, sample=200):
    """Was the right place ON THE MENU at all?

    The control that makes every other number interpretable. A low score means
    one of two very different things — the model chose badly from a good menu,
    or the menu never held the answer — and only this separates them.

    Measured against COORDINATES, not ids: a candidate counts as the right place
    if it sits within NEAR_KM of where the annotators put it. That is the same
    standard the predictions are held to.
    """
    hits = tried = 0
    need = set()
    per_query = {}
    for (doc_id, start), (lat, lon, surface, canon) in list(gold.items())[:sample]:
        cands = registry.shortlist(surface, k=k)
        per_query[(doc_id, start)] = [c["code"] for c in cands]
        need.update(c["code"] for c in cands)

    coords = dict(dump_coords)
    missing = need - coords.keys()
    if missing:
        coords.update(load_geonames_coords(ARGS.dump, missing))

    for key, codes in per_query.items():
        lat, lon, surface, canon = gold[key]
        tried += 1
        if any(code in coords and haversine((lat, lon), coords[code]) <= NEAR_KM
               for code in codes):
            hits += 1
    return hits, tried


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dump", default=os.path.expanduser("~/Downloads/allCountries.txt"))
    ap.add_argument("--root", default="data/gwn/Geocoding")
    ap.add_argument("--splits", default="data/gwn/splits")
    ap.add_argument("--split", default="test")
    ap.add_argument("--db", default="ladder/cache/geonames.sqlite")
    ap.add_argument("--ceiling", action="store_true",
                    help="also measure whether the right place was on the menu (slow)")
    global ARGS
    ARGS = ap.parse_args()

    ids = set(read_split(ARGS.splits, ARGS.split))
    gold = gold_coordinates(ARGS.root, ids)
    docs = load_corpus(ARGS.root)
    stratum = {(m.doc_id, m.spans[0][0]): m.cadec_type
               for d in ids for m in docs[d].mentions}

    runs = {}
    for tag in ("gptoss", "llama", "mistral"):
        fs = sorted(glob.glob(f"out/geo-{tag}/*.records.jsonl"))
        if fs:
            runs[tag] = fs

    wanted = set()
    for fs in runs.values():
        for f in fs:
            for line in open(f):
                c = predicted_code(json.loads(line))
                if c:
                    wanted.add(str(c))
    print(f"\nresolving {len(wanted)} predicted ids against the dump", file=sys.stderr)
    coords = load_geonames_coords(ARGS.dump, wanted)
    print(f"  {len(coords)} found\n", file=sys.stderr)

    print(f"{'arm':16} {'draws':>5} {'recs':>6} {'scored':>7} "
          f"{'<=10km':>7} {'<=161km':>8} {'median km':>10}")
    print("-" * 66)

    detail = {}
    for tag, fs in runs.items():
        signatures = set()
        first = None
        for f in fs:
            rows = [json.loads(l) for l in open(f)]
            signatures.add(len(rows))
            if first is None:
                first = rows
        n = m = near = far = 0
        errs = []
        lanes = collections.defaultdict(lambda: [0, 0])
        strata = collections.defaultdict(lambda: [0, 0])
        for rec in first:
            n += 1
            if not rec.get("spans"):
                continue
            key = (rec["doc_id"], rec["spans"][0][0])
            g = gold.get(key)
            if not g:
                continue
            m += 1
            code = predicted_code(rec)
            d = None
            if code and str(code) in coords:
                d = haversine((g[0], g[1]), coords[str(code)])
                errs.append(d)
                near += d <= NEAR_KM
                far += d <= FAR_KM
            lane = (rec.get("checks") or {}).get("r1_verdict")
            lanes[lane][0] += 1
            lanes[lane][1] += bool(d is not None and d <= NEAR_KM)
            st = stratum.get(key, "?")
            strata[st][0] += 1
            strata[st][1] += bool(d is not None and d <= NEAR_KM)
        errs.sort()
        med = errs[len(errs) // 2] if errs else float("nan")
        print(f"{tag:16} {len(fs):5} {n:6} {m:7} "
              f"{near/m if m else 0:7.3f} {far/m if m else 0:8.3f} {med:10.1f}")
        detail[tag] = (lanes, strata, len(signatures) == 1)

    print("\nreproducibility across draws")
    for tag, (_, _, same) in detail.items():
        print(f"   {tag:12} {'identical record counts' if same else 'DIFFER'}")

    print(f"\nrung 1 lane vs correctness (within {NEAR_KM:.0f} km) — the arm's question")
    print(f"{'arm':12} {'lane':10} {'n':>5} {'right':>6} {'rate':>7}")
    for tag, (lanes, _, _) in detail.items():
        for lane, (tot, ok) in sorted(lanes.items(), key=lambda x: -x[1][0]):
            print(f"{tag:12} {str(lane):10} {tot:5} {ok:6} {ok/tot if tot else 0:7.3f}")

    print("\nby lexical-overlap stratum — the independent variable")
    print(f"{'arm':12} {'stratum':11} {'n':>5} {'right':>6} {'rate':>7}")
    for tag, (_, strata, _) in detail.items():
        for st in ("identical", "subset", "partial", "none"):
            tot, ok = strata.get(st, [0, 0])
            if tot:
                print(f"{tag:12} {st:11} {tot:5} {ok:6} {ok/tot:7.3f}")

    if ARGS.ceiling:
        print("\nmenu ceiling — was the right place offered at all?")
        reg = Registry(ARGS.db)
        hits, tried = menu_ceiling(gold, reg, coords)
        print(f"   recall@20 within {NEAR_KM:.0f} km: {hits}/{tried} = "
              f"{hits/tried if tried else 0:.1%}")
        print("   CADEC's comparable figure is 86.1%. A low number here means the")
        print("   menu never held the answer, and no amount of model is the fix.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""What rung 1 can and cannot catch — the detection half of the gate.

`calibrate.py` measures rung 1's FALSE-rejection rate by replaying it over gold,
where every rejection is wrong by construction. That is half the picture. This
is the other half: take the same gold records, corrupt them in one known way at
a time, and ask what rung 1 does about it.

Both halves are model-free and run on the whole corpus, so the gate is fully
characterised before rung 0 emits a single record. When the real rung-1 rejection
rate arrives, it can be read against a known detection profile instead of being
the only number in the room.

Six corruptions, chosen to separate what the plan asserts:

    hallucinated_code    a code no release has ever contained
    wrong_type_code      a real, active concept from outside |Clinical finding|
    span_shift           the same text, offsets moved two characters
    span_fabricate       a quote that is not at those offsets at all
    plausible_wrong      a random ACTIVE CLINICAL FINDING that is not the gold
                         code -- real, well-typed, and wrong
    sibling_wrong        a finding sharing a parent with the gold code -- the
                         near-miss a normalisation model actually makes
    meddra_hallucinated  a MedDRA code no table has. Only meaningful with
                         meddra_check="reject", and included to show WHY the
                         default is "flag": the available table is the answer
                         key's 666 codes, so this scores 1.000 by construction
                         and says nothing about a real MedDRA check

The first four are what a deterministic check exists for. The last two are the
class the plan says nothing deterministic can catch; this measures how right
that is, and what the lexical lane does about it.

    python -m ladder.probe --split pool --json out/rung1_detection.json
"""

from __future__ import annotations

import argparse
import json
import random
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from ladder import corpus as corpus_mod
from ladder.calibrate import gold_to_record, load_meddra
from ladder.manifest import friendly, load_manifest
from ladder.registry import Registry
from ladder.rungs import r1
from ladder.schema import Record, ZONE_ACCEPT, ZONE_BAND, ZONE_REJECT

CORRUPTIONS = (
    "hallucinated_code",
    "wrong_type_code",
    "span_shift",
    "span_fabricate",
    "plausible_wrong",
    "sibling_wrong",
    "meddra_hallucinated",
)


def _pool(registry: Registry, sql: str, limit: int = 4000) -> list[str]:
    return [r[0] for r in registry._db.execute(sql + f" LIMIT {limit}")]


def corrupt(rec: Record, kind: str, rng: random.Random, pools: dict[str, list[str]]) -> Record | None:
    """One corruption, or None when this record cannot carry it."""
    out = rec.copy()
    if kind == "hallucinated_code":
        out.sct = str(rng.randint(10**8, 10**9))
    elif kind == "wrong_type_code":
        out.sct = rng.choice(pools["not_finding"])
    elif kind == "span_shift":
        out.spans = [(a + 2, b + 2) for a, b in rec.spans]
    elif kind == "span_fabricate":
        out.text = rec.text + " zenoprofen"
    elif kind == "plausible_wrong":
        pick = rng.choice(pools["finding"])
        if pick == rec.sct:
            return None
        out.sct = pick
    elif kind == "sibling_wrong":
        sibs = pools["siblings"].get(rec.sct or "")
        if not sibs:
            return None
        out.sct = rng.choice(sibs)
    elif kind == "meddra_hallucinated":
        if not rec.meddra:
            return None
        out.meddra = str(rng.randint(10_000_000, 99_999_999))
    else:
        raise ValueError(kind)
    return out


def build_pools(registry: Registry, gold_codes: list[str]) -> dict[str, Any]:
    findings = _pool(registry, "SELECT id FROM concept WHERE active=1 AND is_finding=1")
    not_findings = _pool(registry, "SELECT id FROM concept WHERE active=1 AND is_finding=0")
    # Siblings: concepts sharing a parent with a gold code. The is-a graph is not
    # in the index (rung 1 never needs it), so approximate a near-miss with the
    # nearest neighbours by preferred term — which is the confusion a
    # normalisation model actually makes: |Knee pain| for |Leg pain|.
    siblings: dict[str, list[str]] = {}
    for code in set(gold_codes):
        term = registry.preferred(code)
        if not term:
            continue
        head = term.split()[-1].lower()
        if len(head) < 4:
            continue
        near = [
            r[0]
            for r in registry._db.execute(
                "SELECT DISTINCT d.concept_id FROM description d JOIN concept c "
                "ON c.id = d.concept_id WHERE c.active=1 AND c.is_finding=1 "
                "AND d.norm LIKE ? AND d.concept_id != ? LIMIT 8",
                (f"%{head}", code),
            )
        ]
        if near:
            siblings[code] = near
    return {"finding": findings, "not_finding": not_findings, "siblings": siblings}


def run(docs, doc_ids, registry, params, seed: int = 42, meddra=None) -> dict[str, Any]:
    rng = random.Random(seed)
    mentions = [m for d in doc_ids for m in docs[d].mentions if m.sct]
    pools = build_pools(registry, [m.sct[0] for m in mentions])
    out: dict[str, Any] = {"n_records": len(mentions), "corruptions": {}}
    examples: dict[str, list] = defaultdict(list)

    for kind in CORRUPTIONS:
        zones: Counter = Counter()
        reasons: Counter = Counter()
        by_type: dict[str, Counter] = defaultdict(Counter)
        skipped = 0
        for m in mentions:
            rec = corrupt(gold_to_record(m), kind, rng, pools)
            if rec is None:
                skipped += 1
                continue
            z, reason, checks = r1.zone(rec, docs[m.doc_id].text, registry, params, meddra)
            zones[z] += 1
            by_type[m.entity_type][z] += 1
            if reason:
                reasons[reason] += 1
            if z == ZONE_ACCEPT and len(examples[kind]) < 6:
                examples[kind].append(
                    {
                        "text": rec.text,
                        "gold": m.sct,
                        "gold_term": registry.preferred(m.sct[0]),
                        "planted": rec.sct,
                        "planted_term": registry.preferred(rec.sct),
                    }
                )
        n = sum(zones.values())
        out["corruptions"][kind] = {
            "n": n,
            "skipped": skipped,
            "rejected": zones[ZONE_REJECT],
            "banded": zones[ZONE_BAND],
            "accepted": zones[ZONE_ACCEPT],
            "detection_rate": round(zones[ZONE_REJECT] / n, 5) if n else 0.0,
            "wrongly_accepted_rate": round(zones[ZONE_ACCEPT] / n, 5) if n else 0.0,
            "reasons": dict(reasons),
            "by_entity_type": {
                t: {
                    "n": sum(c.values()),
                    "rejected": c[ZONE_REJECT],
                    "banded": c[ZONE_BAND],
                    "accepted": c[ZONE_ACCEPT],
                    "detection_rate": round(c[ZONE_REJECT] / sum(c.values()), 5),
                }
                for t, c in sorted(by_type.items())
            },
            "examples_wrongly_accepted": examples[kind],
        }
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--manifest", default="manifest.json")
    ap.add_argument("--split", default="pool")
    ap.add_argument("--json")
    ap.add_argument(
        "--lexical-mode",
        help="override the manifest, to compare what the ACCEPT/BAND divider costs",
    )
    ap.add_argument("--meddra-check", choices=["off", "flag", "reject"])
    a = ap.parse_args(argv)

    man = load_manifest(a.manifest)
    docs = corpus_mod.load_corpus(man["corpus"]["cadec_root"])
    registry = Registry(man["vocabulary"]["snomed_db"])
    doc_ids = sorted(docs) if a.split == "all" else corpus_mod.read_split(
        man["corpus"]["splits_dir"], a.split
    )
    params = {**r1.DEFAULTS, **{k: v for k, v in man["rungs"].get("1", {}).items() if k in r1.DEFAULTS}}
    if a.lexical_mode:
        params["lexical_mode"] = a.lexical_mode
    if a.meddra_check:
        params["meddra_check"] = a.meddra_check
    meddra = load_meddra(man)
    res = run(docs, doc_ids, registry, params, seed=man["seed"], meddra=meddra)

    print(
        f"split={a.split}  {res['n_records']} coded gold records, one corruption each  "
        f"(lexical_mode={params['lexical_mode']}, meddra_check={params['meddra_check']})\n"
    )
    print(f"{'corruption':20s} {'n':>6} {'REJECT':>8} {'BAND':>7} {'ACCEPT':>8}   caught   shipped")
    for kind, r in res["corruptions"].items():
        print(
            f"{kind:20s} {r['n']:>6} {r['rejected']:>8} {r['banded']:>7} {r['accepted']:>8}"
            f"   {r['detection_rate']:6.3f}   {r['wrongly_accepted_rate']:6.3f}"
        )
        for t, b in r["by_entity_type"].items():
            print(
                f"  {'  · ' + t:18s} {b['n']:>6} {b['rejected']:>8} {b['banded']:>7} "
                f"{b['accepted']:>8}   {b['detection_rate']:6.3f}"
            )
    print(
        "\ncaught  = rung 1 rejected it outright."
        "\nshipped = rung 1 put it in ACCEPT: a wrong answer the gate actively vouched for."
        "\nthe gap = BAND, where rung 1 correctly declines to have an opinion."
    )
    if a.json:
        Path(a.json).parent.mkdir(parents=True, exist_ok=True)
        Path(a.json).write_text(json.dumps(res, indent=2))
        print(f"\nwrote {a.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(friendly(main))

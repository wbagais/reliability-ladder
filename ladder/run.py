"""The pipeline. Owner A owns this file; owner B registers a rung by adding
`ladder/rungs/rN.py` and telling A the rung number — B never edits run.py.

    python -m ladder.run init                       # step 0: splits + manifest check
    python -m ladder.run gate                       # step 3: the fixture gate
    python -m ladder.run ladder --split test        # the run
    python -m ladder.run ladder --split test --rungs 1,2 --predictions out/r0.jsonl
    python -m ladder.run ablate --split test        # each rung alone on rung-0 output

There is no free-text entry point. `--split` takes a split identifier; the
runner reads documents out of the licensed corpus by ID and nothing else.

Execution order comes from manifest["rung_order"], not from the rung numbers.
Rung IDs are identity — they are shared with anyone else running this ladder, so
renumbering them would break comparability — while order is configuration, which
makes "is 0-1-3-5-4-2-6 actually better than 0-1-2-3-4-5-6?" a one-line ablation
rather than an assertion.
"""

from __future__ import annotations

import argparse
import csv
import importlib
import json
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any, Callable

from ladder import corpus as corpus_mod
from ladder.ledger import Ledger
from ladder.manifest import friendly, load_manifest
from ladder.registry import MeddraTable, Registry
from ladder.schema import (
    OPEN_ZONES,
    Record,
    ZONE_ABSTAIN,
    ZONE_ACCEPT,
    ZONE_BAND,
    ZONE_ESCALATE,
    ZONE_REJECT,
    ZONE_RESOLVED,
    ZONE_VERIFIED,
    dumps,
    loads,
)

#: Rung 0 is the one rung that RECEIVES an empty record list: it is handed the
#: split's `sources` and returns the records every other rung then routes.


RUNG_NAMES = {
    0: "bare LLM",
    1: "deterministic",
    2: "abstention",
    3: "self-correct",
    4: "LLM judge",
    5: "voting",
    6: "human loop",
}


# --- rung loading -----------------------------------------------------------


def load_rung(n: int):
    """Import `ladder.rungs.rN`, or None if that owner has not written it yet.

    A missing rung is reported, never faked. Half a ladder honestly labelled is
    a result; a ladder with a silently absent rung is not.
    """
    try:
        return importlib.import_module(f"ladder.rungs.r{n}")
    except ModuleNotFoundError as exc:
        if exc.name and exc.name.endswith(f"r{n}"):
            return None
        raise


def load_scorer(spec: str | None) -> Callable[[Record, Any], bool] | None:
    """`module:function` — owner B's shared scorer, injected rather than imported.

    Without it the run still produces every cost and zone number; the accuracy
    columns are written empty rather than guessed.
    """
    if not spec:
        try:
            mod = importlib.import_module("ladder.score")
        except ModuleNotFoundError:
            return None
        return getattr(mod, "reaction_sct_strict", None)
    mod_name, _, fn = spec.partition(":")
    return getattr(importlib.import_module(mod_name), fn or "reaction_sct_strict")


# --- rung 0 input -----------------------------------------------------------


def gold_as_records(docs, doc_ids) -> list[Record]:
    """The gold standard dressed as rung-0 output.

    Not a baseline and not a rung — a control. Every rejection the deterministic
    rungs make on this input is a FALSE rejection, so it measures the gate's own
    error floor. Reported as `--source gold`, never as a rung 0 number.
    """
    from ladder.calibrate import gold_to_record

    return [gold_to_record(m) for d in doc_ids for m in docs[d].mentions]


def read_predictions(path: str | Path, doc_ids: set[str]) -> list[Record]:
    recs = loads(Path(path).read_text(encoding="utf-8"))
    unknown = {r.doc_id for r in recs} - doc_ids
    if unknown:
        raise SystemExit(
            f"{path} has records for {len(unknown)} documents outside the split "
            f"(e.g. {sorted(unknown)[:3]}). Split discipline: predictions for the "
            "test split may only cover the test split."
        )
    for i, r in enumerate(recs):
        if not r.record_id:
            r.record_id = f"{r.doc_id}#p{i}"
    return recs


# --- the run ----------------------------------------------------------------


def run_ladder(
    man: dict[str, Any],
    split: str,
    rungs: list[int],
    records: list[Record],
    sources: dict[str, str],
    registry: Registry | None,
    out_dir: Path,
    run_id: str,
    meddra: MeddraTable | None = None,
) -> dict[str, Any]:
    order = [n for n in man["rung_order"] if n in rungs]
    ledger = Ledger(out_dir / f"{run_id}.ledger.jsonl", run_id=run_id)
    snapshots: dict[int, list[Record]] = {}
    missing: list[int] = []

    print(f"[run] {run_id}  split={split}  records={len(records)}  order={order}")
    for n in order:
        mod = load_rung(n)
        if mod is None:
            missing.append(n)
            print(f"[run] rung {n} ({RUNG_NAMES[n]}) — not implemented, skipped")
            continue
        cfg: dict[str, Any] = dict(man["rungs"].get(str(n), {}))
        cfg.update(
            ledger=ledger, registry=registry, meddra=meddra, manifest=man, split=split
        )
        t0 = time.perf_counter()
        records = mod.apply(records, sources, cfg)
        dt = time.perf_counter() - t0
        snapshots[n] = [r.copy() for r in records]
        verdicts = ledger.verdicts(n)
        routed = any(p.get("rung") == n for r in records for p in r.provenance)
        counts = verdicts if verdicts else Counter(r.zone for r in records)
        label = "judged  " if verdicts and not routed else "routed  "
        print(
            f"[run] rung {n} ({RUNG_NAMES[n]:14s}) {dt:6.2f}s  {label}"
            + "  ".join(f"{z}={c}" for z, c in sorted(counts.items()))
        )
    ledger.close()

    return {
        "run_id": run_id,
        "split": split,
        "order": order,
        "missing_rungs": missing,
        "records": records,
        "snapshots": snapshots,
        "ledger": ledger,
    }


# --- reporting --------------------------------------------------------------

CSV_COLUMNS = [
    "rung",
    "layer",
    "n_records",
    "accept",
    "band",
    "reject",
    "abstained",
    "escalated",
    "verified",
    "r1_reject_pct",
    "r1_mode",
    "coverage",
    "f1_sct_strict",
    "yield",
    "settled",
    "corrupted",
    "err_per_100",
    "tokens_per_record",
    "p95_s",
    "reviews_per_100",
    "marginal_tokens_per_error",
    "marginal_reviews_per_error",
    "ci_low",
    "ci_high",
]


def results_rows(result: dict[str, Any], is_correct=None, gold=None) -> list[dict[str, Any]]:
    ledger: Ledger = result["ledger"]
    n = len(result["records"])
    costs = ledger.cost_by_rung(n_records=n)
    rows = []
    prev_errors = None
    for rung in result["order"]:
        snap = result["snapshots"].get(rung)
        if snap is None:
            continue
        # A rung that judges without routing (rung 1 in "observe" mode) has to be
        # reported on what it CONCLUDED; every other rung on where records ended
        # up. Reading zones for rung 1 in observe mode would report all-zeroes
        # and quietly drop the rung 1 rejection rate, which is the milestone.
        verdicts = ledger.verdicts(rung)
        z = verdicts if verdicts else Counter(r.zone for r in snap)
        cost = costs.get(rung, {})
        # "Would this ship if the run stopped at this rung?" A rejected record
        # has been called wrong by the gate, so it is not an answer even though
        # rung 2 has not withdrawn it yet.
        answered = [r for r in snap if r.zone not in (ZONE_ABSTAIN, ZONE_REJECT) and r.sct]
        settled = [r for r in snap if r.zone not in OPEN_ZONES]
        row = {c: "" for c in CSV_COLUMNS}
        row.update(
            rung=rung,
            layer=RUNG_NAMES[rung],
            n_records=len(snap),
            accept=z[ZONE_ACCEPT],
            band=z[ZONE_BAND],
            reject=z[ZONE_REJECT],
            abstained=z[ZONE_ABSTAIN],
            escalated=z[ZONE_ESCALATE],
            verified=z[ZONE_VERIFIED] + z[ZONE_RESOLVED],
            settled=len(settled),
            coverage=round(len(answered) / len(snap), 5) if snap else "",
            tokens_per_record=round(cost.get("tokens_per_record", 0.0), 2),
            p95_s=round(cost.get("p95_latency_s", 0.0), 4),
            reviews_per_100=round(cost.get("reviews_per_100", 0.0), 2),
        )
        if rung == 1:
            row["r1_reject_pct"] = round(100 * z[ZONE_REJECT] / len(snap), 3) if snap else ""
            row["r1_mode"] = next(
                (e.extra.get("mode") for e in ledger.rows if e.rung == 1), ""
            )
        if is_correct and gold is not None:
            correct = sum(1 for r in answered if is_correct(r, gold))
            errors = len(answered) - correct
            row["f1_sct_strict"] = round(correct / len(answered), 5) if answered else 0.0
            row["yield"] = round(correct / len(snap), 5) if snap else 0.0
            row["corrupted"] = errors
            row["err_per_100"] = round(100 * errors / len(snap), 3) if snap else ""
            # The rungs are cumulative, so a rung's OWN spend is the marginal
            # spend. Dividing by the errors it prevented gives the exchange rate
            # the article is actually about — in two currencies, never fused.
            tokens = cost.get("tokens_in", 0.0) + cost.get("tokens_out", 0.0)
            reviews = cost.get("human_minutes", 0.0)
            if prev_errors is not None and prev_errors > errors:
                prevented = prev_errors - errors
                row["marginal_tokens_per_error"] = round(tokens / prevented, 1)
                row["marginal_reviews_per_error"] = round(reviews / prevented, 2)
            prev_errors = errors
        rows.append(row)
    return rows


def write_results(rows: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=CSV_COLUMNS)
        w.writeheader()
        w.writerows(rows)


# --- subcommands ------------------------------------------------------------


def cmd_init(a) -> int:
    man = load_manifest(a.manifest)
    docs = corpus_mod.load_corpus(man["corpus"]["cadec_root"])
    mentions = sum(len(d.mentions) for d in docs.values())
    print(f"corpus  : {len(docs)} documents, {mentions} gold mentions")

    db = Path(man["vocabulary"]["snomed_db"])
    if not db.exists():
        print(
            f"\nvocabulary index missing. Build it once (a few seconds):\n"
            f"    python -m ladder.registry --build "
            f"--release {man['vocabulary']['snomed_release_dir']}",
            file=sys.stderr,
        )
        return 2
    reg = Registry(db)
    print(f"vocab   : {reg.release}  {reg.stats()}")
    # The plan's first-three-commands gate: a real code resolves, a fake one does not.
    assert reg.exists("162031009") and not reg.exists("999999999"), "vocabulary gate FAILED"
    print("gate    : real code resolves, fake code does not — rung 1 has a vocabulary")

    splits_dir = Path(man["corpus"]["splits_dir"])
    if (splits_dir / "test.json").exists() and not a.force:
        for name in ("dev", "test", "pool"):
            ids = corpus_mod.read_split(splits_dir, name)
            recs = corpus_mod.gold_records(docs, ids)
            print(f"split   : {name:5s} {len(ids):5d} docs  {len(recs):5d} mentions (frozen)")
        return 0
    splits = corpus_mod.make_splits(
        docs,
        seed=man["seed"],
        n_dev=man["corpus"]["n_dev_docs"],
        n_test=man["corpus"]["n_test_docs"],
    )
    corpus_mod.write_splits(
        splits, splits_dir, {"seed": man["seed"], "corpus": man["corpus"]["version"]}
    )
    for name, ids in splits.items():
        recs = corpus_mod.gold_records(docs, ids)
        cl = sum(1 for m in recs if m.gold_kind == "concept_less")
        print(f"split   : {name:5s} {len(ids):5d} docs  {len(recs):5d} mentions  {cl} concept_less")
    print(f"\nwrote {splits_dir}/*.json — these are frozen; never regenerate them.")
    return 0


def cmd_gate(a) -> int:
    """Step 3: ten hand-made records through the harness, one deliberately broken."""
    from ladder.fixture import run_gate

    return run_gate(a.manifest)


def cmd_ladder(a) -> int:
    man = load_manifest(a.manifest)
    docs = corpus_mod.load_corpus(man["corpus"]["cadec_root"])
    doc_ids = corpus_mod.read_split(man["corpus"]["splits_dir"], a.split)
    sources = {d: docs[d].text for d in doc_ids}
    registry = Registry(man["vocabulary"]["snomed_db"])
    meddra = _load_meddra(man)
    rungs = _parse_rungs(a.rungs)

    if a.source == "gold":
        records = gold_as_records(docs, doc_ids)
        rungs = [n for n in rungs if n != 0]
    elif a.predictions:
        records = read_predictions(a.predictions, set(doc_ids))
        rungs = [n for n in rungs if n != 0]
    else:
        r0 = load_rung(0)
        if r0 is None:
            raise SystemExit(
                "rung 0 is not implemented yet (owner B). Run against a prediction\n"
                "file with --predictions out/r0.jsonl, or measure the deterministic\n"
                "gate's own error floor with --source gold."
            )
        records = []  # rung 0 generates them from `sources`

    out_dir = Path(man["output"]["dir"])
    run_id = a.run_id or f"{a.split}_{a.source}_{time.strftime('%Y%m%d-%H%M%S')}"
    result = run_ladder(
        man, a.split, rungs, records, sources, registry, out_dir, run_id, meddra=meddra
    )

    gold = {m.record_id: m for d in doc_ids for m in docs[d].mentions}
    scorer = load_scorer(a.scorer)
    rows = results_rows(result, is_correct=scorer, gold=gold)
    write_results(rows, out_dir / f"{run_id}.results.csv")
    (out_dir / f"{run_id}.records.jsonl").write_text(dumps(result["records"]), encoding="utf-8")
    (out_dir / f"{run_id}.manifest.json").write_text(json.dumps(man, indent=2))

    print(
        f"\n{'rung':>4}  {'layer':14s} {'accept':>7} {'band':>6} {'reject':>7} "
        f"{'abstain':>8} {'cov':>6}"
    )
    for r in rows:
        print(
            f"{r['rung']:>4}  {r['layer']:14s} {r['accept']:>7} {r['band']:>6} "
            f"{r['reject']:>7} {r['abstained']:>8} {r['coverage']:>6}"
            + (f"   (rung 1 {r['r1_mode']}: judged, not routed)" if r.get("r1_mode") == "observe" else "")
        )
    if result["missing_rungs"]:
        print(f"\nNOT IN THIS RUN: rungs {result['missing_rungs']} (not implemented)")
    if scorer is None:
        print("NO SCORER: accuracy columns are empty. Wire ladder/score.py (owner B).")
    print(f"\nwrote {out_dir}/{run_id}.*")
    return 0


def _load_meddra(man: dict[str, Any]) -> MeddraTable | None:
    path = man.get("vocabulary", {}).get("meddra_csv")
    if not path:
        return None
    p = Path(path)  # already absolutised by manifest._resolve_paths
    if not p.exists():
        print(f"[run] meddra table {p} not found — MedDRA checks are off", file=sys.stderr)
        return None
    return MeddraTable(p, name=man["vocabulary"].get("meddra_release") or p.name)


def _parse_rungs(spec: str) -> list[int]:
    out: list[int] = []
    for part in spec.split(","):
        part = part.strip()
        if "-" in part:
            a, b = part.split("-")
            out.extend(range(int(a), int(b) + 1))
        elif part:
            out.append(int(part))
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="ladder.run", description=__doc__.split("\n")[0])
    ap.add_argument("--manifest", default="manifest.json")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("init", help="step 0 — verify corpus + vocabulary, write the frozen splits")
    p.add_argument("--force", action="store_true", help="regenerate splits (do not)")
    p.set_defaults(fn=cmd_init)

    p = sub.add_parser("gate", help="step 3 — the fixture gate")
    p.set_defaults(fn=cmd_gate)

    p = sub.add_parser("ladder", help="run the ladder over a split")
    p.add_argument("--split", default="test")
    p.add_argument("--rungs", default="0-6")
    p.add_argument("--source", default="model", choices=["model", "gold"])
    p.add_argument("--predictions", help="JSONL of rung-0 records (owner B's output)")
    p.add_argument("--scorer", help="module:function, defaults to ladder.score if present")
    p.add_argument("--run-id")
    p.set_defaults(fn=cmd_ladder)

    a = ap.parse_args(argv)
    return friendly(a.fn, a)


if __name__ == "__main__":
    raise SystemExit(main())

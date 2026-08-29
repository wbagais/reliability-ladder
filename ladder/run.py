"""The pipeline. A rung registers itself by existing: add `ladder/rungs/rN.py`
and the runner picks it up. Nothing else needs editing to add one.

    python -m ladder.run init                       # step 0: splits + manifest check
    python -m ladder.run gate                       # step 3: the fixture gate
    python -m ladder.run ladder --split test        # the run
    python -m ladder.run ladder --split test --rungs 1,2 --predictions out/r0.jsonl
    python -m ladder.run ablate --split test        # each rung ALONE on the same input
    python -m ladder.run ablate --split test --source gold --rungs 1,2

There is no free-text entry point. `--split` takes a split identifier; the
runner reads documents out of the licensed corpus by ID and nothing else.

Execution order comes from manifest["rung_order"], which is now the identity
permutation: rung ID equals execution position, so 0-1-2-3-4-5-6 is both the
numbering and the running order. Order is still read from configuration rather
than assumed, so a different order remains testable — see docs/decisions.md for
the renumbering and the old-to-new mapping every earlier measurement uses.
"""

from __future__ import annotations

import argparse
import csv
import importlib
import json
import sys
import time
from collections import Counter
import functools
from pathlib import Path
from typing import Any, Callable

from ladder import clean as clean_mod
from ladder import corpus as corpus_mod

# Set by cmd_ladder when --tui is passed. run_ladder consults it rather than
# taking a parameter, so no caller signature changes and nothing else in the
# module has to know the monitor exists.
_MON = None
_TUI_REQUESTED = False


def _corpus_for(man):
    """The corpus adapter named in the manifest. Defaults to CADEC.

    Added for the FiNER-139 arm. schemas/adapter.py is listed in the plan as
    one of the three contracts and was never written, so there is no declared
    interface — only the five functions ladder/corpus.py happens to expose.
    That absence is a finding; see docs/decisions.md.
    """
    name = (man.get("corpus") or {}).get("adapter", "cadec")
    if name == "cadec":
        return corpus_mod
    if name == "finer":
        from ladder import corpus_finer
        return corpus_finer
    raise ValueError(f"unknown corpus adapter {name!r}")


def _corpus_opts(man):
    """Corpus-specific loader options from the manifest.

    CADEC's load_corpus takes only a root. FiNER's needs sampling parameters —
    how many sentences per pseudo-document, how many documents, in what order —
    and those are properties of the CORPUS, so they belong in the manifest
    rather than in the adapter's defaults. An earlier version had them in the
    manifest and read from the defaults, so the config was decorative.
    """
    c = man.get("corpus") or {}
    return {k: v for k, v in (c.get("sampling") or {}).items()
            if not k.startswith("_")}


def _corpus_root(man):
    c = man.get("corpus") or {}
    return c.get("root") or c["cadec_root"]


def _vocab_for(man):
    """The vocabulary the manifest names. Registry unless told otherwise."""
    if (man.get("vocabulary") or {}).get("backend") == "finer-tags":
        from ladder import vocab_finer
        return vocab_finer.load(_corpus_root(man))
    return Registry(man["vocabulary"]["snomed_db"])
from ladder import llm as llm_mod
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
    2: "self-correct",
    3: "voting",
    4: "LLM judge",
    5: "abstention",
    6: "human loop",
}


# --- rung loading -----------------------------------------------------------


def load_rung(n: int):
    """Import `ladder.rungs.rN`, or None if that rung has not been written yet.

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
    """`module:function` — the shared scorer, injected rather than imported.

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


def load_outcome(spec: str | None = None) -> Callable[..., str] | None:
    """`ladder.score:outcome` — the four-way version of the same judgement.

    Injected the same way and for the same reason as `load_scorer`: run.py must
    not import the scorer, so a checkout without one still produces every cost
    and zone number. Absent, the outcome columns are written empty; they are
    never inferred from the boolean, which cannot tell outdated from invented.
    """
    if spec:
        mod_name, _, fn = spec.partition(":")
        return getattr(importlib.import_module(mod_name), fn or "outcome", None)
    try:
        mod = importlib.import_module("ladder.score")
    except ModuleNotFoundError:
        return None
    return getattr(mod, "outcome", None)


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
    _ledger_path = out_dir / f"{run_id}.ledger.jsonl"
    ledger = Ledger(_ledger_path, run_id=run_id)

    global _MON
    if _TUI_REQUESTED and _MON is None:
        # Started HERE rather than in cmd_ladder because this is the first
        # point at which the ledger path exists. A monitor pointed at a file
        # that has not been created yet shows an empty frame and looks broken.
        import sys as _sys
        _sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
        from ladder_top import Monitor
        _MON = Monitor(str(_ledger_path), provenance={
            "run": run_id,
            "split": split,
            "order": ",".join(str(r) for r in [g["rung"] for g in rungs])
            if rungs and isinstance(rungs[0], dict) else "",
        }).start()
    else:
        print(f"[run] watch:  python3 scripts/ladder_top.py --file {_ledger_path}")
    snapshots: dict[int, list[Record]] = {}
    callers: dict[int, Any] = {}
    aggregates: dict[int, dict] = {}
    missing: list[int] = []

    print(f"[run] {run_id}  split={split}  records={len(records)}  order={order}")
    for n in order:
        mod = load_rung(n)
        if mod is None:
            missing.append(n)
            print(f"[run] rung {n} ({RUNG_NAMES[n]}) — not implemented, skipped")
            continue
        cfg: dict[str, Any] = dict(man["rungs"].get(str(n), {}))
        # A rung disabled in the manifest is a RECORDED state, never a silent
        # skip: "rung n did not run" and "rung n found nothing" are different
        # claims about the same numbers, and only the first belongs to a rung
        # that was off. The check sits BEFORE model resolution — a disabled
        # rung must not need a model to be recorded as disabled.
        if cfg.get("enabled", True) is False:
            aggregates[n] = {"disabled": True}
            ledger.log(
                rung=n, doc_id="-", record_id=f"rung{n}", zone="CONFIG",
                outcome="disabled", reason=f"manifest.rungs.{n}.enabled=false",
                evaluable="could_not_run",
            )
            print(f"[run] rung {n} ({RUNG_NAMES[n]}) — DISABLED in manifest, not run")
            continue
        # The rung never picks a model. One resolution point, here, so that
        # "which model produced this number" is answered by the manifest.
        caller = llm_mod.for_rung(n, man)
        if caller is not None:
            callers[n] = caller
            print(f"[run] rung {n} model={caller.spec} ({caller.role})")
        if _MON is not None:
            _MON.mark_running(n, f"{caller.spec}" if caller else "")
        cfg.update(
            ledger=ledger,
            registry=registry,
            # The task description belongs to the CORPUS, not the ladder. None
            # keeps rung 0's CADEC wording, so nothing changes for that arm.
            prompt_slots=(man.get("corpus") or {}).get("prompts"),
            # Bound with the manifest's sampling options. An unbound
            # loader builds a DIFFERENT corpus than the one the splits
            # were cut from, and the pool ids then do not exist.
            corpus_loader=functools.partial(
                _corpus_for(man).load_corpus, **_corpus_opts(man)),
            meddra=meddra,
            manifest=man,
            split=split,
            llm=caller,
        )
        # Rung 3 votes by calling the extractor k times, so it needs a SAMPLER,
        # not the greedy caller: at temperature 0 the disk cache would return
        # one answer k times and the rung would report unanimity it never
        # measured. The temperature is the rung's setting; the model is not.
        if n == 3 and caller is not None:
            cfg["llm"] = caller.sampler(float(cfg.get("temperature", 0.7)))
        # Rung 4 takes its model under its own keys, and refuses to fall back to
        # the extractor — a model judging its own output measures
        # self-consistency, not correctness. Resolution still happens here.
        if n == 4:
            extractor = llm_mod.for_rung(0, man)
            cfg.update(
                judge_llm=caller,
                judge_model=caller.spec if caller else None,
                extractor_model=extractor.spec if extractor else None,
            )
        t0 = time.perf_counter()
        if _MON is not None:
            # A rung's report() prints, and printing into a Live display tears
            # it. Captured text goes to the reports panel instead — collapsed
            # to one line once read, most recent expanded. Nothing is lost.
            import contextlib as _ctx, io as _io
            _buf = _io.StringIO()
            with _ctx.redirect_stdout(_buf):
                out = mod.apply(records, sources, cfg)
            _txt = _buf.getvalue()
            if _txt.strip():
                _MON.add_report(n, _txt)
        else:
            out = mod.apply(records, sources, cfg)
        # Two return conventions live in ladder/rungs: r1 and r5 return the
        # records, r0/r2/r3/r4 return (records, aggregates). Normalising here
        # means neither convention has to be rewritten to make a run work.
        if isinstance(out, tuple):
            records, meta = out
            aggregates[n] = meta
        else:
            records = out
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
    if _MON is not None:
        _MON.stop()

    return {
        "run_id": run_id,
        "split": split,
        "order": order,
        "missing_rungs": missing,
        "records": records,
        "snapshots": snapshots,
        "ledger": ledger,
        "callers": callers,
        "aggregates": aggregates,
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
    # Appended 2026-08-24 with the fourth outcome. `corrupted` is still every
    # error; these two name which KIND, and are never subtracted from it. A
    # retired code the release replaced with the gold answer is out of date,
    # not invented — see ladder/score.py.
    "sct_outdated",
    "sct_abstained",
    "err_per_100",
    # Appended 2026-08-26 with the fifth outcome (the mirror of sct_outdated:
    # the model answered the successor of a RETIRED GOLD code). Appended at
    # the end because CSV_COLUMNS is append-only, not beside its siblings.
    "sct_modernised",
    "tokens_per_record",
    "p95_s",
    "reviews_per_100",
    "marginal_tokens_per_error",
    "marginal_reviews_per_error",
    "ci_low",
    "ci_high",
]


def snapshot_row(
    rung: Any,
    layer: str,
    snap: list[Record],
    z: Counter,
    cost: dict[str, float],
    is_correct=None,
    gold=None,
    outcome_fn=None,
    vocab=None,
) -> tuple[dict[str, Any], int | None]:
    """One results row from one snapshot of the record set.

    Returns (row, errors). `errors` is what the marginal columns divide into,
    and only a CUMULATIVE run can compute those — so this function does not.
    Both `ladder` and `ablate` build their rows here, because two accounting
    paths is how a benchmark ends up with two numbers for the same run.
    """
    # "Would this ship if the run stopped at this rung?" A rejected record has
    # been called wrong by the gate, so it is not an answer even though rung 5
    # has not withdrawn it yet.
    answered = [r for r in snap if r.zone not in (ZONE_ABSTAIN, ZONE_REJECT) and r.sct]
    settled = [r for r in snap if r.zone not in OPEN_ZONES]
    row = {c: "" for c in CSV_COLUMNS}
    row.update(
        rung=rung,
        layer=layer,
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
    errors = None
    if is_correct and gold is not None:
        correct = sum(1 for r in answered if is_correct(r, gold))
        errors = len(answered) - correct
        row["f1_sct_strict"] = round(correct / len(answered), 5) if answered else 0.0
        row["yield"] = round(correct / len(snap), 5) if snap else 0.0
        row["corrupted"] = errors
        row["err_per_100"] = round(100 * errors / len(snap), 3) if snap else ""
        if outcome_fn is not None:
            # Which KIND of error, not how many. `corrupted` is unchanged and
            # these do not sum to it: `incorrect` is the remainder and is left
            # implicit rather than given a column that would invite the three
            # to be read as a partition of the record set.
            got = [outcome_fn(r, gold, vocab) for r in answered]
            row["sct_outdated"] = got.count("outdated")
            row["sct_abstained"] = got.count("abstained")
            row["sct_modernised"] = got.count("modernised")
    return row, errors


def results_rows(
    result: dict[str, Any], is_correct=None, gold=None, outcome_fn=None, vocab=None
) -> list[dict[str, Any]]:
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
        row, errors = snapshot_row(
            rung, RUNG_NAMES[rung], snap, z, cost, is_correct, gold, outcome_fn, vocab
        )
        if rung == 1:
            row["r1_reject_pct"] = round(100 * z[ZONE_REJECT] / len(snap), 3) if snap else ""
            row["r1_mode"] = next(
                (e.extra.get("mode") for e in ledger.rows if e.rung == 1), ""
            )
        if errors is not None:
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
    docs = _corpus_for(man).load_corpus(_corpus_root(man), **_corpus_opts(man))
    mentions = sum(len(d.mentions) for d in docs.values())
    print(f"corpus  : {len(docs)} documents, {mentions} gold mentions")

    # The vocabulary gate is corpus-independent: a real code resolves and a fake
    # one does not. Only the codes differ, so they come from the backend rather
    # than being hardcoded to SNOMED.
    if man["vocabulary"].get("backend") == "finer-tags":
        reg = _vocab_for(man)
        real = sorted(reg._tags)[0]
        print(f"vocab   : {reg.name}  {reg.stats()}")
    else:
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
        real = "162031009"
        print(f"vocab   : {reg.release}  {reg.stats()}")
    assert reg.exists(real) and not reg.exists("999999999"), "vocabulary gate FAILED"
    print("gate    : real code resolves, fake code does not — rung 1 has a vocabulary")

    splits_dir = Path(man["corpus"]["splits_dir"])
    if (splits_dir / "test.json").exists() and not a.force:
        for name in ("dev", "test", "pool"):
            ids = _corpus_for(man).read_split(splits_dir, name)
            recs = _corpus_for(man).gold_records(docs, ids)
            print(f"split   : {name:5s} {len(ids):5d} docs  {len(recs):5d} mentions (frozen)")
        return 0
    splits = _corpus_for(man).make_splits(
        docs,
        seed=man["seed"],
        n_dev=man["corpus"]["n_dev_docs"],
        n_test=man["corpus"]["n_test_docs"],
    )
    _corpus_for(man).write_splits(
        splits, splits_dir, {"seed": man["seed"], "corpus": man["corpus"]["version"]}
    )
    for name, ids in splits.items():
        recs = _corpus_for(man).gold_records(docs, ids)
        cl = sum(1 for m in recs if m.gold_kind == "concept_less")
        print(f"split   : {name:5s} {len(ids):5d} docs  {len(recs):5d} mentions  {cl} concept_less")
    print(f"\nwrote {splits_dir}/*.json — these are frozen; never regenerate them.")
    return 0


def cmd_gate(a) -> int:
    """Step 3: ten hand-made records through the harness, one deliberately broken."""
    from ladder.fixture import run_gate

    return run_gate(a.manifest)


NO_RUNG0 = (
    "rung 0 is not implemented yet. Run against a prediction\n"
    "file with --predictions out/r0.jsonl, or measure the deterministic\n"
    "gate's own error floor with --source gold."
)


def _load_inputs(man: dict[str, Any], split: str):
    """Corpus, split, sources and the two vocabularies. One reader, two commands."""
    docs = _corpus_for(man).load_corpus(_corpus_root(man), **_corpus_opts(man))
    doc_ids = _corpus_for(man).read_split(man["corpus"]["splits_dir"], split)
    sources = {d: docs[d].text for d in doc_ids}
    registry = _vocab_for(man)
    return docs, doc_ids, sources, registry, _load_meddra(man)


def cmd_ladder(a) -> int:
    man = load_manifest(a.manifest)
    man = apply_overrides(man, getattr(a, "rung0_step", None),
                          getattr(a, "extractor", None))
    docs, doc_ids, sources, registry, meddra = _load_inputs(man, a.split)
    rungs = _parse_rungs(a.rungs)
    if getattr(a, "limit", 0):
        # Always announced. A truncated split is a different experiment from the
        # split, and a number produced on 1 of 40 documents must never be filed
        # as a number on dev.
        doc_ids = doc_ids[: a.limit]
        sources = {d: sources[d] for d in doc_ids}
        print(f"[run] LIMIT {a.limit}: {a.split} truncated to {doc_ids} — "
              "a smoke run, not a split result")

    if a.source == "gold":
        records = gold_as_records(docs, doc_ids)
        rungs = [n for n in rungs if n != 0]
    elif a.predictions:
        records = read_predictions(a.predictions, set(doc_ids))
        rungs = [n for n in rungs if n != 0]
    else:
        if load_rung(0) is None:
            raise SystemExit(NO_RUNG0)
        records = []  # rung 0 generates them from `sources`

    out_dir = Path(man["output"]["dir"])
    run_id = a.run_id or f"{a.split}_{a.source}_{time.strftime('%Y%m%d-%H%M%S')}"
    global _TUI_REQUESTED
    _TUI_REQUESTED = (
        not getattr(a, "plain", False)
        and sys.stdout.isatty()          # never in a pipe, a log or CI
    )
    # A monitor that hides a traceback is worse than no monitor: rich.Live
    # owns the terminal and the next frame overwrites whatever was printed.
    # Stop it first, then let the exception through untouched.
    try:
        result = run_ladder(
            man, a.split, rungs, records, sources, registry, out_dir, run_id,
            meddra=meddra,
        )
    except BaseException:
        global _MON
        if _MON is not None:
            _MON.stop()
            _MON = None
        raise

    # Declared exclusions are applied to the ANSWER KEY, once, here — see
    # ladder/clean.py. 7 of 7,311 reaction mentions cannot be answered (3 carry
    # only invalid codes, 4 quote text that is not at their offsets). They are
    # excluded and counted, never corrected.
    excluded = clean_mod.load_exclusions()
    gold = {
        m.record_id: m
        for d in doc_ids for m in docs[d].mentions
        if m.record_id not in excluded
    }
    if excluded:
        print(f"[run] gold exclusions applied: {len(excluded)} (see data/exclusions.csv)")
    scorer = load_scorer(a.scorer)
    rows = results_rows(
        result, is_correct=scorer, gold=gold,
        outcome_fn=load_outcome(), vocab=registry,
    )
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
        print("NO SCORER: accuracy columns are empty. Wire ladder/score.py.")
    print(f"\nwrote {out_dir}/{run_id}.*")
    return 0


def cmd_ablate(a) -> int:
    """Each rung ALONE on identical input — the single-rung ablation.

    `ladder` measures a STACK: its rung 4 row is rung 4 applied to whatever
    rungs 1, 3 and 5 already did to the records, so a difference there is
    attributable to the stack and not to rung 4. `ablate` holds the input fixed
    and varies one rung at a time, which is the comparison the article needs
    when it claims a rung bought something.

    Rung 0 is not ablatable — it MAKES the records every other rung is varied
    over. It runs once (or `--source gold` / `--predictions` supplies its
    output) and is reported as the `input` row the other rows are read against.
    """
    man = load_manifest(a.manifest)
    man = apply_overrides(man, getattr(a, "rung0_step", None),
                          getattr(a, "extractor", None))
    docs, doc_ids, sources, registry, meddra = _load_inputs(man, a.split)
    out_dir = Path(man["output"]["dir"])
    run_id = a.run_id or f"{a.split}_{a.source}_ablate_{time.strftime('%Y%m%d-%H%M%S')}"

    if a.source == "gold":
        base = gold_as_records(docs, doc_ids)
    elif a.predictions:
        base = read_predictions(a.predictions, set(doc_ids))
    else:
        if load_rung(0) is None:
            raise SystemExit(NO_RUNG0)
        seed = run_ladder(
            man, a.split, [0], [], sources, registry, out_dir, f"{run_id}.r0", meddra=meddra
        )
        base = seed["records"]

    # Declared exclusions are applied to the ANSWER KEY, once, here — see
    # ladder/clean.py. 7 of 7,311 reaction mentions cannot be answered (3 carry
    # only invalid codes, 4 quote text that is not at their offsets). They are
    # excluded and counted, never corrected.
    excluded = clean_mod.load_exclusions()
    gold = {
        m.record_id: m
        for d in doc_ids for m in docs[d].mentions
        if m.record_id not in excluded
    }
    if excluded:
        print(f"[run] gold exclusions applied: {len(excluded)} (see data/exclusions.csv)")
    scorer = load_scorer(a.scorer)
    outcome_fn = load_outcome()
    rows = [
        snapshot_row(
            "", f"input ({a.source})", base, Counter(r.zone for r in base), {},
            scorer, gold, outcome_fn, registry,
        )[0]
    ]
    missing: list[int] = []

    print(f"[ablate] {run_id}  split={a.split}  input={len(base)} records, source={a.source}")
    for n in _parse_rungs(a.rungs):
        if n == 0:
            continue
        if load_rung(n) is None:
            missing.append(n)
            print(f"[ablate] rung {n} ({RUNG_NAMES[n]}) — not implemented, skipped")
            continue
        # A fresh copy per rung: an ablation that let rung N see rung N-1's
        # mutations would be measuring the pair, which is what `ladder` is for.
        result = run_ladder(
            man,
            a.split,
            [n],
            [r.copy() for r in base],
            sources,
            registry,
            out_dir,
            f"{run_id}.r{n}",
            meddra=meddra,
        )
        rows.extend(results_rows(
            result, is_correct=scorer, gold=gold,
            outcome_fn=outcome_fn, vocab=registry,
        ))

    write_results(rows, out_dir / f"{run_id}.results.csv")
    (out_dir / f"{run_id}.manifest.json").write_text(json.dumps(man, indent=2))

    print(
        f"\n{'rung':>4}  {'layer':14s} {'accept':>7} {'band':>6} {'reject':>7} "
        f"{'abstain':>8} {'cov':>6}"
    )
    for r in rows:
        print(
            f"{r['rung']:>4}  {r['layer']:14s} {r['accept']:>7} {r['band']:>6} "
            f"{r['reject']:>7} {r['abstained']:>8} {r['coverage']:>6}"
        )
    if missing:
        print(f"\nNOT IN THIS ABLATION: rungs {missing} (not implemented)")
    if scorer is None:
        print("NO SCORER: accuracy columns are empty. Wire ladder/score.py.")
    print(
        "\nEach row is that rung applied to the SAME input, not to the row above it.\n"
        f"wrote {out_dir}/{run_id}.*"
    )
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

    def _run_args(p):
        p.add_argument("--split", default="test")
        # ON BY DEFAULT. A run with no visible progress is the failure that
        # has come up four times on this project; --plain restores the old
        # scrolling output. The monitor is skipped anyway when stdout is
        # not a terminal, so piped and CI runs are unaffected.
        p.add_argument("--plain", action="store_true",
                       help="scrolling reports instead of the live monitor")
        p.add_argument("--tui", action="store_true",
                       help=argparse.SUPPRESS)
        p.add_argument("--rungs", default="0-6")
        p.add_argument("--source", default="model", choices=["model", "gold"])
        p.add_argument("--predictions", help="JSONL of rung-0 records")
        p.add_argument("--limit", type=int, default=0,
                       help="run on the first N documents of the split. A smoke "
                            "run: the result is not a result for the split")
        p.add_argument("--scorer", help="module:function, defaults to ladder.score if present")
        p.add_argument(
            "--extractor",
            help="provider/model from ladder/models.yaml for rungs 0/2/3, "
                 "overriding manifest.model.extractor for this run. Never "
                 "changes model.judge — rung 4 must stay a different family. "
                 "A non-local provider still needs LADDER_ALLOW_REMOTE=1.",
        )
        p.add_argument(
            "--rung0-step", choices=["S0", "S1", "S2"],
            help="rung 0's extraction step for the prompt-engineering study. "
                 "Scope is identical in all three; only the way the CODE is "
                 "obtained changes. Overrides manifest.rungs.0.rung0_step so "
                 "three runs are three commands rather than three manifest "
                 "edits. S3 was dropped 2026-08-24 — see docs/decisions.md.",
        )
        p.add_argument("--run-id")
        return p

    p = _run_args(sub.add_parser("ladder", help="run the ladder over a split"))
    p.set_defaults(fn=cmd_ladder)

    p = _run_args(sub.add_parser("ablate", help="each rung ALONE on the same input"))
    p.set_defaults(fn=cmd_ablate)

    a = ap.parse_args(argv)
    return friendly(a.fn, a)


def apply_overrides(
    man: dict[str, Any], step: str | None = None, extractor: str | None = None,
    **_: Any,
) -> dict[str, Any]:
    """Fold per-run CLI overrides into the manifest the run reports.

    Into the MANIFEST, not a side channel: the step and the model both change
    what every number in the run means, so they have to appear in the copy
    written beside the results. A setting that only lived in argv would leave
    two runs looking identical on disk.

    `--extractor` never touches `model.judge`. Rung 4 must be a different
    family from the extractor, and an override that quietly made them the same
    would turn the judge into a self-judge — which measures self-consistency,
    not correctness.
    """
    if step:
        man.setdefault("rungs", {}).setdefault("0", {})["rung0_step"] = step
    if extractor:
        man.setdefault("model", {})["extractor"] = extractor
    return man


def apply_rung0_step(man: dict[str, Any], step: str | None) -> dict[str, Any]:
    """Back-compatible alias for `apply_overrides`."""
    return apply_overrides(man, step=step)


if __name__ == "__main__":
    raise SystemExit(main())

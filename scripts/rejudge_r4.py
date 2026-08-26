"""rejudge_r4.py — replay rung 4 over a finished run with the CURRENT judge.

Phase C swaps the judge (granite4:micro-h, 2B -> BioMistral-7B) without paying
for a full ladder re-run: rung 4 is one call per record and reads nothing a
saved record does not carry, so the 240 records of `full-ladder-dev-1` are
re-judged in place and the two judges compared on identical inputs.

Two replay corrections, both tested in tests/test_rejudge_r4.py:

* Rung 5 ran AFTER rung 4 and withdrew codes into `checks.withheld`, so the
  saved `sct` is null on all 208 abstained records. The judge graded the
  pre-abstention code; it is restored before re-judging.
* `r4.apply` overwrites `checks.r4*`. The incumbent's verdicts are the
  baseline (granite: pass = 33% correct vs fail = 17%), so they are stashed
  under `checks.r4_prior` first — and never re-stashed, so rerunning the
  script over its own output cannot replace granite's verdicts with the new
  judge's.

Correctness is `ladder.score.outcome` — exact span key, four outcomes, the
same collection-and-rekey path `run.py` uses — with exclusions applied to the
answer key exactly as `cmd_ladder` applies them.

Run from the repo root:

    .venv/bin/python scripts/rejudge_r4.py \\
        --records ../agitated-lewin-346b03/out/full-ladder-dev-1.records.jsonl \\
        --out out/rejudge-biomistral
"""

from __future__ import annotations

import argparse
import collections
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

from ladder.schema import Record  # noqa: E402


def restore_preabstention(rec: Record) -> bool:
    """Put back the code rung 5 withdrew, so the judge sees what rung 4 saw.

    Only an abstained record with a `withheld` stash is touched. A record that
    never had a code (rung 0 answered null) is judged as the null it was, and
    a VERIFIED record still carries its code.
    """
    withheld = rec.checks.get("withheld")
    if rec.zone == "ABSTAIN" and rec.sct is None and isinstance(withheld, dict):
        rec.sct = withheld.get("sct")
        return rec.sct is not None
    return False


def stash_prior_judge(rec: Record, judge_model: str) -> None:
    """Move the incumbent judge's verdicts out of r4.apply's way — once.

    The first stash wins: it is the baseline, and a second pass of this
    script over its own output must not replace it.
    """
    if "r4_prior" in rec.checks:
        return
    rec.checks["r4_prior"] = {
        "judge_model": judge_model,
        "r4_verdict": rec.checks.get("r4_verdict"),
        "r4_confidence": rec.checks.get("r4_confidence"),
        "r4": rec.checks.get("r4"),
    }


def split_by_verdict(pairs: list[tuple[str | None, str]]) -> dict:
    """(verdict, outcome) pairs -> {verdict: {n, correct, pct}}.

    THE comparison number: granite's was pass = 33% correct vs fail = 17%.
    A judge whose pass and fail rows show the same pct carries no signal.
    """
    table: dict = {}
    for verdict, out in pairs:
        t = table.setdefault(verdict, {"n": 0, "correct": 0})
        t["n"] += 1
        t["correct"] += out == "correct"
    for t in table.values():
        t["pct"] = round(t["correct"] / t["n"] * 100, 1)
    return table


def main(argv: list[str] | None = None) -> int:
    from ladder import clean as clean_mod
    from ladder import corpus as corpus_mod
    from ladder import llm as llm_mod
    from ladder.registry import Registry
    from ladder.rungs import r4
    from ladder.schema import loads
    from ladder.score import outcome

    ap = argparse.ArgumentParser()
    ap.add_argument("--records", required=True,
                    help="records.jsonl of the finished run to re-judge")
    ap.add_argument("--out", default="out/rejudge",
                    help="basename for <out>.records.jsonl and <out>.summary.json")
    ap.add_argument("--manifest", default="manifest.json")
    a = ap.parse_args(argv)

    man = json.loads(pathlib.Path(a.manifest).read_text())
    records = loads(pathlib.Path(a.records).read_text())
    print(f"loaded {len(records)} records from {a.records}")

    # What the run's own manifest says judged these records = the baseline.
    run_man_path = pathlib.Path(a.records.replace(".records.jsonl", ".manifest.json"))
    prior_judge = "unknown"
    if run_man_path.exists():
        prior_judge = json.loads(run_man_path.read_text())["model"]["judge"]

    restored = sum(restore_preabstention(r) for r in records)
    for rec in records:
        stash_prior_judge(rec, prior_judge)
    print(f"pre-abstention codes restored on {restored} records; "
          f"prior judge ({prior_judge}) stashed under checks.r4_prior")

    docs = corpus_mod.load_corpus(man["corpus"]["cadec_root"])
    doc_ids = sorted({r.doc_id for r in records})
    sources = {d: docs[d].text for d in doc_ids}

    excluded = clean_mod.load_exclusions()
    gold = {
        m.record_id: m
        for d in doc_ids for m in docs[d].mentions
        if m.record_id not in excluded
    }
    registry = Registry(man["vocabulary"]["snomed_db"])

    caller = llm_mod.for_rung(4, man)
    print(f"judge: {caller.spec}")
    records, agg = r4.apply(records, sources, {
        "judge_llm": caller,
        "judge_model": caller.spec,
        "extractor_model": llm_mod.resolve("extractor", man),
    })
    r4.report(agg)

    # -- the comparison the replay exists for ---------------------------------
    outcomes = {r.record_id: outcome(r, gold, registry) for r in records}

    def table(name: str, verdict_of) -> dict:
        t = split_by_verdict(
            [(verdict_of(r), outcomes[r.record_id]) for r in records])
        print(f"\n  {name}")
        for v in ("pass", "fail", None):
            if v in t:
                row = t[v]
                print(f"     {str(v):6s} n={row['n']:4d}  "
                      f"correct {row['correct']:3d}  ({row['pct']}%)")
        return {str(k): v for k, v in t.items()}

    print(f"\n{'=' * 58}\nVERDICT vs EXACT-MATCH TRUTH (pre-abstention codes)\n{'=' * 58}")
    prior_t = table(f"prior judge ({prior_judge})",
                    lambda r: r.checks["r4_prior"]["r4_verdict"])
    new_t = table(f"new judge ({caller.spec})",
                  lambda r: r.checks.get("r4_verdict"))

    # -- head-to-head ----------------------------------------------------------
    grid = collections.Counter(
        (r.checks["r4_prior"]["r4_verdict"], r.checks.get("r4_verdict"))
        for r in records)
    print("\n  head-to-head (prior, new):")
    for k, n in sorted(grid.items(), key=lambda kv: -kv[1]):
        print(f"     {str(k[0]):6s} -> {str(k[1]):6s} {n:4d}")

    # -- confidence: does the tau sweep have anything to sweep? ---------------
    confs = collections.Counter(
        r.checks.get("r4_confidence") for r in records
        if r.checks.get("r4_verdict") is not None)
    print(f"\n  new judge confidence values: {dict(sorted(confs.items(), key=lambda kv: (kv[0] is None, kv[0])))}")
    if len(confs) <= 1:
        print("  FLAT — a tau sweep over this field has nothing to sweep.")

    out = pathlib.Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    from ladder.schema import dumps
    pathlib.Path(f"{out}.records.jsonl").write_text(dumps(records), encoding="utf-8")
    summary = {
        "records": a.records,
        "prior_judge": prior_judge,
        "new_judge": caller.spec,
        "restored_preabstention": restored,
        "prior_table": prior_t,
        "new_table": new_t,
        "head_to_head": {f"{k[0]}->{k[1]}": n for k, n in grid.items()},
        "new_confidences": {str(k): v for k, v in confs.items()},
        "agg": {k: v for k, v in agg.items() if isinstance(v, (int, float, str, dict))},
    }
    pathlib.Path(f"{out}.summary.json").write_text(json.dumps(summary, indent=2))
    print(f"\nwrote {out}.records.jsonl and {out}.summary.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

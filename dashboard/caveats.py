"""C4 — caveats are DATA, held in one module and auto-attached where the
numbers they qualify render. The texts restate the repo's standing measurement
rules (CLAUDE.md / docs/decisions.md); a view showing a rung-3 number without
the samples caveat is a bug by definition.
"""
from __future__ import annotations

CAVEATS: dict[str, str] = {
    "rung3_samples": (
        "Rung 3 numbers are SAMPLES — individual votes differ between draws "
        "(measured: the record rung 3 overwrote in one run was not re-found at "
        "all in the next). Always cite the run id; a cross-draw delta is noise "
        "until shown otherwise."
    ),
    "judge_2b": (
        "Rung 4's judge is granite4:micro-h (2B) judging a 20B extractor — the "
        "wrong way round, kept as the measured lesser evil (BioMistral-7B was "
        "rejected on the 240-record re-judge, 2026-08-25). Read rung 4's "
        "numbers with that stated."
    ),
    "minutes_declared": (
        "Human minutes are priced at the declared minutes_per_record rate — an "
        "illustration, never a measurement. The headline rung-6 cost is the "
        "COUNT of records routed to a person (decided 2026-08-26)."
    ),
    "outdated_separate": (
        "`outdated` and `modernised` are never folded into `correct` — "
        "precision, recall and F1 count `correct` only. They name kinds of "
        "error, not partial credit."
    ),
    "backend_dependent": (
        "A rung 1 rejection rate is meaningless without its backend: local-rf2 "
        "and OLS4 are NOT interchangeable (an OLS4-backed exists() calls 23.9% "
        "of CADEC gold nonexistent). The backend is in the provenance footer."
    ),
    "oracle_ceiling": (
        "Oracle numbers are a CEILING derived from gold, not a measurement of "
        "human work — every such row is labeled resolved_oracle, and the "
        "oracle desk is refused on the test split by design."
    ),
    "spent_test": (
        "The test split is SPENT: phaseF-test-1 is the ladder's final test "
        "run. Test results are read-only displays; nothing is re-run."
    ),
    "live_single_document": (
        "LIVE RUN — one document through the real rungs, written to a scratch "
        "directory and deleted. It is an example of the mechanism, not a "
        "measurement: no F1, no run id in the runs list, nothing under out/. "
        "The measured numbers are on the Results tab."
    ),
    "results_drilldown": (
        "A batch run's document, drawn from the run's own records, state rows "
        "and call traces — nothing re-run. The menu-shown judge (J+) is the "
        "live run's own second pass and is not computed for a batch run."
    ),
    "no_state_table": (
        "This run predates the state table (2026-09-03): only the final state "
        "of each record is on disk, so the grid shows one row per record and "
        "rung 0's menu without the calls that produced it."
    ),
    "live_cache_hits": (
        "Some of these calls were served from .llm_cache (the same prompt was "
        "seen before). A cached call's latency is not the model's, and its "
        "reply is the earlier one — change the text to see a cold call."
    ),
}


def keys_for_run(ledger_rows: list[dict], split: str | None = None) -> list[str]:
    """Which caveats a run's own artifacts demand. Facts come from the ledger,
    never from assumptions: rung 3 disabled is a recorded state and gets no
    samples caveat, because no sample was drawn."""
    keys: list[str] = []
    by_rung: dict[int, list[dict]] = {}
    for row in ledger_rows:
        by_rung.setdefault(int(row.get("rung", -1)), []).append(row)

    r3 = by_rung.get(3, [])
    if r3 and not any(r.get("outcome") == "disabled" for r in r3):
        keys.append("rung3_samples")
    if by_rung.get(4):
        keys.append("judge_2b")
    if any(r.get("human_minutes") for r in by_rung.get(6, [])):
        keys.append("minutes_declared")
    if any(r.get("verdict") for r in by_rung.get(1, [])):
        keys.append("backend_dependent")
    if any(r.get("outcome") == "resolved_oracle" for r in ledger_rows):
        keys.append("oracle_ceiling")
    if split == "test":
        keys.append("spent_test")
    return keys


def texts(keys: list[str]) -> dict[str, str]:
    return {k: CAVEATS[k] for k in keys if k in CAVEATS}

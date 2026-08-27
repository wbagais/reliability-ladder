"""How the rungs connect — computed from the RUN'S OWN artifacts, never
hard-coded numbers.

The STRUCTURE (which rung feeds which, what each denominator means) is ladder
semantics held here as data, the same pattern as `dashboard/caveats.py`; every
COUNT, mode and enabled/disabled state comes from the run's manifest copy and
ledger. Two claims the diagram must keep distinct (spec / CLAUDE.md):

- rung 1 in "observe" mode JUDGES, it does not ROUTE — records pass through
  untouched and the verdict is a signal consumed by rungs 2 and 5. In "gate"
  mode it routes, which confounds every rung above it — rendered differently.
- a per-rung row in results.csv is a CUMULATIVE stack state ("would this ship
  if the run stopped here"); per-rung attribution is `ablate`. An ablate run
  is detectable from its own ledger (only the rung it ran — Phase E's r6
  ledgers in the archive are examples) and is labeled as such.
"""
from __future__ import annotations

from collections import Counter
from typing import Any

from ladder.rungs.r2 import DEFAULTS as R2_DEFAULTS

from dashboard.runsindex import RunInfo, read_manifest_copy
from dashboard.state import AppState

#: Denominator name -> (the rung whose output it is, what it is). Structure
#: as data; the counts beside it are always the run's own.
DENOMINATOR_SOURCES: dict[str, tuple[int | None, str]] = {
    "r0_documents": (None, "the split's documents"),
    "r1_offered": (0, "rung 0's records"),
    "r2_offered": (1, "records after rung 1's verdicts"),
    "r2_attempted": (1, "rung 1 REJECTs with a statable, correctable reason"),
    "r3_documents": (0, "documents re-drawn through rung 0's configured path"),
    "r3_resampled": (0, "documents re-drawn through rung 0's configured path"),
    "r4_offered": (3, "records after rung 3's voting"),
    "r4_judged": (3, "records after rung 3's voting"),
    "r5_offered": (4, "records carrying rung 1 + rung 4 verdicts"),
    "r6_queue": (5, "rung 5's abstained residue"),
}

#: What each rung IS — what it can and cannot do. The repo's own semantics
#: (CLAUDE.md / the rung docstrings), held as data like the caveats; the
#: run-specific facts (mode, counts, disabled) are computed beside it.
MEANINGS: dict[int, str] = {
    0: ("The extractor. Everything above only checks, votes on, or withdraws "
        "what rung 0 produced — no later rung adds a mention."),
    1: ("Deterministic checks against the vocabulary. It can prove a code "
        "WRONG; it can never prove one right — most records land in BAND "
        "(plausible, unverifiable)."),
    2: ("States a proven failure back to the model as a fact. It can only "
        "act on records rung 1 rejected for a statable reason — a pass gives "
        "it nothing to say."),
    3: ("Re-extracts each document k times and takes a real majority. The "
        "only rung that can rewrite an answer; its numbers are samples of "
        "those draws."),
    4: ("A different model family judges each claim. It writes a verdict, "
        "never a route — rung 5 is where verdicts get consequences."),
    5: ("Refuses rather than answers: withdraws records the verdicts do not "
        "support. It fixes nothing — it trades coverage for shipped "
        "accuracy."),
    6: ("A person. Simulated mode only counts and prices the queue — no "
        "answer is invented; a real desk session applies span-keyed "
        "decisions."),
}

#: Edge structure: (src, dst, kind). Labels are composed with run counts.
#: "records" edges are where the records physically travel; "verdict" edges
#: are signals (recorded on checks, consumed later); "trigger"/"queue" edges
#: carry a subset with the run's own size.
EDGES: list[tuple[int, int, str]] = [
    (0, 1, "records"),
    (1, 2, "trigger"),
    (2, 3, "records"),
    (3, 4, "records"),
    (4, 5, "verdict"),
    (1, 5, "verdict"),
    (5, 6, "queue"),
]


def verdict_flow(records, r1_mode: str) -> dict[str, Any]:
    """The bucket-level crosstab: rung 1's verdict × what actually happened
    downstream, computed from the records — never assumed. In observe mode
    the buckets are SIGNALS (every record passes through rungs 2-4; rung 5
    is where the verdicts act), so any ACCEPT that abstained or BAND that
    settled is real interaction and must render as a split."""
    buckets: dict[str, dict[str, Any]] = {}
    for rec in records:
        c = rec.checks or {}
        verdict = c.get("r1_verdict") or "none"
        b = buckets.setdefault(verdict, {
            "verdict": verdict, "n": 0, "settled": 0, "abstained": 0,
            "open": 0, "queued": 0, "r3_changed": 0,
            "r4": {"pass": 0, "fail": 0, "parse_failed": 0, "absent": 0},
        })
        b["n"] += 1
        if rec.zone in ("VERIFIED", "RESOLVED"):
            b["settled"] += 1
        elif rec.zone in ("ESCALATE", "ABSTAIN"):
            b["abstained"] += 1
            if rec.zone == "ESCALATE":
                b["queued"] += 1
        else:
            b["open"] += 1
        if (c.get("r3") or {}).get("changed"):
            b["r3_changed"] += 1
        if "r4_verdict" in c:
            v = c["r4_verdict"]
            b["r4"]["parse_failed" if v is None else v] = \
                b["r4"].get("parse_failed" if v is None else v, 0) + 1
        else:
            b["r4"]["absent"] += 1
    order = {"ACCEPT": 0, "BAND": 1, "REJECT": 2, "none": 3}
    return {
        "mode": r1_mode,
        "total": len(records),
        "buckets": sorted(buckets.values(),
                          key=lambda b: order.get(b["verdict"], 9)),
    }


def dependencies_payload(state: AppState, info: RunInfo) -> dict[str, Any]:
    man = read_manifest_copy(info) or {}
    rung_order = list(man.get("rung_order", [0, 1, 2, 3, 4, 5, 6]))
    rungs_cfg = man.get("rungs", {})
    entries = state.ledger_entries(info)
    records = state.records(info)

    by_rung: dict[int, list] = {}
    for e in entries:
        by_rung.setdefault(e.rung, []).append(e)
    rungs_present = sorted(by_rung)

    # An ablate ledger carries only the rungs it ran; a stack run always
    # starts at the order's first rung (rung 0 writes one row per document).
    run_kind = "stack"
    if entries and rung_order and rung_order[0] not in rungs_present:
        run_kind = "ablate"

    # -- per-rung facts, all from the artifacts -------------------------------

    r1_rows = by_rung.get(1, [])
    r1_mode = next((e.extra.get("mode") for e in r1_rows
                    if e.extra.get("mode")), None) \
        or rungs_cfg.get("1", {}).get("mode", "observe")
    verdicts = Counter(e.verdict for e in r1_rows if e.verdict)

    correctable_set = tuple(
        rungs_cfg.get("2", {}).get("correctable", R2_DEFAULTS["correctable"]))
    rejects = [e for e in r1_rows if e.verdict == "REJECT"]
    correctable = [e for e in rejects if e.reason in correctable_set]
    attempted = sum(1 for e in by_rung.get(2, []) if e.api_calls)

    r3_rows = by_rung.get(3, [])
    r3_disabled = any(e.outcome == "disabled" for e in r3_rows) or \
        rungs_cfg.get("3", {}).get("enabled", True) is False
    r3_cfg = rungs_cfg.get("3", {})
    r3_changed = sum(1 for r in records if (r.checks.get("r3") or {}).get("changed"))
    r3_not_resampled = sum(
        1 for r in records
        if (r.checks.get("r3") or {}).get("outcome") == "not_resampled")

    r4_verdicts = Counter(
        r.checks.get("r4_verdict") for r in records if "r4_verdict" in r.checks)

    r5_rows = by_rung.get(5, [])
    r5_abstained = sum(1 for e in r5_rows if e.outcome == "abstained") or None
    r5_settled = sum(1 for e in r5_rows if e.outcome == "settled")

    r6_rows = by_rung.get(6, [])
    r6_cfg = rungs_cfg.get("6", {})
    minutes_sources = {e.extra.get("minutes_source") for e in r6_rows} - {None}

    model = man.get("model", {})

    nodes: list[dict[str, Any]] = []
    for rung in rung_order:
        n: dict[str, Any] = {"rung": rung, "in_run": rung in rungs_present,
                             "disabled": False,
                             "meaning": MEANINGS.get(rung, "")}
        if rung == 0:
            n.update(label="bare LLM", role="produces the records",
                     documents=len(by_rung.get(0, [])) or None,
                     records=len(records) or None,
                     model=model.get("extractor"))
        elif rung == 1:
            n.update(label="deterministic", mode=r1_mode,
                     routes=r1_mode == "gate",
                     role=("ROUTES: REJECT leaves the stack here — confounds "
                           "every rung above" if r1_mode == "gate" else
                           "judges only — writes r1_verdict/r1_reason; "
                           "records pass through untouched"),
                     verdicts=dict(verdicts))
        elif rung == 2:
            n.update(label="self-correct",
                     role="consumes rung 1 REJECT + statable reason only",
                     eligible={"reject": len(rejects),
                               "correctable": len(correctable),
                               "attempted": attempted},
                     correctable_reasons=list(correctable_set))
        elif rung == 3:
            n.update(label="voting", disabled=r3_disabled,
                     role=("DISABLED — a recorded run state" if r3_disabled
                           else "rewrites answers by resampling through "
                                "rung 0's configured path"),
                     k=r3_cfg.get("k"), temperature=r3_cfg.get("temperature"),
                     changed=r3_changed, not_resampled=r3_not_resampled)
        elif rung == 4:
            n.update(label="LLM judge", model=model.get("judge"),
                     role="judges post-rung-3 records; writes r4_verdict",
                     verdicts={k or "parse_failed": v
                               for k, v in r4_verdicts.items()})
        elif rung == 5:
            n.update(label="abstention",
                     role="consumes rung 1 + rung 4 verdicts — the first "
                          "place a verdict is allowed to cost coverage",
                     abstained=r5_abstained, settled=r5_settled or None)
        elif rung == 6:
            n.update(label="human loop", mode=r6_cfg.get("mode"),
                     role="queue = rung 5's abstained residue",
                     queue=len(r6_rows) or None,
                     human_minutes=round(sum(e.human_minutes for e in r6_rows), 1),
                     minutes_source=next(iter(minutes_sources), None))
        nodes.append(n)

    # -- edges with run-composed labels --------------------------------------

    def _edge_label(src: int, dst: int, kind: str) -> str:
        if (src, dst) == (0, 1):
            return f"{len(records)} records, one per mention"
        if (src, dst) == (1, 2):
            return (f"REJECT + statable reason only — {len(rejects)} REJECT, "
                    f"{len(correctable)} correctable")
        if (src, dst) == (2, 3):
            return "records (corrections adopted in place)"
        if (src, dst) == (3, 4):
            return "rung 4 judges post-rung-3 records"
        if (src, dst) == (4, 5):
            return "r4_verdict (signal, recorded on checks)"
        if (src, dst) == (1, 5):
            return ("r1_verdict (signal)" if r1_mode == "observe"
                    else "r1 already routed — rung 5 sees the survivors")
        if (src, dst) == (5, 6):
            q = len(r6_rows)
            return f"abstained residue -> queue ({q})" if q else \
                "abstained residue -> queue"
        return kind

    edges = [{"src": s, "dst": d, "kind": k, "label": _edge_label(s, d, k)}
             for s, d, k in EDGES if s in rung_order and d in rung_order]

    # -- denominators with their source rung ----------------------------------

    denominators = []
    for rung in rungs_present:
        names = Counter(e.extra.get("denominator") for e in by_rung[rung]
                        if e.extra.get("denominator"))
        name = names.most_common(1)[0][0] if names else None
        src, label = DENOMINATOR_SOURCES.get(name, (None, None))
        denominators.append({
            "rung": rung, "denominator": name, "rows": len(by_rung[rung]),
            "source_rung": src,
            "source_label": (
                f"rung 5's abstained residue ({len(r6_rows)} abstained)"
                if name == "r6_queue" else
                f"rung 1 REJECTs with a statable reason "
                f"({len(rejects)} REJECT, {len(correctable)} correctable)"
                if name in ("r2_offered", "r2_attempted") else label),
        })

    return {
        "rung_order": rung_order,
        "run_kind": run_kind,
        "rungs_present": rungs_present,
        "r1_mode": r1_mode,
        "nodes": nodes,
        "edges": edges,
        "verdict_flow": verdict_flow(records, r1_mode),
        "denominators": denominators,
        "stack_semantics": (
            "Each per-rung row is a CUMULATIVE stack state — \"would this "
            "ship if the run stopped here\" — so a delta between rows is "
            "attributable to the stack up to that rung, not to the rung "
            "alone. Per-rung attribution is `ablate` (one rung over "
            "identical input; the Phase E r6 ledgers in the archive are "
            "examples)."
            if run_kind == "stack" else
            f"ABLATE run: only rung(s) {rungs_present} ran, over a saved "
            "input — rows measure that rung alone, not a stack."),
    }


def gate_caveat(r1_mode: str) -> dict[str, str]:
    if r1_mode != "gate":
        return {}
    return {"r1_gate": (
        "rung 1 ran in GATE mode: it routed records instead of only judging "
        "them, so every rung above it saw a pre-cleaned set — a filtering "
        "rung 1 confounds rungs 3-6, which is why observe is the default."
    )}

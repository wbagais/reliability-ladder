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


def per_record_from_ledger(entries) -> dict[str, dict[str, Any]]:
    """One dict per record from the ledger's one-row-per-record-per-rung —
    the join a corpus-free copy of a run can still make. `verdict` is rung
    1's word, moved to the zone rung 2 left when rung 2 rescued the record
    (the record itself reads that way); `r3` is the ledger's vote outcome
    (voted · tie · not_resampled — the ledger does not say unanimous from
    2-of-3); `r4` the judge's word or parse_failed; `zone` the last zone."""
    recs: dict[str, dict[str, Any]] = {}
    for e in sorted(entries, key=lambda x: x.rung):
        rid = e.record_id
        if not rid or "#" not in rid:
            continue  # per-document rows (rung 0, rung 3's samples) and config rows
        r = recs.setdefault(rid, {"record_id": rid, "doc_id": e.doc_id, "verdict": None,
                                  "rescued": False, "r3": None, "r4": None, "r4_menu": None,
                                  "zone": None, "r5": None, "r6": None})
        if e.rung == 1 and e.verdict:
            r["verdict"] = e.verdict
        elif e.rung == 2 and e.outcome == "rescued":
            r["rescued"] = True
            r["verdict"] = e.zone or r["verdict"]
        elif e.rung == 3 and e.outcome in ("voted", "tie", "not_resampled"):
            r["r3"] = e.outcome
        elif e.rung == 4:
            r["r4"] = e.verdict if e.verdict else ("parse_failed" if e.outcome == "parse_failed" else None)
            r["r4_menu"] = e.extra.get("menu")
        elif e.rung == 5:
            r["r5"] = e.outcome
        elif e.rung == 6:
            r["r6"] = e.outcome
        if e.zone and e.zone != "CONFIG":
            r["zone"] = e.zone
    return recs


def verdict_flow_from_ledger(entries, r1_mode: str) -> dict[str, Any]:
    """`verdict_flow` from the ledger instead of the records — the same
    buckets, so a tracked corpus-free copy of a run draws the same flow.
    What only a record knows (whether rung 3 CHANGED its code) is stated
    unknown, never zero-as-a-fact."""
    buckets: dict[str, dict[str, Any]] = {}
    for r in per_record_from_ledger(entries).values():
        verdict = r["verdict"] or "none"
        b = buckets.setdefault(verdict, {
            "verdict": verdict, "n": 0, "settled": 0, "abstained": 0,
            "open": 0, "queued": 0, "r3_changed": 0,
            "r4": {"pass": 0, "fail": 0, "parse_failed": 0, "absent": 0},
        })
        b["n"] += 1
        if r["zone"] in ("VERIFIED", "RESOLVED"):
            b["settled"] += 1
        elif r["zone"] in ("ESCALATE", "ABSTAIN"):
            b["abstained"] += 1
            if r["zone"] == "ESCALATE":
                b["queued"] += 1
        else:
            b["open"] += 1
        if r["r4"] is None:
            b["r4"]["absent"] += 1
        else:
            b["r4"][r["r4"]] = b["r4"].get(r["r4"], 0) + 1
    order = ["ACCEPT", "BAND", "REJECT", "none"]
    return {
        "mode": r1_mode, "total": sum(b["n"] for b in buckets.values()),
        "buckets": [buckets[k] for k in order if k in buckets],
        "r3_changed_known": False,
    }


#: The six shipping rules, in the Live grid's legend order.
RULE_NAMES = [
    ("V", "strict vocabulary check says ACCEPT"),
    ("V+", "loose vocabulary check says ACCEPT"),
    ("3", "all 3 voting samples agree"),
    ("2", "2 of 3 voting samples agree"),
    ("J", "blind judge says pass"),
    ("J+", "menu-shown judge says pass"),
]


def rules_over_run(state: AppState, info: RunInfo) -> dict[str, Any]:
    """Figure 3 as a table: each of the six verdicts read as a shipping rule
    over the whole run — how many records it ships and how many it holds
    for a person, and when the records and the corpus are on this machine,
    how many of the shipped are right. From the ledger alone the loose
    vocabulary check, unanimity among the votes and the menu-shown judge
    cannot be answered and read NOT RUN. Also the vote agreement per rung-1
    lane, for the flow's rung 3 column."""
    entries = state.ledger_entries(info)
    per = per_record_from_ledger(entries)
    records = state.records(info)
    by_id = {r.record_id: r for r in records}
    source = "records" if records else "ledger"
    man = read_manifest_copy(info) or {}
    menu_on = (man.get("rungs", {}).get("4", {}) or {}).get("menu", "off") not in (None, "off")
    r5 = man.get("rungs", {}).get("5", {}) or {}
    own_zones = set(r5.get("abstain_zones", ["BAND"])) | ({"REJECT"} if r5.get("abstain_on_reject", True) else set())
    vocab = state.registry()

    # right/wrong per record, when scorable
    outcome_of: dict[str, str] = {}
    scorable = False
    if records and state.corpus() is not None:
        try:
            from dashboard import scoring
            ann = scoring.annotate_records(state, info, "exact")
            if ann:
                scorable = True
                for rec, a in zip(records, ann):
                    outcome_of[rec.record_id] = a.get("outcome")
        except Exception:
            scorable = False

    def decide(rid: str, r: dict) -> dict[str, str | None]:
        """rule id -> ship | hold | None (not run) for one record."""
        rec = by_id.get(rid)
        c = (rec.checks or {}) if rec is not None else {}
        out: dict[str, str | None] = {}
        v = r["verdict"]
        out["V"] = None if v is None else ("ship" if v == "ACCEPT" else "hold")
        if v is None or rec is None or vocab is None:
            out["V+"] = None      # a rule half-answerable is not run at all
        elif v == "ACCEPT":
            out["V+"] = "ship"
        elif v == "BAND" and (rec.sct or (c.get("withheld") or {}).get("sct")):
            sct = rec.sct if rec.sct is not None else (c.get("withheld") or {}).get("sct")
            try:
                out["V+"] = "ship" if vocab.lexical_match(rec.text or "", str(sct), mode="contained") else "hold"
            except Exception:
                out["V+"] = "hold"
        else:
            out["V+"] = "hold"
        r3 = (c.get("r3") or {}) if rec is not None else {}
        if rec is not None and r3:
            raw = [x for x in (r3.get("raw") or []) if x]
            k = int(r3.get("k") or 3)
            seen = int(r3.get("seen") or 0)
            out["3"] = "ship" if (seen >= 2 and len(raw) == k and len(set(raw)) == 1) else "hold"
        else:
            out["3"] = None
        out["2"] = None if r["r3"] is None else ("ship" if r["r3"] == "voted" else "hold")
        j = r["r4"]
        jd = None if j is None else ("ship" if j == "pass" else "hold")
        if menu_on:
            out["J"], out["J+"] = None, jd
        else:
            out["J"], out["J+"] = jd, None
        return out

    tally = {rid: {"ships": 0, "held": 0, "right": 0, "wrong": 0, "run": False}
             for rid, _ in RULE_NAMES}
    lanes: dict[str, dict[str, int]] = {}
    for rid, r in per.items():
        d = decide(rid, r)
        for rule_id, verdict in d.items():
            t = tally[rule_id]
            if verdict is None:
                continue
            t["run"] = True
            if verdict == "ship":
                t["ships"] += 1
                if scorable:
                    t["right" if outcome_of.get(rid) == "correct" else "wrong"] += 1
            else:
                t["held"] += 1
        # vote agreement per rung-1 lane: from the record when it carries the
        # votes (all / two / none / no vote), from the ledger otherwise
        lane = r["verdict"] or "none"
        rec = by_id.get(rid)
        r3c = ((rec.checks or {}).get("r3") or {}) if rec is not None else {}
        if r3c:
            raw = [x for x in (r3c.get("raw") or []) if x]
            k = int(r3c.get("k") or 3)
            seen = int(r3c.get("seen") or 0)
            if seen < 2:
                cat = "no_vote"
            elif r3c.get("tie"):
                cat = "none"
            elif len(raw) == k and len(set(raw)) == 1:
                cat = "all"
            else:
                cat = "two"
        elif r["r3"] is not None:
            cat = {"voted": "voted", "tie": "tie", "not_resampled": "no_vote"}[r["r3"]]
        else:
            cat = None
        if cat is not None:
            for key in (lane, "all"):
                lanes.setdefault(key, {})
                lanes[key][cat] = lanes[key].get(cat, 0) + 1

    ran = {e.rung for e in entries if e.outcome != "disabled"}
    why_not = {
        "V": "rung 1 did not run",
        "V+": ("rung 1 did not run" if 1 not in ran else
               "needs the records and the vocabulary index (a contained lexical match per record)"),
        "3": ("rung 3 did not run" if 3 not in ran else
              "needs the records (which samples agreed); the ledger says voted or tie only"),
        "2": "rung 3 did not run",
        "J": ("rung 4 did not run" if 4 not in ran else "this run judged with the menu shown, not blind"),
        "J+": ("rung 4 did not run" if 4 not in ran else
               "this run judged blind; the menu-shown judge is the Live tab's second pass"),
    }
    rules = []
    for rule_id, name in RULE_NAMES:
        t = tally[rule_id]
        own = (rule_id == "V" and own_zones == {"BAND", "REJECT"})
        rules.append({
            "id": rule_id, "name": name, "run": t["run"],
            "ships": t["ships"] if t["run"] else None,
            "held": t["held"] if t["run"] else None,
            "right": t["right"] if (t["run"] and scorable) else None,
            "wrong": t["wrong"] if (t["run"] and scorable) else None,
            "own": own,
            "note": None if t["run"] else why_not[rule_id],
        })
    return {"total": len(per), "source": source, "scorable": scorable,
            "rules": rules, "lanes_r3": lanes,
            "votes_from": "records" if any(
                ((by_id.get(rid).checks or {}).get("r3")) for rid in per if by_id.get(rid)) else "ledger"}


def flow_map(vf: dict[str, Any], r1_mode: str, rungs_cfg: dict,
             rescued: int, eligible: dict[str, int]) -> dict[str, Any]:
    """The integrated diagram's data: per bucket, the ACTUAL path this run
    took and every STRUCTURALLY POSSIBLE path it did not — so the reader sees
    what CAN happen at each rung next to what DID. Possible-path derivation
    is mode-aware:

    - r2 touches REJECT only; ACCEPT and BAND bypass it by construction.
      The rescue path (corrected — rejoins as changed) exists as an option
      for every run with a rung 2, even one whose correctable count was 0.
    - r5 can structurally withdraw anything and keep anything — EXCEPT a
      REJECT when `abstain_on_reject` is true (the manifest default), which
      makes REJECT -> shipped impossible, not merely untaken: it is omitted,
      never drawn as an option.
    - gate mode: REJECT leaves the stack AT rung 1 (an actual exit path that
      observe runs must not render at all), so it has no queue path.
    """
    r5_cfg = rungs_cfg.get("5", {})
    abstain_on_reject = bool(r5_cfg.get("abstain_on_reject", True))

    def leg(n: int) -> dict[str, Any]:
        return {"n": n, "kind": "actual" if n > 0 else "possible"}

    buckets = []
    for b in vf["buckets"]:
        v = b["verdict"]
        out: dict[str, Any] = {
            "verdict": v, "n": b["n"],
            "through_r2": v == "REJECT",
            "r3_changed": b.get("r3_changed", 0),
            "r4": b.get("r4"),
        }
        if v == "REJECT":
            out["r2"] = {**eligible, "rescued": rescued,
                         "rescue": {**leg(rescued),
                                    "label": "corrected — rejoins as changed"}}
            if r1_mode == "gate":
                out["exit_at_r1"] = {"n": b["n"], "kind": "actual"}
                buckets.append(out)
                continue
        settled, abstained = b.get("settled", 0), b.get("abstained", 0)
        if v == "REJECT" and abstain_on_reject:
            pass  # shipped omitted: impossible under this config, not untaken
        else:
            out["shipped"] = {**leg(settled)}
            if settled == 0:
                out["shipped"]["label"] = "settled at r5"
        out["person"] = {**leg(abstained)}
        if abstained == 0:
            out["person"]["label"] = "withdrawn at r5"
        buckets.append(out)
    return {"mode": r1_mode, "total": vf["total"], "buckets": buckets,
            "abstain_on_reject": abstain_on_reject}


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
    rescued = sum(1 for e in by_rung.get(2, [])
                  if e.api_calls and e.extra.get("evaluable") == "pass")

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

    # The crosstab from the records when the run has them, from the ledger
    # when it does not (a tracked copy is corpus-free by design) — the same
    # buckets either way, so a fresh clone draws the same flow.
    vf = verdict_flow(records, r1_mode) if records else verdict_flow_from_ledger(entries, r1_mode)
    return {
        "rung_order": rung_order,
        "run_kind": run_kind,
        "rungs_present": rungs_present,
        "r1_mode": r1_mode,
        "nodes": nodes,
        "edges": edges,
        "flow_source": "records" if records else "ledger",
        "verdict_flow": vf,
        "flow_map": flow_map(
            vf, r1_mode, rungs_cfg, rescued,
            {"reject": len(rejects), "correctable": len(correctable),
             "attempted": attempted}),
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

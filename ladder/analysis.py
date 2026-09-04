"""Every number the article quotes from a run, computed from the run's own
artifacts by one tested module.

Written 2026-09-03 for the consolidated re-run (plan item 0b). Until then the
article's development-side story was told from at least four runs with four
record counts, under three F1 denominators, by ~80 scratch harness scripts
that were deleted with their worktrees. These functions take records, the
state table (`ladder/trace.py`) and gold, and return plain dicts; the CLI in
`scripts/rerun_analysis.py` loads a run set, calls them, and writes the JSON
and the markdown that `docs/decisions.md` quotes.

Every function names its denominator in its docstring, because an F1 quoted
without one is not reproducible and two of this repo's differ by more than any
arm it ever shipped.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

from ladder.schema import (
    REACTION,
    Record,
    ZONE_ABSTAIN,
    ZONE_ESCALATE,
    ZONE_REJECT,
)

# --- the state table, read back -------------------------------------------


def read_jsonl(path: str | Path) -> list[dict[str, Any]]:
    return [json.loads(l) for l in Path(path).read_text(encoding="utf-8").splitlines()
            if l.strip()]


def rows_at(rows: Iterable[dict[str, Any]], rung: int) -> dict[str, dict[str, Any]]:
    """The state rows of one rung, keyed by record_id."""
    return {r["record_id"]: r for r in rows if r.get("rung") == rung}


def outcome_counts(rows: Iterable[dict[str, Any]], rung: int) -> dict[str, int]:
    return dict(Counter(r["outcome"] for r in rows_at(rows, rung).values()))


def sha256_file(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _pct(a: float, b: float) -> float:
    return round(100.0 * a / b, 2) if b else 0.0


# --- the error budget --------------------------------------------------------


def error_budget(
    records: list[Record],
    golds: list,
    span_match: str = "exact",
    exclude: set[str] | None = None,
    vocab: Any = None,
    full_vocabulary: bool = False,
) -> dict[str, Any]:
    """Detection -> retrieval -> pick, on ONE denominator: the post-exclusion
    gold set, paired by `span_match` exactly as `score_run` pairs.

    matched          gold mentions some prediction sits on
    missed           gold mentions no prediction reached (detection)
    invented         predictions on no gold mention (detection, other side)
    on_menu          matched records whose menu held a gold code
    lost_retrieval   matched - on_menu (the menu never offered the answer)
    correct          matched records scored CORRECT
    lost_pick        on_menu - correct (the answer was offered and not taken)

    `full_vocabulary` is FiNER: the menu is the whole tag list, so retrieval
    cannot lose anything by construction and on_menu == matched. The pick loss
    is split by LANE — the model's own choice against rung 0's fallback rule —
    because B4 (2026-09-01) found the fallback, not the model, behind 74 of 77
    slot-0 predictions.
    """
    from ladder import score

    exclude = exclude or set()
    gold_mentions = [g for g in golds if g.entity_type == REACTION
                     and g.record_id not in exclude]
    dropped = [g for g in golds if g.entity_type == REACTION and g.record_id in exclude]

    def on_excluded(r: Record) -> bool:
        return any(g.doc_id == r.doc_id and score._overlaps(r.spans, g.spans)
                   for g in dropped) and not any(
            g.doc_id == r.doc_id and score._overlaps(r.spans, g.spans)
            for g in gold_mentions)

    preds = [r for r in records if r.entity_type == REACTION and not on_excluded(r)]
    pairs = score._pair(preds, gold_mentions, span_match)
    matched = on_menu = correct = 0
    lost_pick_by_lane: Counter = Counter()
    for r, g in pairs:
        if g is None:
            continue
        matched += 1
        gold_codes = {str(c) for c in (g.sct or [])}
        menu = {str(c.get("code")) for c in (r.checks.get("candidates") or [])}
        held = full_vocabulary or bool(gold_codes & menu) or not gold_codes
        if held:
            on_menu += 1
        if score.outcome(r, g, vocab) == score.CORRECT:
            correct += 1
        elif held:
            lost_pick_by_lane["fallback" if r.checks.get("pick_fallback") else "model"] += 1
    return {
        "span_match": span_match,
        "n_gold": len(gold_mentions),
        "n_pred": len(preds),
        "excluded": len(dropped),
        "matched": matched,
        "missed": len(gold_mentions) - matched,
        "invented": len(preds) - matched,
        "on_menu": on_menu,
        "lost_retrieval": matched - on_menu,
        "correct": correct,
        "lost_pick": on_menu - correct,
        "lost_pick_by_lane": dict(lost_pick_by_lane),
    }


# --- rung 1 lanes --------------------------------------------------------------


def lanes(rows: Iterable[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Per rung 1 verdict: how many, how many correct (exact), how many sit on
    no gold mention, and the overlap-matched denominator the five-model table
    used (`correct_pct_matched_overlap`). Both denominators, stated."""
    out: dict[str, dict[str, Any]] = {}
    for row in rows:
        v = row.get("r1_verdict")
        if v is None:
            continue
        d = out.setdefault(v, {"n": 0, "correct": 0, "on_no_gold": 0,
                               "matched_overlap": 0, "correct_overlap": 0})
        d["n"] += 1
        d["correct"] += row.get("outcome") == "correct"
        d["on_no_gold"] += row.get("outcome_overlap") == "unmatched"
        if row.get("outcome_overlap") not in ("unmatched", "unscored", None):
            d["matched_overlap"] += 1
            d["correct_overlap"] += row.get("outcome_overlap") == "correct"
    for d in out.values():
        d["correct_pct"] = _pct(d["correct"], d["n"])
        d["correct_pct_matched_overlap"] = _pct(d["correct_overlap"], d["matched_overlap"])
    return out


# --- rung 3 by lane ---------------------------------------------------------------


def _r3_category(rec: Record) -> str:
    r3 = rec.checks.get("r3") or {}
    if not r3:
        return "absent"
    if r3.get("seen", 0) == 0:
        return "not_resampled"
    if r3.get("tie"):
        return "tie"
    if r3.get("changed"):
        return "changed"
    if r3.get("single_sample"):
        return "single_sample"
    votes = rec.checks.get("r3_votes") or {}
    if votes and max(votes.values()) == r3.get("seen"):
        return "unanimous"
    return "split"


def r3_crosstab(
    records: list[Record],
    rows: Iterable[dict[str, Any]],
    before_outcomes: dict[str, str],
) -> dict[str, Any]:
    """Plan item 11: every node of the rung 3 tree broken down by what rung 1
    had said (the lane) and what rung 0 had already achieved (`before_outcomes`,
    the state outcome at the rung before 3). `changes` lists each overwrite
    with its lane, votes and outcome transition."""
    after = {r["record_id"]: r for r in rows}
    by_lane: dict[str, Counter] = defaultdict(Counter)
    changes = []
    not_resampled_before: Counter = Counter()
    destroyed = gained = 0
    for rec in records:
        cat = _r3_category(rec)
        lane = rec.checks.get("r1_verdict") or "none"
        by_lane[lane][cat] += 1
        before = before_outcomes.get(rec.record_id)
        now = (after.get(rec.record_id) or {}).get("outcome")
        if cat == "not_resampled":
            not_resampled_before[before] += 1
        if cat == "changed":
            r3 = rec.checks["r3"]
            changes.append({"record_id": rec.record_id, "lane": lane,
                            "was": r3.get("was"), "now": r3.get("winner"),
                            "votes": rec.checks.get("r3_votes"),
                            "before": before, "after": now})
            destroyed += before == "correct" and now != "correct"
            gained += before != "correct" and now == "correct"
    return {
        "by_lane": {k: dict(v) for k, v in by_lane.items()},
        "changes": changes,
        "changed": len(changes),
        "correct_destroyed": destroyed,
        "correct_gained": gained,
        "net_correct": gained - destroyed,
        "not_resampled_before": dict(not_resampled_before),
    }


# --- the judge ---------------------------------------------------------------------


def judge_summary(records: list[Record], rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Pass/fail against correctness (exact), the separation
    P(correct|pass) / P(correct|fail), the two questions counted apart, and
    the menu arm's own verdicts: `menu_missing`, `best_correct` (the judge's
    own line is a gold code), `best_is_pick`."""
    state = {r["record_id"]: r for r in rows}
    out: Counter = Counter()
    correct_pass = correct_fail = 0
    for rec in records:
        row = state.get(rec.record_id) or {}
        v = row.get("r4_verdict", rec.checks.get("r4_verdict"))
        if v is None:
            out["parse_failed"] += 1
            continue
        out["judged"] += 1
        out[v] += 1
        r4 = rec.checks.get("r4") or {}
        out["span_bad"] += not r4.get("span_ok", True)
        out["code_bad"] += not r4.get("code_ok", True)
        is_correct = row.get("outcome") == "correct"
        if v == "pass":
            correct_pass += is_correct
        else:
            correct_fail += is_correct
        if rec.checks.get("r4_menu_missing") is not None:
            out["menu_shown"] += 1
            out["menu_missing"] += bool(rec.checks.get("r4_menu_missing"))
            best = rec.checks.get("r4_best_code")
            if best is not None:
                out["best_correct"] += str(best) in [str(c) for c in row.get("gold_codes", [])]
                out["best_is_pick"] += str(best) == str(rec.sct)
    p_pass = correct_pass / out["pass"] if out["pass"] else 0.0
    p_fail = correct_fail / out["fail"] if out["fail"] else 0.0
    return {
        **{k: out[k] for k in ("judged", "parse_failed", "pass", "fail", "span_bad",
                                "code_bad", "menu_shown", "menu_missing",
                                "best_correct", "best_is_pick")},
        "correct_given_pass": p_pass,
        "correct_given_fail": p_fail,
        "separation": (p_pass / p_fail) if p_fail else None,
    }


# --- the policy table ------------------------------------------------------------


def policy_row(rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """From the FINAL state rows: ships, coverage, accuracy on what it
    answers, yield (correct / all — the number abstention cannot fool), errors
    per 100 records, and the count routed to a person."""
    rows = list(rows)
    n = len(rows)
    answered = [r for r in rows if r.get("zone") not in (ZONE_ABSTAIN, ZONE_REJECT,
                                                          ZONE_ESCALATE) and r.get("sct")]
    correct = sum(1 for r in answered if r.get("outcome") == "correct")
    errors = len(answered) - correct
    person = sum(1 for r in rows if r.get("zone") == ZONE_ESCALATE)
    return {
        "n": n,
        "ships": len(answered),
        "coverage": round(len(answered) / n, 5) if n else 0.0,
        "accuracy": round(correct / len(answered), 5) if answered else 0.0,
        "yield": round(correct / n, 5) if n else 0.0,
        "correct": correct,
        "errors": errors,
        "err_per_100": round(100.0 * errors / n, 3) if n else 0.0,
        "to_person": person,
    }


# --- three-draw consensus -------------------------------------------------------


def _overlaps(a, b) -> bool:
    return any(x < q and p < y for x, y in a for p, q in b)


def consensus(draws: list[list[Record]]) -> dict[str, Any]:
    """Section 3's agreement table. Mentions are grouped across draws by span
    OVERLAP within a document (union-find), then each group is classified by
    how many draws found it and whether they agreed on span and code."""
    k = len(draws)
    items = [(d, r) for d, recs in enumerate(draws) for r in recs
             if r.entity_type == REACTION]
    parent = list(range(len(items)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def _key(r: Record):
        # An unlocated span, (-1, -1), overlaps nothing — not even its own copy
        # in the next draw — so those records are matched on their quoted
        # text instead, which is what they have.
        located = all(0 <= a < b for a, b in r.spans)
        return ("span", frozenset((int(a), int(b)) for a, b in r.spans)) if located \
            else ("text", r.text)

    def _same(ra: Record, rb: Record) -> bool:
        ka, kb = _key(ra), _key(rb)
        if ka[0] == "text" or kb[0] == "text":
            return ka == kb
        return _overlaps(ra.spans, rb.spans)

    by_doc: dict[str, list[int]] = defaultdict(list)
    for i, (_, r) in enumerate(items):
        by_doc[r.doc_id].append(i)
    for idx in by_doc.values():
        for a in range(len(idx)):
            for b in range(a + 1, len(idx)):
                ia, ib = idx[a], idx[b]
                if items[ia][0] != items[ib][0] and _same(items[ia][1], items[ib][1]):
                    parent[find(ia)] = find(ib)
    groups: dict[int, list[tuple[int, Record]]] = defaultdict(list)
    for i, it in enumerate(items):
        groups[find(i)].append(it)
    c: Counter = Counter()
    same_span_all = same_code_given_all = 0
    for members in groups.values():
        found = {d for d, _ in members}
        if len(found) < k:
            c["found_by_two" if len(found) == k - 1 else "found_by_one"] += 1
            continue
        # Compared PER DRAW: two records that overlap each other inside one
        # draw are that draw's reading of the mention, and the draws agree
        # when each draw's set of spans (and multiset of codes) is the same.
        per_draw_spans = {d: frozenset(_key(r) for dd, r in members if dd == d) for d in found}
        per_draw_codes = {d: tuple(sorted(str(r.sct) for dd, r in members if dd == d)) for d in found}
        spans = set(per_draw_spans.values())
        codes = set(per_draw_codes.values())
        same_span, same_code = len(spans) == 1, len(codes) == 1
        same_span_all += same_span
        same_code_given_all += same_code
        if same_span and same_code:
            c["all_agree"] += 1
        elif same_span:
            c["same_span_diff_code"] += 1
        elif same_code:
            c["same_code_diff_span"] += 1
        else:
            c["both_differ"] += 1
    n = len(groups)
    all_found = n - c["found_by_two"] - c["found_by_one"]
    return {
        "draws": k,
        "mentions": n,
        **{key: c[key] for key in ("all_agree", "same_span_diff_code", "same_code_diff_span",
                                   "both_differ", "found_by_two", "found_by_one")},
        "consensus_pct": _pct(c["all_agree"], n),
        "same_span_all_three_pct": _pct(same_span_all, n),
        "same_code_given_all_found_pct": _pct(same_code_given_all, all_found),
    }


# --- item 8: what the looser lexical setting admits ------------------------------


def lane_moves(base_records: list[Record], arm_records: list[Record],
               rows: Iterable[dict[str, Any]], vocab: Any) -> dict[str, Any]:
    """The records whose rung 1 verdict differs between a base run and the
    `lexical_mode: contained` arm (plan item 8), each with the vocabulary term
    the looser test matched and the DIRECTION of the subset: `span_in_term`
    (the span's words are a subset of a term's) or `term_in_span` (a term's
    words are a subset of the span's — the model quoted more than the concept
    names, section 1's boundary problem). Outcomes come from the arm's rung 1
    state rows, so 'correct' here is span-exact against gold."""
    from ladder.registry import normalise_term

    state = {r["record_id"]: r for r in rows}
    base = {r.record_id: r for r in base_records}
    out = []
    by_dir: dict[str, dict[str, int]] = {}
    for rec in arm_records:
        b = base.get(rec.record_id)
        before = b.checks.get("r1_verdict") if b else None
        after = rec.checks.get("r1_verdict")
        if before == after:
            continue
        want = normalise_term(rec.text)
        toks = set(want.split())
        # The CLOSEST matching term — fewest extra words — not the first one
        # the vocabulary happens to list: |Gonalgia| carries both "knee pain"
        # and "pain of knee region", and only the first says what the span
        # was one word short of.
        direction, term, extra = None, None, []
        best: int | None = None
        for t in vocab.terms(rec.sct):
            got = normalise_term(t)
            other = set(got.split())
            if got == want:
                direction, term, extra, best = "exact", t, [], 0
                break
            if toks and toks < other:
                cand = ("span_in_term", t, sorted(other - toks))
            elif other and other < toks:
                cand = ("term_in_span", t, sorted(toks - other))
            else:
                continue
            if best is None or len(cand[2]) < best:
                direction, term, extra = cand
                best = len(extra)
        row = state.get(rec.record_id, {})
        entry = {"record_id": rec.record_id, "text": rec.text, "sct": rec.sct,
                 "sct_label": rec.sct_label, "before": before, "after": after,
                 "direction": direction, "term": term, "extra_words": extra,
                 "outcome": row.get("outcome"), "outcome_overlap": row.get("outcome_overlap")}
        out.append(entry)
        d = by_dir.setdefault(direction or "none", {"n": 0, "correct": 0, "on_no_gold": 0})
        d["n"] += 1
        d["correct"] += entry["outcome"] == "correct"
        d["on_no_gold"] += entry["outcome_overlap"] == "unmatched"
    return {"moved": len(out), "records": out, "by_direction": by_dir}


# --- gold lane occupancy ---------------------------------------------------------


def gold_lane_occupancy(golds: Iterable[Any], exclude: set[str] | None,
                        zone: Any) -> dict[str, Any]:
    """How much of a PERFECT answer set each rung 1 lane can hold — the free
    check's ceiling, replayed over the answer key with no model.

    Denominator: the same one the run is scored on — reaction gold only,
    `exclude` applied. Concept-less gold is counted in `n` (it is in the
    scorer's denominator) but reported separately, because a record with no
    code can only ever land in BAND, so it is a floor on that lane rather than
    a verdict about the vocabulary's words. `zone(record) -> lane` is rung 1
    bound to the document text, the registry and the manifest's rung 1
    settings; passing it in keeps the arithmetic testable without a release.
    """
    from ladder.calibrate import gold_to_record

    exclude = exclude or set()
    lanes: Counter = Counter()
    concept_less: Counter = Counter()
    n = 0
    for g in golds:
        if g.entity_type != REACTION or g.record_id in exclude:
            continue
        n += 1
        lane = zone(gold_to_record(g))
        (lanes if g.sct else concept_less)[lane] += 1
    total: Counter = lanes + concept_less
    return {
        "n": n,
        "coded": sum(lanes.values()),
        "concept_less": sum(concept_less.values()),
        "lanes": dict(total),
        "concept_less_lanes": dict(concept_less),
        "pct": {k: round(100.0 * v / n, 1) for k, v in sorted(total.items())} if n else {},
    }

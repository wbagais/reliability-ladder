"""Build the plan page's "Ladder demo" traces from a run's archived files.

    PYTHONPATH=. python3 scripts/plan_demo.py --archive out/archive/<dir> \
        --run rerun-cadec-d0 --corpus cadec --db ladder/cache/snomed.sqlite --out demo.json

The demo used to be invented posts with measured numbers pasted beside them.
This script follows REAL records through the files every run writes
(`<run>.r<N>.records.jsonl`, `<run>.state.jsonl`, and the `-judgemenu` arm's
rung 4 records): the menu rung 0 retrieved and the line it picked, rung 1's
verdict and the checks behind it, rung 2's attempt, rung 3's raw votes, rung
4's verdict blind and shown the menu, where rung 5 put the record, and the
outcome against gold under both pairings.

What it will not emit: a document, a prompt, a model's prose reply, or a
quoted span longer than the tracked report's own precedent (seven words —
`runs/archive/consolidated-2026-09-03/rerun/cadec.json` carries spans up to
that length). CADEC is non-transferable; annotated spans and vocabulary labels
are the licence rule for examples, a sentence of post prose is not. The
selection — which records, what each case is called — is editorial and lives
in SPEC below; every value in a trace comes from the files.

Stdlib only, so tests/test_plan_demo.py runs in CI without the archive.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys
from typing import Callable

MAX_SPAN_WORDS = 7

# The editorial part: which records, and what each one shows. Record ids are
# the run's own (`<doc>#<index>`); a wrong id is an error, never a blank.
SPEC: dict[str, list[dict]] = {
    "rerun-cadec-d0": [
        {"id": "ARTHROTEC.57#0", "group": "shipped", "case": "The clean case",
         "shows": "The span is one of the concept's own names, every layer agrees, and it ships right. 39 of the 53 shipped records look like this."},
        {"id": "LIPITOR.171#4", "group": "shipped", "case": "Shipped, and wrong",
         "shows": "The words match a real concept — |Injury of muscle| — but the annotators coded |Traumatic injury of skeletal muscle|. The free check can prove a code wrong, never right; the judge, blind or shown the menu, passed it too."},
        {"id": "LIPITOR.8#5", "group": "shipped", "case": "Voting broke a right answer, and it shipped as verified",
         "shows": "ACCEPT on |Pain|, correct. Two of three samples said |Increased pain|, the vote overwrote the code, nothing re-ran rung 1, and the record shipped marked verified with the wrong code. The metric cannot see it: exact F1 moved 0.204 → 0.204 when this was fixed on the held-out run. The menu-shown judge is the one layer that said fail."},
        {"id": "LIPITOR.48#8", "group": "shipped", "case": "Shipped onto nothing",
         "shows": "A real reaction the annotators did not mark, so it sits on no gold mention: unjudgeable, not wrong. It leaves the denominator rather than counting against the lane."},
        {"id": "ARTHROTEC.139#0", "group": "held", "case": "Right, and held anyway",
         "shows": "\"Lower Back Pain\" against |Low back pain|: one word off the concept's names, so BAND, so held. 49 of the 177 records a person receives already carry the right code; the reviewer confirms as often as they fix."},
        {"id": "ARTHROTEC.107#0", "group": "held", "case": "Right concept, boundary off",
         "shows": "The annotators marked \"rectal bleed\"; the model quoted three words. Correct on the overlap pairing, unmatched span-exact — a false positive and a false negative at once. Half the finding loss is this."},
        {"id": "ARTHROTEC.107#1", "group": "held", "case": "Not on this list",
         "shows": "The retriever never surfaced |Generally unwell|, so no pick could be right. Blind, the judge just failed it; shown the menu, it answered best: null — the one verdict that tells a failed menu from a failed pick. Nothing reads it."},
        {"id": "LIPITOR.24#2", "group": "held", "case": "The model said no code exists; the vote invented one",
         "shows": "Rung 0 answered CONCEPT_LESS. Gold is two codes, post-coordinated. Two samples then agreed on |Pain in muscle of ankle joint| and the vote wrote it in — a wrong answer where an honest abstention had been."},
        {"id": "LIPITOR.739#1", "group": "rejected", "case": "Rung 2's one rescue",
         "shows": "The quote could not be located, so REJECT — the only trigger rung 2 has. Told the fact, the model relocated the quote (to a whole sentence, withheld here), re-validated to BAND, and voting then argued the code back. Fired twice in the run; corrected nothing."},
        {"id": "LIPITOR.380#2", "group": "rejected", "case": "Still failing after the retry",
         "shows": "Unlocatable quote, and the pick was absent, so a fallback rule wrote menu line 0 — |Effusion of hip joint|, for muscle pain. Rung 2 relocated the quote to another sentence and it was still unlocatable. The vote moved it to |Pain of hip joint|; still held."},
        {"id": "LIPITOR.48#5", "group": "vote", "case": "Voting fixed it, and nothing shipped it",
         "shows": "Rung 0 picked |Burning sensation of ear| for a chest; two samples said |Burning sensation|, the gold code. One of three answers voting gained this run — and it was BAND, so it went to a person anyway."},
        {"id": "LIPITOR.24#3", "group": "vote", "case": "The fallback rule, not the model",
         "shows": "The model's pick was absent and a fallback wrote line 0, |Rupture of muscle|. All three samples repeated it — a vote cannot outvote a rule. Shown the menu, the judge said not on this list."},
        {"id": "DICLOFENAC-SODIUM.6#4", "group": "denied", "case": "A denied mention, extracted and flagged",
         "shows": "The writer denies memory loss and CADEC still annotates it. The negation cue fired and was logged, not rejected — as a rejection it cost 427 gold mentions. ACCEPT, shipped, correct."},
        {"id": "LIPITOR.70#10", "group": "denied", "case": "The model quoted the denial itself",
         "shows": "\"no problems\" coded to |No complaints|. Flagged negated, no gold mention, held. The cue does its job on both sides."},
    ],
    "psytar-gpt-oss_20b-d0": [
        {"id": "PSYTAR.zoloft.147#0", "group": "psytar", "case": "ACCEPT, ships, judge agrees",
         "shows": "The same forum as CADEC, the same vocabulary, different drugs. |Night sweats| is one of the concept's own names, so ACCEPT and shipped; the judge passed it too. PsyTAR's ACCEPT lane is 80–90 percent right across four model families."},
        {"id": "PSYTAR.zoloft.91#1", "group": "psytar", "case": "ACCEPT, ships, judge disagrees",
         "shows": "|Dry mouth| ships on the free check while the blind judge failed it. Nothing reads the judge, so the disagreement changes nothing — on this corpus the judge failed 31 of the 77 shipped records."},
        {"id": "PSYTAR.zoloft.184#3", "group": "psytar", "case": "BAND, held, judge passes",
         "shows": "A psychiatric symptom described in a phrase that only brushes the clinical term: on PsyTAR that partial overlap is 40 percent of records against 5 on CADEC, which is why its ACCEPT lane is narrower. Held for a person."},
        {"id": "PSYTAR.zoloft.184#0", "group": "psytar", "case": "BAND, held, no sample re-found it",
         "shows": "The three voting samples never re-found this span, so the vote had nothing to count; the judge failed it; held. A record the paid rungs could not touch."},
        {"id": "PSYTAR.zoloft.147#9", "group": "psytar", "case": "BAND, the vote changed the code, still held",
         "shows": "Two samples outvoted the original code. Whether that helped cannot be told here — the answer key is not on this machine — and it did not matter for routing: BAND is held regardless. On PsyTAR the three paid rungs routed zero records in three draws."},
        {"id": "PSYTAR.effexorXR.135#8", "group": "psytar", "case": "A denied mention on another corpus",
         "shows": "The negation cue fired on a weight-gain mention and flagged it, as on CADEC. The cue list is corpus-independent; what is not is rung 1's semantic check, which encodes CADEC's annotation guide and wrongly rejects 37 correct PsyTAR gold codes such as |Suicide| — and still fired on no model output here."},
    ],
    "rerun-finer-d0": [
        {"id": "FINER.test.0021#7", "group": "finer", "case": "REJECT: the quote could not be located",
         "shows": "\"275569\" — a number the model quoted that is not at any offset it named, so schema_invalid and REJECT. Rung 2 was not tried: an unlocatable span is not a statable fact. One of three REJECTs in 304; held for a person, unreviewable by a span-keyed desk."},
        {"id": "FINER.test.0059#14", "group": "finer", "case": "Right, and the check cannot say so",
         "shows": "\"63.8\" coded to the right tag. The lexical check compares a numeral against |EffectiveIncomeTaxRateContinuingOperations| and can never fire, so every FiNER record is BAND and every one goes to a person. Shown the menu the judge picked it as best; blind, it failed it."},
        {"id": "FINER.test.0057#0", "group": "finer", "case": "The slot-0 attractor",
         "shows": "\"two\" is not a numeric fact and the pick was absent; a fallback wrote menu line 0, |AccrualForEnvironmentalLossContingencies| — 73 of 304 records this run, 19.5 percent of all FiNER predictions, none of them the model's choice."},
        {"id": "FINER.test.0059#11", "group": "finer", "case": "Where voting helps: a coding error",
         "shows": "Rung 0 read \"0.7\" as |Depreciation|; two samples said |AmortizationOfIntangibleAssets|, the gold tag. On FiNER the model found two thirds of the mentions and mis-coded them, so a vote has something to move: net +6 here against +1 / −1 / −1 on CADEC."},
    ],
}


def withhold(text: str | None) -> str | None:
    """Return the span if it is within the precedent, else its word count."""
    if text is None:
        return None
    n = len(text.split())
    return text if n <= MAX_SPAN_WORDS else f"({n}-word quote withheld)"


def _load(path: pathlib.Path) -> list[dict]:
    with path.open() as fh:
        return [json.loads(line) for line in fh if line.strip()]


def _by_id(rows: list[dict]) -> dict[str, dict]:
    return {r["record_id"]: r for r in rows}


def _label(labels: Callable[[str], str | None], code: str | None) -> str | None:
    if code is None:
        return None
    if code == "CONCEPT_LESS":
        return "CONCEPT_LESS"
    return labels(code) or code


def build_demo(archive: pathlib.Path, run: str, spec: list[dict], corpus: str,
               labels: Callable[[str], str | None]) -> list[dict]:
    """One trace per spec entry, every value read from the run's files."""
    archive = pathlib.Path(archive)
    recs = {n: _by_id(_load(archive / f"{run}.r{n}.records.jsonl")) for n in range(7)}
    menu_arm = _by_id(_load(archive / f"{run}-judgemenu.r4.records.jsonl"))
    state: dict[str, dict[int, dict]] = {}
    for row in _load(archive / f"{run}.state.jsonl"):
        state.setdefault(row["record_id"], {})[row["rung"]] = row

    out = []
    for item in spec:
        rid = item["id"]
        if rid not in state or rid not in recs[0]:
            raise KeyError(f"{rid} is not a record of {run}")
        st = state[rid]
        r0, r4, final = recs[0][rid], recs[4][rid], recs[6][rid]
        # rung 1's checks are read from the rung 1 file: rung 2 can relocate a
        # REJECTed quote and re-validate, so the rung 4 record already carries
        # the checks AFTER the rescue, not the ones that produced the verdict
        c0, c1, c4 = r0["checks"], recs[1][rid]["checks"], r4["checks"]
        gold = st[6]["gold_codes"]
        menu = [{"i": m["i"], "label": m["label"], "gold": m["code"] in gold}
                for m in (c0.get("candidates") or [])]
        r3 = c4.get("r3") or {}
        arm = menu_arm.get(rid, {}).get("checks", {})
        arm_r4 = arm.get("r4") if isinstance(arm.get("r4"), dict) else {}
        best = arm_r4.get("best")
        best_label = None
        if best is not None and 0 <= best < len(menu):
            best_label = menu[best]["label"]
        r2 = c4.get("r2") or {}
        out.append({
            "id": rid, "corpus": corpus, "run": run, "group": item.get("group", ""),
            "case": item["case"], "shows": item["shows"],
            "span": withhold(r0["text"]),
            "negated": bool(c0.get("r0_negated")),
            "r0": {"code": r0["sct"], "label": r0.get("sct_label"), "picked": c0.get("label_rank"),
                   "fallback": st[0].get("pick_fallback"), "menu": menu},
            "gold": [{"code": g, "label": _label(labels, g)} for g in gold], "gold_known": True,
            "r1": {"verdict": st[1].get("r1_verdict"), "reason": st[1].get("r1_reason"),
                   "span_grounded": c1.get("span_grounded"), "exists": c1.get("sct_exists"),
                   "finding": c1.get("sct_is_finding"), "label_verified": c1.get("label_verified"),
                   "lexical_match": c1.get("lexical_match"), "negation_cue": c1.get("negation_cue")},
            "r2": {"outcome": r2.get("outcome"), "reason": r2.get("reason")},
            "r3": {"votes": [_label(labels, v) for v in (r3.get("raw") or [])], "seen": r3.get("seen"),
                   "was": _label(labels, r3.get("was")), "winner": _label(labels, r3.get("winner")),
                   "changed": bool(r3.get("changed"))},
            "r4": {"blind": st[4].get("r4_verdict"), "confidence": c4.get("r4_confidence"),
                   "menu": arm.get("r4_verdict"), "best": best, "best_label": best_label},
            "final": {"zone": final["zone"], "shipped": final["zone"] == "VERIFIED",
                      "outcome": st[6]["outcome"], "outcome_overlap": st[6]["outcome_overlap"]},
            # the answer as it stood after the last rung that changes a code (rung 4);
            # refusal clears `sct` on a withheld record and keeps it in checks.withheld
            "final_code": {"code": r4["sct"], "label": _label(labels, r4["sct"])},
        })
    return out


def build_demo_stripped(records: pathlib.Path, run: str, spec: list[dict], corpus: str,
                        labels: Callable[[str], str | None]) -> list[dict]:
    """The same trace from one published `records.stripped.jsonl` — a run whose
    raw files live on another machine. Stripped records carry the lane, the
    votes, the judge's verdict and the final zone, but no span text and no
    answer key, so `span` is a placeholder and `gold_known` is False."""
    rows = _by_id(_load(records))
    out = []
    for item in spec:
        rid = item["id"]
        if rid not in rows:
            raise KeyError(f"{rid} is not a record of {run}")
        r = rows[rid]
        c = r["checks"]
        r3 = c.get("r3") or {}
        r2 = c.get("r2") or {}
        code = r["sct"] or r3.get("winner") or r3.get("was")
        out.append({
            "id": rid, "corpus": corpus, "run": run, "group": item.get("group", ""),
            "case": item["case"], "shows": item["shows"],
            "span": "(span text not published for this run)",
            "negated": bool(c.get("r0_negated")),
            "r0": {"code": r3.get("was") or code, "label": r.get("sct_label"), "picked": c.get("label_rank"),
                   "fallback": None, "menu": []},
            "gold": [], "gold_known": False,
            "r1": {"verdict": c.get("r1_verdict"), "reason": c.get("r1_reason"),
                   "span_grounded": c.get("span_grounded"), "exists": c.get("sct_exists"),
                   "finding": c.get("sct_is_finding"), "label_verified": c.get("label_verified"),
                   "lexical_match": c.get("lexical_match"), "negation_cue": c.get("negation_cue")},
            "r2": {"outcome": r2.get("outcome"), "reason": r2.get("reason")},
            "r3": {"votes": [_label(labels, v) for v in (r3.get("raw") or [])], "seen": r3.get("seen"),
                   "was": _label(labels, r3.get("was")), "winner": _label(labels, r3.get("winner")),
                   "changed": bool(r3.get("changed"))},
            "r4": {"blind": c.get("r4_verdict"), "confidence": c.get("r4_confidence"),
                   "menu": None, "best": None, "best_label": None},
            "final": {"zone": r["zone"], "shipped": r["zone"] == "VERIFIED",
                      "outcome": None, "outcome_overlap": None},
            "final_code": {"code": code, "label": _label(labels, code)},
        })
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--archive", default=None, help="directory holding <run>.r<N>.records.jsonl etc.")
    ap.add_argument("--run", required=True, help="run id, e.g. rerun-cadec-d0")
    ap.add_argument("--corpus", required=True)
    ap.add_argument("--db", default=None, help="SNOMED sqlite for gold labels; omit for a label-free corpus")
    ap.add_argument("--stripped", default=None, help="a published records.stripped.jsonl instead of a raw archive")
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    if args.db:
        from ladder.registry import Registry
        reg = Registry(args.db)
        labels = reg.label
    else:
        labels = lambda code: None  # noqa: E731 — FiNER's tags are their own labels
    if args.stripped:
        demo = build_demo_stripped(pathlib.Path(args.stripped), args.run, SPEC[args.run], args.corpus, labels)
    else:
        demo = build_demo(pathlib.Path(args.archive), args.run, SPEC[args.run], args.corpus, labels)
    pathlib.Path(args.out).write_text(json.dumps(demo, indent=1))
    print(f"{len(demo)} traces -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

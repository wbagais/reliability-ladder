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
import re
import sys
from typing import Callable

MAX_SPAN_WORDS = 7

# corpora whose licence allows the document text on a published page
REDISTRIBUTABLE = {"finer"}   # FiNER-139 is CC-BY-SA-4.0; CADEC is non-transferable; PsyTAR's text is not on this machine

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


# ---------------------------------------------------------------- the document view

BAND_WORDS = {"colloquial_no_lexical_match": "no lexical match", "no_lexical_match": "no lexical match"}

# The documents the demo shows the way the Workbench's Live tab shows one:
# every document a SPEC example lives in, so each example is seen among its
# neighbours. Keyed by run.
DOCS: dict[str, list[str]] = {
    run: sorted({item["id"].split("#")[0] for item in items}) for run, items in SPEC.items()
}


def _span(text):
    return withhold(text) if text else text


def reduce_document(payload: dict, corpus: str, keep_text: bool = False) -> dict:
    """The Workbench's document payload (`dashboard.document_view.run_document_payload`,
    the same shape its Live tab draws) reduced to what a static page may carry:
    no post, no model call, no prose from the judge or the retry, spans within
    the seven-word precedent. Everything structural — the pairing against gold,
    the menu and the pick, the lanes, the votes, the verdicts, the six rules,
    the cost per rung — passes through unchanged."""
    gold_of: dict[str, set] = {}
    for x in (payload.get("gold_diff") or {}).get("pairs", []):
        if x.get("pred"):
            gold_of.setdefault(x["pred"], set()).update(str(s) for s in (x["gold"].get("sct") or []))
    recs = []
    for r in payload.get("records", []):
        c = r.get("checks") or {}
        st = {s["id"]: s for s in (r.get("r0_path") or {}).get("steps", [])}
        ret, pick, find, trim = st.get("retrieve") or {}, st.get("pick") or {}, st.get("find") or {}, st.get("trim") or {}
        gold_codes = gold_of.get(r["record_id"], set())
        for row in r.get("timeline") or []:
            gold_codes.update(str(g) for g in (row.get("gold_codes") or []))
        cands = ret.get("candidates") or c.get("candidates") or []
        choice = pick.get("choice") if isinstance(pick.get("choice"), int) else None
        keep = {x["i"] for x in cands[:3]} | ({choice} if choice is not None else set()) \
            | {x["i"] for x in cands if str(x.get("code")) in gold_codes}
        menu = [{"i": x["i"], "label": x["label"], "gold": str(x.get("code")) in gold_codes}
                for x in cands if x["i"] in keep]
        menu_n = len(cands)
        r3 = c.get("r3") or {}
        votes: dict[str, int] = {}
        for v in r3.get("raw") or []:
            if v:
                votes[str(v)] = votes.get(str(v), 0) + 1
        # rung 1's verdict is read from the rung 1 state row: after a rescue
        # the final record's checks carry the re-validated verdict (BAND), not
        # the one that triggered rung 2 (REJECT)
        at1 = next((row for row in (r.get("timeline") or []) if row.get("rung") == 1), None)
        r1v = (at1 or {}).get("r1_verdict") or c.get("r1_verdict")
        r1reason = (at1 or {}).get("r1_reason") or c.get("r1_reason")
        why = BAND_WORDS.get(c.get("reason_band"), c.get("reason_band") or "") if r1v == "BAND" else (r1reason or "")
        r2 = c.get("r2") or {}
        final = r.get("timeline")[-1] if r.get("timeline") else {}
        recs.append({
            "record_id": r["record_id"], "span": _span(r.get("text")), "spans": r.get("spans"),
            "negated": bool(c.get("r0_negated") if c.get("r0_negated") is not None else c.get("negated")),
            "r0": {"menu": menu, "menu_n": menu_n, "retrieval": ret.get("retrieval"),
                   "pick": {"state": pick.get("state"), "choice": pick.get("choice")},
                   "trimmed": trim.get("state") == "done", "code": (r.get("timeline") or [{}])[0].get("sct") if r.get("timeline") else r.get("sct"),
                   "label": (r.get("timeline") or [{}])[0].get("sct_label") if r.get("timeline") else r.get("sct_label")},
            "r1": {"verdict": r1v, "reason": why},
            "r2": {"outcome": r2.get("outcome"), "was": (r2.get("was") or {}).get("sct"), "now": (r2.get("now") or {}).get("sct"), "reason": r2.get("reason")},
            "r3": {"votes": votes, "k": r3.get("k", 3), "seen": r3.get("seen", 0), "changed": bool(r3.get("changed")), "tie": bool(r3.get("tie"))},
            "r4": {"verdict": c.get("r4_verdict"), "confidence": c.get("r4_confidence"),
                   "best": (c.get("r4") or {}).get("best") if isinstance(c.get("r4"), dict) else None},
            "rules": [{"id": x["id"], "state": x["state"], "value": x.get("value")} for x in r.get("rules") or []],
            "person": {"held": (r.get("person") or {}).get("held"), "run": (r.get("person") or {}).get("run")},
            "final": {"zone": final.get("zone", r.get("zone")), "sct": final.get("sct", r.get("sct")),
                      "outcome": final.get("outcome"), "outcome_overlap": final.get("outcome_overlap")},
        })
    diff = payload.get("gold_diff") or {}
    pairs = []
    for x in diff.get("pairs", []):
        g = x["gold"]
        pairs.append({"gold": {"record_id": g["record_id"], "span": _span(g.get("text")), "sct": list(g.get("sct") or []),
                               "labels": list(x.get("gold_labels") or []), "spans": g.get("spans")},
                      "span_match": x.get("span"), "pred": x.get("pred"), "pred_span": _span(x.get("pred_text")),
                      "pred_sct": x.get("pred_sct"), "pred_label": x.get("pred_label"),
                      "withheld": bool(x.get("withheld")), "code": x.get("code")})
    spurious = [{"record_id": s["record_id"], "span": _span(s.get("text")), "sct": s.get("sct"),
                 "label": s.get("sct_label"), "zone": s.get("zone")} for s in diff.get("spurious", [])]
    cost = {}
    for n, blk in (payload.get("rungs") or {}).items():
        cst = blk.get("cost") or {}
        if cst.get("api_calls"):
            cost[str(n)] = {"tokens": cst.get("tokens"), "n_calls": cst.get("api_calls"), "p95_ms": cst.get("latency_p95_ms")}
    pv = payload.get("provenance") or {}
    git = pv.get("git") or {}
    out = {
        "doc_id": payload["doc_id"], "corpus": corpus, "run": payload.get("run_id"), "split": payload.get("split"),
        "words": len(str(payload.get("text") or "").split()),
        "chars": len(str(payload.get("text") or "")),   # a count, never the text: the span map's scale
        # each word's offsets, so the page can draw the post as blank blocks with only the quoted spans filled in
        "word_spans": [[m.start(), m.end()] for m in re.finditer(r"\S+", str(payload.get("text") or ""))],
        "order_run": payload.get("order_run"), "records": recs, "pairs": pairs, "spurious": spurious,
        "counts": diff.get("counts"), "cost": cost, "legend": payload.get("rules_legend"),
        "calls_total": payload.get("calls_total"),
        "provenance": {"run_id": pv.get("run_id"), "backend": pv.get("backend"), "manifest": pv.get("manifest_hash"),
                       "git": git.get("sha") if isinstance(git, dict) else None},
        # the Workbench returns caveats as {key: text}
        "caveats": (list(payload["caveats"].values()) if isinstance(payload.get("caveats"), dict)
                    else [x["text"] if isinstance(x, dict) else str(x) for x in payload.get("caveats") or []]),
    }
    if keep_text:
        # only for a corpus whose licence allows redistribution (FiNER-139, CC-BY-SA)
        out["text"] = payload.get("text")
        out["gold_spans"] = [{"record_id": g["record_id"], "spans": g.get("spans"), "excluded": bool(g.get("excluded"))}
                             for g in payload.get("gold") or []]
    return out


def build_documents(repo_root: pathlib.Path, run_key: str, doc_ids: list[str], corpus_name: str,
                    **state_overrides) -> list[dict]:
    """Local only: the Workbench's own document builder over the archived raw
    run, reduced for the page and checked against the post it came from.
    `state_overrides` (corpus=, exclusion_rows=, registry=) point the
    Workbench at a corpus other than the manifest's, e.g. FiNER."""
    from dashboard.document_view import run_document_payload
    from dashboard.scrub import assert_clean
    from dashboard.state import AppState

    state = AppState(repo_root=repo_root, **state_overrides)
    info = state.get_run(run_key)
    git_sha = None
    agg = info.files.get("aggregates")
    if agg is not None and agg.exists():
        git_sha = ((json.loads(agg.read_text()).get("git") or {}).get("sha"))
    out = []
    for doc_id in doc_ids:
        payload = run_document_payload(state, info, doc_id)
        if payload is None:
            raise KeyError(f"{doc_id} is not a document of {run_key} on this machine")
        reduced = reduce_document(payload, corpus_name, keep_text=corpus_name in REDISTRIBUTABLE)
        reduced["provenance"]["git"] = git_sha
        if corpus_name in REDISTRIBUTABLE:
            out.append(reduced)
            continue
        post = str(payload.get("text") or "")
        # C1: no 24-character window of the post survives, except inside a
        # quoted span the precedent allows (an annotated span or the model's
        # own quote of at most seven words, which is by construction a
        # substring of the post)
        allowed = [x["span"] for x in reduced["records"] if x.get("span")]
        allowed += [x["gold"]["span"] for x in reduced["pairs"] if x["gold"].get("span")]
        allowed += [x["pred_span"] for x in reduced["pairs"] if x.get("pred_span")]
        allowed += [x["span"] for x in reduced["spurious"] if x.get("span")]
        # vocabulary labels are allowed too, and a tag name can share words with a filing
        allowed += [m["label"] for x in reduced["records"] for m in x["r0"]["menu"]]
        allowed += [l for x in reduced["pairs"] for l in x["gold"]["labels"] if l]
        allowed += [x["pred_label"] for x in reduced["pairs"] if x.get("pred_label")]
        windows = [post[i:i + 24] for i in range(0, max(1, len(post) - 24), 8)]
        windows = [w for w in windows if not any(w in a for a in allowed)]
        assert_clean(json.dumps(reduced), windows)
        out.append(reduced)
    return out


def build_documents_stripped(records: pathlib.Path, run: str, doc_ids: list[str], corpus: str,
                             labels: Callable[[str], str | None]) -> list[dict]:
    """The same view from a published stripped-records file — no post, no
    menu, no gold; the lanes, votes, verdicts and rules are the record."""
    rows = _load(records)
    out = []
    for doc_id in doc_ids:
        recs = []
        for r in rows:
            if r["doc_id"] != doc_id:
                continue
            c = r["checks"]
            r3 = c.get("r3") or {}
            votes: dict[str, int] = {}
            for v in r3.get("raw") or []:
                if v:
                    votes[str(v)] = votes.get(str(v), 0) + 1
            r1v = c.get("r1_verdict")
            code = r["sct"] or r3.get("winner") or r3.get("was")
            rules = [{"id": "V", "state": "ship" if r1v == "ACCEPT" else "hold", "value": r1v},
                     {"id": "V+", "state": "not_run", "value": None},
                     {"id": "3", "state": ("ship" if max(votes.values()) == 3 else "hold") if votes else "not_run", "value": None},
                     {"id": "2", "state": ("ship" if max(votes.values()) >= 2 else "hold") if votes else "not_run", "value": None},
                     {"id": "J", "state": {"pass": "ship", "fail": "hold"}.get(c.get("r4_verdict"), "not_run"), "value": c.get("r4_verdict")},
                     {"id": "J+", "state": "not_run", "value": None}]
            run_n = sum(1 for x in rules if x["state"] != "not_run")
            recs.append({
                "record_id": r["record_id"], "span": "(not published)", "spans": r.get("spans"),
                "negated": bool(c.get("r0_negated")),
                "r0": {"menu": [], "retrieval": None, "pick": {"state": None, "choice": c.get("label_rank")}, "trimmed": False,
                       "code": r3.get("was") or code, "label": r.get("sct_label")},
                "r1": {"verdict": r1v, "reason": BAND_WORDS.get(c.get("reason_band"), c.get("reason_band") or "") if r1v == "BAND" else (c.get("r1_reason") or "")},
                "r2": {"outcome": (c.get("r2") or {}).get("outcome"), "was": None, "now": None, "reason": None},
                "r3": {"votes": votes, "k": r3.get("k", 3), "seen": r3.get("seen", 0), "changed": bool(r3.get("changed")), "tie": bool(r3.get("tie"))},
                "r4": {"verdict": c.get("r4_verdict"), "confidence": c.get("r4_confidence"), "best": None},
                "rules": rules, "person": {"held": sum(1 for x in rules if x["state"] == "hold"), "run": run_n},
                "final": {"zone": r["zone"], "sct": code, "outcome": None, "outcome_overlap": None},
                "label": _label(labels, code),
            })
        if not recs:
            raise KeyError(f"{doc_id} is not a document of {run}")
        out.append({"doc_id": doc_id, "corpus": corpus, "run": run, "split": "dev", "words": None, "chars": None,
                    "order_run": [0, 1, 2, 3, 4, 5, 6], "records": recs, "pairs": [], "spurious": [], "counts": None,
                    "cost": {}, "legend": None, "calls_total": None,
                    "provenance": {"run_id": run, "backend": None, "manifest": None, "git": None},
                    "caveats": ["Published stripped records: no post, no menu, no answer key on this machine — the lanes, votes and verdicts are the record."]})
    return out



def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--archive", default=None, help="directory holding <run>.r<N>.records.jsonl etc.")
    ap.add_argument("--run", required=True, help="run id, e.g. rerun-cadec-d0")
    ap.add_argument("--corpus", required=True)
    ap.add_argument("--db", default=None, help="SNOMED sqlite for gold labels; omit for a label-free corpus")
    ap.add_argument("--stripped", default=None, help="a published records.stripped.jsonl instead of a raw archive")
    ap.add_argument("--documents", action="store_true", help="write the document views (DOCS[run]) instead of the record traces")
    ap.add_argument("--run-key", default=None, help="documents mode: the Workbench's run key, e.g. <archive>/rerun-cadec-d0")
    ap.add_argument("--manifest", default=None, help="documents mode: load the corpus this manifest names instead of manifest.json's (FiNER)")
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    if args.db:
        from ladder.registry import Registry
        reg = Registry(args.db)
        labels = reg.label
    else:
        labels = lambda code: None  # noqa: E731 — FiNER's tags are their own labels
    if args.documents and args.stripped:
        demo = build_documents_stripped(pathlib.Path(args.stripped), args.run, DOCS[args.run], args.corpus, labels)
    elif args.documents:
        overrides = {}
        if args.manifest:
            # the corpus the manifest names, through the runner's own adapter
            # selection, so a FiNER document is read the way the run read it
            from ladder.run import _corpus_for, _corpus_opts, _corpus_root
            man = json.loads(pathlib.Path(args.manifest).read_text())
            overrides = {"corpus": _corpus_for(man).load_corpus(_corpus_root(man), **_corpus_opts(man)),
                         "exclusion_rows": [], "registry": None, "manifest": man}
        demo = build_documents(pathlib.Path("."), args.run_key or args.run, DOCS[args.run], args.corpus, **overrides)
    elif args.stripped:
        demo = build_demo_stripped(pathlib.Path(args.stripped), args.run, SPEC[args.run], args.corpus, labels)
    else:
        demo = build_demo(pathlib.Path(args.archive), args.run, SPEC[args.run], args.corpus, labels)
    pathlib.Path(args.out).write_text(json.dumps(demo, indent=1))
    print(f"{len(demo)} {'documents' if args.documents else 'traces'} -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

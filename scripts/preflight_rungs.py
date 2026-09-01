#!/usr/bin/env python3
"""
preflight_rungs.py — measure whether a rung will pay, BEFORE you build it.

Not to be confused with scripts/preflight.py, which is the licence gate.

WHY THIS EXISTS

Every rung on the ladder makes a bet:

    rung 1  the output has a decidable invalid state
    rung 2  rung 1 produces rejections there is something to correct
    rung 3  errors are uncorrelated across samples, so a majority means something
    rung 4  a second model has signal the first lacks
    rung 5  rung 1 produces a signal worth acting on
    rung 6  the queue contains records worth adjudicating

Four of ours were dead, and not one announced it. Each ran, returned, wrote its
field and passed its tests. What every failure had in common is that the bet was
FALSE ON THIS PIPELINE, and in every case the bet is measurable on a dev split
in minutes — before a line of the rung is written.

This is that measurement. It reports; it never edits a config. A rung that
"fails" here is not broken: it is being told, cheaply, that its precondition
does not hold on this data, which is the difference between a null result and
five months.

    PYTHONPATH=. python3 scripts/preflight_rungs.py
    PYTHONPATH=. python3 scripts/preflight_rungs.py --manifest manifest.finer.json
    PYTHONPATH=. python3 scripts/preflight_rungs.py --split dev --docs 10
    PYTHONPATH=. python3 scripts/preflight_rungs.py --static      # no model calls

Exit code is always 0. This is a report, not a gate — the whole point is that
you read it and decide.
"""
from __future__ import annotations

import argparse
import collections
import json
import os
import pathlib
import re
import sys
import time

BUILD, DONT, UNKNOWN = "BUILD", "DON'T", "UNKNOWN"

# ── presentation ────────────────────────────────────────────────────────
IS_TTY = sys.stdout.isatty()
def _c(code, s): return f"\033[{code}m{s}\033[0m" if IS_TTY else s
GREEN = lambda s: _c("32", s)
RED = lambda s: _c("31", s)
DIM = lambda s: _c("90", s)
BOLD = lambda s: _c("1", s)
AMBER = lambda s: _c("33", s)


class Check:
    """One rung's precondition, its measurement, and what it implies."""

    def __init__(self, rung, name, question):
        self.rung, self.name, self.question = rung, name, question
        self.verdict = UNKNOWN
        self.evidence = ""
        self.because = ""
        self.cost = "free"
        self.error = None

    def report(self, verdict, evidence, because, cost="free"):
        self.verdict, self.evidence, self.because, self.cost = verdict, evidence, because, cost
        return self

    def failed(self, exc):
        self.error = str(exc)[:180]
        return self

    def render(self):
        tag = {BUILD: GREEN(" BUILD "), DONT: RED(" DON'T "),
               UNKNOWN: AMBER("UNKNOWN")}[self.verdict]
        head = f"  rung {self.rung}  {self.name:<16} {tag}   {DIM(self.cost)}"
        lines = [head, f"      {DIM(self.question)}"]
        if self.error:
            lines.append(f"      {AMBER('could not measure: ' + self.error)}")
        else:
            if self.evidence:
                lines.append(f"      {self.evidence}")
            if self.because:
                for ln in _wrap(self.because, 92):
                    lines.append(f"      {DIM(ln)}")
        return "\n".join(lines)


def _wrap(text, width):
    out, line = [], ""
    for w in text.split():
        if len(line) + len(w) + 1 > width:
            out.append(line); line = w
        else:
            line = (line + " " + w).strip()
    if line:
        out.append(line)
    return out


# ── the static check, which costs nothing and found the most ────────────
def check_readers(root: pathlib.Path):
    """Does anything READ each rung's verdict field?

    The single highest-value check here, and it needs no data at all. Three of
    our rungs wrote a verdict field that nothing downstream consumed: rung 2
    wrote r2_declined, rung 3 wrote r3_unanimous_none, rung 4 wrote r4_verdict,
    and the refusal step reads the deterministic verdict and nothing else.
    Three layers ran, cost money, passed their own tests, and were wired to
    nothing. No test could have caught it, because each layer does exactly what
    its documentation promises — the hole is BETWEEN them.

    WHAT COUNTS. Most fields on a record are DIAGNOSTIC: candidates, label_rank,
    code_source. They are written for the ledger and for later analysis, and
    nothing in the pipeline should read them — reporting those as orphans buries
    the signal in noise, which an earlier version of this check did.

    A VERDICT is different. It is a rung's claim about a record, written so that
    a LATER rung can act on it, and one nothing reads is a rung paying for a
    comment. Recognised by name: r2_*, r3_*, r4_* and anything ending in
    _verdict, _declined, _rescued, _unanimous or _agreed.
    """
    VERDICT = re.compile(
        r'^(r\d+_|.*_(verdict|declined|rescued|unanimous|unanimous_none|agreed|approved))$')

    written, read = {}, collections.defaultdict(set)
    files = [f for f in sorted(root.rglob("*.py")) if "__pycache__" not in str(f)]
    srcs = {}
    for py in files:
        try:
            srcs[py] = py.read_text(errors="replace")
        except Exception:
            continue

    for py, src in srcs.items():
        for m in re.finditer(r'checks\[\s*["\']([A-Za-z0-9_]+)["\']\s*\]\s*=(?!=)', src):
            written.setdefault(m.group(1), set()).add(py.name)

    for py, src in srcs.items():
        for f in written:
            pat = (r'checks\.get\(\s*["\']' + re.escape(f) + r'["\']'
                   r'|checks\[\s*["\']' + re.escape(f) + r'["\']\s*\](?!\s*=[^=])')
            if re.search(pat, src):
                read[f].add(py.name)

    verdicts, diagnostics = {}, {}
    for f, w in written.items():
        rec = {"written": w, "read": read.get(f, set()) - w}   # a rung reading its own write is not a consumer
        (verdicts if VERDICT.match(f) else diagnostics)[f] = rec
    return verdicts, diagnostics


# ── the measured checks ─────────────────────────────────────────────────
def load(manifest_path):
    from ladder.manifest import load_manifest
    return load_manifest(manifest_path)


def corpus_for(man):
    name = (man.get("corpus") or {}).get("adapter", "cadec")
    if name == "geo":
        from ladder import corpus_geo as mod
        return mod
    if name == "finer":
        from ladder import corpus_finer as mod
    else:
        from ladder import corpus as mod
    return mod


def corpus_root(man):
    c = man.get("corpus") or {}
    return c.get("root") or c["cadec_root"]


def corpus_opts(man):
    c = man.get("corpus") or {}
    return {k: v for k, v in (c.get("sampling") or {}).items() if not k.startswith("_")}


def vocab_for(man):
    if (man.get("vocabulary") or {}).get("backend") == "finer-tags":
        from ladder import vocab_finer
        return vocab_finer.load(corpus_root(man))
    from ladder.registry import Registry
    return Registry(man["vocabulary"]["snomed_db"])


def check_accept_lane(man, gold, vocab):
    """rung 1 · can the ACCEPT lane fire on this corpus AT ALL?

    The cheapest and most consequential of the measured checks. rung 1 sorts
    answers into REJECT, ACCEPT and BAND, and the ACCEPT lane is the one thing
    on our ladder that demonstrably paid: 80-89% correct across five model
    families whose headline F1 spans a factor of 2.8.

    It is also the one with a precondition nobody stated. ACCEPT requires that
    the extracted span and the code's own name be comparable AS STRINGS. On
    patient text against SNOMED they often are. On SEC filings the span is
    "47.6" and the code is EffectiveIncomeTaxRateContinuingOperations, and a
    number shares no tokens with a name by construction — ACCEPT 0 of 704.

    Run against GOLD, so the answer is a property of the corpus rather than of
    any model: if the lane cannot fire on a PERFECT answer set, no model will
    ever reach it.
    """
    c = Check(1, "ACCEPT lane", "can span and code be compared lexically at all?")
    hits = tried = 0
    mode = ((man.get("rungs") or {}).get("1") or {}).get("lexical_mode", "exact")
    for m in gold:
        codes = getattr(m, "sct", None) or []
        if not codes or not m.text:
            continue
        tried += 1
        try:
            if any(vocab.lexical_match(m.text, code, mode=mode) for code in codes):
                hits += 1
        except Exception:
            pass
    if not tried:
        return c.failed(RuntimeError("no coded gold mentions to test"))
    rate = hits / tried
    ev = f"{hits} of {tried} gold mentions match a term for their own code ({rate:.1%}), mode={mode!r}"
    if hits == 0:
        return c.report(DONT, ev,
                        "The lane cannot fire on a PERFECT answer set, so no model can reach it. "
                        "Rungs 2 and 5 inherit this: with no ACCEPT there is nothing to endorse, "
                        "and with no REJECT there is nothing to correct or withhold. Check whether "
                        "your span and your code are drawn from the same language before building "
                        "anything on top of a lexical check.")
    if rate < 0.05:
        return c.report(DONT, ev,
                        "Under 5% of a perfect answer set is settleable for free. The lane exists "
                        "but is too thin to carry a system.")
    return c.report(BUILD, ev,
                    "The lane can fire. On our CADEC arm the records that land in it were 80-89% "
                    "correct regardless of which model produced them — worth measuring on yours.")


def check_reject_lane(man, gold, vocab):
    """rungs 2 and 5 · does rung 1 produce REJECTIONS to act on?

    Rung 2 fires only on rejections. Rung 5 routes on rung 1's verdict. Both
    inherit their input from the rejection rate, and ours went from 5.1% to
    0.4% when a span filter three rungs BELOW started dropping ungrounded spans
    at source. Nothing broke, both rungs still passed every test, and both
    stopped doing anything: a layer with nothing to do is indistinguishable
    from inside from a layer doing nothing.

    Measured here as a property of the vocabulary: how many gold codes fail the
    free existence check. On gold every rejection is FALSE by construction, so
    this doubles as rung 1's false-positive rate, for nothing.
    """
    c = Check(2, "correctable", "does rung 1 produce rejections to correct?")
    bad = tried = 0
    for m in gold:
        codes = getattr(m, "sct", None) or []
        if not codes:
            continue
        tried += 1
        try:
            if not all(vocab.exists(code) for code in codes):
                bad += 1
        except Exception:
            pass
    if not tried:
        return c.failed(RuntimeError("no coded gold mentions"))
    rate = bad / tried
    ev = f"{bad} of {tried} gold codes fail the free existence check ({rate:.2%}) — every one a FALSE positive"
    if bad == 0:
        return c.report(BUILD, ev,
                        "Rung 1's existence check has a zero false-positive rate on this vocabulary, "
                        "which is the ideal starting point. Whether rung 2 has anything to DO depends "
                        "on how often the MODEL fails it — run rung 0 on ten documents and count.")
    if rate > 0.05:
        return c.report(DONT, ev,
                        "Rung 1 rejects more than 5% of a PERFECT answer set, so a large share of what "
                        "rung 2 would be asked to correct is not wrong. Fix the check before building "
                        "the layer that acts on it — ours went from 9.3% to 0.13% this way.")
    return c.report(BUILD, ev, "False-positive rate is low enough that rejections mean something.")


def check_tau(man, records):
    """rung 5 · does the confidence field actually VARY?

    Rung 5 has a confidence threshold. Ours is a dead dial: rung 0 emits
    exactly {1.0, 0.99} and nothing else, so the threshold never separates
    anything and the planned sweep was cancelled rather than run over a
    constant. A knob on a variable that does not vary is worse than no knob,
    because it looks tunable.
    """
    c = Check(5, "threshold", "does the confidence field take more than one value?")
    vals = [r.get("confidence") for r in records if r.get("confidence") is not None]
    if not vals:
        return c.failed(RuntimeError("no confidence values in the sampled records"))
    d = collections.Counter(round(float(v), 3) for v in vals)
    top = ", ".join(f"{k}×{v}" for k, v in d.most_common(4))
    ev = f"{len(d)} distinct value(s) over {len(vals)} records: {top}"
    if len(d) <= 2:
        return c.report(DONT, ev,
                        "A threshold over this field is a dead dial — it cannot separate records "
                        "because the field barely varies. Either find a confidence signal that does, "
                        "or route on the deterministic verdict and drop the knob.")
    return c.report(BUILD, ev, "The field varies enough for a threshold to mean something. Sweep it on dev, never on test.")


def check_resample(man, docs, doc_ids, n_docs):
    """rung 3 · do independent samples RE-FIND the same spans?

    Voting matches records by (doc_id, spans). If two draws of the same
    document quote different phrasings, the keys never align and the rung
    reports not_resampled rather than a disagreement — it is not voting, it is
    failing to find anything to vote on. Ours could not re-find 98% of mentions
    on CADEC and 46% on FiNER.

    This is the only check here that spends tokens, and it is deliberately
    small: k=3 over a handful of documents is enough to see whether the keys
    align at all.
    """
    c = Check(3, "resample", "do independent draws re-find the same spans?")
    try:
        from ladder import llm as llm_mod
        from ladder.rungs import r0
    except Exception as exc:
        return c.failed(exc)

    caller = llm_mod.for_rung(0, man)
    if caller is None:
        return c.failed(RuntimeError("no model configured for rung 0"))
    sampler = caller.sampler(float(((man.get("rungs") or {}).get("3") or {}).get("temperature", 0.7)))

    cfg = dict((man.get("rungs") or {}).get("0") or {})
    cfg.update(registry=vocab_for(man), manifest=man,
               prompt_slots=(man.get("corpus") or {}).get("prompts"))
    try:
        cfg = r0.prepare(cfg)
    except Exception as exc:
        return c.failed(exc)

    keysets, calls = [], 0
    t0 = time.time()
    for draw in range(3):
        keys = set()
        for d in doc_ids[:n_docs]:
            doc = docs[d]
            try:
                recs, _ = r0.extract_document(d, doc.text, sampler, cfg)
                calls += 1
            except Exception as exc:
                return c.failed(exc)
            for r in recs:
                sp = getattr(r, "spans", None)
                if sp:
                    keys.add((d, tuple(tuple(x) for x in sp)))
        keysets.append(keys)
    secs = time.time() - t0

    inter = set.intersection(*keysets) if keysets else set()
    union = set.union(*keysets) if keysets else set()
    j = len(inter) / len(union) if union else 0.0
    ev = (f"{len(inter)} spans found in all 3 draws of {len(union)} ever found "
          f"— Jaccard {j:.2f} over {n_docs} documents")
    cost = f"{calls} calls · {secs:.0f}s"
    if j < 0.35:
        return c.report(DONT, ev,
                        "Draws mostly do not agree on WHERE the mentions are, so a vote keyed on spans "
                        "has almost nothing to vote on. Match on overlap instead of exact spans, or "
                        "do not build the rung.", cost)
    if j < 0.7:
        return c.report(UNKNOWN, ev,
                        "Partial agreement. Voting will engage on the shared subset and report "
                        "not_resampled on the rest — make sure that third state is recorded, or the "
                        "rung's rate will be computed over a set nobody named.", cost)
    return c.report(BUILD, ev,
                    "Draws agree on the spans, so a vote is well defined. Whether AGREEMENT means "
                    "CORRECTNESS is a separate question — the voter and the answerer are usually the "
                    "same model, and a vote carries no information the original answer lacked.", cost)


def sample_records(man, docs, doc_ids, n_docs):
    """A small rung 0 run, greedy, used by the checks that need model output."""
    from ladder import llm as llm_mod
    from ladder.rungs import r0
    caller = llm_mod.for_rung(0, man)
    if caller is None:
        raise RuntimeError("no model configured for rung 0")
    cfg = dict((man.get("rungs") or {}).get("0") or {})
    cfg.update(registry=vocab_for(man), manifest=man,
               prompt_slots=(man.get("corpus") or {}).get("prompts"))
    cfg = r0.prepare(cfg)
    out = []
    for d in doc_ids[:n_docs]:
        recs, _ = r0.extract_document(d, docs[d].text, caller, cfg)
        for r in recs:
            out.append({"confidence": (r.checks or {}).get("confidence",
                                       getattr(r, "confidence", None)),
                        "sct": getattr(r, "sct", None)})
    return out


# ── main ────────────────────────────────────────────────────────────────
def main() -> int:
    ap = argparse.ArgumentParser(
        description="Measure whether each rung's precondition holds, before building it.")
    ap.add_argument("--manifest", default="manifest.json")
    ap.add_argument("--split", default="dev")
    ap.add_argument("--docs", type=int, default=8,
                    help="documents for the checks that call a model (default 8)")
    ap.add_argument("--static", action="store_true",
                    help="only the checks that need no model calls")
    a = ap.parse_args()

    root = pathlib.Path("ladder")
    print()
    print(BOLD("  preflight — does each rung's bet hold on this pipeline?"))
    print(DIM(f"  manifest {a.manifest} · split {a.split}"
              + ("" if a.static else f" · {a.docs} documents for the model checks")))
    print()

    # -- static: who reads what -----------------------------------------
    print(BOLD("  wiring") + DIM("  — free, and it found the most"))
    if not root.is_dir():
        verdicts, diagnostics, orphans = {}, {}, {}
        print(f"      {AMBER('no ladder/ directory found — run from the repo root')}")
    else:
        verdicts, diagnostics = check_readers(root)
        orphans = {f: r for f, r in verdicts.items() if not r["read"]}
        if orphans:
            print(f"      {RED(str(len(orphans)) + ' verdict field(s) written and never read by another module')}")
            for f, r in sorted(orphans.items()):
                print(f"        {RED('·')} {f:<26} written by {', '.join(sorted(r['written']))}")
            for ln in _wrap("A rung that writes a verdict nothing consumes is paying for a comment. "
                            "Ours had three, each correctly deferring to a rung that never read it. "
                            "Grep for the readers of every field you write.", 92):
                print(f"      {DIM(ln)}")
        elif verdicts:
            print(f"      {GREEN('all ' + str(len(verdicts)) + ' verdict fields are read by another module')}")
        else:
            print(f"      {DIM('no verdict-shaped fields found')}")
        print(f"      {DIM(str(len(diagnostics)) + ' diagnostic field(s) not checked — written for the ledger, not for a rung')}")
    print()

    checks = []
    try:
        man = load(a.manifest)
        cmod = corpus_for(man)
        docs = cmod.load_corpus(corpus_root(man), **corpus_opts(man))
        doc_ids = cmod.read_split(man["corpus"]["splits_dir"], a.split)
        gold = cmod.gold_records(docs, doc_ids)
        vocab = vocab_for(man)
    except Exception as exc:
        print(f"  {AMBER('could not load the corpus: ' + str(exc)[:160])}")
        return 0

    print(BOLD("  preconditions") + DIM(f"  — {len(gold)} gold mentions, {len(doc_ids)} documents"))
    checks.append(check_accept_lane(man, gold, vocab))
    checks.append(check_reject_lane(man, gold, vocab))

    if not a.static:
        try:
            recs = sample_records(man, docs, doc_ids, a.docs)
            checks.append(check_tau(man, recs))
        except Exception as exc:
            checks.append(Check(5, "threshold",
                                "does the confidence field take more than one value?").failed(exc))
        checks.append(check_resample(man, docs, doc_ids, min(a.docs, 5)))
    else:
        for rung, name, q in ((5, "threshold", "does the confidence field vary?"),
                              (3, "resample", "do independent draws re-find the same spans?")):
            c = Check(rung, name, q)
            c.report(UNKNOWN, "not run", "needs model calls — drop --static to measure it")
            checks.append(c)

    c4 = Check(4, "judge", "does a second model separate known-good from known-bad?")
    if pathlib.Path("scripts/r4_gold_control.py").is_file():
        c4.report(UNKNOWN, "not run here",
                  "scripts/r4_gold_control.py already does this properly: it feeds the judge "
                  "known-correct and known-wrong records and reports whether the verdicts differ. "
                  "Ours returned two constants — 83% span_ok on gold AND on model output. Run it "
                  "before believing a judge, and check the parse-failure rate separately: "
                  "availability was one judge's problem, not judging's.")
    else:
        c4.report(UNKNOWN, "no gold control found",
                  "Feed the judge records you KNOW are right and records you KNOW are wrong. If the "
                  "verdict distribution is the same for both, it is a constant, not a checker.")
    checks.append(c4)

    print()
    for c in sorted(checks, key=lambda x: x.rung):
        print(c.render()); print()

    verdicts = collections.Counter(c.verdict for c in checks)
    print(BOLD("  summary  ")
          + GREEN(f"{verdicts[BUILD]} build") + "   "
          + RED(f"{verdicts[DONT]} don't") + "   "
          + AMBER(f"{verdicts[UNKNOWN]} unknown")
          + (f"   {RED(str(len(orphans)) + ' orphaned field(s)')}" if orphans else ""))
    print(DIM("  A rung marked DON'T is not broken. Its bet does not hold on this data,"))
    print(DIM("  and you now know that in minutes rather than after building it."))
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

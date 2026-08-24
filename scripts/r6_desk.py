#!/usr/bin/env python3
"""r6_desk.py — rung 6, as a timing study rather than a product.

WHY THIS EXISTS

The plan's thesis is "stop at the rung your economics justify". Cost is three
measures — tokens, latency, records routed to a person — and the third has been
zero everywhere, not because review is free but because nobody has timed it.
The ladder's full cost cannot be stated without it.

Rung 6 is not falsifiable the way rungs 0-5 were. Each of those could have
worked and did not. Nobody doubts a person can code an adverse reaction. What
is genuinely unknown is what it COSTS.

WHAT v2 ADDS: SEARCH

v1 gave the reviewer no way to look anything up, so a record with no candidates
measured the time to DECLINE, not to CODE. That is a floor, not an estimate.
This version puts the vocabulary in the reviewer's hands: /term searches,
results are numbered, the loop runs until a decision. The searching IS the
cost, so the timer covers all of it, and the number of searches is recorded —
a record settled on the first query and one that took five share a median and
are not the same work.

DESIGN

  Blind        gold and model records shuffled together, shown identically.
               Without it you time your recall of a corpus you have been
               reading all day.
  Stratified   on what the vocabulary actually returns, which is what decides
               the reviewer's job. Never pooled.
  Timed,       decision and seconds recorded; accuracy NOT computed. The moment
  not scored   it is an accuracy test it measures the reviewer.
  Cached       rung 0 runs once. The pool does not change between sessions.

WHAT IT CANNOT TELL YOU — in the write-up, not a footnote:
  - whether a trained safety officer is faster. Probably much.
  - whether fatigue changes it over 155 records rather than 6.
  - anything about review ACCURACY.

    LADDER_N=8 PYTHONPATH=. python3 scripts/r6_desk.py
    LADDER_N=8 PYTHONPATH=. python3 scripts/r6_desk.py --n 3 --seed 7 --rebuild
"""
from __future__ import annotations

import argparse
import json
import pathlib
import random
import statistics
import time

try:
    from rich.console import Console
    from rich.table import Table
    from rich.text import Text
    from rich.panel import Panel
    from rich.rule import Rule
except ImportError:
    raise SystemExit("needs rich:  pip install rich --break-system-packages")

from ladder.registry import Registry
from ladder.rungs.r0 import run, Record
from ladder.rungs import r1
from ladder.ledger import Ledger
from ladder import stub_llm as S, corpus as C

RUNG = 6
OUT = "runs/r6-timing.jsonl"
CACHE = "runs/.r6-pool.json"

con = Console()


def build_pool(man, use_cache: bool = True):
    """Model records plus gold records, rung 1 verdicts attached.

    Cached: rung 0 is N sequential model calls and the pool does not change
    between review sessions. --rebuild forces it.
    """
    cache = pathlib.Path(CACHE)
    reg = Registry(man["vocabulary"]["snomed_db"])
    items = S.load_items(man["corpus"]["splits_dir"])
    src = {i["doc_id"]: i["text"] for i in items}

    if use_cache and cache.exists():
        con.print("[grey50]pool from cache · --rebuild to refresh[/]")
        raw = json.loads(cache.read_text())
        pool = []
        for r in raw["records"]:
            r = dict(r)
            r["spans"] = [tuple(s) for s in r["spans"]]
            pool.append(Record(**r))
        return reg, src, pool

    con.print("[grey50]building pool — rung 0 runs once, then it is cached[/]")
    docs = C.load_corpus(man["corpus"]["cadec_root"])
    recs, _ = run(items, "A", S.stub, {"registry": reg, "rung0_offsets": "search"})
    for r in recs:
        r.checks["_source"] = "model"

    for it in items:
        for g in docs[it["doc_id"]].mentions:
            d = g.to_dict()
            if d.get("entity_type") != "reaction" or d.get("gold_kind") != "single":
                continue
            sp, cd = d.get("spans") or [], [str(c) for c in (d.get("sct") or [])]
            if not sp or len(cd) != 1:
                continue
            recs.append(Record(
                doc_id=it["doc_id"], entity_type="reaction", text=d.get("text", ""),
                spans=[tuple(x) for x in sp], sct=cd[0], meddra=None,
                confidence=1.0, zone="NEW", reason=None,
                record_id=f"{it['doc_id']}#g{d.get('index')}",
                provenance=["gold"], checks={"_source": "gold"}))

    for r in recs:
        v, why, _ = r1.zone(r, src.get(r.doc_id, ""), reg, {"registry": reg})
        r.checks["r1_verdict"], r.checks["r1_reason"] = v, why

    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps({"records": [
        {"doc_id": r.doc_id, "entity_type": r.entity_type, "text": r.text,
         "spans": [list(s) for s in r.spans], "sct": r.sct, "meddra": r.meddra,
         "confidence": r.confidence, "zone": r.zone, "reason": r.reason,
         "record_id": r.record_id, "provenance": list(r.provenance or []),
         "checks": r.checks} for r in recs]}))
    return reg, src, recs


def search(reg, term: str, k: int = 6):
    try:
        found = reg.search(term, k) or []
    except Exception as e:
        con.print(f"[red]  search failed: {e}[/]")
        return []
    out = []
    for c in found:
        if isinstance(c, dict):
            out.append((str(c.get("code") or c.get("sct") or "?"),
                        c.get("term") or c.get("fsn") or ""))
        else:
            out.append((str(c), ""))
    return out[:k]


def print_candidates(cands, title):
    t = Table(box=None, pad_edge=False, show_header=False)
    t.add_column(width=4, style="cyan")
    t.add_column(width=16, style="grey70")
    t.add_column(style="white")
    for n, (code, term) in enumerate(cands, 1):
        t.add_row(str(n), code, term)
    con.print(Text(f"  {title}", style="grey50"))
    con.print(t)


def show_record(i, total, rec, cands, src):
    text = src.get(rec.doc_id, "")
    s, e = rec.spans[0] if rec.spans else (0, 0)
    body = Text()
    body.append("…" + text[max(0, s - 130):s], style="grey58")
    body.append(text[s:e], style="bold black on yellow")
    body.append(text[e:e + 130] + "…", style="grey58")

    con.print()
    con.print(Rule(f"record {i} of {total}", style="grey30", align="left"))
    con.print()
    con.print(Panel(body, border_style="grey30", padding=(1, 2)))
    con.print(Text(f"  quoted   {rec.text!r}", style="grey62"))
    con.print()
    if cands:
        print_candidates(cands, "candidates for this text")
    else:
        con.print(Text("  the vocabulary returned nothing for this text",
                       style="dark_orange3"))
    con.print()
    con.print(Text("  /term  search     1-6  pick     c  no valid code     "
                   "x  not a reaction     s  skip", style="grey42"))


def report(results):
    con.print()
    con.print(Rule("rung 6 — measured review time", style="grey30", align="left"))
    t = Table(box=None, pad_edge=False)
    t.add_column("stratum", width=18)
    t.add_column("n", width=4, justify="right")
    t.add_column("median", width=9, justify="right")
    t.add_column("range", width=14, justify="right")
    t.add_column("searches", width=10, justify="right")
    for stratum in ("with_candidates", "no_candidates"):
        v = [r[1] for r in results if r[0] == stratum]
        sr = [r[4] for r in results if r[0] == stratum]
        if not v:
            continue
        t.add_row(stratum, str(len(v)), f"{statistics.median(v):.1f}s",
                  f"{min(v):.0f}–{max(v):.0f}s",
                  f"{statistics.median(sr):.0f}" if sr else "—")
    con.print(t)
    con.print(Text("\n  Not pooled. Picking from a list and searching a "
                   "129,675-concept terminology are different jobs.",
                   style="grey50"))

    no_c = [r[1] for r in results if r[0] == "no_candidates"]
    if no_c:
        m = statistics.median(no_c)
        con.print(Text.assemble(
            ("\n  EXTRAPOLATION", "yellow"),
            (f", from n={len(no_c)}: the withheld queue holds 155 records with\n"
             f"  no valid code. At {m:.0f}s each that is "
             f"{155 * m / 3600:.1f} reviewer-hours, against 234,727 tokens\n"
             "  that produced 0 correct codes. Quote it as an extrapolation "
             "from a handful\n  of records, never as a measured total — and "
             "note the reviewer was not a\n  trained coder.", "grey62")))

    by_src = {}
    for _, secs, _, source, _ in results:
        by_src.setdefault(source, []).append(secs)
    if len(by_src) > 1:
        con.print(Text("\n  unblinded, after the fact — at this n treat any "
                       "difference as noise:", style="grey42"))
        for k, v in by_src.items():
            con.print(Text(f"    {k:6} n={len(v)}  median "
                           f"{statistics.median(v):.1f}s", style="grey50"))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=3, help="records per stratum")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--rebuild", action="store_true", help="ignore the cached pool")
    a = ap.parse_args()

    man = json.loads(pathlib.Path("manifest.json").read_text())
    reg, src, pool = build_pool(man, use_cache=not a.rebuild)

    rng = random.Random(a.seed)
    rng.shuffle(pool)
    with_c, without_c = [], []
    for r in pool:
        if len(with_c) >= a.n and len(without_c) >= a.n:
            break
        c = search(reg, r.text)
        (with_c if c else without_c).append((r, c))
    q = with_c[:a.n] + without_c[:a.n]
    rng.shuffle(q)

    con.print()
    con.print(Panel(Text.assemble(
        ("rung 6 — timing study\n\n", "bold"),
        (f"{len(q)} records · {len(with_c[:a.n])} with candidates, "
         f"{len(without_c[:a.n])} without\n", "white"),
        ("Provenance is hidden and the order shuffled. Decisions are recorded; "
         "accuracy is not scored.\n", "grey62"),
        ("Search with /term as often as you need — the searching is the cost, "
         "and the timer covers it.", "grey62")),
        border_style="grey30", padding=(1, 2)))
    input("\n  enter to start… ")

    led = Ledger(OUT, run_id=f"r6-{int(time.time())}")
    results = []
    try:
        for i, (rec, cands) in enumerate(q, 1):
            stratum = "with_candidates" if cands else "no_candidates"
            shown = list(cands)
            show_record(i, len(q), rec, shown, src)
            t0 = time.perf_counter()
            searches = 0
            decision = code = None

            while decision is None:
                ans = con.input("\n  [bold]>[/] ").strip()
                if ans.startswith("/"):
                    term = ans[1:].strip()
                    if not term:
                        continue
                    searches += 1
                    found = search(reg, term)
                    con.print()
                    if found:
                        shown = found
                        print_candidates(found,
                                         f"'{term}' — pick a number, or search again")
                    else:
                        con.print(Text(f"  nothing for '{term}'",
                                       style="dark_orange3"))
                    continue
                low = ans.lower()
                if low == "c":
                    decision = "declined"
                elif low == "x":
                    decision = "not_a_reaction"
                elif low == "s":
                    decision = "skipped"
                elif ans.isdigit() and shown and 1 <= int(ans) <= len(shown):
                    decision, code = "coded", shown[int(ans) - 1][0]
                elif ans.isdigit() and len(ans) >= 6:
                    decision, code = "coded", ans     # SCTID typed directly
                else:
                    con.print(Text("  /term to search · 1-6 · c · x · s",
                                   style="grey42"))

            secs = time.perf_counter() - t0
            results.append((stratum, secs, decision,
                            rec.checks.get("_source"), searches))
            led.log(rung=RUNG, doc_id=rec.doc_id, record_id=rec.record_id,
                    zone="REVIEWED", outcome=decision,
                    reason=rec.checks.get("r1_reason"),
                    human_minutes=secs / 60.0, api_calls=0,
                    denominator=f"r6_{stratum}", evaluable="pass",
                    seconds=round(secs, 1), searches=searches,
                    chose=code, source=rec.checks.get("_source"))
            con.print(Text(f"  {decision}" + (f" {code}" if code else "")
                           + f" · {secs:.0f}s · {searches} search"
                           + ("" if searches == 1 else "es"), style="green"))
    except KeyboardInterrupt:
        con.print("\n[grey50]stopped early[/]")
    finally:
        led.close()

    if results:
        report(results)
        con.print(f"\n[grey50]written to {OUT}[/]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""r6_desk.py — the rung 6 desk: a person works a run's abstained queue.

WHAT THIS IS

Rung 5 abstains and withholds; this is where the withheld records meet a
person. The desk loads a finished run's `records.jsonl`, queues every record
rung 5 left in ABSTAIN, and shows each one with its source context, the answer
the system withdrew (`checks.withheld` — WITH its vocabulary label, never a
bare SCTID), and the candidate menu the run itself retrieved. The reviewer
decides; the decision, the seconds it took and the number of searches are
appended to a resolutions file that `ladder/rungs/r6.py` (mode "desk") applies
back onto the records in the shape the scorer grades.

The searching is part of the job, so the timer covers it: `/term` searches
through the SAME retriever the run's rung 0 used, and the search count is
recorded — a record settled on sight and one that took five queries share a
median and are not the same work.

Resolution rows carry record ids, offsets, codes and vocabulary labels ONLY —
no corpus text — so the file is shareable where the corpus is not.

--oracle writes the resolutions deterministically from the gold annotations
instead of asking anyone. That is an ORACLE CEILING — the best a perfect
reviewer could do with this queue — and never a measurement of human work; the
rows are stamped `oracle:gold`, rung 6 labels every number they produce, and
the flag refuses to touch test-split documents at all.

    PYTHONPATH=. python3 scripts/r6_desk.py out/RUN.records.jsonl
    PYTHONPATH=. python3 scripts/r6_desk.py out/RUN.records.jsonl --oracle
"""
from __future__ import annotations

import argparse
import getpass
import json
import pathlib
import statistics
import time

from ladder import corpus as corpus_mod
from ladder.manifest import load_manifest
from ladder.registry import Registry
from ladder.rungs import r0, r6
from ladder.schema import loads

# Plain ANSI, on purpose: no dependency, and the import smoke test can reach
# every line of this file on any machine.
DIM, BOLD, MARK, WARN, OK, END = (
    "\033[2m", "\033[1m", "\033[30;43m", "\033[33m", "\033[32m", "\033[0m"
)

MENU_ROWS = 9
CONTEXT = 130

HELP = "/term search · 1-9 pick · w withheld · SCTID · c no-code · u uphold · s skip · q quit"


# --- queue and resume --------------------------------------------------------


def load_queue(records_path: str | pathlib.Path):
    """The abstained residue, in a stable order a session can resume into."""
    recs = loads(pathlib.Path(records_path).read_text(encoding="utf-8"))
    return sorted(r6.queue(recs), key=lambda r: (r.doc_id, r.record_id))


def resume_keys(out_path: pathlib.Path) -> set[tuple]:
    """Span keys already resolved in the output file — a session resumes."""
    if not out_path.exists():
        return set()
    return {
        r6._span_key(row["doc_id"], row["spans"])
        for row in r6.load_resolutions(out_path)
    }


def default_out(records_path: str, oracle: bool) -> pathlib.Path:
    stem = str(records_path)
    if stem.endswith(".records.jsonl"):
        stem = stem[: -len(".records.jsonl")]
    else:
        stem = stem.rsplit(".jsonl", 1)[0]
    suffix = ".oracle-resolutions.jsonl" if oracle else ".resolutions.jsonl"
    return pathlib.Path(stem + suffix)


# --- display -----------------------------------------------------------------


def show(i, total, rec, source, withheld_label, cands):
    s, e = rec.spans[0] if rec.spans else (0, 0)
    ctx = (
        f"{DIM}…{source[max(0, s - CONTEXT):s]}{END}"
        f"{MARK}{source[s:e]}{END}"
        f"{DIM}{source[e:e + CONTEXT]}…{END}"
    )
    wh = (rec.checks.get("withheld") or {})
    code = wh.get("sct")
    print(f"\n{DIM}── record {i} of {total} — {rec.record_id} " + "─" * 20 + END)
    print(f"\n{ctx}\n")
    denied = "  [denied]" if rec.checks.get("r0_negated") else ""
    print(f"  quoted    {rec.text!r}{denied}")
    # r1_reason is legitimately absent on a BAND verdict — omit it rather
    # than print a Python None at a person (seen in the first live session).
    r1 = rec.checks.get("r1_verdict") or "?"
    why = rec.checks.get("r1_reason")
    print(f"  abstained {rec.reason}  (r1: {r1}{f' — {why}' if why else ''})")
    if code:
        label = withheld_label or f"{WARN}<no label in the vocabulary>{END}"
        print(f"  withheld  {code}  {label}")
    print_menu(cands, "candidates from the run's own menu")


def print_menu(cands, title):
    if not cands:
        print(f"\n  {WARN}nothing on the menu for this record{END}")
        return
    print(f"\n  {DIM}{title}{END}")
    # Width follows the longest code shown: SCTIDs run 6-18 digits, and a
    # fixed column jammed 1085271000119102 into its label in the first
    # live session.
    width = max(len(str(c["code"])) for c in cands[:MENU_ROWS])
    for n, c in enumerate(cands[:MENU_ROWS], 1):
        print(f"   {n}  {str(c['code']):<{width}} {c.get('label') or c.get('fsn') or ''}")


# --- oracle ------------------------------------------------------------------


def oracle_main(a, man, queue, out_path) -> int:
    test_ids = set(
        corpus_mod.read_split(man["corpus"]["splits_dir"], "test")
    )
    touched = sorted({r.doc_id for r in queue} & test_ids)
    if touched:
        raise SystemExit(
            f"--oracle refuses test-split documents ({touched[:3]}…): Phase F "
            "runs test ONCE, and a gold-derived desk would put the answer key "
            "inside that run."
        )
    docs = corpus_mod.load_corpus(man["corpus"]["cadec_root"])
    golds = [m for d in sorted({r.doc_id for r in queue}) for m in docs[d].mentions]
    rows = r6.oracle_resolutions(queue, golds)
    with out_path.open("a", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    by = {}
    for row in rows:
        by[row["decision"]] = by.get(row["decision"], 0) + 1
    print(f"{WARN}{BOLD}ORACLE CEILING{END}{WARN} — these resolutions come from "
          f"the gold annotations, not a person. They bound what a perfect "
          f"reviewer could recover from this queue and measure NOTHING about "
          f"human work. Label every number derived from them.{END}")
    print(f"\n  {len(rows)} resolutions  " +
          "  ".join(f"{k}={v}" for k, v in sorted(by.items())))
    print(f"  written to {out_path}")
    return 0


# --- the desk ----------------------------------------------------------------


def decide(rec, shown, search, reg) -> tuple[str, str | None, str | None, int]:
    """One record's decision loop: (decision, sct, label, searches)."""
    searches = 0
    while True:
        # A dead or closed stdin (non-interactive panel, Ctrl+D) reads as a
        # clean quit — the appended file resumes — never as a traceback. The
        # first real session hit exactly this: EOFError at the first prompt,
        # a created-but-empty resolutions file, and no saved work to resume.
        try:
            ans = input(f"\n  {BOLD}>{END} ").strip()
        except EOFError:
            print(f"\n  {WARN}stdin closed — this desk needs an interactive "
                  f"terminal. Quitting cleanly; the file resumes.{END}")
            return "quit", None, None, searches
        if ans.startswith("/"):
            term = ans[1:].strip()
            if not term:
                continue
            searches += 1
            found = search(term, MENU_ROWS)
            if found:
                shown = found
                print_menu(found, f"'{term}' — pick a number, or search again")
            else:
                print(f"  {WARN}nothing for '{term}'{END}")
            continue
        low = ans.lower()
        if low == "w":
            code = (rec.checks.get("withheld") or {}).get("sct")
            if not code:
                print(f"  {WARN}this record has no withheld answer{END}")
                continue
            return "code", str(code), reg.preferred(str(code)), searches
        if low == "c":
            return "concept_less", None, None, searches
        if low == "u":
            return "uphold", None, None, searches
        if low == "s":
            return "skip", None, None, searches
        if low == "q":
            return "quit", None, None, searches
        if ans.isdigit() and shown and 1 <= int(ans) <= len(shown[:MENU_ROWS]):
            c = shown[int(ans) - 1]
            return "code", str(c["code"]), c.get("label") or c.get("fsn"), searches
        if ans.isdigit() and len(ans) >= 6:
            label = reg.preferred(ans)
            if label is None:
                print(f"  {WARN}{ans} is not in the vocabulary — 'y' to file it "
                      f"anyway, anything else to go back{END}")
                try:
                    confirm = input(f"  {BOLD}>{END} ").strip().lower()
                except EOFError:
                    return "quit", None, None, searches
                if confirm != "y":
                    continue
            else:
                print(f"  {ans} = {label}")
            return "code", ans, label, searches
        print(f"  {DIM}{HELP}{END}")


def desk_main(a, man, queue, out_path) -> int:
    reg = Registry(man["vocabulary"]["snomed_db"])
    docs = corpus_mod.load_corpus(man["corpus"]["cadec_root"])
    sources = {d: docs[d].text for d in {r.doc_id for r in queue}}
    search, retriever = r0._retriever({**man["rungs"]["0"], "registry": reg})
    reviewer = a.reviewer or getpass.getuser()

    done = resume_keys(out_path)
    todo = [r for r in queue if r6._span_key(r.doc_id, r.spans) not in done]
    if a.limit:
        todo = todo[: a.limit]
    print(f"\n{BOLD}rung 6 desk{END} — {len(todo)} of {len(queue)} queued records"
          f" ({len(done)} already resolved in {out_path.name})")
    print(f"{DIM}search runs through the run's retriever ({retriever}); the "
          f"timer covers the searching. {HELP}{END}")

    results = []
    with out_path.open("a", encoding="utf-8") as fh:
        for i, rec in enumerate(todo, 1):
            source = sources.get(rec.doc_id, "")
            code = (rec.checks.get("withheld") or {}).get("sct")
            wh_label = reg.preferred(str(code)) if code else None
            cands = rec.checks.get("candidates") or []
            show(i, len(todo), rec, source, wh_label, cands)
            t0 = time.perf_counter()
            decision, sct, label, searches = decide(rec, cands, search, reg)
            if decision == "quit":
                print(f"{DIM}stopped — the file resumes where you left off{END}")
                break
            secs = round(time.perf_counter() - t0, 1)
            row = r6.resolution_row(
                rec, decision, sct=sct, label=label, seconds=secs,
                searches=searches, reviewer=reviewer,
            )
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
            fh.flush()
            results.append((decision, secs, searches))
            shown = f" {sct}  {label or ''}" if sct else ""
            print(f"  {OK}{decision}{shown} · {secs:.0f}s · {searches} "
                  f"search{'' if searches == 1 else 'es'}{END}")

    if results:
        secs = [s for _, s, _ in results]
        by = {}
        for d, _, _ in results:
            by[d] = by.get(d, 0) + 1
        print(f"\n  {len(results)} reviewed  "
              + "  ".join(f"{k}={v}" for k, v in sorted(by.items())))
        print(f"  median {statistics.median(secs):.0f}s · total "
              f"{sum(secs) / 60:.1f} min · written to {out_path}")
        print(f"{DIM}apply with rungs.6 mode='desk', resolutions="
              f"'{out_path}'{END}")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("records", help="a run's records.jsonl (the desk queues its ABSTAIN residue)")
    ap.add_argument("--manifest", default="manifest.json")
    ap.add_argument("--out", help="resolutions file (default: beside the records)")
    ap.add_argument("--oracle", action="store_true",
                    help="write gold-derived resolutions — AN ORACLE CEILING, "
                         "labeled as such; refused on test-split documents")
    ap.add_argument("--limit", type=int, default=0, help="review at most N records")
    ap.add_argument("--reviewer", help="name recorded on each row (default: $USER)")
    a = ap.parse_args(argv)

    man = load_manifest(a.manifest)
    queue = load_queue(a.records)
    if not queue:
        print("no abstained records in this file — the queue is empty.")
        return 0
    out_path = pathlib.Path(a.out) if a.out else default_out(a.records, a.oracle)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if a.oracle:
        return oracle_main(a, man, queue, out_path)
    return desk_main(a, man, queue, out_path)


if __name__ == "__main__":
    raise SystemExit(main())

"""ladder_run.py — the full ladder in specified order [0, 1, 2, 3, 4, 5, 6].

Every rung so far has been measured standalone. This is the first script that
runs them in the order the manifest specifies, which is the only way to see
whether the rungs interact. Per-rung numbers all assume they do not.

Rung 1 runs in OBSERVE mode: it records a verdict and never moves the zone.
Rung 5 pays the coverage cost, last, per docs/wiki/content/r2.md.

    LADDER_N=0 PYTHONPATH=. python3 scripts/ladder_run.py
"""
import json, os, pathlib, collections, inspect, time

from ladder.registry import Registry
from ladder.rungs.r0 import run
from ladder.rungs import r1, r2, r3, r4, r5
from ladder.ledger import Ledger
from ladder.run import check_snomed_backend, ledger_for
import argparse, contextlib, io, sys, select, shutil
from ladder import stub_llm as S

ORDER = [0, 1, 2, 3, 4, 5, 6]

man = json.loads(pathlib.Path("manifest.json").read_text())
check_snomed_backend(man)   # same blind spot as _vocab_for's, same check
reg = Registry(man["vocabulary"]["snomed_db"])
items = S.load_items(man["corpus"]["splits_dir"])
src = {i["doc_id"]: i["text"] for i in items}

# The signature banner moved BELOW say()'s definition. It was called at import
# time, above it, so this script raised NameError before doing anything at all
# — every run, on every machine, since the --tui commit introduced say(). It
# survived because nothing imported the module; tests/test_scripts_import.py
# now does.
#
# The pairing was also stale. Rung IDs were renumbered 2026-08-23 (old->new:
# 3->2, 5->3, 2->5) and the MODULES were renamed with them, so r2.py is
# self-correction and r3.py is voting. The line still read
# (("r2", r3), ("r4", r4), ("r3", r5), ("r5", r2)) and printed each module's
# signature under a different rung's name — wrong only in the output, which is
# the hardest place to notice it. 9849c31 fixed the body and missed this.


def banner():
    say("rung order:", ORDER)
    for name, mod in (("r2", r2), ("r3", r3), ("r4", r4), ("r5", r5)):
        say(f"  {name}.apply{inspect.signature(mod.apply)}")
    say()


def call(mod, name, records, cfg):
    """Call rungN.apply, surfacing the real signature if it differs."""
    try:
        out = mod.apply(records, src, cfg)
    except TypeError as e:
        raise SystemExit(
            f"{name}.apply signature mismatch: {e}\n"
            f"  actual: {name}.apply{inspect.signature(mod.apply)}"
        )
    if isinstance(out, tuple):
        return out
    return out, None


def observe(records, label):
    """Rung 1 in observe mode: record the verdict, never move the zone."""
    for rec in records:
        v, why, audit = r1.zone(rec, src.get(rec.doc_id, ""), reg, {"registry": reg})
        rec.checks["r1_verdict"] = v
        rec.checks["r1_reason"] = why
        rec.checks["r1_audit"] = audit
    c = collections.Counter(r.checks["r1_verdict"] for r in records)
    print(f"  r1 observe [{label}]: {dict(c)}")
    return records


def say(*a, **kw):
    """Section banners and inline counts. Silent under --tui, where the table
    carries the same information and a scrolling print would fight the Live
    display for the terminal."""
    if MON is None:
        print(*a, **kw)


def codes(records):
    return sum(1 for r in records if r.sct)


_ap = argparse.ArgumentParser()
_ap.add_argument("--tui", action="store_true",
                 help="live terminal monitor instead of scrolling reports")
_ap.add_argument("--plain", action="store_true", help="explicit default")
_args, _ = _ap.parse_known_args()

MON = None
if _args.tui:
    sys.path.insert(0, str(pathlib.Path(__file__).parent))
    from ladder_top import Monitor
    MON = Monitor("runs/ladder.ledger.jsonl", provenance={
        "split": man["corpus"].get("splits_dir", "dev"),
        "extractor": man.get("model", {}).get("extractor", "?"),
        "judge": man.get("model", {}).get("judge", "?"),
        "order": ",".join(str(r) for r in ORDER),
    }).start()


def emit(rung, fn, *a):
    """Print a rung's report, or capture it for the monitor.

    Captured text is also appended to runs/<run-id>.report.txt — a report that
    exists only inside a terminal frame is a report that is lost.
    """
    if MON is None:
        fn(*a)
        return
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        fn(*a)
    text = buf.getvalue()
    MON.add_report(rung, text)
    with open(f"runs/{RUN_ID}.report.txt", "a", encoding="utf-8") as fh:
        fh.write(text + "\n")


RUN_ID = f"ladder-{int(time.time())}"
# Through ledger_for, not Ledger: ladder/otel.py names THIS script as the way
# to switch tracing on (`LADDER_OTEL=1 ... scripts/ladder_run.py`) and nothing
# imported it, so the documented command emitted no spans. Off, this is the
# same plain Ledger it always was.
LEDGER = ledger_for("runs/ladder.ledger.jsonl", run_id=RUN_ID, man=man,
                    split=os.environ.get("LADDER_SPLIT", "dev"),
                    order=ORDER, registry=reg)

t_start = time.perf_counter()

# ---- 0 -----------------------------------------------------------------
banner()
say("=" * 58, "\nRUNG 0 — extract\n", "=" * 58, sep="")
recs, m0 = run(items, "A", S.stub, {"registry": reg, "ledger": LEDGER, "rung0_offsets": "search"})
say(f"  mentions {len(recs)}   carrying a code {codes(recs)}")

# ---- 1 (observe) -------------------------------------------------------
say("\n" + "=" * 58, "\nRUNG 1 — validate (observe)\n", "=" * 58, sep="")
observe(recs, "after r0")

# ---- 2 -----------------------------------------------------------------
say("\n" + "=" * 58, "\nRUNG 2 — self-correction\n", "=" * 58, sep="")
recs, m2 = call(r2, "r2", recs, {"registry": reg, "ledger": LEDGER, "llm": S.stub})
if m2 and hasattr(r2, "report"):
    emit(2, r2.report, m2)
observe(recs, "after r2")
say(f"  carrying a code {codes(recs)}")

# ---- 3 -----------------------------------------------------------------
say("\n" + "=" * 58, "\nRUNG 3 — voting\n", "=" * 58, sep="")
recs, m3 = call(r3, "r3", recs, {"registry": reg, "ledger": LEDGER, "llm": S.voter(0.7), "k": 3})
if m3:
    emit(3, r3.report, m3)
observe(recs, "after r3")
say(f"  carrying a code {codes(recs)}")

# ---- 4 -----------------------------------------------------------------
say("\n" + "=" * 58, "\nRUNG 4 — judge\n", "=" * 58, sep="")
recs, m4 = call(r4, "r4", recs, {"registry": reg, "ledger": LEDGER,
                                 "judge_llm": S.judge("llama3.2:3b"),
                                 "extractor_model": S.MODEL,
                                 "judge_model": "llama3.2:3b"})
if m4:
    emit(4, r4.report, m4)

# ---- 5 (last) ----------------------------------------------------------
say("\n" + "=" * 58, "\nRUNG 5 — abstention\n", "=" * 58, sep="")
recs, _ = call(r5, "r5", recs, {"registry": reg, "ledger": LEDGER})
say("  zones:", dict(collections.Counter(r.zone for r in recs)))
say("  reasons:", dict(collections.Counter(r.reason for r in recs).most_common(8)))
withheld = sum(1 for r in recs if "withheld" in r.checks)
say(f"  withheld {withheld} of {len(recs)}   still carrying a code {codes(recs)}")

# ---- 6 -----------------------------------------------------------------
say("\n" + "=" * 58, "\nRUNG 6 — triage desk\n", "=" * 58, sep="")
say(f"  NOT BUILT. Would receive {withheld} withheld records.")
say("  Blocked upstream, not unfinished: rung 0 produced 0 correct codes,")
say("  so every record reaching a reviewer carries a wrong answer or none.")

# ---- summary -----------------------------------------------------------
say("\n" + "=" * 58, "\nEND TO END\n", "=" * 58, sep="")
say(f"  order {ORDER}")
say(f"  records {len(recs)}   published {codes(recs)}   withheld {withheld}")
say(f"  coverage {codes(recs) / len(recs):.3f}")
def offer_r6(withheld: int) -> None:
    """Offer the rung 6 desk, with a timeout so an unattended run never blocks.

    Asked here rather than at the start: at the start the answer is given 77
    minutes before it matters. Without the timeout, a run left alone overnight
    waits forever on input that never comes.
    """
    cmd = "PYTHONPATH=. python3 scripts/r6_desk.py"
    if not sys.stdin.isatty():
        print(f"\n  rung 6 queue ready — {withheld} withheld records")
        print(f"  review:  {cmd}")
        return
    print(f"\n  rung 6 — {withheld} records withheld and reviewable.")
    print("  The desk is a blind, timed study; it is not part of the run.")
    print("  Open it now? [y/N]  (20s, defaults to no) ", end="", flush=True)
    ready, _, _ = select.select([sys.stdin], [], [], 20)
    ans = sys.stdin.readline().strip().lower() if ready else ""
    print()
    if ans.startswith("y"):
        import subprocess
        subprocess.run([sys.executable, "scripts/r6_desk.py"])
    else:
        print(f"  skipped. Review later with:  {cmd}")


LEDGER.close()
if MON:
    MON.stop()
    print(f"\nreports written to runs/{RUN_ID}.report.txt")
offer_r6(withheld)
from ladder import provenance as _prov
_stamp = _prov.gather(
    man, n_docs=len(items), vocab=reg, rung_order=ORDER,
    entry_point="scripts/ladder_run.py", run_id=RUN_ID,
    models_spec={"extractor": (man.get("model", {}).get("extractor"), S.MODEL),
                 "judge": (man.get("model", {}).get("judge"), "llama3.2:3b")},
    extra={"records": len(recs), "withheld": withheld})
_prov.write(f"runs/{RUN_ID}.json", _stamp)
for _w in _prov.warnings(_stamp):
    print(f"  WARNING  {_w}")
print(f"  provenance  runs/{RUN_ID}.json")

say(f"  wall clock {time.perf_counter() - t_start:.1f}s")
say("\n  Compare against the standalone runs. Any difference is rung")
say("  interaction, which every per-rung figure so far assumes is zero.")

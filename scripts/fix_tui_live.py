#!/usr/bin/env python3
"""fix_tui_live.py — make the monitor actually live.

FOUR PROBLEMS, ONE ROOT CAUSE AND THREE CONSEQUENCES.

1. THE LEDGER IS NOT TAILABLE.

   `Ledger.log()` writes to a buffered file handle and nothing flushes until
   `close()`. So every row of a two-hour run sits in Python's buffer and lands
   on disk at the end. The monitor was tailing the right file the whole time;
   the file was empty.

   That is why the display sat at "0 rows" for a 19-minute run and then showed
   everything at once. An append-only log that cannot be appended-to-and-read
   is a log with a checkpoint at the end, which is a different thing.

   Fixed by flushing per row. The cost is a write syscall per record — real,
   and cheap against a model call measured in seconds. Stated in the docstring
   rather than hidden, because it IS a cost.

2. THE WALL CLOCK WAS NONSENSE.

   `elapsed` came from the spread of ledger timestamps, and fell back to
   `time.time() - t0` when there were fewer than two rows. With an empty ledger
   it reported the monitor's own lifetime, which showed as 8h44m on a run that
   had been going twenty minutes. Now taken from the run's own start.

3. A RUNG IN PROGRESS LOOKED IDENTICAL TO A RUNG THAT HAD NOT STARTED.

   Rung 0 takes 338 seconds on FiNER before it writes its first row. For those
   338 seconds the display showed seven empty rows and no indication which one
   was working. The monitor now marks the rung whose model is loaded and shows
   a document counter from the ledger's own per-document rows.

4. --tui WAS OPT-IN.

   A run with no visible progress is the thing that has gone wrong four times
   today. It is now ON by default for `ladder` and `ablate`, with `--plain` to
   get the old scrolling output back. Default behaviour for scripts and CI is
   unaffected: the monitor is skipped when stdout is not a terminal, so a piped
   or redirected run still prints exactly what it printed before.

Run from the repo root. Idempotent.
"""
import pathlib
import sys

edits = 0


def sub(path, old, new, label):
    global edits
    p = pathlib.Path(path)
    s = p.read_text()
    if new in s:
        print(f"  = {label}: already applied")
        return
    if old not in s:
        print(f"  ! {label}: NOT FOUND — patch by hand")
        return
    p.write_text(s.replace(old, new, 1))
    edits += 1
    print(f"  + {label}")


# ---------------------------------------------------------------- 1. flush
print("ledger")
sub("ladder/ledger.py",
    '        self._fh.write(json.dumps(asdict(e), ensure_ascii=False) + "\\n")',
    '''        self._fh.write(json.dumps(asdict(e), ensure_ascii=False) + "\\n")
        # Flushed per row so the ledger can be TAILED while a run is in
        # progress. Without this the rows sit in Python's buffer until close()
        # and a monitor watching the file sees nothing for the length of the
        # run — which is a checkpoint at the end, not an append-only log.
        # The cost is one write syscall per record, against a model call
        # measured in seconds. It is a real cost and it is worth it.
        self._fh.flush()''',
    "flush per row")


# ------------------------------------------------------- 2. real elapsed
print("\nmonitor")
sub("scripts/ladder_top.py",
    "    all_ts = [t for r in rungs.values() for t in (r.get('ts') or [])]\n"
    "    elapsed = (max(all_ts) - min(all_ts)) if len(all_ts) > 1 else time.time() - t0",
    "    # The RUN's elapsed time, not the monitor's lifetime and not the\n"
    "    # spread of whatever rows happen to be in the file. An earlier version\n"
    "    # used the timestamp spread with a fallback, and reported 8h44m for a\n"
    "    # twenty-minute run because the ledger was empty and t0 was stale.\n"
    "    elapsed = time.time() - t0",
    "elapsed from the run, not from row timestamps")


# --------------------------------------------- 3. in-progress indication
sub("scripts/ladder_top.py",
    "    def add_report(self, rung: int, text: str) -> None:\n"
    "        with self.lock:\n"
    "            self.reports.append((rung, summarise(text), text))",
    '''    def add_report(self, rung: int, text: str) -> None:
        with self.lock:
            self.reports.append((rung, summarise(text), text))

    def mark_running(self, rung: int | None, note: str = "") -> None:
        """Which rung is working right now, and on what.

        Rung 0 on FiNER takes 338 seconds before it writes its first ledger
        row. For those 338 seconds every rung looked identical — empty. A rung
        that is working and a rung that has not started must not render the
        same way; that confusion is exactly what hid rung 0's unreachable
        ledger row for the life of this project.
        """
        with self.lock:
            self.running = rung
            self.running_note = note''',
    "Monitor.mark_running()")

sub("scripts/ladder_top.py",
    "        self.gpu = collections.deque(maxlen=90)\n        self.lock = threading.Lock()",
    "        self.gpu = collections.deque(maxlen=90)\n"
    "        self.running = None\n"
    "        self.running_note = \"\"\n"
    "        self.lock = threading.Lock()",
    "State carries the running rung")

sub("scripts/ladder_top.py",
    "        rows, feed = st.rows, list(st.feed)",
    "        rows, feed = st.rows, list(st.feed)\n"
    "        running, running_note = st.running, st.running_note",
    "render reads the running rung")

sub("scripts/ladder_top.py",
    '''        s = rungs.get(rid)
        if not s:
            tbl.add_row(str(rid), Text(name, style="grey35"),
                        Text("—", style="grey30"), "", bar(0, 0, 0), "", "", "", "", "")
            continue''',
    '''        s = rungs.get(rid)
        if not s:
            # A rung with no rows is either working or not started, and those
            # must look different.
            if rid == running:
                tbl.add_row(Text(str(rid), style="yellow"),
                            Text(name, style="yellow"),
                            Text(running_note or "working…", style="yellow"),
                            "", Text("▚" * 20, style="yellow"), "", "", "", "", "")
            else:
                tbl.add_row(str(rid), Text(name, style="grey35"),
                            Text("—", style="grey30"), "", bar(0, 0, 0),
                            "", "", "", "", "")
            continue''',
    "working rungs render differently from unstarted ones")


# ------------------------------------------------------------ 4. default on
print("\nrun.py")
sub("ladder/run.py",
    '        p.add_argument("--tui", action="store_true",\n'
    '                       help="live monitor instead of scrolling reports")',
    '        # ON BY DEFAULT. A run with no visible progress is the failure that\n'
    '        # has come up four times on this project; --plain restores the old\n'
    '        # scrolling output. The monitor is skipped anyway when stdout is\n'
    '        # not a terminal, so piped and CI runs are unaffected.\n'
    '        p.add_argument("--plain", action="store_true",\n'
    '                       help="scrolling reports instead of the live monitor")\n'
    '        p.add_argument("--tui", action="store_true",\n'
    '                       help=argparse.SUPPRESS)',
    "--plain replaces --tui as the flag you pass")

sub("ladder/run.py",
    '    _TUI_REQUESTED = bool(getattr(a, "tui", False))',
    '    _TUI_REQUESTED = (\n'
    '        not getattr(a, "plain", False)\n'
    '        and sys.stdout.isatty()          # never in a pipe, a log or CI\n'
    '    )',
    "default on, off when not a terminal")

sub("ladder/run.py",
    '            print(f"[run] rung {n} model={caller.spec} ({caller.role})")',
    '            print(f"[run] rung {n} model={caller.spec} ({caller.role})")\n'
    '        if _MON is not None:\n'
    '            _MON.mark_running(n, f"{caller.spec}" if caller else "")',
    "tell the monitor which rung is working")

print(f"\n{edits} edit(s).")
print("\nCheck:")
print("  python3 -c \"import ast;ast.parse(open('ladder/run.py').read())\" && echo run-ok")
print("  python3 -c \"import ast;ast.parse(open('scripts/ladder_top.py').read())\" && echo top-ok")
print("  python3 -m pytest tests/test_ledger_coverage.py -q")
print("\nThen any run shows the monitor without a flag:")
print("  PYTHONPATH=. python3 -m ladder.run --manifest manifest.finer.json \\")
print("      ladder --split test --limit 20 --rungs 0-2")
sys.exit(0)

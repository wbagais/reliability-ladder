#!/usr/bin/env python3
"""ladder_top.py — watch a ladder run, in the terminal.

Tails the append-only ledger and redraws in place. Same data source as
docs/ladder-monitor.html, so the two views cannot disagree.

    pip install rich --break-system-packages

    python3 scripts/ladder_top.py                    # follow the default ledger
    python3 scripts/ladder_top.py --once             # render a finished run
    LADDER_N=0 PYTHONPATH=. python3 scripts/ladder_run.py --tui   # in-process

WHAT IT SHOWS

  Rungs    one row each, drawn over the denominator THE LEDGER NAMES, never
           over the run total. A rung using two denominators shows both: rungs
           0 and 3 pay a per-document cost and a per-record cost, and fusing
           them overstates the per-record price.

  ▚        could_not_run. A third state, dim rather than coloured, because it
           is the absence of a measurement and must not read as one.

  Watch    live checks derived from this project's own findings. Every one is
           a mistake that was made here and caught late.

  Reports  each rung's report(), collapsed to one line once read, most recent
           expanded. Nothing is discarded.

  Compute  GPU clock against temperature. The end-to-end run was 2-4x slower
           than the same rungs run separately at identical token counts;
           thermal throttling is the hypothesis and this is what confirms it.
"""
from __future__ import annotations

import argparse
import collections
import json
import pathlib
import re
import shutil
import subprocess
import sys
import threading
import time

try:
    from rich.console import Console, Group
    from rich.live import Live
    from rich.table import Table
    from rich.text import Text
    from rich.rule import Rule
except ImportError:
    sys.exit("needs rich:  pip install rich --break-system-packages")

DEFAULT_LEDGER = "runs/ladder.ledger.jsonl"
WEB_URL = "http://localhost:8000/docs/ladder-monitor.html"

RUNGS = [
    (0, "extract",      "model"),
    (1, "validate",     "deterministic"),
    (2, "self-correct", "model"),
    (3, "vote",         "model"),
    (4, "judge",        "model"),
    (5, "abstain",      "deterministic"),
    (6, "triage",       "human"),
]

PASS, FAIL, CNR, WARN = "green", "dark_orange3", "grey42", "yellow"

RUNG_NAME = {r: (n, k) for r, n, k in RUNGS}


def visible_rungs(rungs: dict) -> list[tuple[int, str, str]]:
    """Which rungs to draw.

    Nothing yet: all seven, greyed — a rung that produced nothing and a rung
    that never ran must not look identical. That confusion is what hid rung 0's
    unreachable ledger row for the life of the project.

    Rows present: everything from the lowest to the highest seen, so a GAP IN
    THE MIDDLE stays visible (rung 3 ran, rung 2 did not — worth knowing).
    Trailing absence is not shown: a single-rung run should not draw four empty
    rows below itself.
    """
    seen = sorted(rungs)
    if not seen:
        return list(RUNGS)
    lo, hi = seen[0], seen[-1]
    return [(r, *RUNG_NAME.get(r, (f"rung {r}", "?"))) for r in range(lo, hi + 1)]

# Thresholds for the Watch panel. Each is a real failure from this project.
MINORITY_FLOOR = 0.10     # rung 4's guard fired only on a SINGLE value; two
                          # BAND records out of 96 slipped past and a
                          # meaningless 98% agreement printed.
CNR_CEILING = 0.25        # rung 4 lost 43% to parse failures, rung 3 lost 98%.


class State:
    def __init__(self) -> None:
        self.rung: dict[int, dict] = {}
        self.rows = 0
        self.feed = collections.deque(maxlen=6)
        self.run_id = None
        self.t0 = time.time()
        self.last_row_at = None
        self.reports: list[tuple[int, str, str]] = []
        self.gpu = collections.deque(maxlen=90)
        self.lock = threading.Lock()

    def _slot(self, r: int) -> dict:
        if r not in self.rung:
            self.rung[r] = {"pass": 0, "fail": 0, "could_not_run": 0, "unset": 0,
                            "denoms": collections.Counter(),
                            "verdicts": collections.Counter(),
                            "tok": 0, "calls": 0, "lat": [], "ts": []}
        return self.rung[r]

    def ingest(self, row: dict) -> None:
        r = row.get("rung")
        if r is None:
            return
        extra = row.get("extra") or {}
        with self.lock:
            s = self._slot(r)
            ev = extra.get("evaluable", "unset")
            s[ev] = s.get(ev, 0) + 1
            if extra.get("denominator"):
                s["denoms"][extra["denominator"]] += 1
            if row.get("verdict"):
                s["verdicts"][row["verdict"]] += 1
            s["tok"] += (row.get("tokens_in") or 0) + (row.get("tokens_out") or 0)
            s["calls"] += row.get("api_calls") or 0
            if row.get("latency_ms"):
                s["lat"].append(row["latency_ms"])
            # Row timestamps drive throughput and ETA. Kept separate from
            # latency: one is when the work finished, the other is how long it
            # took, and a rung can be slow without being infrequent.
            s["ts"].append(row.get("ts") or time.time())
            self.rows += 1
            self.run_id = row.get("run_id") or self.run_id
            self.last_row_at = time.time()
            self.feed.appendleft((r, row.get("record_id", "—"),
                                  row.get("outcome", "—"), ev))

    def add_report(self, rung: int, text: str) -> None:
        with self.lock:
            self.reports.append((rung, summarise(text), text))

    @staticmethod
    def p95(v: list[float]) -> float:
        if not v:
            return 0.0
        s = sorted(v)
        return s[min(len(s) - 1, int(round(0.95 * (len(s) - 1))))]


def summarise(text: str) -> str:
    """One line of numbers from a rung's report.

    Collapsed, the counts are what is worth keeping; the explanatory prose is
    written to be read once. Pulls `label  number` pairs and drops the rest.
    """
    bits = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("=") or line.startswith("NOTE"):
            continue
        m = re.match(r"^([a-zA-Z][\w \-/']{2,34}?)\s{2,}(\d[\d,]*)", line)
        if m:
            bits.append(f"{m.group(1).strip()} {m.group(2)}")
        if len(bits) >= 4:
            break
    if bits:
        return " · ".join(bits)
    first = next((l.strip() for l in text.splitlines() if l.strip()), "")
    return first[:70] or "—"


def watch_items(st: State) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for rid, name, _ in visible_rungs(st.rung):
        s = st.rung.get(rid)
        if not s:
            continue
        n = s["pass"] + s["fail"] + s["could_not_run"] + s["unset"]
        if not n:
            continue

        # A verdict distribution with a tiny minority class. Agreement against a
        # near-constant measures the set's composition, not the checker.
        v = s["verdicts"]
        if len(v) >= 2:
            share = min(v.values()) / sum(v.values())
            if share < MINORITY_FLOOR:
                out.append((f"rung {rid}",
                            f"minority verdict class {min(v.values())}/{sum(v.values())} "
                            f"({share:.0%}) — agreement over this set measures its "
                            "composition, not the checker"))
        elif len(v) == 1:
            out.append((f"rung {rid}",
                        f"single verdict {list(v)[0]} across {sum(v.values())} records "
                        "— comparison against this set is guaranteed"))

        # Heavy could_not_run: every rate below is over the remainder, and the
        # remainder is not a random subsample.
        c = s["could_not_run"] / n
        if c > CNR_CEILING:
            out.append((f"rung {rid}",
                        f"{s['could_not_run']}/{n} ({c:.0%}) could not run — rates are "
                        "over the remainder, which is not a random subsample"))

        if s["unset"] or not s["denoms"]:
            out.append((f"rung {rid}",
                        "rows with no denominator — a rate cannot be attributed"))

    return out or [("", "nothing flagged")]


_HAS_SMI = shutil.which("nvidia-smi") is not None


def poll_gpu() -> tuple[float, float, float] | None:
    if not _HAS_SMI:
        return None
    try:
        out = subprocess.run(
            ["nvidia-smi",
             "--query-gpu=temperature.gpu,clocks.current.graphics,utilization.gpu",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=2).stdout.strip().splitlines()[0]
        t, c, u = (float(x) for x in out.split(","))
        return t, c, u
    except Exception:
        return None


SPARK = "▁▂▃▄▅▆▇█"


def spark(vals: list[float]) -> str:
    if not vals:
        return ""
    lo, hi = min(vals), max(vals)
    if hi - lo < 1e-9:
        return SPARK[3] * len(vals)
    return "".join(SPARK[min(7, int((v - lo) / (hi - lo) * 7.99))] for v in vals)



def _median(v: list[float]) -> float:
    if not v:
        return 0.0
    s = sorted(v)
    n = len(s)
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2


def _drift(lat: list[float]) -> tuple[float, float, float] | None:
    """Mean of the first quarter against the last quarter of a rung's records.

    Same rung, same run, same work — so a rise is the machine, not the task.
    Needs enough records for the quarters to mean anything; below 12 the
    comparison is noise and this returns None rather than a number that looks
    like a measurement.
    """
    if len(lat) < 12:
        return None
    if _median(lat) < 10:      # sub-10ms: deterministic, drift is noise
        return None
    q = max(3, len(lat) // 4)
    a = sum(lat[:q]) / q
    b = sum(lat[-q:]) / q
    if a <= 0:
        return None
    return a, b, (b - a) / a


def _rate(ts: list[float], window: float = 60.0) -> float:
    """Records per minute over a trailing window."""
    if len(ts) < 2:
        return 0.0
    now = ts[-1]
    recent = [t for t in ts if now - t <= window]
    if len(recent) < 2:
        return 0.0
    span = recent[-1] - recent[0]
    return (len(recent) / span * 60.0) if span > 0.5 else 0.0


def _hhmm(sec: float) -> str:
    if sec <= 0 or sec != sec or sec > 86400:
        return "—"
    m, s = divmod(int(sec), 60)
    return f"{m}m{s:02d}s" if m < 60 else f"{m // 60}h{m % 60:02d}m"


def time_panel(rungs: dict, t0: float) -> Table:
    """Distribution, throughput, ETA and drift. One row per rung that has run."""
    t = Table(box=None, pad_edge=False, expand=True)
    t.add_column("", width=2, style="grey50")
    t.add_column("rung", width=13)
    t.add_column("latency over the run", width=22)
    t.add_column("med", width=8, justify="right")
    t.add_column("p95", width=8, justify="right")
    t.add_column("rec/min", width=8, justify="right")
    t.add_column("eta", width=8, justify="right")
    t.add_column("drift", width=26)

    for rid, name, _ in RUNGS:
        s = rungs.get(rid)
        if not s or not s["lat"]:
            continue
        lat = s["lat"]
        ts = s.get("ts") or []
        med, p95 = _median(lat), State.p95(lat)

        # Downsample so the sparkline is a shape, not a smear.
        step = max(1, len(lat) // 22)
        shape = spark(lat[::step][-22:])

        rate = _rate(ts)
        n_done = len(lat)
        n_target = max(s["denoms"].values()) if s["denoms"] else 0
        eta = "—"
        if rate > 0 and n_target > n_done:
            eta = _hhmm((n_target - n_done) / rate * 60.0)

        d = _drift(lat)
        if d is None:
            drift = Text("—", style="grey35")
        else:
            a, b, pct = d
            # A rise with flat tokens is the machine. Flag it; do not explain
            # it here — the cause is a separate measurement.
            style = WARN if pct > 0.25 else ("grey62" if pct > -0.25 else PASS)
            drift = Text(f"{a/1000:.2f}s → {b/1000:.2f}s  {pct:+.0%}", style=style)

        t.add_row(str(rid), Text(name), Text(shape, style="grey62"),
                  f"{med/1000:.2f}s", f"{p95/1000:.2f}s",
                  f"{rate:.0f}" if rate else "—", eta, drift)
    return t

def bar(p: int, f: int, c: int, width: int = 20) -> Text:
    total = p + f + c
    t = Text()
    if not total:
        t.append("·" * width, style="grey30")
        return t
    wp, wf = round(p / total * width), round(f / total * width)
    wc = max(0, width - wp - wf)
    t.append("█" * wp, style=PASS)
    t.append("█" * wf, style=FAIL)
    t.append("▚" * wc, style=CNR)
    return t


def render(st: State, path: pathlib.Path, provenance: dict | None = None) -> Group:
    with st.lock:
        rungs = {k: dict(v, denoms=dict(v["denoms"]),
                         verdicts=dict(v["verdicts"]), lat=list(v["lat"]),
                         ts=list(v.get("ts") or []))
                 for k, v in st.rung.items()}
        rows, feed = st.rows, list(st.feed)
        reports, gpu = list(st.reports), list(st.gpu)
        last_row_at, t0 = st.last_row_at, st.t0

    all_ts = [t for r in rungs.values() for t in (r.get('ts') or [])]
    elapsed = (max(all_ts) - min(all_ts)) if len(all_ts) > 1 else time.time() - t0
    age = ""
    if last_row_at:
        d = time.time() - last_row_at
        age = " · live" if d < 4 else f" · idle {d:.0f}s"
    head = Text.assemble(
        ("ladder", "bold"), ("  ", ""), (str(path), "grey50"), ("  ", ""),
        (f"{rows} rows", "grey70"),
        (f" · {int(elapsed // 60)}m{int(elapsed % 60):02d}s", "grey50"),
        (age, "green" if "live" in age else "grey50"))
    prov = (Text(" · ".join(f"{k} {v}" for k, v in provenance.items()), style="grey42")
            if provenance else None)

    tbl = Table(box=None, pad_edge=False, expand=True)
    tbl.add_column("", width=2, style="grey50")
    tbl.add_column("rung", width=13)
    tbl.add_column("denominator", width=26, style="cyan")
    tbl.add_column("n", width=5, justify="right")
    tbl.add_column("", width=20)
    tbl.add_column("ok", width=5, justify="right", style=PASS)
    tbl.add_column("fail", width=5, justify="right", style=FAIL)
    tbl.add_column("can't", width=6, justify="right", style=CNR)
    tbl.add_column("tokens", width=9, justify="right")
    tbl.add_column("p95", width=7, justify="right")

    tot_tok, worst = 0, 0.0
    for rid, name, kind in visible_rungs(rungs):
        s = rungs.get(rid)
        if not s:
            tbl.add_row(str(rid), Text(name, style="grey35"),
                        Text("—", style="grey30"), "", bar(0, 0, 0), "", "", "", "", "")
            continue
        p, f, c = s["pass"], s["fail"], s["could_not_run"]
        n = p + f + c + s["unset"]
        dn = " ".join(sorted(s["denoms"])) if s["denoms"] else Text("unset", style="red")
        p95 = State.p95(s["lat"])
        tot_tok += s["tok"]
        worst = max(worst, p95)
        tbl.add_row(str(rid), Text(name), dn, str(n), bar(p, f, c),
                    str(p) if p else "", str(f) if f else "", str(c) if c else "",
                    f"{s['tok']:,}" if s["tok"] else "—",
                    f"{p95 / 1000:.2f}s" if p95 else "—")

    cost = Table.grid(padding=(0, 3))
    cost.add_row(Text(f"{tot_tok:,}", style="bold"), Text("tokens", style="grey50"),
                 Text(f"{worst / 1000:.2f}s", style="bold"), Text("worst p95", style="grey50"),
                 Text(str(rungs.get(6, {}).get("pass", 0)), style="bold"),
                 Text("reviewed by a person", style="grey50"),
                 Text("never summed", style="grey35"))

    wt = Table(box=None, pad_edge=False, show_header=False)
    wt.add_column(width=8, style=WARN)
    wt.add_column(overflow="fold")
    for who, msg in watch_items(st):
        wt.add_row(who, Text(msg, style="grey62" if who else "grey42"))

    rep_parts: list = []
    for i, (rid, summary, full) in enumerate(reports):
        if i == len(reports) - 1:
            rep_parts.append(Text(f"rung {rid}", style="bold"))
            for ln in full.strip().splitlines():
                if ln.strip().startswith("="):
                    continue
                rep_parts.append(Text("  " + ln.rstrip(), style="grey70"))
        else:
            rep_parts.append(Text.assemble((f"rung {rid}  ", "grey50"),
                                           (summary, "grey42")))
    if not rep_parts:
        rep_parts = [Text("no rung has reported yet", style="grey35")]

    ft = Table(box=None, pad_edge=False, show_header=False)
    ft.add_column(width=2, style="grey50")
    ft.add_column(width=32)
    ft.add_column(width=18)
    ft.add_column(width=13)
    for rid, rec, out, ev in feed:
        ft.add_row(str(rid), Text(str(rec), style="grey70"),
                   Text(str(out), style="grey50"),
                   Text(ev.replace("_", " "),
                        style={"pass": PASS, "fail": FAIL}.get(ev, CNR)))

    gpu_line = None
    if gpu:
        temps = [g[1] for g in gpu]
        clocks = [g[2] for g in gpu]
        throttling = len(clocks) > 12 and clocks[-1] < max(clocks) * 0.9
        gpu_line = Text.assemble(
            ("compute  ", "grey50"),
            (f"{temps[-1]:.0f}°C ", "grey70"), (spark(temps), "grey62"),
            ("   ", ""), (f"{clocks[-1]:.0f}MHz ", "grey70"), (spark(clocks), "grey62"),
            ("   clock falling while temp climbs — throttling" if throttling else "", WARN))

    parts = [head]
    if prov:
        parts.append(prov)
    parts += [Rule(style="grey23"), tbl, Text(""), cost]
    if gpu_line:
        parts += [Text(""), gpu_line]
    # Wall clock against the sum of per-call latencies. The gap is
    # orchestration — model load, eviction, Python — and it appears in neither
    # tokens nor per-call latency.
    measured_s = sum(sum(s["lat"]) for s in rungs.values()) / 1000.0
    overhead = elapsed - measured_s
    over_line = Text.assemble(
        ("time     ", "grey50"),
        (f"{_hhmm(elapsed)} wall", "grey70"), ("   ", ""),
        (f"{_hhmm(measured_s)} in calls", "grey70"), ("   ", ""),
        (f"{_hhmm(max(0, overhead))} elsewhere", WARN if overhead > measured_s * 0.5 else "grey50"),
        ("   model load, eviction, orchestration" if overhead > measured_s * 0.5 else "", "grey35"))

    parts += [Text(""), Rule("time", style="grey23", align="left"),
              time_panel(rungs, t0), Text(""), over_line,
              Text("drift is the first quarter of a rung's records against the last — "
                   "same work, so a rise is the machine", style="grey35"),
              Text(""), Rule("watch", style="grey23", align="left"), wt,
              Text(""), Rule("reports", style="grey23", align="left"), *rep_parts,
              Text(""), Rule("ledger", style="grey23", align="left"), ft,
              Text(""), Text(f"web view  {WEB_URL}", style="grey42")]
    return Group(*parts)


def read_new(path: pathlib.Path, seen: int) -> tuple[list[dict], int]:
    """Whole lines only; a partial final line is retried next tick."""
    if not path.exists():
        return [], seen
    lines = path.read_text(errors="replace").split("\n")
    out, i = [], seen
    while i < len(lines):
        ln = lines[i].strip()
        if not ln:
            i += 1
            continue
        try:
            out.append(json.loads(ln))
        except json.JSONDecodeError:
            break
        i += 1
    return out, i


class Monitor:
    """Owns the Live display. `ladder_run.py --tui` drives it from a thread."""

    def __init__(self, path: str = DEFAULT_LEDGER, provenance: dict | None = None,
                 interval: float = 0.7):
        self.path = pathlib.Path(path)
        self.state = State()
        self.provenance = provenance or {}
        self.interval = interval
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def add_report(self, rung: int, text: str) -> None:
        self.state.add_report(rung, text)

    def _loop(self) -> None:
        console = Console()
        seen, last_gpu = 0, 0.0
        with Live(render(self.state, self.path, self.provenance),
                  console=console, refresh_per_second=4, screen=False) as live:
            while not self._stop.is_set():
                rows, seen = read_new(self.path, seen)
                for r in rows:
                    self.state.ingest(r)
                now = time.time()
                if now - last_gpu > 4:
                    g = poll_gpu()
                    if g:
                        self.state.gpu.append((now, *g))
                    last_gpu = now
                live.update(render(self.state, self.path, self.provenance))
                self._stop.wait(self.interval)
            live.update(render(self.state, self.path, self.provenance))

    def start(self) -> "Monitor":
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        return self

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=3)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", default=DEFAULT_LEDGER)
    ap.add_argument("--once", action="store_true", help="render a finished run and exit")
    ap.add_argument("--interval", type=float, default=0.7)
    a = ap.parse_args()

    path = pathlib.Path(a.file)
    console = Console()

    if a.once:
        st = State()
        rows, _ = read_new(path, 0)
        if not rows:
            console.print(f"[red]no rows in {path}[/]")
            return 1
        for r in rows:
            st.ingest(r)
        console.print(render(st, path))
        return 0

    console.print(f"[grey50]watching {path} · web view {WEB_URL} · ctrl-c to stop[/]")
    m = Monitor(a.file, interval=a.interval)
    try:
        m._loop()
    except KeyboardInterrupt:
        console.print(f"[grey50]stopped · {m.state.rows} rows[/]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

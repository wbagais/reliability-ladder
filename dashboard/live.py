"""Live run — one document through the REAL rungs, in-process, to a scratch
directory that is read for the view and then deleted.

The plan page's "Ladder demo" pane is a static picture of the mechanism over
synthetic posts. This is the same picture over a text the operator pastes
(or a dev/pool document they pick), produced by the pipeline's own driver:
`ladder.run.run_ladder`, every rung's own `apply`, the model resolved through
`llm.for_rung` from the manifest, the calls served by the same `.llm_cache`
(so the same text twice is a hit, and the payload says so). Nothing here
re-implements a rung — the governing rule — and nothing here is a run:

  * it writes to a TEMPORARY directory, never `out/`; the runs list never
    sees it and no results.csv is produced;
  * it is ONE document, so every number it shows is an example and the
    payload carries the `live_single_document` caveat on every render;
  * the test split is refused (C2 — a live look at a held-out document is
    still a look);
  * one live run at a time (spec R2), and a run that dies reports its error
    instead of hanging the tab.

It is not the R2 launcher: that one runs `python -m ladder.run` over a split
into `out/` and is still M3. The C2 test that no dashboard module can spawn
a process still holds — this is an import, not a child process.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from dashboard import caveats as caveats_mod
from dashboard.state import AppState

SPLIT_LIVE = "live"
SPENT_SPLIT = "test"
MAX_TEXT_CHARS = 20_000


class LiveError(Exception):
    """A refusal with the HTTP status the route should answer with."""

    def __init__(self, status: int, detail: str):
        super().__init__(detail)
        self.status = status
        self.detail = detail


@dataclass
class LiveJob:
    id: str
    source: str            # "pasted" | "corpus"
    doc_id: str
    split: str
    through_rung: int
    order_run: list[int]
    status: str = "running"   # running | done | error
    started: float = field(default_factory=time.time)
    finished: float | None = None
    error: str | None = None
    result: dict[str, Any] | None = None
    scratch_dir: str = ""
    run_id: str = ""

    def progress(self) -> dict[str, Any]:
        """What the scratch directory says so far — the spec's progress
        signal is the run's own files, never a guess."""
        d = Path(self.scratch_dir) if self.scratch_dir else None
        done: list[int] = []
        calls: dict[str, int] = {}
        if self.status == "done":
            # The scratch dir is gone by now; the result carries the calls.
            done = list(self.order_run)
            calls = {n: len(p.get("calls", []))
                     for n, p in (self.result or {}).get("rungs", {}).items()}
        elif d is not None and d.is_dir():
            for n in self.order_run:
                if (d / f"{self.run_id}.r{n}.records.jsonl").exists():
                    done.append(n)
                p = d / f"{self.run_id}.r{n}.calls.jsonl"
                if p.exists():
                    calls[str(n)] = sum(1 for l in p.read_text(encoding="utf-8").splitlines() if l.strip())
        running = next((n for n in self.order_run if n not in done), None) \
            if self.status == "running" else None
        return {"rungs_done": done, "rung_running": running, "calls": calls,
                "elapsed_s": round((self.finished or time.time()) - self.started, 1)}

    def public(self) -> dict[str, Any]:
        return {
            "job_id": self.id, "status": self.status, "source": self.source,
            "doc_id": self.doc_id, "split": self.split,
            "through_rung": self.through_rung, "order_run": self.order_run,
            "error": self.error, "progress": self.progress(),
            "result": self.result,
        }


class LiveRunner:
    def __init__(self, state: AppState, background: bool = True):
        self.state = state
        self.background = background
        self.jobs: dict[str, LiveJob] = {}
        self._busy = threading.Lock()

    # -- options ------------------------------------------------------------

    def options(self) -> dict[str, Any]:
        man = self.state.manifest()
        order = list(man.get("rung_order", []))
        rungs = {}
        for n in order:
            cfg = dict((man.get("rungs") or {}).get(str(n), {}))
            rungs[str(n)] = {k: v for k, v in cfg.items()
                             if "note" not in k.lower() and not k.startswith("_")}
        model = man.get("model") or {}
        return {
            "rung_order": order,
            "rungs": rungs,
            "models": {k: model.get(k) for k in ("extractor", "judge")},
            "temperature": model.get("temperature"),
            "splits_offered": [s for s in ("dev", "pool")
                               if s in (self.state.splits() or {})],
            "corpus_available": self.state.corpus() is not None,
            "registry_available": self.state.registry() is not None,
            "max_text_chars": MAX_TEXT_CHARS,
            "busy": self._busy.locked(),
        }

    # -- start / status -----------------------------------------------------

    def job(self, job_id: str) -> LiveJob:
        if job_id not in self.jobs:
            raise LiveError(404, f"unknown live job {job_id!r}")
        return self.jobs[job_id]

    def start(self, *, text: str | None = None, doc_id: str | None = None,
              through_rung: int) -> LiveJob:
        man = self.state.manifest()
        order = list(man.get("rung_order", []))
        if through_rung not in order:
            raise LiveError(400, f"rung {through_rung} is not in rung_order {order}")
        if (text is None or not text.strip()) == (doc_id is None):
            raise LiveError(400, "give exactly one of `text` (non-empty) or `doc_id`")
        if text is not None and len(text) > MAX_TEXT_CHARS:
            raise LiveError(400, f"text is longer than {MAX_TEXT_CHARS} characters")

        if doc_id is not None:
            corpus = self.state.corpus()
            if corpus is None:
                raise LiveError(404, "corpus unavailable on this machine")
            splits = self.state.splits() or {}
            if doc_id in set(splits.get(SPENT_SPLIT) or []):
                raise LiveError(403, f"{doc_id} is in the test split, which is "
                                     "spent (C2): phaseF-test-1 is final and "
                                     "nothing is re-run on it, live included")
            if doc_id not in corpus:
                raise LiveError(404, f"unknown document {doc_id!r}")
            source, split, text = "corpus", "unknown", corpus[doc_id].text
            for name, ids in splits.items():
                if doc_id in set(ids):
                    split = name
                    break
        else:
            assert text is not None
            source, split = "pasted", SPLIT_LIVE
            doc_id = f"LIVE.{hashlib.sha256(text.encode('utf-8')).hexdigest()[:8]}"

        if not self._busy.acquire(blocking=False):
            raise LiveError(409, "a live run is already in progress — one at a time")
        run_id = f"live-{doc_id.split('.')[-1]}-{time.strftime('%H%M%S')}"
        job = LiveJob(id=uuid.uuid4().hex[:12], source=source, doc_id=doc_id,
                      split=split, through_rung=through_rung,
                      order_run=order[: order.index(through_rung) + 1],
                      run_id=run_id)
        job.scratch_dir = tempfile.mkdtemp(prefix="ladder-live-")
        self.jobs[job.id] = job
        if self.background:
            threading.Thread(target=self._run, args=(job, text), daemon=True).start()
        else:
            self._run(job, text)
        return job

    def _run(self, job: LiveJob, text: str) -> None:
        try:
            job.result = run_one(self.state, job, text)
            job.status = "done"
        except (Exception, SystemExit) as exc:  # a SystemExit is how run_ladder refuses
            job.error = str(exc) or exc.__class__.__name__
            job.status = "error"
        finally:
            job.finished = time.time()
            shutil.rmtree(job.scratch_dir, ignore_errors=True)
            self._busy.release()


# --- the run --------------------------------------------------------------


def run_one(state: AppState, job: LiveJob, text: str) -> dict[str, Any]:
    """`run_ladder` over one document into the job's scratch dir, then the
    view's payload read back from the files the run wrote — the same files a
    real run writes, read the same way."""
    from ladder import clean as clean_mod
    from ladder import run as run_mod
    from ladder import trace as trace_mod
    from ladder.ledger import Ledger

    man = state.manifest()
    out_dir = Path(job.scratch_dir)
    sources = {job.doc_id: text}

    gold = None
    gold_view = None
    if job.source == "corpus":
        doc = state.corpus()[job.doc_id]
        try:
            excluded = clean_mod.exclusions_for(man)
        except Exception:
            excluded = set()
        gold = {m.record_id: m for m in doc.mentions if m.record_id not in excluded}
        gold_view = [{"record_id": m.record_id, "text": m.text,
                      "spans": [list(s) for s in m.spans], "sct": list(m.sct),
                      "gold_kind": m.gold_kind,
                      "excluded": m.record_id in excluded}
                     for m in doc.mentions]

    try:
        meddra = run_mod._load_meddra(man)
    except Exception:
        meddra = None

    result = run_mod.run_ladder(
        man, job.split, job.order_run, [], sources, state.registry(), out_dir,
        job.run_id, meddra=meddra, gold=gold,
    )

    # -- read back what the run wrote ---------------------------------------
    state_rows = trace_mod.read_rows(out_dir / f"{job.run_id}.state.jsonl") \
        if (out_dir / f"{job.run_id}.state.jsonl").exists() else []
    ledger_entries = Ledger.read(out_dir / f"{job.run_id}.ledger.jsonl")
    aggregates = json.loads((out_dir / f"{job.run_id}.aggregates.json").read_text(
        encoding="utf-8"))

    timelines: dict[str, list[dict]] = {}
    for row in state_rows:
        timelines.setdefault(row["record_id"], []).append({
            k: row.get(k) for k in (
                "rung", "sct", "sct_label", "zone", "reason", "text", "spans",
                "confidence", "created_this_rung", "dropped_this_rung",
                "changed_this_rung", "changed_fields", "was_sct", "was_zone",
                "r1_verdict", "r1_reason", "r4_verdict", "r3_changed",
                "pick_fallback", "outcome", "outcome_overlap", "gold_codes")
        })

    records = []
    for rec in result["records"]:
        d = rec.to_dict()
        d["timeline"] = timelines.get(rec.record_id, [])
        records.append(d)
    # records the run dropped along the way still have a timeline
    for rid, tl in timelines.items():
        if rid not in {r["record_id"] for r in records}:
            records.append({"record_id": rid, "doc_id": job.doc_id,
                            "text": tl[-1].get("text"), "spans": tl[-1].get("spans"),
                            "sct": None, "zone": None, "dropped": True,
                            "timeline": tl})

    ledger_rows_all = [{
        "rung": e.rung, "doc_id": e.doc_id, "record_id": e.record_id,
        "zone": e.zone, "outcome": e.outcome, "reason": e.reason,
        "verdict": e.verdict, "tokens_in": e.tokens_in, "tokens_out": e.tokens_out,
        "api_calls": e.api_calls, "latency_ms": e.latency_ms, "usd": e.usd,
        "human_minutes": e.human_minutes,
        "denominator": e.extra.get("denominator"),
        "evaluable": e.extra.get("evaluable"),
    } for e in ledger_entries]

    rungs: dict[str, Any] = {}
    calls_total = calls_cached = 0
    for n in job.order_run:
        rows = [r for r in ledger_rows_all if r["rung"] == n]
        calls = []
        p = out_dir / f"{job.run_id}.r{n}.calls.jsonl"
        if p.exists():
            for line in p.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    calls.append(json.loads(line))
        calls_total += len(calls)
        calls_cached += sum(1 for c in calls if c.get("cached"))
        lat = sorted(float(c.get("seconds", 0.0)) * 1000 for c in calls
                     if not c.get("cached"))
        rungs[str(n)] = {
            "aggregate": _jsonable(aggregates.get("rungs", {}).get(str(n), {})),
            "ledger": rows,
            "calls": calls,
            # C5: three measures, side by side, never fused
            "cost": {
                "tokens": sum(r["tokens_in"] + r["tokens_out"] for r in rows),
                "tokens_in": sum(r["tokens_in"] for r in rows),
                "tokens_out": sum(r["tokens_out"] for r in rows),
                "api_calls": sum(r["api_calls"] for r in rows),
                "latency_p95_ms": (lat[min(len(lat) - 1, int(round(0.95 * (len(lat) - 1))))]
                                   if lat else None),
                "routed_to_person": sum(1 for r in rows if r["zone"] == "ESCALATE" and n == 6),
                "human_minutes": sum(r["human_minutes"] or 0 for r in rows),
                "usd": sum(r["usd"] or 0 for r in rows),
                "wall_s": aggregates.get("rungs", {}).get(str(n), {}).get("wall_s"),
            },
        }

    caveat_rows = [{"rung": r["rung"], "outcome": r["outcome"],
                    "verdict": r["verdict"], "human_minutes": r["human_minutes"]}
                   for r in ledger_rows_all]
    keys = ["live_single_document"] + caveats_mod.keys_for_run(caveat_rows, split=job.split)
    if calls_cached:
        keys.append("live_cache_hits")

    man_path = state.repo_root / "manifest.json"
    provenance = {
        "run_id": job.run_id, "split": job.split, "span_match": "exact+overlap",
        "backend": (man.get("vocabulary") or {}).get("snomed_backend", "unknown"),
        "manifest_hash": (hashlib.sha256(man_path.read_bytes()).hexdigest()[:12]
                          if man_path.exists() else "absent"),
        "archived": False, "live": True,
        "models": aggregates.get("models", {}),
        "temperature": aggregates.get("temperature"),
        "llm_cache": aggregates.get("llm_cache"),
        "git": aggregates.get("git"),
        "started_utc": aggregates.get("started_utc"),
        "finished_utc": aggregates.get("finished_utc"),
    }
    return {
        "run_id": job.run_id, "source": job.source, "doc_id": job.doc_id,
        "split": job.split, "text": text, "through_rung": job.through_rung,
        "order_run": job.order_run, "scratch_dir": job.scratch_dir,
        "records": records, "gold": gold_view, "rungs": rungs,
        "calls_total": calls_total, "calls_cached": calls_cached,
        "provenance": provenance, "caveats": caveats_mod.texts(keys),
        "local_only": True,
    }


def _jsonable(x: Any) -> Any:
    return json.loads(json.dumps(x, default=str))

"""What actually ran — not what the manifest asked for.

Every script that produced a published figure built its own run stamp, or none
at all. `full_run.py` recorded two fields inline; `ladder_run.py` and
`r4_gold_control.py` recorded nothing. That is an odd gap in a project whose
central claim is that provenance is what makes two runs comparable.

Worse, the stamp recorded INTENT. On the day this was written the manifest
asked for `ollama/ibm/granite4:micro-h`, which 404'd, while every measured run
used `granite4:micro-h` named inline in a script. A stamp that records the
manifest is a stamp that can be wrong.

(THAT EXAMPLE HAS SINCE INVERTED, 2026-08-31: ollama now namespaces the model
under `ibm/`, so `ollama/ibm/granite4:micro-h` is the name that exists and bare
`granite4:micro-h` is the one that 404s — three tracked manifests carried the
bare name and were corrected. The point stands and is stronger for having
flipped: what the manifest asks for and what the provider answers to are two
facts, and only one of them is a property of this run.)

So this gathers from the live objects and the live machine. Three fields exist
because of specific things that went wrong:

  models.*.requested vs .resolved
      The manifest string and the string actually sent. A silent fallback or a
      404 is visible in the diff between them.

  compute.fits
      Rung 4 slowed 6x mid-run. The cause was a 4.7 GB judge on a 4 GB card:
      the inference server loaded it partially and ran layers on the CPU. One
      record took 134 seconds — that was the load. Resident bytes against card
      capacity would have made it obvious immediately.

  git.sha / git.dirty
      A figure traceable to a date is not traceable. Rung IDs were renumbered
      mid-project; runs either side are not comparable without knowing which
      code produced them.

Usage:

    from ladder import provenance
    stamp = provenance.gather(man, split="dev", n_docs=40,
                              vocab=reg, entry_point="scripts/ladder_run.py",
                              models={"extractor": ("granite4:micro-h",
                                                    S.MODEL)})
    # sampling is left unset on purpose: gather reads it from the manifest
    # (sampling_for). An entry point that passes a literal is stamping a
    # temperature nobody configured, which is what both scripts used to do.
    json.dump({"provenance": stamp, ...}, fh)

Nothing here raises. A stamp that crashes a run is worse than an incomplete
stamp, and every field records its own absence honestly rather than guessing.
"""
from __future__ import annotations

import datetime as _dt
import json
import os
import pathlib
import re
import shutil
import subprocess
from typing import Any


def _run(cmd: list[str], timeout: float = 3) -> str:
    try:
        return subprocess.run(cmd, capture_output=True, text=True,
                              timeout=timeout).stdout.strip()
    except Exception:
        return ""


# ------------------------------------------------------------------ git
def git() -> dict[str, Any]:
    """Which code produced this. `dirty` matters more than `sha`.

    A run from a working tree with uncommitted changes cannot be reproduced
    from the repository, and saying so is the whole point.
    """
    if not shutil.which("git"):
        return {"sha": None, "dirty": None, "note": "git not on PATH"}
    sha = _run(["git", "rev-parse", "--short", "HEAD"]) or None
    status = _run(["git", "status", "--porcelain"])
    return {
        "sha": sha,
        "branch": _run(["git", "rev-parse", "--abbrev-ref", "HEAD"]) or None,
        "dirty": bool(status),
        "dirty_files": len(status.splitlines()) if status else 0,
    }


# --------------------------------------------------------------- compute
def compute(model_gib: float | None = None) -> dict[str, Any]:
    """The GPU, and whether the model fits on it.

    `fits` is None when it cannot be determined. It is False when a model was
    named and the card is smaller — the condition that cost rung 4 a 6x
    slowdown and 92 minutes on the gold control.
    """
    out: dict[str, Any] = {"gpu": None, "vram_total_mib": None,
                           "vram_used_mib": None, "driver": None,
                           "resident_models": [], "fits": None}
    if shutil.which("nvidia-smi"):
        csv = _run(["nvidia-smi",
                    "--query-gpu=name,memory.total,memory.used,driver_version",
                    "--format=csv,noheader,nounits"])
        if csv:
            parts = [p.strip() for p in csv.splitlines()[0].split(",")]
            if len(parts) >= 4:
                out["gpu"] = parts[0]
                out["vram_total_mib"] = _int(parts[1])
                out["vram_used_mib"] = _int(parts[2])
                out["driver"] = parts[3]

    # Ollama reports what is resident and how it was placed. "100% GPU" from
    # its own placement estimate has been wrong here before — it reported that
    # while running on CPU at 4.4 tok/s — so record the line, do not trust it.
    if shutil.which("ollama"):
        ps = _run(["ollama", "ps"])
        for line in ps.splitlines()[1:]:
            if line.strip():
                out["resident_models"].append(" ".join(line.split()))

    if model_gib and out["vram_total_mib"]:
        out["model_gib"] = model_gib
        out["fits"] = (model_gib * 1024) < out["vram_total_mib"] * 0.92
    return out


def _int(s: str) -> int | None:
    try:
        return int(float(s))
    except Exception:
        return None


# ------------------------------------------------------------ vocabulary
def vocabulary(vocab: Any, man: dict | None = None) -> dict[str, Any]:
    """Which backend answered, and whether it is the lossy one.

    schemas/vocabulary.py says plainly that a rung 1 rejection rate "is not
    comparable across backends and must never be reported without saying which
    one produced it". This is what makes that possible.
    """
    d: dict[str, Any] = {
        "backend": getattr(vocab, "name", None),
        "lossy": getattr(vocab, "lossy", None),
    }
    if man:
        d["db_path"] = man.get("vocabulary", {}).get("snomed_db")
        d["release"] = man.get("vocabulary", {}).get("release")
    # The index knows its own release; prefer it over the manifest's claim.
    try:
        stats = vocab.stats()
        if isinstance(stats, dict):
            d["index_stats"] = stats
    except Exception:
        pass
    return d


# ---------------------------------------------------------------- models
def models(spec: dict[str, tuple[str | None, str | None]]) -> dict[str, Any]:
    """{"extractor": (requested, resolved), ...} -> a diffable record.

    `requested` is the manifest string. `resolved` is what was actually sent.
    They diverged today: the manifest carried a vendor prefix the local server
    does not use, and every measured run bypassed it by naming the model
    inline. A stamp that recorded only the manifest would have been wrong for
    every figure in the repository.
    """
    out = {}
    for role, pair in spec.items():
        req, res = (pair if isinstance(pair, (tuple, list)) else (pair, pair))
        out[role] = {"requested": req, "resolved": res,
                     "matches": (req == res) if (req and res) else None}
    return out


# ----------------------------------------------------------------- main
def sampling_for(man: dict | None = None) -> dict[str, Any]:
    """What temperature this run actually called at, read from the manifest.

    Added 2026-08-31 with the `manifest.model.temperature` wiring. Before it,
    `scripts/ladder_run.py` stamped `{"temperature": 0.7, "k": 3}` and
    `scripts/full_run.py` stamped `{"temperature": 0.0}` — both LITERALS, and
    the first reported RUNG 3's sampler temperature as though it were the
    run's. A stamp that hardcodes its answer cannot be wrong and cannot be
    right, which is the same failure the input side had.

    `temperature_declared` is the field that earns this function. `0` in the
    manifest and 0.0 from `llm.GREEDY_TEMPERATURE` are the same number and not
    the same fact, and after the wiring nothing else can tell them apart.

    Rung 3's sampler is reported SEPARATELY and only when declared: absent
    means absent, never a guessed 0.7, because a stamp that invents k=3 for a
    run with no rung 3 reports a vote nobody took. Nothing here raises.
    """
    from ladder import llm as _llm

    man = man or {}
    out: dict[str, Any] = {}
    try:
        out["temperature"] = _llm.temperature_for(man)
        out["temperature_declared"] = (
            ((man.get("model") or {}).get("temperature")) is not None)
    except Exception:
        out["temperature"] = _llm.GREEDY_TEMPERATURE
        out["temperature_declared"] = False
    r3 = ((man.get("rungs") or {}).get("3") or {})
    if r3.get("enabled") is False:
        # `enabled: false` is a RECORDED run state, never a silent skip — the
        # same rule run.py's disabled ledger row follows.
        out["sampler"] = "disabled"
    for key, src, cast in (("sampler_temperature", "temperature", float),
                           ("k", "k", int)):
        if src in r3:
            try:
                out[key] = cast(r3[src])
            except Exception:
                out[key] = r3[src]
    return out


def gather(man: dict | None = None, *, split: str | None = None,
           n_docs: int | None = None, vocab: Any = None,
           models_spec: dict | None = None, sampling: dict | None = None,
           rung_order: list[int] | None = None, entry_point: str | None = None,
           model_gib: float | None = None, run_id: str | None = None,
           extra: dict | None = None) -> dict[str, Any]:
    """One stamp, gathered from live objects rather than from the manifest."""
    man = man or {}
    stamp: dict[str, Any] = {
        "run_id": run_id,
        "started_utc": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
        "entry_point": entry_point,
        "rung_order": list(rung_order) if rung_order else man.get("rung_order"),
        "git": git(),
        "compute": compute(model_gib),
        "corpus": {
            "root": (man.get("corpus") or {}).get("root")
                    or (man.get("corpus") or {}).get("cadec_root"),
            "version": man.get("corpus", {}).get("version"),
            "split": split or os.environ.get("LADDER_SPLIT", "dev"),
            "n_docs": n_docs,
            "ladder_n": os.environ.get("LADDER_N"),
        },
        # An entry point that says nothing about sampling must not produce a
        # stamp that says nothing about sampling. Explicit still wins.
        "sampling": sampling if sampling is not None else sampling_for(man),
        "env": {
            # `ladder_otel` was stamped here until 2026-08-31 and named an env
            # var that switched on an exporter nothing imported. Removed with
            # it: a stamp recording a knob that does nothing describes a run
            # nobody had.
            "ollama_host": os.environ.get("OLLAMA_HOST"),
        },
    }
    if vocab is not None:
        stamp["vocabulary"] = vocabulary(vocab, man)
    if models_spec:
        stamp["models"] = models(models_spec)
    if extra:
        stamp.update(extra)
    return stamp


def warnings(stamp: dict) -> list[str]:
    """Conditions that make a figure hard to trust. Printed, not raised.

    Each of these has cost this project a measurement:
      dirty tree        a figure that cannot be traced to committed code
      model mismatch    the manifest and the run disagreed on the model
      does not fit      partial GPU offload, and a 6x slowdown mid-rung
      lossy backend     23.9% of the answer key invisible
    """
    out = []
    g = stamp.get("git") or {}
    if g.get("dirty"):
        out.append(f"working tree dirty ({g.get('dirty_files')} files) — "
                   "this run is not reproducible from the repository")
    for role, m in (stamp.get("models") or {}).items():
        if m.get("matches") is False:
            out.append(f"{role}: manifest asked for {m['requested']!r}, "
                       f"run used {m['resolved']!r}")
    c = stamp.get("compute") or {}
    if c.get("fits") is False:
        out.append(f"model {c.get('model_gib')}GiB does not fit "
                   f"{c.get('vram_total_mib')}MiB of VRAM — expect partial "
                   "offload and a latency step change mid-run")
    v = stamp.get("vocabulary") or {}
    if v.get("lossy"):
        out.append(f"vocabulary backend {v.get('backend')!r} is lossy — a "
                   "rejection rate from it is not comparable with the local "
                   "index")
    return out


def write(path: str | os.PathLike, stamp: dict, results: dict | None = None) -> None:
    p = pathlib.Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"provenance": stamp, **(results or {})},
                            indent=2, ensure_ascii=False))


if __name__ == "__main__":
    man = {}
    mp = pathlib.Path("manifest.json")
    if mp.exists():
        man = json.loads(mp.read_text())
    s = gather(man, entry_point="ladder.provenance")
    print(json.dumps(s, indent=2))
    for w in warnings(s):
        print(f"  WARNING  {w}")

"""
stub_llm.py — the model client rung0_ab.py runs against.

Two functions, and deliberately nothing else:

    stub(prompt, text, mode) -> (raw, usage)
    load_items(splits_dir)   -> [{doc_id, text}, ...]

WHAT THIS FILE MUST NOT DO
--------------------------
No repair of model output. No stripping code fences, no extracting the first
{...}, no retry on malformed JSON. rung0_ab.py counts a parse failure as rung
0's counter-metric — quietly fixing them here deletes the measurement and makes
rung 0 look better than it is.

The one exception, and it is not a repair: Ollama's /api/generate wraps the
model's text in a transport envelope. Unwrapping that envelope is reading the
response, not editing it. Everything inside `.response` is passed through
untouched.

COST
----
`usage` carries prompt_eval_count and eval_count from Ollama, which are real
token counts, not estimates. Latency is recorded per call so p95 can be taken
over the run rather than derived from a total.
"""
from __future__ import annotations

import json
import os
import pathlib
import time
import urllib.error
import urllib.request

MODEL = os.environ.get("LADDER_MODEL", "granite4:micro-h")
HOST = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")
TIMEOUT = int(os.environ.get("LADDER_TIMEOUT", "180"))

# Every call's latency, in order. rung0_ab aggregates tokens itself; it has no
# per-call hook for time, so p95 is taken from here after the run.
LATENCIES: list[float] = []


def stub(prompt: str, text: str, mode: str, model: str | None = None,
         temperature: float = 0.0) -> tuple[str, dict]:
    """One generation. Returns the model's raw text and its token usage.

    `model` and `temperature` are per-call because rung 4 needs a different
    model family (a self-judge measures self-consistency) and rung 5 needs
    temperature above 0 (identical samples cannot vote). Everything else in the
    project stays greedy on the default model.
    """
    body = json.dumps(
        {
            "model": model or MODEL,
            "prompt": f"{prompt}\n\nPOST:\n{text}",
            "stream": False,
            "keep_alive": "30m",
            "options": {
                # Greedy by default. A run that cannot be repeated is not a
                # measurement — rung 5 is the one deliberate exception.
                "temperature": float(temperature),
                "seed": 0,
            },
        }
    ).encode()

    req = urllib.request.Request(
        f"{HOST}/api/generate", data=body, headers={"Content-Type": "application/json"}
    )
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            payload = json.loads(r.read())
    except urllib.error.URLError as e:
        raise RuntimeError(
            f"cannot reach ollama at {HOST} ({e}). Start it with `ollama serve`."
        ) from e
    elapsed = time.time() - t0
    LATENCIES.append(elapsed)

    usage = {
        "in": int(payload.get("prompt_eval_count", 0)),
        "out": int(payload.get("eval_count", 0)),
        "seconds": round(elapsed, 3),
        "model": MODEL,
        "done_reason": payload.get("done_reason"),
    }
    # Raw. Not stripped, not repaired.
    return payload.get("response", ""), usage


def load_items(splits_dir: str | os.PathLike) -> list[dict]:
    """Split ids -> [{doc_id, text}].

    Reads the DEV split by default. `test` is frozen; spending it on a smoke run
    cannot be undone. LADDER_SPLIT and LADDER_N override, and both are echoed so
    a run always says what it read.
    """
    from ladder import corpus as C

    man = json.loads(pathlib.Path("manifest.json").read_text())
    split = os.environ.get("LADDER_SPLIT", "dev")
    if split == "test":
        raise SystemExit(
            "refusing to read the test split from a smoke run. "
            "Set LADDER_SPLIT=test deliberately in the harness when you mean it."
        )

    doc_ids = C.read_split(splits_dir, split)
    docs = C.load_corpus(man["corpus"]["cadec_root"])

    n = int(os.environ.get("LADDER_N", "10"))
    doc_ids = doc_ids[:n] if n > 0 else doc_ids

    print(f"[corpus] split={split} docs={len(doc_ids)}")
    return [{"doc_id": d, "text": docs[d].text} for d in doc_ids]



def voter(temperature: float = 0.7):
    """Rung 5's sampler: same model, temperature above 0 so samples can differ."""
    def _call(prompt, text, mode):
        return stub(prompt, text, mode, temperature=temperature)
    return _call


def judge(model: str):
    """Rung 4's judge: a DIFFERENT model, greedy.

    Passing the extractor's own model here defeats the rung; r4.apply also
    checks, but the mistake is easiest to make at this call site.
    """
    if model == MODEL:
        raise ValueError(
            f"judge model {model!r} is the extractor. A model judging its own "
            "output measures self-consistency, not correctness."
        )
    def _call(prompt, text, mode):
        return stub(prompt, text, mode, model=model, temperature=0.0)
    return _call

def latency_p95() -> float | None:
    """p95 over the run. One of the three cost measures; never fused with the others."""
    if not LATENCIES:
        return None
    s = sorted(LATENCIES)
    return round(s[min(len(s) - 1, int(round(0.95 * (len(s) - 1))))], 3)


if __name__ == "__main__":
    raw, usage = stub("Reply with the word OK and nothing else.", "", "A")
    print("usage:", usage)
    print("raw  :", repr(raw[:400]))

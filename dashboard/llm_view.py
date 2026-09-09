"""R5 — prompt and raw-reply drill-down from `.llm_cache`.

The cache stores REPLIES keyed by a hash of the exact request payload; the
prompt itself is not retained on disk. So the drill-down RECONSTRUCTS the
request through the rungs' own prompt builders (`ladder.rungs.r0` /
`ladder.rungs.r4` — never a re-implementation) and looks the hash up. Any
divergence — a config that drifted, a record the pick dropped, a cache that
was pruned — renders as "not_retained", never as an empty reply (spec R5).

LOCAL-ONLY: these views carry corpus text and are excluded from every export
path (C1). M1 reconstructs rung 0's extract+pick calls and rung 4's judge
call; rung 2/3 calls are not reconstructed (rung 2 fired zero times on every
measured run; rung 3's k samples are addressed by sample_index and belong
with a voting view in a later milestone).
"""
from __future__ import annotations

import json
from typing import Any

from dashboard.runsindex import RunInfo, read_manifest_copy
from dashboard.state import AppState
from dashboard.util import span_key


def _client(state: AppState, spec: str):
    from ladder.llm import LLMClient

    return LLMClient(spec, cache_dir=state.repo_root / ".llm_cache")


def _lookup(state: AppState, spec: str, content: str) -> dict[str, Any]:
    """The cache entry for one reconstructed request, or not_retained."""
    try:
        client = _client(state, spec)
        payload = {
            "model": client.info.spec,
            "messages": [{"role": "user", "content": content}],
            "temperature": 0.0,
            "sample_index": 0,
            "max_tokens": client.info.max_tokens,
            "reasoning_effort": client.info.reasoning_effort,
        }
        path = client._cache_path(payload)
        if not path.exists():
            return {"status": "not_retained", "prompt": content, "model": spec}
        data = json.loads(path.read_text())
        return {
            "status": "retained", "model": spec, "prompt": content,
            "reply": data.get("text", ""),
            "prompt_tokens": data.get("prompt_tokens"),
            "completion_tokens": data.get("completion_tokens"),
            "latency_s": data.get("latency_s"),
            "truncated": data.get("truncated", False),
        }
    except Exception as exc:  # model registry gap, unreadable cache, ...
        return {"status": "not_retained", "model": spec, "note": str(exc)[:200]}


def record_llm_payload(state: AppState, info: RunInfo, doc_id: str,
                       spans) -> dict[str, Any]:
    from ladder.rungs import r0

    man = read_manifest_copy(info) or {}
    model = man.get("model", {})
    extractor = model.get("extractor")
    judge_model = model.get("judge")
    cfg = dict(man.get("rungs", {}).get("0", {}))
    step = cfg.get("rung0_step") or "S2"

    corpus = state.corpus()
    calls: list[dict[str, Any]] = []
    want = span_key(doc_id, spans)
    records = [r for r in state.records(info) if r.doc_id == doc_id]
    rec = next((r for r in records
                if span_key(r.doc_id, r.spans) == want), None)

    if corpus is None or doc_id not in corpus or extractor is None:
        note = ("corpus unavailable" if corpus is None or doc_id not in corpus
                else "no extractor in the run's manifest copy")
        return {"local_only": True, "calls": [], "note": note}

    source = corpus[doc_id].text
    base = {"S0": r0.S0_PROMPT, "S1": r0.S1_PROMPT, "S2": r0.FIND_PROMPT}.get(
        step, r0.FIND_PROMPT)
    # The few-shot block is rendered at runtime from pool documents (the
    # corpus is non-transferable, so only doc IDs live in the manifest);
    # rebuild it through r0's own renderer or the hash cannot match.
    if cfg.get("rung0_fewshot") and cfg.get("rung0_fewshot_docs") \
            and not cfg.get("rung0_fewshot_block"):
        try:
            cfg["rung0_fewshot_block"] = r0.pool_fewshot_block(
                man, cfg["rung0_fewshot_docs"])
        except Exception:
            pass  # reconstruction stays best-effort; a miss says not_retained
    extract_prompt = r0._extraction_prompt(base, cfg)
    entry = _lookup(state, extractor, f"{extract_prompt}\n\nPOST:\n{source}")
    calls.append({"rung": 0, "call": f"{step} extract", **entry})

    if step == "S2":
        pairs = [(r, (r.checks or {}).get("candidates") or []) for r in records]
        if pairs:
            pick_prompt = r0.PICK_PROMPT.format(blocks=r0._blocks(pairs))
            entry = _lookup(state, extractor,
                            f"{pick_prompt}\n\nPOST:\n{source}")
            calls.append({"rung": 0, "call": "S2 pick", **entry})

    if rec is not None and judge_model and \
            (rec.checks or {}).get("r4_verdict") is not None:
        from ladder.rungs import r4

        withheld = (rec.checks or {}).get("withheld") or {}
        sct = rec.sct if rec.sct is not None else withheld.get("sct")
        s, e = (rec.spans[0] if rec.spans else (-1, -1))
        judge_prompt = r4.PROMPT.format(source=source, text=rec.text,
                                        start=s, end=e, sct=sct)
        entry = _lookup(state, judge_model, judge_prompt)
        calls.append({"rung": 4, "call": "judge", **entry})

    return {"local_only": True, "calls": calls}

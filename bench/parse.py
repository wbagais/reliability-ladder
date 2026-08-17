"""Lenient parsing of model output (rung 0 takes whatever comes back)."""

from __future__ import annotations

import json
import re


def extract_json(text: str) -> dict | list | None:
    """Pull the first JSON object/array out of a model reply (fences, prose, etc.)."""
    if not text:
        return None
    fence = re.search(r"```(?:json)?\s*([\{\[].*?[\}\]])\s*```", text, re.DOTALL)
    candidates = [fence.group(1)] if fence else []
    starts = [i for i in (text.find("{"), text.find("[")) if i != -1]
    if starts:
        start = min(starts)
        open_ch = text[start]
        close_ch = "}" if open_ch == "{" else "]"
        depth = 0
        for i, ch in enumerate(text[start:], start):
            if ch == open_ch:
                depth += 1
            elif ch == close_ch:
                depth -= 1
                if depth == 0:
                    candidates.append(text[start : i + 1])
                    break
        else:
            candidates.append(text[start:])  # truncated output: try repair below
    for cand in candidates:
        for attempt in (cand, _repair(cand)):
            try:
                obj = json.loads(attempt)
                if isinstance(obj, (dict, list)):
                    return obj
            except json.JSONDecodeError:
                continue
    return None


def _repair(s: str) -> str:
    s = re.sub(r",\s*([}\]])", r"\1", s)  # trailing commas
    # close unbalanced braces/brackets from truncated output
    opens = s.count("{") - s.count("}")
    s = s.rstrip().rstrip(",")
    if s.endswith(":"):
        s += " null"
    return s + "]" * max(0, s.count("[") - s.count("]")) + "}" * max(0, opens)


def parse_reply(text: str) -> tuple[dict | list | None, dict, dict]:
    """-> (answer object/array | None, confidence map, verdict map).

    Accepts {"answer": ..., "confidence": ..., "verdicts": ...} or a bare
    answer object/array (model skipped the envelope).
    """
    obj = extract_json(text)
    if obj is None:
        return None, {}, {}
    if isinstance(obj, list):
        return obj, {}, {}
    if isinstance(obj.get("answer"), (dict, list)):
        conf = obj.get("confidence") if isinstance(obj.get("confidence"), dict) else {}
        verd = obj.get("verdicts") if isinstance(obj.get("verdicts"), dict) else {}
        return obj["answer"], conf, verd
    obj.pop("confidence", None)
    obj.pop("verdicts", None)
    return obj, {}, {}

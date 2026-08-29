"""Provider-agnostic LLM client.

One `chat()` against any OpenAI-compatible endpoint (Ollama local, Gemini,
OpenRouter, Groq, ...). Every call is disk-cached by
(model, messages, temperature, sample_index) so reruns are free and resumable.
Temperature is locked to 0 project-wide; the parameter exists only so the cache
key stays honest if that ever changes.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path

import sys

import yaml
from typing import Any


def _timeout_errors() -> tuple[type[BaseException], ...]:
    """What the provider raises when a call outlives its budget."""
    try:
        import openai
    except ImportError:  # pragma: no cover - openai is a local-only extra
        return (TimeoutError,)
    return (openai.APITimeoutError, TimeoutError)

REGISTRY_PATH = Path(__file__).parent / "models.yaml"

#: Completion tokens allowed when models.yaml names no budget. Enough for a
#: document's worth of mentions from an instruct model; a reasoning model
#: needs its own entry — see ModelInfo.max_tokens.
DEFAULT_MAX_TOKENS = 2000

#: Wall-clock seconds for one call. A reasoning model can run away on a short
#: post — measured on a 761-character document, one call passed 25 minutes
#: generating toward a 32,000-token cap — and a 40-document split then never
#: finishes. A timeout turns "the run hangs" into "one record timed out",
#: which is the difference between a measurement and nothing.
DEFAULT_TIMEOUT_S = 120
DEFAULT_CACHE_DIR = Path(__file__).parent.parent / ".llm_cache"


@dataclass
class LLMResponse:
    text: str
    prompt_tokens: int
    completion_tokens: int
    latency_s: float
    cached: bool = False
    #: Did the provider stop because the token budget ran out?
    #: A TRUNCATION IS NOT A MODEL FAILURE. Measured 2026-08-24: gpt-oss:20b
    #: at rung 0's S0 burned all 16,000 completion tokens and returned an
    #: empty string, and the ledger recorded parse_failed/json_decode —
    #: identical to a model that emitted malformed JSON, which is the number
    #: rung 0 exists to report. Raising the cap does not fix that, it moves
    #: it; the provider already says which happened, so it is kept.
    truncated: bool = False
    #: Did the call exceed its wall-clock budget? A subset of `truncated` —
    #: nothing usable came back either way — kept separate because the causes
    #: differ: one is the model writing too much, the other is it writing too
    #: slowly, and only the second is a property of this machine.
    timed_out: bool = False


class ModelInfo:
    """Registry entry for one provider/model spec."""

    def __init__(self, spec: str, registry_path: Path = REGISTRY_PATH):
        if "/" not in spec:
            raise ValueError(
                f"Model spec must be 'provider/model', e.g. 'ollama/gpt-oss:20b' — got {spec!r}"
            )
        self.spec = spec
        self.provider, self.model = spec.split("/", 1)
        registry = yaml.safe_load(registry_path.read_text())["providers"]
        if self.provider not in registry:
            raise ValueError(
                f"Unknown provider {self.provider!r}. Known: {', '.join(registry)}"
            )
        p = registry[self.provider]
        self.base_url: str = p["base_url"]
        self.api_key_env: str | None = p.get("api_key_env")
        self.local: bool = bool(p.get("local", False))
        overrides = (p.get("models") or {}).get(self.model, {})
        self.input_per_mtok: float = overrides.get("input_per_mtok", p["input_per_mtok"])
        self.output_per_mtok: float = overrides.get("output_per_mtok", p["output_per_mtok"])
        #: Does this model accept temperature/top_p/top_k? The Claude 5 family
        #: removed them and 400s if one is sent. Registry data rather than a
        #: branch in a rung: a rung must not know which family it is calling.
        self.sampling: bool = bool(
            overrides.get("sampling", p.get("sampling", True))
        )
        #: Completion-token budget. REGISTRY DATA, not a constant, because a
        #: reasoning model spends the budget thinking before it emits an
        #: answer. Measured 2026-08-24: gpt-oss:20b returned exactly 2000
        #: completion tokens for rung 0's S0 and S2 and both were logged
        #: parse_failed/json_decode — truncated mid-structure by a cap tuned
        #: for a 2B instruct model. That is the harness failing, recorded as
        #: the model failing, in the one number rung 0 exists to report.
        self.max_tokens: int = int(
            overrides.get("max_tokens", p.get("max_tokens", DEFAULT_MAX_TOKENS))
        )
        #: "low" | "medium" | "high", or None for a model with no reasoning
        #: channel. gpt-oss:20b writes its chain of thought to a SEPARATE
        #: `reasoning` field and leaves `content` empty until it finishes.
        #: Measured 2026-08-24 on rung 0's S0, which asks it to recall a
        #: nine-digit SNOMED id: default effort spent 16,000 tokens and
        #: returned nothing, "medium" spent 8,000 and returned nothing, "low"
        #: answered in 104 tokens and 2 seconds. Registry data like
        #: max_tokens and sampling — a rung must not know which family it is
        #: calling, and sending this to a model that has no such parameter is
        #: at best ignored and at worst a 400.
        self.reasoning_effort: str | None = overrides.get(
            "reasoning_effort", p.get("reasoning_effort")
        )
        self.timeout_s: float = float(
            overrides.get("timeout_s", p.get("timeout_s", DEFAULT_TIMEOUT_S))
        )

    def dollars(self, prompt_tokens: int, completion_tokens: int) -> float:
        return (
            prompt_tokens * self.input_per_mtok
            + completion_tokens * self.output_per_mtok
        ) / 1_000_000


class LLMClient:
    def __init__(
        self,
        model_spec: str,
        cache_dir: Path | str = DEFAULT_CACHE_DIR,
        api_key: str | None = None,
    ):
        self.info = ModelInfo(model_spec)
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        key = api_key
        if key is None and self.info.api_key_env:
            key = os.environ.get(self.info.api_key_env)
            if not key:
                raise ValueError(
                    f"Provider {self.info.provider!r} needs an API key: "
                    f"set {self.info.api_key_env} or pass api_key."
                )
        self._api_key = key or "not-needed"
        self._client = None  # lazy, so cached-only runs never touch the network

    def _cache_path(self, payload: dict) -> Path:
        digest = hashlib.sha256(
            json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()
        ).hexdigest()
        return self.cache_dir / f"{digest}.json"

    def chat(
        self,
        messages: list[dict],
        sample_index: int = 0,
        temperature: float = 0.0,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        # EVERYTHING THAT CHANGES THE ANSWER GOES IN THE KEY. max_tokens and
        # reasoning_effort were absent, so raising a budget or lowering an
        # effort served the PREVIOUS answer from disk as though it were the
        # new configuration's. Caught the worst way: S0 rerun with
        # reasoning_effort=low reported 16,000 tokens and a truncation, which
        # was the old entry. A cache that survives a parameter change is not a
        # cache, it is a stale result.
        payload = {
            "model": self.info.spec,
            "messages": messages,
            "temperature": temperature,
            "sample_index": sample_index,
            "max_tokens": max_tokens or self.info.max_tokens,
            "reasoning_effort": self.info.reasoning_effort,
        }
        path = self._cache_path(payload)
        if path.exists():
            data = json.loads(path.read_text())
            # Older cache entries predate the flag; absent means "not known to
            # be truncated", never "known not to be".
            data.setdefault("truncated", False)
            return LLMResponse(**data, cached=True)

        if self._client is None:
            from openai import OpenAI

            self._client = OpenAI(base_url=self.info.base_url, api_key=self._api_key)

        t0 = time.monotonic()
        # `temperature` stays in the CACHE KEY above even when it is not sent:
        # two sampling requests must not collide just because the model has no
        # dial for them, or rung 3's k votes would be one answer k times.
        params: dict[str, Any] = {
            "model": self.info.model,
            "messages": messages,
            # The model's own budget unless the caller overrides it.
            "max_tokens": max_tokens or self.info.max_tokens,
            "timeout": self.info.timeout_s,
        }
        if self.info.sampling:
            params["temperature"] = temperature
        if self.info.reasoning_effort:
            params["reasoning_effort"] = self.info.reasoning_effort
        try:
            resp = self._client.chat.completions.create(**params)
        except _timeout_errors() as exc:
            # NOT raised onward, and NOT cached. A run that dies on one
            # runaway document has measured nothing; a run that records the
            # timeout has measured the other 39 and one timeout, which is a
            # result. And a timeout is a property of this run — of load, of
            # this machine — not of the question, so caching it would make the
            # answer permanently unavailable on every later run.
            print(f"[llm] timed out after {self.info.timeout_s}s: {exc}", file=sys.stderr)
            return LLMResponse(
                text="", prompt_tokens=0, completion_tokens=0,
                latency_s=round(time.monotonic() - t0, 3),
                truncated=True, timed_out=True,
            )
        latency = time.monotonic() - t0
        usage = resp.usage
        choice = resp.choices[0]
        data = {
            "text": choice.message.content or "",
            "prompt_tokens": usage.prompt_tokens if usage else 0,
            "completion_tokens": usage.completion_tokens if usage else 0,
            "latency_s": round(latency, 3),
            # Cached alongside the text: a cached reply that was truncated is
            # still truncated, or one run reports two different failure counts.
            "truncated": getattr(choice, "finish_reason", None) == "length",
        }
        path.write_text(json.dumps(data, ensure_ascii=False))
        return LLMResponse(**data, cached=False)


# --- one call path for every rung --------------------------------------------
#
# Rungs must not choose models. A rung that reads a model name is a rung whose
# number changes meaning when someone edits a config, and four rungs each doing
# their own resolution is four places to change and three places to forget.
# So: the manifest names a model per ROLE, run.py binds a Caller per rung, and
# a rung only ever sees `cfg["llm"]` — a plain callable it invokes.
#
#     raw, usage = cfg["llm"](prompt, source, mode)
#
# Roles, not rung numbers, because that is how the plan constrains them: rung 4
# judges what rung 0 extracted and MUST be a different model family, or it
# shares the extractor's blind spots. Rungs 2 and 3 correct and re-sample the
# extractor's own work, so they are the extractor by definition.

ROLE_BY_RUNG = {0: "extractor", 2: "extractor", 3: "extractor", 4: "judge"}

# NO DEFAULT MODEL HERE, DELIBERATELY.
#
# `llm.py` used to carry DEFAULT_MODEL = "ollama/gpt-oss:20b" while
# `manifest.model.extractor` said granite4:micro-h, so "which model produced
# this number" had two answers depending on whether a manifest reached the
# call. A silent fallback is the exact defect centralising model selection was
# meant to remove: the run still produces numbers, just not the ones the
# manifest describes. The manifest is the one place a model is named, and a
# missing entry raises.

_FENCE = re.compile(r"^\s*```(?:json)?\s*\n(.*?)\n\s*```\s*$", re.S)
#: The same fence with a preamble in front of it. Kept SEPARATE from
#: _FENCE, which is anchored deliberately: an anchored match is the strict
#: reading and this is the fallback, so the two cases stay countable apart.
_FENCE_LOOSE = re.compile(r"```(?:json)?\s*\n(.*?)\n\s*```", re.S)


class Caller:
    """A bound model, callable with the signature every rung expects.

        caller(prompt, text, mode) -> (raw_text, usage)

    Holds its own latencies and fence count, so two rungs on two models never
    pool their cost measures into one misleading number.

    LICENCE: rung prompts carry CADEC post text verbatim, and CADEC is
    non-commercial and NON-TRANSFERABLE. Any provider with `local: false` puts
    licensed text on someone else's machine, so a non-local model is refused
    unless LADDER_ALLOW_REMOTE=1 makes that a deliberate act.

    FENCES: a markdown fence around JSON is a transport convention, not a
    modelling failure, so it is stripped — but counted in `fenced` and never
    silently. Nothing inside the fence is touched.
    """

    def __init__(self, spec: str, role: str = "", cache_dir: Path | str = DEFAULT_CACHE_DIR):
        self.spec = spec
        self.role = role
        self.client = LLMClient(spec, cache_dir=cache_dir)
        self.latencies: list[float] = []
        self.fenced = 0
        self.preambled = 0
        self.unwrapped = 0
        self.unclosed = 0
        if not self.client.info.local and os.environ.get("LADDER_ALLOW_REMOTE") != "1":
            raise SystemExit(
                f"{spec} is a hosted provider, and rung prompts contain CADEC post\n"
                "text, which is non-transferable. Set LADDER_ALLOW_REMOTE=1 if you\n"
                "have decided that is acceptable for this run."
            )

    def _reclose(self, raw: str) -> str:
        """Append the one closing brace a stopped-short reply is missing.

        Measured 2026-08-25 (BioMistral-7B on the 240-record re-judge): 91
        replies were a complete judgement that hit EOS immediately before the
        final "}" — finish_reason stop, valid JSON plus one brace. Same class
        as a markdown fence: repaired centrally, counted in `unclosed`, never
        silent. Fires only when the text does not parse, text+"}" does, and
        the result is non-empty — " {" must NOT become a fabricated {}.
        """
        try:
            json.loads(raw)
            return raw
        except json.JSONDecodeError:
            pass
        try:
            repaired = json.loads(raw + "}")
        except json.JSONDecodeError:
            return raw
        if not repaired:
            return raw
        self.unclosed += 1
        return raw + "}"

    def _unfence(self, raw: str) -> str:
        m = _FENCE.match(raw)
        if not m:
            # SEARCH rather than MATCH: some models put a sentence before the
            # fence ("Here are the reported financial facts:"). Measured on
            # FiNER: llama3.1:8b did this on 60 of 60 documents, and every one
            # of the 60 contained a CORRECT extraction that the parser
            # rejected on presentation. An anchored match makes the parse rate
            # a measure of one model's output conventions rather than of
            # extraction, which is the opposite of what it is for.
            m = _FENCE_LOOSE.search(raw)
            if not m:
                return raw
            self.preambled += 1
        self.fenced += 1
        return m.group(1)

    def _unwrap_array(self, raw: str) -> str:
        """A bare JSON array where an object was expected.

        Same class as the fence and the missing brace: a transport convention,
        not a modelling failure. llama3.1:8b returns [{...}] where the schema
        asks for {"mentions": [{...}]} — the CONTENT is right and the envelope
        is not. Wrapped, counted in `unwrapped`, and only ever when the parse
        would otherwise fail and the payload is genuinely a list.
        """
        t = raw.strip()
        if not (t.startswith("[") and t.endswith("]")):
            return raw
        try:
            import json as _j
            if not isinstance(_j.loads(t), list):
                return raw
        except Exception:
            return raw
        self.unwrapped += 1
        return '{"mentions": ' + t + "}"

    def __call__(
        self,
        prompt: str,
        text: str,
        mode: str,
        temperature: float = 0.0,
        sample_index: int = 0,
    ) -> tuple[str, dict]:
        t0 = time.time()
        # A rung whose template embeds the post passes text="" — appending a
        # POST section anyway would send the post twice (rung 4 did, measured
        # 2026-08-25: doubled judge prompts) or dangle an empty header.
        content = f"{prompt}\n\nPOST:\n{text}" if text else prompt
        resp = self.client.chat(
            [{"role": "user", "content": content}],
            temperature=temperature,
            sample_index=sample_index,
        )
        elapsed = time.time() - t0
        if not resp.cached:
            self.latencies.append(elapsed)
        usage = {
            "in": resp.prompt_tokens,
            "out": resp.completion_tokens,
            "seconds": round(elapsed, 3),
            "model": self.spec,
            "cached": resp.cached,
            "timed_out": resp.timed_out,
            "usd": self.client.info.dollars(resp.prompt_tokens, resp.completion_tokens),
            # The rung logs this. Without it the flag stops at the client and
            # nothing downstream can tell a cut-off reply from a bad one.
            "truncated": resp.truncated,
        }
        return self._unwrap_array(self._reclose(self._unfence(resp.text))), usage

    def sampler(self, temperature: float):
        """A callable that draws a DIFFERENT sample each time it is called.

        Rung 3 votes by calling the extractor k times. Greedy decoding would
        return one answer k times and a disk cache would make that free and
        invisible — k identical votes reported as unanimity. So each call gets
        its own `sample_index`, which is part of the cache key: samples stay
        reproducible across runs while still differing from each other.
        """
        if temperature <= 0.0:
            raise ValueError(
                f"sampler(temperature={temperature}) cannot vote: at temperature 0 "
                "every sample is the same answer, and k of them is not a majority."
            )
        counter = {"i": -1}

        def draw(prompt: str, text: str, mode: str) -> tuple[str, dict]:
            counter["i"] += 1
            return self(prompt, text, mode, temperature=temperature,
                        sample_index=counter["i"])

        draw.spec = self.spec  # type: ignore[attr-defined]
        draw.role = self.role  # type: ignore[attr-defined]
        return draw

    def latency_p95(self) -> float | None:
        """p95 over uncached calls. One of the three cost measures; never fused."""
        if not self.latencies:
            return None
        s = sorted(self.latencies)
        return s[max(0, int(len(s) * 0.95) - 1)]


def resolve(role: str, manifest: dict | None = None, override: str | None = None) -> str:
    """Which model plays `role`. Explicit > env > manifest, and then it stops.

    There is no fallback. A run whose manifest does not name a model is a run
    nobody can attribute, and guessing one produces numbers that describe a
    model the results file does not mention.
    """
    spec = (
        override
        or os.environ.get("LADDER_MODEL_SPEC")
        or ((manifest or {}).get("model") or {}).get(role)
    )
    if not spec:
        raise SystemExit(
            f"no model for role {role!r}. Set manifest.model.{role}, or pass "
            f"--extractor / LADDER_MODEL_SPEC for a single run.\n"
            "manifest.model is the ONE place a model is named — see "
            "ladder/llm.py:for_rung."
        )
    return spec


def for_rung(n: int, manifest: dict | None = None, override: str | None = None) -> Caller | None:
    """The Caller a rung should be handed, or None if that rung needs no model."""
    role = ROLE_BY_RUNG.get(n)
    if role is None:
        return None
    return Caller(resolve(role, manifest, override), role=role)

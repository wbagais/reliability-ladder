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

import yaml
from typing import Any

REGISTRY_PATH = Path(__file__).parent / "models.yaml"

#: Completion tokens allowed when models.yaml names no budget. Enough for a
#: document's worth of mentions from an instruct model; a reasoning model
#: needs its own entry — see ModelInfo.max_tokens.
DEFAULT_MAX_TOKENS = 2000
DEFAULT_CACHE_DIR = Path(__file__).parent.parent / ".llm_cache"


@dataclass
class LLMResponse:
    text: str
    prompt_tokens: int
    completion_tokens: int
    latency_s: float
    cached: bool = False


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
        payload = {
            "model": self.info.spec,
            "messages": messages,
            "temperature": temperature,
            "sample_index": sample_index,
        }
        path = self._cache_path(payload)
        if path.exists():
            data = json.loads(path.read_text())
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
        }
        if self.info.sampling:
            params["temperature"] = temperature
        resp = self._client.chat.completions.create(**params)
        latency = time.monotonic() - t0
        usage = resp.usage
        data = {
            "text": resp.choices[0].message.content or "",
            "prompt_tokens": usage.prompt_tokens if usage else 0,
            "completion_tokens": usage.completion_tokens if usage else 0,
            "latency_s": round(latency, 3),
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

#: Local, free, and no corpus text leaves the machine. See LICENCE note below.
DEFAULT_MODEL = "ollama/gpt-oss:20b"

_FENCE = re.compile(r"^\s*```(?:json)?\s*\n(.*?)\n\s*```\s*$", re.S)


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
        if not self.client.info.local and os.environ.get("LADDER_ALLOW_REMOTE") != "1":
            raise SystemExit(
                f"{spec} is a hosted provider, and rung prompts contain CADEC post\n"
                "text, which is non-transferable. Set LADDER_ALLOW_REMOTE=1 if you\n"
                "have decided that is acceptable for this run."
            )

    def _unfence(self, raw: str) -> str:
        m = _FENCE.match(raw)
        if not m:
            return raw
        self.fenced += 1
        return m.group(1)

    def __call__(
        self,
        prompt: str,
        text: str,
        mode: str,
        temperature: float = 0.0,
        sample_index: int = 0,
    ) -> tuple[str, dict]:
        t0 = time.time()
        resp = self.client.chat(
            [{"role": "user", "content": f"{prompt}\n\nPOST:\n{text}"}],
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
            "usd": self.client.info.dollars(resp.prompt_tokens, resp.completion_tokens),
        }
        return self._unfence(resp.text), usage

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
    """Which model plays `role`. Explicit > env > manifest > default."""
    return (
        override
        or os.environ.get("LADDER_MODEL_SPEC")
        or ((manifest or {}).get("model") or {}).get(role)
        or DEFAULT_MODEL
    )


def for_rung(n: int, manifest: dict | None = None, override: str | None = None) -> Caller | None:
    """The Caller a rung should be handed, or None if that rung needs no model."""
    role = ROLE_BY_RUNG.get(n)
    if role is None:
        return None
    return Caller(resolve(role, manifest, override), role=role)

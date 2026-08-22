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
import time
from dataclasses import dataclass
from pathlib import Path

import yaml

REGISTRY_PATH = Path(__file__).parent / "models.yaml"
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
        max_tokens: int = 2000,
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
        resp = self._client.chat.completions.create(
            model=self.info.model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
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

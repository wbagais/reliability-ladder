"""The model registry, and the one request parameter that is not universal.

No network: `ModelInfo` only reads `ladder/models.yaml`, and the sampling test
inspects the payload the client would send rather than sending it.

WHY `sampling` EXISTS. The Claude 5 family removed `temperature`, `top_p` and
`top_k` — sending any of them returns a 400. Every rung here calls with
`temperature=0` because determinism is a project-wide choice, so without this
flag a Claude 5 extractor fails on its first request. The flag is per-model
registry data, not a special case in a rung: a rung must not know which family
it is talking to.
"""

import pytest

from ladder.llm import ModelInfo


def test_the_local_default_is_still_local():
    info = ModelInfo("ollama/gpt-oss:20b")
    assert info.local is True
    assert info.dollars(1000, 1000) == 0.0


def test_claude_sonnet_5_is_registered():
    info = ModelInfo("anthropic/claude-sonnet-5")
    assert info.local is False
    assert info.api_key_env == "ANTHROPIC_API_KEY"


def test_claude_sonnet_5_is_priced():
    """Intro pricing to 2026-08-31: $2.00 in / $10.00 out per million."""
    info = ModelInfo("anthropic/claude-sonnet-5")
    assert info.dollars(1_000_000, 0) == pytest.approx(2.00)
    assert info.dollars(0, 1_000_000) == pytest.approx(10.00)


def test_an_unregistered_model_falls_back_to_provider_pricing():
    info = ModelInfo("anthropic/claude-haiku-4-5-20251001")
    assert info.dollars(1_000_000, 0) == pytest.approx(1.00)


# --- sampling: the parameter the Claude 5 family rejects --------------------


def test_ollama_accepts_sampling_parameters():
    assert ModelInfo("ollama/gpt-oss:20b").sampling is True


def test_claude_sonnet_5_refuses_sampling_parameters():
    assert ModelInfo("anthropic/claude-sonnet-5").sampling is False


def test_claude_haiku_4_5_still_accepts_them():
    """The removal is Claude 5 only. Haiku 4.5 is unaffected."""
    assert ModelInfo("anthropic/claude-haiku-4-5-20251001").sampling is True


def test_temperature_is_omitted_for_a_model_that_rejects_it(monkeypatch, tmp_path):
    """A rung asking for temperature=0 must not 400 on a Claude 5 model.

    Determinism is still requested; the model simply has no dial for it, and
    that is the registry's business rather than the rung's.
    """
    from ladder.llm import LLMClient

    sent = {}

    class FakeCompletions:
        def create(self, **kw):
            sent.update(kw)
            raise RuntimeError("stop here — the payload is what is under test")

    class FakeClient:
        def __init__(self, **kw):
            self.chat = type("C", (), {"completions": FakeCompletions()})()

    c = LLMClient("anthropic/claude-sonnet-5", cache_dir=tmp_path, api_key="x")
    c._client = FakeClient()
    with pytest.raises(RuntimeError):
        c.chat([{"role": "user", "content": "hi"}], temperature=0.0)
    assert "temperature" not in sent


def test_temperature_is_sent_to_a_model_that_accepts_it(monkeypatch, tmp_path):
    from ladder.llm import LLMClient

    sent = {}

    class FakeCompletions:
        def create(self, **kw):
            sent.update(kw)
            raise RuntimeError("stop")

    class FakeClient:
        def __init__(self, **kw):
            self.chat = type("C", (), {"completions": FakeCompletions()})()

    c = LLMClient("ollama/gpt-oss:20b", cache_dir=tmp_path)
    c._client = FakeClient()
    with pytest.raises(RuntimeError):
        c.chat([{"role": "user", "content": "hi"}], temperature=0.7)
    assert sent["temperature"] == 0.7


def test_the_cache_key_still_records_the_requested_temperature(tmp_path):
    """Omitting the parameter must NOT make two different sampling requests
    collide in the cache — rung 3's k votes depend on that separation."""
    from ladder.llm import LLMClient

    c = LLMClient("anthropic/claude-sonnet-5", cache_dir=tmp_path, api_key="x")
    msgs = [{"role": "user", "content": "hi"}]
    a = c._cache_path({"model": c.info.spec, "messages": msgs, "temperature": 0.0, "sample_index": 0})
    b = c._cache_path({"model": c.info.spec, "messages": msgs, "temperature": 0.7, "sample_index": 0})
    assert a != b


# --- selecting the extractor for one run ------------------------------------


def test_run_py_exposes_an_extractor_flag(monkeypatch):
    """Comparing models must not require editing the append-only manifest."""
    from ladder import run as run_mod

    seen = {}

    def fake(man, split, rungs, records, sources, registry, out_dir, run_id, meddra=None):
        seen.update(man["model"])
        raise SystemExit(0)

    monkeypatch.setattr(run_mod, "run_ladder", fake)
    with pytest.raises(SystemExit):
        run_mod.main(["ladder", "--extractor", "anthropic/claude-sonnet-5",
                      "--split", "dev", "--limit", "1"])
    assert seen["extractor"] == "anthropic/claude-sonnet-5"


def test_the_extractor_flag_leaves_the_judge_alone():
    """Rung 4 must stay a different family — the flag must not touch it."""
    from ladder.run import apply_overrides
    import json

    man = json.load(open("manifest.json"))
    judge = man["model"]["judge"]
    out = apply_overrides(man, extractor="anthropic/claude-sonnet-5", rung0_step=None)
    assert out["model"]["judge"] == judge

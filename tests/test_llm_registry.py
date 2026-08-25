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


# --- the output budget is per MODEL, not a global constant -------------------
#
# Measured 2026-08-24 on ARTHROTEC.107: gpt-oss:20b returned exactly 2000
# completion tokens for S0 and S2 and both were logged parse_failed /
# json_decode. It is a REASONING model — it spends the budget thinking before
# it emits the JSON, so a cap tuned for a 2B instruct model truncates it
# mid-structure every time.
#
# That failure is indistinguishable in the ledger from a model that cannot
# produce JSON, which is the reliability number rung 0 exists to report. A
# harness-imposed truncation counted as a model failure is a measurement of
# the harness.


def test_max_tokens_comes_from_the_registry():
    """models.yaml carries the budget, so a reasoning model can be given room
    without moving it for every model."""
    from ladder.llm import ModelInfo

    info = ModelInfo("ollama/gpt-oss:20b")
    assert info.max_tokens >= 8000, "a reasoning model needs room to think"


def test_an_ordinary_model_keeps_the_default_budget():
    from ladder.llm import DEFAULT_MAX_TOKENS, ModelInfo

    info = ModelInfo("ollama/ibm/granite4:micro-h")
    assert info.max_tokens == DEFAULT_MAX_TOKENS


def test_the_caller_sends_the_models_own_budget(monkeypatch):
    """The number has to REACH the request, or the registry entry is decoration."""
    from ladder.llm import LLMClient

    sent = {}

    class FakeCompletions:
        def create(self, **kw):
            sent.update(kw)
            raise RuntimeError("stop here — the payload is the assertion")

    class FakeClient:
        def __init__(self, **kw):
            self.chat = type("C", (), {"completions": FakeCompletions()})()

    client = LLMClient("ollama/gpt-oss:20b")
    client._client = FakeClient()
    try:
        client.chat([{"role": "user", "content": "hi"}])
    except RuntimeError:
        pass
    assert sent["max_tokens"] >= 8000


# --- a truncation is not a model failure -------------------------------------
#
# Measured 2026-08-24: gpt-oss:20b at S0 burned all 16,000 completion tokens
# and returned an EMPTY STRING. The ledger logged parse_failed / json_decode —
# identical to a model that emitted malformed JSON, which is the specific
# reliability number rung 0 exists to report.
#
# They are not the same event. One is the model failing; the other is the
# harness cutting it off. Raising the cap does not fix that — it just moves
# where the confusion happens. The provider already says which occurred
# (finish_reason == "length"), so it is recorded.


class _Resp:
    def __init__(self, text, finish_reason):
        self.choices = [type("C", (), {
            "message": type("M", (), {"content": text})(),
            "finish_reason": finish_reason,
        })()]
        self.usage = type("U", (), {"prompt_tokens": 10, "completion_tokens": 20})()


def _client_returning(resp, tmp_path):
    from ladder.llm import LLMClient

    class FakeCompletions:
        def create(self, **kw):
            return resp

    client = LLMClient("ollama/gpt-oss:20b", cache_dir=tmp_path)
    client._client = type("C", (), {
        "chat": type("Ch", (), {"completions": FakeCompletions()})()
    })()
    return client


def test_a_completed_reply_is_not_truncated(tmp_path):
    client = _client_returning(_Resp('{"mentions":[]}', "stop"), tmp_path)
    assert client.chat([{"role": "user", "content": "x"}]).truncated is False


def test_hitting_the_cap_is_recorded_as_truncated(tmp_path):
    client = _client_returning(_Resp("", "length"), tmp_path)
    assert client.chat([{"role": "user", "content": "x"}]).truncated is True


def test_truncation_survives_the_cache(tmp_path):
    """A cached reply that was truncated is still truncated. Losing the flag on
    a rerun would make the same run report two different failure counts."""
    client = _client_returning(_Resp("", "length"), tmp_path)
    client.chat([{"role": "user", "content": "x"}])
    again = client.chat([{"role": "user", "content": "x"}])
    assert again.cached is True
    assert again.truncated is True


def test_the_caller_passes_truncation_through_to_the_rung(tmp_path):
    """usage["truncated"] is what a rung logs. Without it the flag stops at
    the client and nothing downstream can tell the two failures apart."""
    from ladder.llm import Caller

    caller = Caller("ollama/gpt-oss:20b", cache_dir=tmp_path)
    caller.client = _client_returning(_Resp("", "length"), tmp_path)
    _, usage = caller("prompt", "text", "S0")
    assert usage["truncated"] is True

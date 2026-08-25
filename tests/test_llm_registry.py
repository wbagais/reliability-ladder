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

import os

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


# --- ONE place names a model -------------------------------------------------
#
# `manifest.model` said granite4:micro-h while `llm.py` said gpt-oss:20b, so
# "which model produced this number" had two answers depending on whether a
# manifest reached the call. A silent fallback is exactly the defect that
# centralising model selection was supposed to remove: the run still produces
# numbers, just not the ones the manifest describes.
#
# The manifest is the single source. A missing entry RAISES.


def test_llm_py_names_no_model_of_its_own():
    """A constant here is a second manifest that nobody edits."""
    import ladder.llm as m

    assert not hasattr(m, "DEFAULT_MODEL"), (
        "ladder/llm.py must not carry a model name — manifest.model is the "
        "one place a model is chosen."
    )


def test_a_missing_manifest_entry_raises_rather_than_guessing():
    from ladder.llm import resolve

    with pytest.raises(SystemExit, match="manifest.model"):
        resolve("extractor", {"model": {}})


def test_the_manifest_supplies_the_model():
    from ladder.llm import resolve

    assert resolve("extractor", {"model": {"extractor": "ollama/x:1"}}) == "ollama/x:1"


def test_an_explicit_override_still_wins():
    """--extractor on the command line, for one run, without editing shared
    config. It is recorded in the manifest copy saved beside the results."""
    from ladder.llm import resolve

    got = resolve("extractor", {"model": {"extractor": "ollama/x:1"}}, "ollama/y:2")
    assert got == "ollama/y:2"


def test_the_env_override_still_wins_over_the_manifest():
    from ladder.llm import resolve

    os.environ["LADDER_MODEL_SPEC"] = "ollama/z:3"
    try:
        assert resolve("extractor", {"model": {"extractor": "ollama/x:1"}}) == "ollama/z:3"
    finally:
        del os.environ["LADDER_MODEL_SPEC"]


# --- reasoning_effort: the fix for S0 ---------------------------------------
#
# gpt-oss:20b writes its chain of thought to a SEPARATE `reasoning` field and
# leaves `content` empty until it finishes. Measured 2026-08-24 on rung 0's S0
# (ARTHROTEC.107), which asks the model to recall a nine-digit SNOMED id:
#
#     default effort, 16000 cap   16000 tokens   content EMPTY   truncated
#     default effort, 32000 cap    2306 tokens   content OK        34s
#     reasoning_effort=medium      8000 tokens   content EMPTY   truncated
#     reasoning_effort=low          104 tokens   content OK         2s
#
# 104 tokens against 16,000, and two seconds against a truncation. Registry
# data like max_tokens and sampling, because it is a property of the MODEL —
# a rung must not know which family it is calling.


def test_reasoning_effort_is_unset_for_the_extractor():
    """Measured over 3 documents / 17 gold mentions: at effort=low S0 finds
    ONE. That is not a speed-up, it is a different experiment — and scope must
    be identical across S0/S1/S2, so the effort cannot differ per step either.
    The mechanism stays; the value is deliberately absent."""
    assert ModelInfo("ollama/gpt-oss:20b").reasoning_effort is None


def test_a_model_with_no_reasoning_channel_declares_none():
    """Sending reasoning_effort to a model that has no such parameter is at
    best ignored and at worst a 400."""
    assert ModelInfo("ollama/ibm/granite4:micro-h").reasoning_effort is None


def test_reasoning_effort_reaches_the_request(tmp_path):
    from ladder.llm import LLMClient

    sent = {}

    class FakeCompletions:
        def create(self, **kw):
            sent.update(kw)
            raise RuntimeError("payload captured")

    client = LLMClient("ollama/gpt-oss:20b", cache_dir=tmp_path)
    client.info.reasoning_effort = "low"      # as if models.yaml declared it
    client._client = type("C", (), {
        "chat": type("Ch", (), {"completions": FakeCompletions()})()})()
    try:
        client.chat([{"role": "user", "content": "hi"}])
    except RuntimeError:
        pass
    assert sent["reasoning_effort"] == "low"


def test_it_is_omitted_for_models_that_do_not_declare_it(tmp_path):
    from ladder.llm import LLMClient

    sent = {}

    class FakeCompletions:
        def create(self, **kw):
            sent.update(kw)
            raise RuntimeError("payload captured")

    client = LLMClient("ollama/ibm/granite4:micro-h", cache_dir=tmp_path)
    client._client = type("C", (), {
        "chat": type("Ch", (), {"completions": FakeCompletions()})()})()
    try:
        client.chat([{"role": "user", "content": "hi"}])
    except RuntimeError:
        pass
    assert "reasoning_effort" not in sent


# --- the cache key must cover everything that changes the answer ------------
#
# The key was (model, messages, temperature, sample_index). max_tokens and
# reasoning_effort were absent, so raising a budget or lowering an effort
# returned the PREVIOUS answer from disk — a cached reply produced under
# different parameters, served as though it were the new configuration's.
#
# Caught in the worst possible way: S0 was rerun with reasoning_effort=low and
# reported 16,000 tokens and a truncation, which was the old entry. A cache
# that survives a parameter change is not a cache, it is a stale result.


def _spy_client(spec, tmp_path, text='{"ok":1}'):
    from ladder.llm import LLMClient

    calls = []

    class FakeCompletions:
        def create(self, **kw):
            calls.append(kw)
            return _Resp(text, "stop")

    client = LLMClient(spec, cache_dir=tmp_path)
    client._client = type("C", (), {
        "chat": type("Ch", (), {"completions": FakeCompletions()})()})()
    return client, calls


def test_a_repeat_call_is_served_from_cache(tmp_path):
    """The property being protected: reruns are free and resumable."""
    client, calls = _spy_client("ollama/gpt-oss:20b", tmp_path)
    msgs = [{"role": "user", "content": "hi"}]
    client.chat(msgs)
    assert client.chat(msgs).cached is True
    assert len(calls) == 1


def test_changing_max_tokens_does_not_reuse_the_old_answer(tmp_path):
    client, calls = _spy_client("ollama/gpt-oss:20b", tmp_path)
    msgs = [{"role": "user", "content": "hi"}]
    client.chat(msgs, max_tokens=2000)
    client.chat(msgs, max_tokens=16000)
    assert len(calls) == 2, "a different budget is a different experiment"


def test_changing_reasoning_effort_does_not_reuse_the_old_answer(tmp_path):
    from ladder.llm import LLMClient

    a, calls_a = _spy_client("ollama/gpt-oss:20b", tmp_path)
    msgs = [{"role": "user", "content": "hi"}]
    a.chat(msgs)
    b, calls_b = _spy_client("ollama/gpt-oss:20b", tmp_path)
    b.info.reasoning_effort = "high"
    b.chat(msgs)
    assert len(calls_b) == 1, "a different reasoning effort is a different run"


# --- one runaway must not hang a whole split --------------------------------
#
# Measured 2026-08-24 on the dev split, S1, gpt-oss:20b over 30 documents
# (median length 309 characters):
#
#     completion tokens   median 1,029   p90 3,244   max 7,836
#     latency seconds     median    32   p90    98   max   694
#
# Then it stopped. One call ran past 25 minutes generating toward the 32,000
# cap on a 761-character forum post — a reasoning runaway, not work. Ninety
# percent of calls finish under 3,244 tokens; the tail is what makes a
# 40-document run unbounded.
#
# A timeout turns "the run never finishes" into "one record is recorded as
# timed out". That is the difference between a measurement and a hang.


def test_timeout_comes_from_the_registry():
    assert ModelInfo("ollama/gpt-oss:20b").timeout_s == 300


def test_a_model_with_no_entry_gets_the_default():
    from ladder.llm import DEFAULT_TIMEOUT_S

    assert ModelInfo("ollama/ibm/granite4:micro-h").timeout_s == DEFAULT_TIMEOUT_S


def test_the_timeout_reaches_the_request(tmp_path):
    from ladder.llm import LLMClient

    sent = {}

    class FakeCompletions:
        def create(self, **kw):
            sent.update(kw)
            raise RuntimeError("payload captured")

    client = LLMClient("ollama/gpt-oss:20b", cache_dir=tmp_path)
    client._client = type("C", (), {
        "chat": type("Ch", (), {"completions": FakeCompletions()})()})()
    try:
        client.chat([{"role": "user", "content": "hi"}])
    except RuntimeError:
        pass
    assert sent["timeout"] == 300


def test_a_timeout_is_reported_as_an_empty_timed_out_response(tmp_path):
    """It must NOT raise. A run that dies on one runaway document has measured
    nothing; a run that records the timeout has measured 39 documents and one
    timeout, which is a result."""
    import openai
    from ladder.llm import LLMClient

    class FakeCompletions:
        def create(self, **kw):
            raise openai.APITimeoutError(request=None)

    client = LLMClient("ollama/gpt-oss:20b", cache_dir=tmp_path)
    client._client = type("C", (), {
        "chat": type("Ch", (), {"completions": FakeCompletions()})()})()
    resp = client.chat([{"role": "user", "content": "hi"}])
    assert resp.text == ""
    assert resp.timed_out is True
    assert resp.truncated is True, "nothing usable came back, like any cut-off"


def test_a_timeout_is_not_cached(tmp_path):
    """A timeout is a property of the run, not of the question. Caching it
    would make the answer permanently unavailable on every later run."""
    import openai
    from ladder.llm import LLMClient

    calls = []

    class FakeCompletions:
        def create(self, **kw):
            calls.append(kw)
            raise openai.APITimeoutError(request=None)

    client = LLMClient("ollama/gpt-oss:20b", cache_dir=tmp_path)
    client._client = type("C", (), {
        "chat": type("Ch", (), {"completions": FakeCompletions()})()})()
    msgs = [{"role": "user", "content": "hi"}]
    client.chat(msgs)
    client.chat(msgs)
    assert len(calls) == 2

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


def _needs_corpus():
    """Skip when the licensed CADEC download is absent.

    These tests drive ladder.run.main, which loads the corpus before it
    reaches the code under test and returns 2 instead of raising. CI has no
    corpus, so without this they fail on a missing prerequisite rather than
    on the flag they are about.
    """
    import json as _json
    import pathlib as _pathlib

    man = _json.loads(_pathlib.Path("manifest.json").read_text())
    root = _pathlib.Path(man["corpus"]["cadec_root"])
    if not (root / "text").is_dir():
        pytest.skip(f"no corpus at {root} — these tests drive run.main()")


def test_run_py_exposes_an_extractor_flag(monkeypatch):
    """Comparing models must not require editing the append-only manifest."""
    from ladder import run as run_mod

    seen = {}

    def fake(man, split, rungs, records, sources, registry, out_dir, run_id, meddra=None):
        seen.update(man["model"])
        raise SystemExit(0)

    monkeypatch.setattr(run_mod, "run_ladder", fake)
    # main() loads the corpus BEFORE it reaches run_ladder, and returns 2
    # rather than raising when the corpus is absent. CI has no corpus, so the
    # flag under test is never reached there.
    _needs_corpus()
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


# --- BioMistral-7B: the rung-4 judge (Phase C) -------------------------------
#
# The judge was granite4:micro-h — a 2B judging a 20B extractor, the wrong way
# round, kept only because it was the sole locally installed family that
# differed from the extractor. BioMistral-7B (Q5_K_M, imported 2026-08-25, see
# docs/decisions.md) is a third family, domain-adapted to medical text, and
# 3.5x the old judge's size. It is a NON-reasoning instruct model: the judge
# reply is one JSON line (smoke test: 39 completion tokens), so its budgets are
# small and explicit rather than inherited defaults.


def test_biomistral_is_registered_and_local():
    info = ModelInfo("ollama/biomistral:7b-q5_k_m")
    assert info.local is True
    assert info.dollars(1000, 1000) == 0.0


def test_biomistral_has_a_small_explicit_output_budget():
    """One JSON line, not a chain of thought. 512 is 13x the measured reply."""
    assert ModelInfo("ollama/biomistral:7b-q5_k_m").max_tokens == 512


def test_biomistral_has_an_explicit_timeout():
    """240 records x one call each: a hung call must cost one record."""
    assert ModelInfo("ollama/biomistral:7b-q5_k_m").timeout_s == 120


def test_biomistral_declares_no_reasoning_channel():
    """Mistral-instruct has no reasoning_effort parameter to send."""
    assert ModelInfo("ollama/biomistral:7b-q5_k_m").reasoning_effort is None


def test_the_manifest_judge_is_still_granite():
    """Phase C swapped BioMistral-7B in and the measurement swapped it back
    out (2026-08-25, docs/decisions.md): 167 of 240 records unjudged even
    after two harness repairs, every parsed verdict "fail" (code_ok false on
    72 of 73, including |Lower back pain| for "Lower Back Pain"), confidence
    flat 0.0 so rung 5 has nothing to sweep. The judge remains granite — the
    2B-judging-20B caveat stands, now as the measured lesser evil. BioMistral
    stays registered above so the arm is reproducible; it must not be the
    judge a full-ladder run silently picks up."""
    import json

    man = json.load(open("manifest.json"))
    assert man["model"]["judge"] == "ollama/ibm/granite4:micro-h"
    assert man["model"]["extractor"] != man["model"]["judge"]


# --- a caller given no post sends no POST section ----------------------------
#
# Caller appends "\n\nPOST:\n{text}" for the rung-0 shape, where the prompt is
# instructions and the text is the document. Rung 4's template embeds the post
# ITSELF (the claim must follow the post), and passing the source again through
# `text` sent every post twice — measured 2026-08-25 on the 240-record re-judge:
# judge prompts at a median 582 tokens where the post once would be ~350, and
# BioMistral-7B answers a 312-token prompt but EOSes after "{" at 582. The fix
# is that a rung which embeds the post passes text="" and the suffix vanishes;
# a dangling "POST:" header over nothing would be an invitation to hallucinate.


def test_an_empty_text_sends_the_bare_prompt(tmp_path):
    from ladder.llm import Caller

    caller = Caller("ollama/gpt-oss:20b", cache_dir=tmp_path)
    caller.client = _client_returning(_Resp('{"ok":1}', "stop"), tmp_path)
    sent = {}

    class FakeCompletions:
        def create(self, **kw):
            sent.update(kw)
            return _Resp('{"ok":1}', "stop")

    caller.client._client = type("C", (), {
        "chat": type("Ch", (), {"completions": FakeCompletions()})()})()
    caller("the whole prompt, post included", "", "judge")
    assert sent["messages"][0]["content"] == "the whole prompt, post included"


def test_a_nonempty_text_still_gets_the_post_section(tmp_path):
    from ladder.llm import Caller

    caller = Caller("ollama/gpt-oss:20b", cache_dir=tmp_path)
    sent = {}

    class FakeCompletions:
        def create(self, **kw):
            sent.update(kw)
            return _Resp('{"ok":1}', "stop")

    caller.client._client = type("C", (), {
        "chat": type("Ch", (), {"completions": FakeCompletions()})()})()
    caller("instructions", "the post", "S1")
    assert sent["messages"][0]["content"] == "instructions\n\nPOST:\nthe post"


# --- a reply that stopped one brace short is repaired, and counted -----------
#
# Measured 2026-08-25, BioMistral-7B judging the 240-record replay: 91 replies
# were a complete, correct judgement that hit EOS immediately BEFORE the
# closing "}" — finish_reason stop, not truncated, valid JSON the moment the
# brace is appended. That is a transport quirk of the same class as a markdown
# fence: the judgement was made and delivered, the envelope is dented. Like
# fences it is repaired centrally, counted on the caller, and never silent.
# The repair fires only when the text does not parse and text+"}" does — a
# prose reply, a truncation mid-string, or a reply missing "]}"  is left alone
# and still fails downstream as it should.


def _caller_returning(text, tmp_path):
    from ladder.llm import Caller

    caller = Caller("ollama/gpt-oss:20b", cache_dir=tmp_path)

    class FakeCompletions:
        def create(self, **kw):
            return _Resp(text, "stop")

    caller.client._client = type("C", (), {
        "chat": type("Ch", (), {"completions": FakeCompletions()})()})()
    return caller


def test_a_reply_missing_only_the_closing_brace_is_repaired(tmp_path):
    caller = _caller_returning('{"span_ok":true,"confidence":0.9,"why":"x"', tmp_path)
    raw, _ = caller("p", "", "judge")
    assert raw == '{"span_ok":true,"confidence":0.9,"why":"x"}'
    assert caller.unclosed == 1


def test_a_complete_reply_is_not_touched(tmp_path):
    caller = _caller_returning('{"span_ok":true}', tmp_path)
    raw, _ = caller("p", "", "judge")
    assert raw == '{"span_ok":true}'
    assert caller.unclosed == 0


def test_a_reply_one_brace_cannot_fix_is_left_alone(tmp_path):
    """'{' + '}' would parse as {} — a repair that INVENTS an empty judgement.
    The guard is that the unrepaired text must already carry content the brace
    completes; a bare '{' does not."""
    caller = _caller_returning(" {", tmp_path)
    raw, _ = caller("p", "", "judge")
    assert raw == " {"
    assert caller.unclosed == 0


def test_prose_is_left_alone(tmp_path):
    caller = _caller_returning("I think the span is fine.", tmp_path)
    raw, _ = caller("p", "", "judge")
    assert raw == "I think the span is fine."
    assert caller.unclosed == 0


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


def test_the_extractor_runs_at_low_reasoning_effort():
    """REVERSES the earlier "deliberately unset", and the reversal is the
    lesson. That call was made over THREE documents, where effort=low appeared
    to find 1 gold mention of 17.

    Re-measured over TEN dev documents, 30 gold reaction mentions, both arms,
    identical prompts:

                    tokens    sec   gold found
        S1 low       1,176     22   19/30  (63%)
        S1 default  15,918    320   19/30  (63%)   <- IDENTICAL
        S0 low       3,805     77   10/30  (33%)
        S0 default  39,426    853   11/30  (37%)   <- one mention

    S1 loses nothing and runs 14x faster; S0 loses one mention of thirty. The
    dev split goes from ~4 hours to ~10 minutes, which is the difference
    between a measurement that gets rerun and one that does not.

    Three documents could not measure this. CLAUDE.md already said so — the
    rule existed before the decision and was not applied to it.
    """
    assert ModelInfo("ollama/gpt-oss:20b").reasoning_effort == "low"


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
    openai = pytest.importorskip(
        "openai", reason="local-only extra; requirements.txt pins pyyaml only")
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
    openai = pytest.importorskip(
        "openai", reason="local-only extra; requirements.txt pins pyyaml only")
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

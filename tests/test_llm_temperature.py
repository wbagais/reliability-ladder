"""`manifest.model.temperature` is the ONE place the greedy temperature is set.

THE DEFECT THIS FILE PINS (found 2026-08-31). `manifest.json` declared
`model.temperature: 0` and nothing read it: `Caller.__call__` carried
`temperature: float = 0.0` as a hardcoded default and no rung passed a value
except rung 3, which reads its own `rungs.3.temperature`. So "which temperature
produced this number" had a declared answer and a real answer, and they agreed
only by accident — the exact failure `manifest.model`'s own note was written
for, one layer down, and the same class as the 5.9-point manifest/arms gap of
2026-08-28.

THE INT/FLOAT TRAP, which is why the cache test below exists. `temperature` is
in the cache key, and the key is a JSON dump: the manifest's `0` serialises as
`0` and the code default as `0.0`. Wiring the declaration through WITHOUT
casting to float would change every cache key in the project — every entry a
miss, every published CADEC number re-generated from a cold cache. The cast is
the whole no-shipped-number-changes guarantee, so it is tested directly rather
than assumed.
"""

import json

from ladder import llm as llm_mod
from ladder.llm import Caller, LLMResponse


def _caller(spec="ollama/gpt-oss:20b", **kw):
    return Caller(spec, role="extractor", **kw)


def _fake_chat(sent):
    """Stand in for LLMClient.chat, recording what the Caller asked for."""

    def chat(messages, sample_index=0, temperature=0.0, max_tokens=None):
        sent["temperature"] = temperature
        sent["sample_index"] = sample_index
        return LLMResponse(text="{}", prompt_tokens=1, completion_tokens=1,
                           latency_s=0.0)

    return chat


# --- the declaration is load-bearing ---------------------------------------


def test_the_manifest_declares_the_temperature_and_llm_reads_it(tmp_path):
    """A declaration nothing reads is decoration. This is the reader."""
    man = {"model": {"extractor": "ollama/gpt-oss:20b", "temperature": 0.4}}
    assert llm_mod.temperature_for(man) == 0.4


def test_an_undeclared_temperature_is_the_greedy_default(tmp_path):
    """The FiNER manifests declare no temperature. Absent is not a
    disagreement — there is nothing to disagree with — so it resolves to the
    one named constant, and provenance records the EFFECTIVE value either way.
    """
    assert llm_mod.temperature_for({"model": {"extractor": "x/y"}}) == \
        llm_mod.GREEDY_TEMPERATURE
    assert llm_mod.temperature_for(None) == llm_mod.GREEDY_TEMPERATURE


def test_for_rung_binds_the_declared_temperature_to_the_caller(tmp_path):
    """for_rung is where a model is resolved, so it is where its temperature
    is resolved too — one place, not two."""
    man = {"model": {"extractor": "ollama/gpt-oss:20b",
                     "judge": "ollama/ibm/granite4:micro-h",
                     "temperature": 0.4}}
    caller = llm_mod.for_rung(0, man, cache_dir=tmp_path)
    assert caller.temperature == 0.4


def test_the_bound_temperature_reaches_the_request(tmp_path):
    """The binding must survive all the way to the provider call. Before the
    wiring this sent 0.0 no matter what the manifest said."""
    sent = {}
    c = _caller(cache_dir=tmp_path, temperature=0.4)
    c.client.chat = _fake_chat(sent)
    c("prompt", "", "find")
    assert sent["temperature"] == 0.4


def test_an_explicit_call_argument_still_wins(tmp_path):
    """The bound value is a DEFAULT, not a lock: rung 3 draws its samples by
    passing a temperature per call, and that must keep working."""
    sent = {}
    c = _caller(cache_dir=tmp_path, temperature=0.0)
    c.client.chat = _fake_chat(sent)
    c("prompt", "", "find", temperature=0.7)
    assert sent["temperature"] == 0.7


def test_rung_3_sampler_overrides_the_declaration(tmp_path):
    """`rungs.3.temperature` is the rung's setting and stays the rung's.
    A greedy declaration must not silently de-sample the vote."""
    sent = {}
    c = _caller(cache_dir=tmp_path, temperature=0.0)
    c.client.chat = _fake_chat(sent)
    draw = c.sampler(0.7)
    draw("prompt", "", "find")
    assert sent["temperature"] == 0.7


# --- the no-shipped-number-changes guarantee --------------------------------


def test_manifest_zero_is_cast_to_the_float_the_cache_key_already_holds(tmp_path):
    """THE INT/FLOAT TRAP, asserted at the byte level.

    Every CADEC figure in the article was produced at an effective 0.0. The
    manifest says `0`, which is an int. json.dumps writes `0` for one and
    `0.0` for the other, so an uncast wiring gives every call in the project a
    different sha256 — a total cache miss dressed up as a no-op change.
    """
    man = {"model": {"extractor": "ollama/gpt-oss:20b", "temperature": 0}}
    t = llm_mod.temperature_for(man)
    assert isinstance(t, float)
    c = _caller(cache_dir=tmp_path, temperature=t)
    msgs = [{"role": "user", "content": "hi"}]
    before = c.client._cache_path({"model": c.client.info.spec, "messages": msgs,
                                   "temperature": 0.0, "sample_index": 0,
                                   "max_tokens": c.client.info.max_tokens,
                                   "reasoning_effort": c.client.info.reasoning_effort})
    after = c.client._cache_path({"model": c.client.info.spec, "messages": msgs,
                                  "temperature": t, "sample_index": 0,
                                  "max_tokens": c.client.info.max_tokens,
                                  "reasoning_effort": c.client.info.reasoning_effort})
    assert before == after


def test_a_cache_entry_written_before_the_wiring_is_still_a_hit(tmp_path):
    """The same guarantee, end to end and behaviourally.

    `out/cadec-manifest-1` — the run whose records sha256 pins every published
    CADEC figure — no longer exists on this machine, so the sha comparison the
    task asked for cannot be made against the file. This is the equivalent
    claim and a stronger one: identical cache key means identical text back
    means identical records, for every call rather than for one sampled run.
    """
    man = {"model": {"extractor": "ollama/gpt-oss:20b", "temperature": 0}}
    c = _caller(cache_dir=tmp_path, temperature=llm_mod.temperature_for(man))
    msgs = [{"role": "user", "content": "prompt"}]
    key = c.client._cache_path({"model": c.client.info.spec, "messages": msgs,
                                "temperature": 0.0, "sample_index": 0,
                                "max_tokens": c.client.info.max_tokens,
                                "reasoning_effort": c.client.info.reasoning_effort})
    key.write_text(json.dumps({"text": "the answer from before the wiring",
                               "prompt_tokens": 7, "completion_tokens": 9,
                               "latency_s": 1.0}))

    def refuse(*a, **kw):
        raise AssertionError("cache MISS — the wiring changed the key")

    c.client._client = type("C", (), {"chat": type("D", (), {"completions": type(
        "E", (), {"create": staticmethod(refuse)})()})()})()
    raw, usage = c("prompt", "", "find")
    assert raw == "the answer from before the wiring"
    assert usage["cached"] is True


# --- rung 4 declared the same thing and read it no more ---------------------


def test_rung_4_declares_no_temperature_it_does_not_read():
    """`r4.DEFAULTS` carried `"temperature": 0` and rung 4 called
    `llm(prompt, "", "judge")` with no temperature — the identical defect one
    layer down. Removed rather than wired: a rung DEFAULT that overrode
    `manifest.model.temperature` would put the code default back on top of the
    declaration, which is the thing being fixed.
    """
    from ladder.rungs import r4

    assert "temperature" not in r4.DEFAULTS


def test_rung_4_judges_at_the_declared_temperature(tmp_path):
    """Rung 4 inherits the declaration through its bound Caller."""
    from ladder.rungs import r4
    from ladder.schema import Record

    sent = {}
    judge = Caller("ollama/ibm/granite4:micro-h", role="judge",
                   cache_dir=tmp_path, temperature=0.4)
    judge.client.chat = _fake_chat(sent)
    rec = Record(doc_id="D.1", entity_type="reaction", text="rash",
                 spans=[(0, 4)], sct="271807003", record_id="D.1#0")
    r4.apply([rec], {"D.1": "rash"}, {
        "judge_llm": judge,
        "extractor_model": "family/a", "judge_model": "family/b"})
    assert sent["temperature"] == 0.4


# --- the pin: every shipped manifest still runs at the published 0.0 --------


def test_every_tracked_manifest_resolves_to_the_published_temperature():
    """The guard that makes the wiring safe to merge, and dangerous to edit.

    Every CADEC and FiNER figure in docs/article.md was produced at an
    effective temperature of 0.0, back when that was a code default nobody
    could change from configuration. It IS changeable from configuration now,
    which is the point of the wiring and also its one risk: editing
    `manifest.model.temperature` no longer just relabels a run, it changes
    one. This fails when that happens, and the failure is the warning.
    """
    import pathlib

    root = pathlib.Path(__file__).resolve().parent.parent
    seen = 0
    for path in sorted(root.glob("manifest*.json")):
        man = json.loads(path.read_text())
        t = llm_mod.temperature_for(man)
        assert t == 0.0, f"{path.name} would run at {t}, not the published 0.0"
        assert isinstance(t, float), f"{path.name} gives an int — cache keys move"
        seen += 1
    assert seen >= 5, "manifests moved; this pin stopped covering them"

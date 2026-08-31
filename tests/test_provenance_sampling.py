"""The temperature a run REPORTS must be the temperature it ran at.

The input side of this defect was `manifest.model.temperature` being declared
and never read (tests/test_llm_temperature.py). This is the output side, and it
is worse: `scripts/ladder_run.py` stamped `sampling={"temperature": 0.7, "k": 3}`
and `scripts/full_run.py` stamped `sampling={"temperature": 0.0}` — both
LITERALS, neither read from the manifest, and the first reports rung 3's
sampler temperature as though it were the run's. A provenance stamp exists to
answer "what produced this number"; one that hardcodes its answer is a stamp
that cannot be wrong and cannot be right.

`scripts/` is the part of this repo with the thinnest coverage, which is how a
NameError in `full_run.py` survived the renumber. The source-level guards below
are the same device as the test asserting a filename is absent from `r0.py`.
"""

import pathlib

import pytest

from ladder import provenance

_ROOT = pathlib.Path(__file__).resolve().parent.parent

MAN = {
    "model": {"extractor": "ollama/gpt-oss:20b",
              "judge": "ollama/ibm/granite4:micro-h",
              "temperature": 0},
    "rungs": {"3": {"k": 3, "temperature": 0.7, "enabled": True}},
}


def test_sampling_is_read_from_the_manifest():
    s = provenance.sampling_for(MAN)
    assert s["temperature"] == 0.0
    assert s["sampler_temperature"] == 0.7
    assert s["k"] == 3


def test_the_stamp_separates_a_declared_zero_from_a_defaulted_one():
    """The whole point. `0` in the manifest and 0.0 out of the code default
    are the same number and NOT the same fact, and only the stamp can say
    which one a run had."""
    assert provenance.sampling_for(MAN)["temperature_declared"] is True
    bare = {"model": {"extractor": "ollama/gpt-oss:20b"}}
    s = provenance.sampling_for(bare)
    assert s["temperature_declared"] is False
    assert s["temperature"] == 0.0


def test_an_undeclared_sampler_is_absent_rather_than_guessed():
    """provenance's rule: every field records its own absence honestly rather
    than guessing. A stamp that invents k=3 for a run with no rung 3 is a
    stamp reporting a vote nobody took."""
    s = provenance.sampling_for({"model": {"extractor": "x/y"}})
    assert "sampler_temperature" not in s
    assert "k" not in s


def test_a_disabled_rung_3_is_recorded_as_disabled():
    """`enabled: false` is a RECORDED run state, never a silent skip — the
    same rule run.py's ledger row follows."""
    man = {"model": {"temperature": 0},
           "rungs": {"3": {"k": 3, "temperature": 0.7, "enabled": False}}}
    assert provenance.sampling_for(man)["sampler"] == "disabled"


def test_sampling_for_never_raises():
    """Nothing in provenance raises: a stamp that crashes a run is worse than
    an incomplete stamp."""
    for junk in (None, {}, {"model": None}, {"model": {"temperature": "hot"}},
                 {"rungs": {"3": {"temperature": "warm", "k": "many"}}}):
        assert isinstance(provenance.sampling_for(junk), dict)


def test_gather_stamps_the_manifest_sampling_by_default():
    """An entry point that says nothing about sampling must not produce a
    stamp that says nothing about sampling."""
    stamp = provenance.gather(MAN, entry_point="test")
    assert stamp["sampling"] == provenance.sampling_for(MAN)


def test_an_explicit_sampling_argument_still_wins():
    stamp = provenance.gather(MAN, entry_point="test", sampling={"temperature": 1.0})
    assert stamp["sampling"] == {"temperature": 1.0}


@pytest.mark.parametrize("script", ["scripts/ladder_run.py", "scripts/full_run.py"])
def test_no_script_stamps_a_hardcoded_temperature(script):
    src = (_ROOT / script).read_text()
    assert 'sampling={"temperature"' not in src, (
        f"{script} stamps a temperature literal into provenance. It must read "
        "the manifest — provenance.gather already does when sampling is left "
        "unset."
    )

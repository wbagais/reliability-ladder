"""Every arm manifest carries the gate codes of the base it is a one-key diff of.

`vocabulary.gate` (the real and the fake code `ladder.run init` checks the
vocabulary with) was added to the base manifests on 2026-09-07 and not to the
arm manifests. Every "differs from its base by exactly one key" test then saw
two keys, and the pipeline went red on main. This test names the rule those
tests enforce by accident: an arm inherits its base's gate.
"""

import json
import pathlib

import pytest

ROOT = pathlib.Path(__file__).parent.parent

#: arm manifest -> the base it is a one-key diff of
ARMS = {
    "manifest.judgearm.json": "manifest.json",
    "manifest.judgemenu.json": "manifest.json",
    "manifest.judgeshuffle.json": "manifest.json",
    "manifest.lexarm.json": "manifest.json",
    "manifest.sapbertarm.json": "manifest.json",
    "manifest.spine.cadec.json": "manifest.json",
    "manifest.finer.ctxmenu.json": "manifest.finer.json",
    "manifest.finer.nofallback.json": "manifest.finer.json",
    "manifest.finer.shufflemenu.json": "manifest.finer.json",
    "manifest.finer.judgemenu.json": "manifest.finer.json",
    "manifest.finer.judgeshuffle.json": "manifest.finer.json",
    "manifest.finer.llama.json": "manifest.finer.json",
    "manifest.finer.mistral.json": "manifest.finer.json",
    "manifest.finer.typecheck.json": "manifest.finer.json",
    "manifest.spine.finer.json": "manifest.finer.json",
}


def _load(name):
    return json.loads((ROOT / name).read_text())


def test_every_arm_manifest_is_listed():
    tracked = {p.name for p in ROOT.glob("manifest*.json")}
    corpora = {p.name for p in ROOT.glob("manifest*.json")
               if _load(p.name)["corpus"]["name"] not in ("CADEC", "FiNER-139")}
    assert tracked - corpora - set(ARMS) == {"manifest.json", "manifest.finer.json"}, \
        "a new CADEC or FiNER manifest must be added to ARMS with its base"


@pytest.mark.parametrize("arm,base", sorted(ARMS.items()))
def test_an_arm_inherits_the_gate_codes_of_its_base(arm, base):
    assert _load(arm)["vocabulary"].get("gate") == _load(base)["vocabulary"]["gate"], \
        f"{arm} does not carry {base}'s vocabulary.gate"

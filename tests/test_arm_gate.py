"""The vocabulary gate is a fact about the VOCABULARY, and an arm shares its
base's vocabulary — so an arm manifest carries its base's gate, verbatim.

WHY THIS IS A SEPARATE TEST FROM THE ONE-KEY DIFFS

The one-key diff tests (test_lexarm, test_menu_order, test_r4_menu,
test_rung0_encoder, test_rungs_audit) went red on 2026-09-07 when
`vocabulary.gate` landed on the two bases and not on their arms. They say
THAT the arms drifted; this test says WHY the gate belongs on the arm and not
only on the base: `ladder.checks.cross.vocabulary_gate` FAILS a manifest with
no gate declared ("the gate runs on CADEC's SNOMED codes"), and `cmd_init`
falls back to CADEC's SNOMED constants — right for a CADEC arm by luck and
wrong for a FiNER arm by construction. Nothing about an arm changes which
codes its vocabulary must and must not hold.
"""
from __future__ import annotations

import json
import pathlib

import pytest

_ROOT = pathlib.Path(__file__).resolve().parent.parent

ARMS = [
    ("manifest.json", "manifest.judgemenu.json"),
    ("manifest.json", "manifest.judgeshuffle.json"),
    ("manifest.json", "manifest.lexarm.json"),
    ("manifest.json", "manifest.judgearm.json"),
    ("manifest.json", "manifest.sapbertarm.json"),
    ("manifest.finer.json", "manifest.finer.judgemenu.json"),
    ("manifest.finer.json", "manifest.finer.judgeshuffle.json"),
    ("manifest.finer.json", "manifest.finer.ctxmenu.json"),
]


@pytest.mark.parametrize("base,arm", ARMS)
def test_an_arm_declares_the_same_vocabulary_gate_as_its_base(base, arm):
    a = json.load(open(_ROOT / base))["vocabulary"]
    b = json.load(open(_ROOT / arm))["vocabulary"]
    assert a.get("gate"), f"{base} declares no vocabulary.gate"
    assert b.get("gate") == a["gate"], (
        f"{arm} does not carry {base}'s vocabulary.gate — "
        "checks.cross.vocabulary_gate fails an undeclared gate"
    )

"""`rung0_pick_fallback` was ON, undeclared, and it manufactured a finding.

B4 set out to break FiNER's slot-0 position prior and found there was none to
break. `AccrualForEnvironmentalLossContingencies` is predicted 77 times in 313
on the dev split — and **74 of those are `r0._fill_from_menu`**, which fills any
record the pick left uncoded with MENU POSITION 0. The model chose the tag 3
times; its own slot-0 rate is 1.3% against a 0.72% chance rate.

The rule was measured on CADEC, where position 0 is the top dense-retrieval hit
and filling from it cannot lose (docs/decisions.md, +0.015 exact). On FiNER
position 0 is an ALPHABETICAL accident, so the same rule writes one arbitrary
tag onto 24% of the run's answers.

It is the project's recurring defect class INVERTED: not a setting declared and
never read, but a behaviour that RUNS and was never declared. So it is declared
now — in both manifests, at the value the code already used, which changes no
number — and `manifest.finer.nofallback.json` is the one-key arm that prices it.
"""

import json
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]


def man(name):
    return json.load(open(ROOT / name))


@pytest.mark.parametrize("name", ["manifest.finer.json",
                                 "manifest.finer.ctxmenu.json",
                                 "manifest.finer.shufflemenu.json"])
def test_the_fallback_is_declared_at_the_value_the_code_already_used(name):
    """Declaring it must not CHANGE a run — every published number was produced
    with the fallback on. Same posture as the temperature wiring: make the
    declaration honest first, move it second."""
    from ladder.rungs import r0

    assert man(name)["rungs"]["0"]["rung0_pick_fallback"] is True
    assert r0.DEFAULTS["rung0_pick_fallback"] is True


def test_the_cadec_manifest_is_deliberately_left_undeclared_for_now():
    """`manifest.json` is NOT touched this session, and the reason is on the
    record rather than in a silence: on CADEC the rule is measured and sound
    (position 0 is the top dense-retrieval hit), and declaring it there would
    ripple into three arm one-key-diff tests for no measurement. The gap is
    real and is registered as its own task."""
    assert "rung0_pick_fallback" not in man("manifest.json")["rungs"]["0"]


def test_the_declaration_is_actually_read():
    """A declared-and-unread setting is the exact defect this is fixing."""
    from ladder.rungs import r0

    pairs = [(_bare(), [{"i": 0, "code": "us-gaap:A", "fsn": "A"}])]
    r0._fill_from_menu(pairs, {"rung0_pick_fallback": True}, {})
    assert pairs[0][0].sct == "us-gaap:A"

    pairs = [(_bare(), [{"i": 0, "code": "us-gaap:A", "fsn": "A"}])]
    r0._fill_from_menu(pairs, {"rung0_pick_fallback": False}, {})
    assert pairs[0][0].sct is None, "the declaration is not read"


def _bare():
    from ladder.schema import REACTION, Record

    r = Record(doc_id="D1", entity_type=REACTION, text="4.5", spans=[(0, 3)])
    r.checks["no_pick"] = True
    return r


def test_the_nofallback_manifest_differs_by_exactly_that_key():
    a = man("manifest.finer.json")
    b = man("manifest.finer.nofallback.json")
    b.pop("_nofallback_note", None)
    b["rungs"]["0"].pop("rung0_pick_fallback_note", None)
    a["rungs"]["0"].pop("rung0_pick_fallback_note", None)

    def walk(x, y, path=""):
        if isinstance(x, dict) and isinstance(y, dict):
            for k in sorted(set(x) | set(y)):
                yield from walk(x.get(k), y.get(k), f"{path}.{k}")
        elif x != y:
            yield path

    assert list(walk(a, b)) == [".rungs.0.rung0_pick_fallback"]
    assert b["rungs"]["0"]["rung0_pick_fallback"] is False

"""Plan item 16 (2026-09-02): `lexical_mode: exact` may be the wrong shipped
default, on the article's own rule — abstaining always raises precision, so
read YIELD. On one draw `exact` ships 48 records at 85.4% (yield 0.185) and
`contained` ships 88 at 63.6% (yield 0.252). One draw decides nothing; three
paired draws do, and the arm is a one-key manifest diff so the comparison
holds everything else fixed.
"""

import json
import pathlib

_ROOT = pathlib.Path(__file__).resolve().parent.parent


def _walk(x, y, path=""):
    if isinstance(x, dict) and isinstance(y, dict):
        for k in sorted(set(x) | set(y)):
            yield from _walk(x.get(k), y.get(k), f"{path}.{k}")
    elif x != y:
        yield path


def test_the_lexical_arm_differs_from_the_shipped_manifest_by_exactly_one_key():
    a = json.load(open(_ROOT / "manifest.json"))
    b = json.load(open(_ROOT / "manifest.lexarm.json"))
    b.pop("_lexarm_note", None)
    assert list(_walk(a, b)) == [".rungs.1.lexical_mode"]
    assert a["rungs"]["1"]["lexical_mode"] == "exact"
    assert b["rungs"]["1"]["lexical_mode"] == "contained"

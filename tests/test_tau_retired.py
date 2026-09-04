"""Plan item 17(d), 2026-09-03: `tau` was a dial that could not turn.

Rung 5 read `rungs.5.tau` — unlike the five settings the 2026-08-31 audit
found dead, this one WAS read — but it could never usefully fire: rung 0
reports >= 0.95 confidence on every record (1.0 on 77%) while being right
about 40% of the time, so no threshold separates anything. A live key that is
structurally inert is the same defect one layer along from "declared and
never read": it looks tunable.

RETIRED, the `otel.py` way: the key is gone from every tracked manifest, the
rung refuses it rather than ignoring it, the sweep that existed only to tune
it went with it, and these tests keep it gone. B7 (a CALIBRATED abstention
input) is registered future work and would be a different dial with a
different name — not this one back under a new note.
"""

import json
import pathlib

import pytest

from ladder.schema import REACTION, Record, ZONE_ACCEPT

_ROOT = pathlib.Path(__file__).resolve().parent.parent


def rec(**kw):
    base = dict(doc_id="D1", entity_type=REACTION, text="bit drowsy",
                spans=[(9, 19)], sct="271782001", record_id="D1#0", confidence=0.01)
    base.update(kw)
    return Record(**base)


def test_rung_5_has_no_tau_default():
    from ladder.rungs import r5

    assert "tau" not in r5.DEFAULTS


def test_decide_refuses_a_tau_rather_than_ignoring_it():
    from ladder.rungs import r5

    r = rec()
    r.mark(1, ZONE_ACCEPT)
    with pytest.raises(ValueError, match="tau"):
        r5.decide(r, {"tau": 0.5})


def test_a_low_confidence_record_is_never_withheld_for_it():
    """Confidence is recorded on the record and read by NOTHING in rung 5."""
    from ladder.rungs import r5
    from ladder.schema import ZONE_VERIFIED

    r = rec(confidence=0.0)
    r.mark(1, ZONE_ACCEPT)
    assert r5.decide(r, {})[0] == ZONE_VERIFIED


def test_the_sweep_went_with_the_dial():
    from ladder.rungs import r5

    for name in ("sweep", "aurc", "free_lunch"):
        assert not hasattr(r5, name), f"r5.{name} survived the retirement"


def test_rung_5_never_emits_low_confidence():
    src = (_ROOT / "ladder" / "rungs" / "r5.py").read_text()
    assert "R_LOW_CONFIDENCE" not in src
    assert "tau" not in src.replace("tau_retired", ""), "the word is only allowed in the retirement note"


def test_the_schema_keeps_the_constant_because_schemas_are_append_only():
    from ladder import schema

    assert schema.R_LOW_CONFIDENCE == "low_confidence"


def test_no_tracked_manifest_declares_tau():
    for p in sorted(_ROOT.glob("manifest*.json")):
        m = json.load(open(p))
        r5 = (m.get("rungs") or {}).get("5") or {}
        bad = [k for k in r5 if k == "tau" or (k.startswith("tau_") and k != "tau_retired")]
        assert not bad, f"{p.name} still declares {bad}"
        assert "tau_retired" in r5, f"{p.name}: rungs.5 must record WHY the key is gone"


def test_the_policy_sweep_script_has_no_tau_policy():
    src = (_ROOT / "scripts" / "r5_policy_sweep.py").read_text()
    assert '"tau"' not in src

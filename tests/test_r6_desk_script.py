"""The desk script's non-interactive surface.

`scripts/` having no coverage is how a NameError survived the renumber, so the
desk's queue loading, session resume and oracle path are tested here — without
a terminal, a corpus or a vocabulary index. The interactive loop itself is a
thin dispatcher over `ladder/rungs/r6.py`, which has its own tests.
"""

from __future__ import annotations

import importlib.util
import json
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).parent.parent


@pytest.fixture()
def desk():
    spec = importlib.util.spec_from_file_location(
        "_r6_desk", ROOT / "scripts" / "r6_desk.py"
    )
    mod = importlib.util.module_from_spec(spec)
    added = str(ROOT) not in sys.path
    if added:
        sys.path.insert(0, str(ROOT))
    try:
        spec.loader.exec_module(mod)
        yield mod
    finally:
        if added:
            sys.path.remove(str(ROOT))


def _records_file(tmp_path):
    rows = [
        {
            "doc_id": "D.2", "entity_type": "reaction", "text": "nausea",
            "spans": [[5, 11]], "sct": None, "zone": "ABSTAIN",
            "reason": "unresolved", "record_id": "D.2#0",
            "checks": {"withheld": {"sct": "422587007", "confidence": 1.0}},
        },
        {
            "doc_id": "D.1", "entity_type": "reaction", "text": "rectal bleed",
            "spans": [[20, 32]], "sct": None, "zone": "ABSTAIN",
            "reason": "unresolved", "record_id": "D.1#0",
            "checks": {"withheld": {"sct": "12063002", "confidence": 1.0}},
        },
        {
            "doc_id": "D.1", "entity_type": "reaction", "text": "headache",
            "spans": [[40, 48]], "sct": "25064002", "zone": "VERIFIED",
            "record_id": "D.1#1", "checks": {},
        },
    ]
    p = tmp_path / "run.records.jsonl"
    p.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    return p


def test_load_queue_is_the_sorted_abstained_residue(desk, tmp_path):
    q = desk.load_queue(_records_file(tmp_path))
    assert [r.record_id for r in q] == ["D.1#0", "D.2#0"]
    assert all(r.zone == "ABSTAIN" for r in q)


def test_default_out_sits_beside_the_records(desk):
    assert str(desk.default_out("out/run.records.jsonl", oracle=False)).endswith(
        "out/run.resolutions.jsonl"
    )
    assert str(desk.default_out("out/run.records.jsonl", oracle=True)).endswith(
        "out/run.oracle-resolutions.jsonl"
    )


def test_resume_keys_skip_already_resolved_records(desk, tmp_path):
    out = tmp_path / "r.resolutions.jsonl"
    out.write_text(
        json.dumps(
            {"record_id": "D.1#0", "doc_id": "D.1", "spans": [[20, 32]],
             "decision": "uphold", "sct": None, "seconds": 3.0}
        ) + "\n",
        encoding="utf-8",
    )
    from ladder.rungs import r6

    keys = desk.resume_keys(out)
    assert r6._span_key("D.1", [(20, 32)]) in keys
    assert desk.resume_keys(tmp_path / "absent.jsonl") == set()


def test_oracle_refuses_test_split_documents(desk, tmp_path, monkeypatch):
    q = desk.load_queue(_records_file(tmp_path))
    monkeypatch.setattr(desk.corpus_mod, "read_split", lambda d, n: ["D.1"])
    man = {"corpus": {"splits_dir": "x", "cadec_root": "x"}}
    with pytest.raises(SystemExit, match="(?i)test"):
        desk.oracle_main(None, man, q, tmp_path / "o.jsonl")


def test_oracle_writes_labeled_rows_the_rung_can_apply(desk, tmp_path, monkeypatch):
    from ladder.corpus import Document, GoldMention
    from ladder.rungs import r6

    q = desk.load_queue(_records_file(tmp_path))
    golds = {
        "D.1": Document(
            doc_id="D.1", drug_group="X", text="x" * 60,
            mentions=[GoldMention(
                doc_id="D.1", index=0, entity_type="reaction", cadec_type="ADR",
                text="rectal bleed", spans=[(20, 32)], sct=["12063002"],
                gold_kind="single",
            )],
        ),
        "D.2": Document(doc_id="D.2", drug_group="X", text="x" * 20, mentions=[]),
    }
    monkeypatch.setattr(desk.corpus_mod, "read_split", lambda d, n: [])
    monkeypatch.setattr(desk.corpus_mod, "load_corpus", lambda root: golds)
    out = tmp_path / "o.jsonl"
    man = {"corpus": {"splits_dir": "x", "cadec_root": "x"}}
    assert desk.oracle_main(None, man, q, out) == 0
    rows = r6.load_resolutions(out)
    assert len(rows) == 2
    by = {r["record_id"]: r for r in rows}
    assert by["D.1#0"]["decision"] == "code" and by["D.1#0"]["sct"] == "12063002"
    # D.2's span was never annotated: upheld, not invented
    assert by["D.2#0"]["decision"] == "uphold"
    assert all(r["reviewer"].startswith("oracle") for r in rows)

"""Corpus parsing and split discipline.

The CADEC download is licensed per-person and never committed, so everything
that needs it is skipped when it is absent. The parser's four awkward cases are
covered without the corpus, on inline fragments in the same file format.
"""

import json
from pathlib import Path

import pytest

from ladder.corpus import (
    GOLD_ALL_OF,
    GOLD_ANY_OF,
    GOLD_NONE,
    GOLD_SINGLE,
    _parse_codes,
    family,
    load_corpus,
    make_splits,
    read_split,
)
from ladder.schema import DRUG, REACTION

ROOT = Path(__file__).resolve().parents[1]


def _write(tmp_path, name, body):
    p = tmp_path / name
    p.write_text(body, encoding="utf-8")
    return p


# --- the annotation-format traps -------------------------------------------


def test_parses_a_plain_sct_row(tmp_path):
    p = _write(tmp_path, "a.ann", "TT1\t271782001 | Drowsy | 9 19\tbit drowsy\n")
    got = _parse_codes(p)
    assert got["TT1"] == (["271782001"], GOLD_SINGLE, [(9, 19)], "bit drowsy")


def test_parses_a_meddra_row_without_swallowing_the_code_as_an_offset(tmp_path):
    """A MedDRA body is all digits: "10013649 9 19". The span match is anchored
    to the end of the body or the code becomes the first offset."""
    p = _write(tmp_path, "a.ann", "TT1\t10013649 9 19\tbit drowsy\n")
    assert _parse_codes(p)["TT1"][:3] == (["10013649"], GOLD_SINGLE, [(9, 19)])


def test_parses_discontinuous_spans(tmp_path):
    p = _write(tmp_path, "a.ann", "TT9\tCONCEPT_LESS 40 44;54 62\tHair breakage\n")
    codes, kind, spans, _ = _parse_codes(p)["TT9"]
    assert (codes, kind, spans) == ([], GOLD_NONE, [(40, 44), (54, 62)])


def test_post_coordination_and_disjunction_are_different_gold_shapes(tmp_path):
    p = _write(
        tmp_path,
        "a.ann",
        "TT1\t76948002 | Severe pain |+ 21522001 | Abdominal pain | 21 42\thorrible stomach pain\n"
        "TT2\t102498003 | Agony | or 76948002|Severe pain| 260 265\tagony\n",
    )
    got = _parse_codes(p)
    assert got["TT1"][:2] == (["76948002", "21522001"], GOLD_ALL_OF)
    assert got["TT2"][:2] == (["102498003", "76948002"], GOLD_ANY_OF)


def test_tolerates_a_missing_closing_pipe(tmp_path):
    p = _write(tmp_path, "a.ann", "TT9\t21499005|Feeling agitated 232 249\tSevere aggitation\n")
    assert _parse_codes(p)["TT9"][:3] == (["21499005"], GOLD_SINGLE, [(232, 249)])


def test_tolerates_spaces_where_the_format_promises_tabs(tmp_path):
    """Two rows in DICLOFENAC-SODIUM.7 do this and would otherwise vanish."""
    p = _write(tmp_path, "a.ann", "TT7     42399005 | Renal failure | 411 415;432 440     renal failure\n")
    assert _parse_codes(p)["TT7"][:3] == (["42399005"], GOLD_SINGLE, [(411, 415), (432, 440)])


# --- splits (no corpus needed) ----------------------------------------------


class FakeDoc:
    def __init__(self, doc_id):
        self.doc_id = doc_id
        self.drug_group = doc_id.split(".")[0]
        self.text = ""
        self.mentions = []


def _fake_corpus(n_lipitor=1000, n_other=250):
    docs = {}
    for i in range(n_lipitor):
        docs[f"LIPITOR.{i}"] = FakeDoc(f"LIPITOR.{i}")
    for i in range(n_other):
        docs[f"VOLTAREN.{i}"] = FakeDoc(f"VOLTAREN.{i}")
    return docs


def test_splits_hit_the_requested_size_exactly():
    s = make_splits(_fake_corpus(), seed=42, n_dev=40, n_test=60)
    assert len(s["dev"]) == 40 and len(s["test"]) == 60
    assert len(s["pool"]) == 1250 - 100


def test_splits_are_disjoint():
    s = make_splits(_fake_corpus(), seed=42)
    assert not (set(s["dev"]) & set(s["test"]))
    assert not (set(s["dev"]) & set(s["pool"]))
    assert not (set(s["test"]) & set(s["pool"]))


def test_splits_are_deterministic_in_the_seed():
    assert make_splits(_fake_corpus(), seed=42) == make_splits(_fake_corpus(), seed=42)
    assert make_splits(_fake_corpus(), seed=1) != make_splits(_fake_corpus(), seed=42)


def test_splits_are_stratified_by_drug_family():
    """CADEC is 80% Lipitor. An unstratified test split would be almost all one
    drug, and the human-agreement ceiling we cite was measured on the other."""
    s = make_splits(_fake_corpus(), seed=42, n_dev=40, n_test=60)
    for name, n in (("dev", 40), ("test", 60)):
        diclofenac = sum(1 for d in s[name] if family(d.split(".")[0]) == "diclofenac")
        assert 0 < diclofenac <= n
        assert abs(diclofenac / n - 0.2) < 0.05


# --- the real corpus, when it is there --------------------------------------

MANIFEST = ROOT / "manifest.json"
_man = json.loads(MANIFEST.read_text()) if MANIFEST.exists() else {}
_cadec = ROOT / _man.get("corpus", {}).get("cadec_root", "nope")
needs_corpus = pytest.mark.skipif(
    not (_cadec / "text").is_dir(), reason="CADEC v3 not downloaded (licensed per person)"
)


@needs_corpus
def test_the_corpus_matches_the_manifest():
    docs = load_corpus(_cadec)
    mentions = [m for d in docs.values() for m in d.mentions]
    assert len(docs) == _man["corpus"]["n_docs_total"]
    assert len(mentions) == _man["corpus"]["n_mentions_total"]


@needs_corpus
def test_every_entity_type_collapses_to_reaction_or_drug():
    docs = load_corpus(_cadec)
    types = {m.entity_type for d in docs.values() for m in d.mentions}
    assert types == {REACTION, DRUG}


@needs_corpus
def test_gold_spans_are_grounded_up_to_four_known_corpus_typos():
    """The floor rung 1's span check can never get below on this corpus."""
    docs = load_corpus(_cadec)
    bad = [
        m
        for d in docs.values()
        for m in d.mentions
        if sorted(" ".join(d.text[a:b] for a, b in m.spans).lower().split())
        != sorted(m.text.lower().split())
    ]
    assert len(bad) == 4, [(m.doc_id, m.text) for m in bad]


@needs_corpus
def test_concept_less_exists_and_is_the_abstention_target():
    docs = load_corpus(_cadec)
    cl = [m for d in docs.values() for m in d.mentions if m.gold_kind == GOLD_NONE]
    assert len(cl) == 445
    assert all(m.sct == [] for m in cl)


@needs_corpus
def test_drug_mentions_do_carry_codes_contrary_to_the_plan():
    """The plan states CADEC has no drug codes to score. v3's sct/ files code
    1,657 of 1,800 drug mentions, mostly to AMT product concepts."""
    docs = load_corpus(_cadec)
    drugs = [m for d in docs.values() for m in d.mentions if m.entity_type == DRUG]
    coded = [m for m in drugs if m.sct]
    assert len(drugs) == 1800 and len(coded) == 1657


@needs_corpus
def test_the_frozen_splits_on_disk_still_match_the_seed():
    """If this fails, someone regenerated a frozen split and every number
    measured before that point is no longer comparable."""
    splits_dir = ROOT / _man["corpus"]["splits_dir"]
    if not (splits_dir / "test.json").exists():
        pytest.skip("splits not generated yet — run `python -m ladder.run init`")
    docs = load_corpus(_cadec)
    fresh = make_splits(
        docs,
        seed=_man["seed"],
        n_dev=_man["corpus"]["n_dev_docs"],
        n_test=_man["corpus"]["n_test_docs"],
    )
    for name in ("dev", "test"):
        assert read_split(splits_dir, name) == fresh[name]

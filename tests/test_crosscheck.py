"""Tests for ladder.checks.cross — every check, made to fail on purpose.

WHY A FAKE ARM AND NOT A REAL CORPUS

Each check is a function of `(Arm) -> Result`, so it can be exercised against a
hand-built arm with exactly the defect under test and nothing else. That matters
for two reasons:

  · a test that loads CADEC needs a licensed corpus nobody else has, so it
    would not run in CI or on a stranger's clone
  · a check validated only against manifests that PASS has not been validated.
    Every test below makes its check FAIL, on the specific defect that reached
    a rented card first, and then confirms the fixed version passes.

The comment on each test names the run it came from.
"""
from __future__ import annotations

import json
import pathlib
import sys
import types

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from ladder.checks import FAIL, PASS, SKIP, Arm, Result, report
from ladder.checks import cross


# ── a corpus small enough to reason about ────────────────────────────
class Mention:
    def __init__(self, text, sct, spans=((0, 4),)):
        self.text, self.sct, self.spans = text, list(sct), list(spans)


class Doc:
    def __init__(self, mentions):
        self.mentions = mentions


class Vocab:
    """Two codes exist; everything else does not."""
    def __init__(self, known=("111", "222")):
        self.known = set(known)

    def exists(self, c):
        return str(c) in self.known

    def terms(self, c):
        return {"111": ["Tremor"], "222": ["Nausea"]}.get(str(c), [])


def arm(manifest=None, docs=None, registry=..., splits=None, mod=None,
        prompt="extract every reaction the writer describes") -> Arm:
    """A loaded Arm with no I/O. `splits` is a dict of name -> ids."""
    a = Arm(path="manifest.fake.json", manifest=manifest or {})
    a.docs = docs if docs is not None else {
        "D1": Doc([Mention("shaking", ["111"]), Mention("sick", ["222"])]),
        "D2": Doc([Mention("Tremor", ["111"])]),
    }
    a.registry = Vocab() if registry is ... else registry
    a._mod, a._opts = mod, {}
    a._splits = splits or {}
    a.split = lambda name: a._splits.get(name)          # type: ignore[assignment]
    a.rendered_prompt = lambda: prompt                   # type: ignore[assignment]
    return a


def only(results, name):
    """The one result whose check name contains `name`."""
    hits = [r for r in (results if isinstance(results, list) else [results])
            if name in r.check]
    assert len(hits) == 1, f"expected one {name!r}, got {[h.check for h in hits]}"
    return hits[0]


# ── corpus loads ─────────────────────────────────────────────────────
def test_empty_corpus_fails():
    assert cross.corpus_loads(arm(docs={})).status == FAIL


def test_loaded_corpus_reports_its_size():
    r = cross.corpus_loads(arm())
    assert r.status == PASS and "3 mentions" in r.found


# ── entity type ──────────────────────────────────────────────────────
def test_entity_type_must_be_one_the_adapter_offers():
    """BC5CDR annotates Chemical and Disease and the arm scores one. A corpus
    that annotates two and scores neither is judged on mentions it never
    asked for."""
    mod = types.SimpleNamespace(TYPES=("Chemical", "Disease"))
    bad = arm({"corpus": {"entity": "Reaction"}}, mod=mod)
    assert cross.entity_type_offered(bad).status == FAIL
    good = arm({"corpus": {"entity": "Disease"}}, mod=mod)
    assert cross.entity_type_offered(good).status == PASS


def test_entity_type_skipped_when_adapter_offers_none():
    assert cross.entity_type_offered(arm()) is None


# ── split ids ────────────────────────────────────────────────────────
def test_split_ids_from_another_corpus_fail():
    """TR-News's splits were frozen while the adapter still defaulted to LGL,
    so they held LGL's document ids. Rung 0 returned in 0.06 s with no records
    and no error, and three theories were wrong before the fourth was right."""
    a = arm(splits={"dev": ["LGL.999", "LGL.888"], "pool": ["D1"], "test": ["D2"]})
    assert only(cross.split_ids_are_in_this_corpus(a), "'dev'").status == FAIL


def test_split_ids_that_exist_pass():
    a = arm(splits={"pool": ["D1"], "dev": ["D2"], "test": ["D1"]})
    assert all(r.status == PASS for r in cross.split_ids_are_in_this_corpus(a))


def test_absent_split_is_skipped_not_failed():
    """An absent split has not been frozen; an empty one was frozen wrongly.
    Different answers, kept apart."""
    assert only(cross.split_ids_are_in_this_corpus(arm()), "'dev'").status == SKIP


# ── the pool ─────────────────────────────────────────────────────────
def test_splits_that_exhaust_the_corpus_fail():
    """LINNAEUS has 95 documents and 40 dev + 60 test left nothing, so the
    few-shot block came back empty and rung 0 fell back to CADEC's synthetic
    examples — on a corpus about species."""
    a = arm({"corpus": {"n_dev_docs": 40, "n_test_docs": 60}})
    r = cross.splits_leave_a_pool(a)
    assert r.status == FAIL and "-98 left" in r.found


def test_splits_that_leave_a_pool_pass():
    a = arm({"corpus": {"n_dev_docs": 1, "n_test_docs": 1}},
            docs={f"D{i}": Doc([Mention("x", ["111"])]) for i in range(10)})
    assert cross.splits_leave_a_pool(a).status == PASS


# ── few-shot ─────────────────────────────────────────────────────────
def test_fewshot_from_outside_the_pool_fails():
    """BC5CDR's were picked from its own `train` split, which is not the pool
    `init` wrote, so the guard refused every cell at the first document."""
    a = arm({"rungs": {"0": {"rung0_fewshot_docs": ["CDR.train.1"]}}},
            splits={"pool": ["CDR.pool.1", "CDR.pool.2"]})
    assert cross.fewshot_ids_are_in_the_pool(a).status == FAIL


def test_fewshot_in_the_pool_passes():
    a = arm({"rungs": {"0": {"rung0_fewshot_docs": ["P1"]}}},
            splits={"pool": ["P1", "P2"]})
    assert cross.fewshot_ids_are_in_the_pool(a).status == PASS


def test_no_fewshot_declared_fails_loudly():
    """Absent ids are not neutral: rung 0 falls back to its synthetic CADEC
    examples, and a corpus running CADEC's examples extracts CADEC's entity —
    mistral returned diseases from a paper about yeast."""
    assert cross.fewshot_ids_are_in_the_pool(arm()).status == FAIL


# ── the vocabulary gate ──────────────────────────────────────────────
def test_gate_fails_when_the_real_code_does_not_resolve():
    a = arm({"vocabulary": {"gate": {"real": "999", "fake": "000"}}})
    assert cross.vocabulary_gate(a).status == FAIL


def test_gate_fails_when_the_fake_code_resolves():
    """A vocabulary that answers True to everything produces a rung 1 that
    looks like it is working."""
    a = arm({"vocabulary": {"gate": {"real": "111", "fake": "222"}}})
    assert cross.vocabulary_gate(a).status == FAIL


def test_gate_passes_when_real_resolves_and_fake_does_not():
    a = arm({"vocabulary": {"gate": {"real": "111", "fake": "999"}}})
    assert cross.vocabulary_gate(a).status == PASS


def test_undeclared_gate_fails():
    """CADEC, FiNER and PsyTAR each ran on CADEC's SNOMED gate codes — by luck
    on two of them, by accident on FiNER, whose vocabulary is 139 XBRL tags."""
    assert cross.vocabulary_gate(arm()).status == FAIL


# ── gold resolves ────────────────────────────────────────────────────
def test_gold_that_does_not_resolve_fails():
    """An OLS4-backed exists() once reported 23.9% of CADEC gold as codes that
    do not exist, because CADEC codes drugs to AMT. Scoring against that pair
    measures the mismatch, not the model."""
    a = arm(docs={"D": Doc([Mention("x", ["999"]), Mention("y", ["888"])])})
    assert cross.gold_codes_resolve(a).status == FAIL


def test_gold_that_resolves_passes():
    assert cross.gold_codes_resolve(arm()).status == PASS


# ── the rendered prompt ──────────────────────────────────────────────
def test_prompt_missing_the_declared_entity_fails():
    """Twelve matrix cells ran with a prompt asking for adverse drug reactions
    on corpora about places, species and diseases."""
    a = arm({"corpus": {"prompts": {"entity_short": "organism"}}})
    r = cross.prompt_names_this_entity(a, "extract every reaction described")
    assert r.status == FAIL


def test_prompt_naming_the_declared_entity_passes():
    a = arm({"corpus": {"prompts": {"entity_short": "organism"}}})
    assert cross.prompt_names_this_entity(a, "every organism mentioned").status == PASS


def test_absent_prompt_block_is_a_decision_on_an_adr_corpus():
    """PsyTAR needs no block — it IS adverse drug reactions, so CADEC's default
    is correct there. LINNAEUS needed one. The check reports which."""
    assert cross.prompt_names_this_entity(
        arm(), "every adverse reaction the writer describes").status == SKIP
    assert cross.prompt_names_this_entity(
        arm(), "every toponym in the article").status == FAIL


def test_prompt_carrying_another_corpus_entity_fails():
    a = arm({"corpus": {"prompts": {"entity_short": "organism"}}})
    r = cross.prompt_names_no_other_entity(a, "find every adverse reaction here")
    assert r.status == FAIL and "adverse reaction" in r.found


def test_a_corpus_is_never_foreign_to_itself():
    """The flat word list this replaced matched `place` against 'place the
    article refers to', so all three geo arms reported carrying another
    corpus's task."""
    a = arm({"corpus": {"prompts": {"entity_short": "place"}}})
    assert cross.prompt_names_no_other_entity(
        a, "every place the article refers to").status == PASS


# ── the doubled slot ─────────────────────────────────────────────────
def test_a_doubled_slot_is_caught():
    """`entity: 'organism the paper mentions'` rendered as *'organism the paper
    mentions the paper describes'*. Written into a SECOND manifest an hour
    after the first was found and explained, which is the argument for the
    check rather than for care."""
    r = cross.no_doubled_slot(arm(), "extract every disease or symptom "
                                     "the abstract describes the abstract "
                                     "describes in the text below")
    assert r.status == FAIL


def test_a_phrase_reused_in_two_rules_is_not_a_doubled_slot():
    """BC5CDR legitimately says 'more than one word' in two separate rules.
    Adjacency is the discriminator, not repetition."""
    text = ("most mentions run to more than one word so quote the whole "
            "phrase and remember that only a few run to more than one word "
            "in the other direction")
    assert cross.no_doubled_slot(arm(), text).status == PASS


# ── prompt length ────────────────────────────────────────────────────
def test_an_enormous_prompt_fails():
    """Two full research papers as few-shot examples, and three models of four
    returned nothing at all."""
    assert cross.prompt_fits_a_small_model(arm(), "x" * 20_000).status == FAIL


def test_a_normal_prompt_passes():
    assert cross.prompt_fits_a_small_model(arm(), "x" * 3_000).status == PASS


# ── the runner and the report ────────────────────────────────────────
def test_run_collects_every_check_and_loses_none():
    a = arm({"corpus": {"prompts": {"entity_short": "reaction"}},
             "vocabulary": {"gate": {"real": "111", "fake": "999"}},
             "rungs": {"0": {"rung0_fewshot_docs": ["P1"]}}},
            splits={"pool": ["P1"], "dev": ["D1"], "test": ["D2"]})
    results = cross.run(a)
    names = [r.check for r in results]
    for expected in ("corpus loads", "vocabulary gate", "gold codes resolve",
                     "prompt names this entity", "no slot rendered",
                     "prompt fits a small model"):
        assert any(expected in n for n in names), f"{expected} missing"


def test_load_errors_are_reported_not_raised():
    """A check run that dies on the first problem reports one defect where
    there may be five, and the whole point is seeing them all before booking."""
    a = arm()
    a.errors = [Result(FAIL, "vocabulary loads", "x.sqlite", "missing")]
    assert any(r.check == "vocabulary loads" for r in cross.run(a))


def test_report_counts_failures(capsys):
    n = report("fake", [Result(PASS, "a"), Result(FAIL, "b"), Result(SKIP, "c")])
    assert n == 1
    assert "3 checks, 1 failed" in capsys.readouterr().out


def test_quiet_stays_quiet_when_everything_passes(capsys):
    report("fake", [Result(PASS, "a"), Result(PASS, "b")], quiet=True)
    out = capsys.readouterr().out
    assert "all pass" in out and "pass a" not in out

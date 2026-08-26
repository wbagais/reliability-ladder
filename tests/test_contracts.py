"""Contract and reachability tests.

Every failure this project has found was code that never executed, not code
that was wrong. Eight dead ledger call sites, a rung 0 log line on an entry
point nothing calls, a manifest resolving to models that do not exist, three
`RuntimeError` guards written to prevent silent skipping that have never fired.
All of it behind a green suite, because nothing constructed the component and
ran it.

So these tests are not about logic. They assert that things are REACHABLE, that
the two vocabulary backends actually implement the contract they claim, and
that documented behaviour is pinned so a future change to it is deliberate
rather than accidental.

Anything needing the corpus, the index or a model is marked `integration` and
SKIPS when the prerequisite is absent — a suite that is red for environmental
reasons stops being read, and a test that errors on a missing prerequisite
tells you nothing about the code.
"""
from __future__ import annotations

import inspect
import json
import pathlib

import pytest

from schemas.vocabulary import Vocabulary


# --------------------------------------------------------------------------
# the vocabulary contract
#
# schemas/vocabulary.py declares a runtime_checkable Protocol and says plainly
# that the two backends are not equivalent. Nothing checked that either of them
# implements it, or that they agree on the surface where they must.
# --------------------------------------------------------------------------

SURFACE = ["exists", "is_active", "is_finding", "finding_status",
           "terms", "preferred", "lexical_match", "search"]


def _manifest():
    p = pathlib.Path("manifest.json")
    if not p.exists():
        pytest.skip("no manifest.json — run from the repo root")
    return json.loads(p.read_text())


def _registry():
    man = _manifest()
    db = pathlib.Path(man["vocabulary"]["snomed_db"])
    if not db.exists():
        pytest.skip(f"no vocabulary index at {db}")
    from ladder.registry import Registry
    return Registry(str(db))


def test_backends_declare_lossiness():
    """`lossy` is not documentation, it is a field the runner reads.

    OLS4 reports 23.9% of the answer key as nonexistent codes. A backend that
    did not declare that would make a rejection rate look comparable across
    backends when it is not.
    """
    from ladder.registry import Registry
    from ladder import vocab

    assert Registry.lossy is False
    assert Registry.name == "local-rf2"

    ols = next((getattr(vocab, n) for n in dir(vocab)
                if n.lower().startswith("ols") and inspect.isclass(getattr(vocab, n))),
               None)
    assert ols is not None, "no OLS4 backend class found in ladder.vocab"
    assert ols.lossy is True, (
        "the OLS4 backend must declare itself lossy — it serves active "
        "international SNOMED only, and 23.9% of CADEC's gold is retired or AU"
    )


@pytest.mark.parametrize("attr", SURFACE)
def test_both_backends_have_the_surface(attr):
    """Two implementations, one contract. Divergence here is silent."""
    from ladder.registry import Registry
    from ladder import vocab

    assert callable(getattr(Registry, attr, None)), f"Registry lacks {attr}"
    ols = next(getattr(vocab, n) for n in dir(vocab)
               if n.lower().startswith("ols") and inspect.isclass(getattr(vocab, n)))
    assert callable(getattr(ols, attr, None)), f"OLS4 backend lacks {attr}"


@pytest.mark.integration
def test_registry_satisfies_the_protocol():
    assert isinstance(_registry(), Vocabulary)


# --------------------------------------------------------------------------
# search is EXACT-TERM, on purpose
#
# Pinned because it was misread once. `search()` is not substring matching: it
# is `WHERE norm=?` over the description table, and the docstring gives the
# reason — a fuzzy local search would stop being comparable with the OLS4 one.
#
# 202 of 343 gold reaction spans return nothing under it. That is a measured
# consequence of the design, not a defect, and these tests exist so that
# changing it is a deliberate act.
# --------------------------------------------------------------------------

@pytest.mark.integration
def test_search_is_exact_term_not_substring():
    reg = _registry()
    # A substring matcher would return many concepts containing "back".
    # Exact-term returns only descriptions whose normalised form IS "back".
    hits = reg.search("back", 50)
    assert len(hits) < 10, (
        f"search('back') returned {len(hits)} — that is substring behaviour. "
        "This index is documented as exact-term; if it changed, the 59% "
        "gold-span miss rate and rung 0 mode B's results change with it."
    )


@pytest.mark.integration
def test_search_normalisation_is_idempotent():
    """search(x) and search(normalise_term(x)) must agree.

    normalise_term lowercases, drops the semantic tag and squashes punctuation.
    If search did not apply it, case alone would change results — and the first
    diagnosis of the miss rate blamed exactly that.
    """
    from ladder.registry import normalise_term
    reg = _registry()
    for term in ("Nausea", "  nausea  ", "NAUSEA"):
        assert reg.search(term, 5) == reg.search(normalise_term(term), 5)


@pytest.mark.integration
def test_search_returns_empty_rather_than_raising():
    """A phrase absent from the description table is normal, not exceptional.

    Six in ten gold spans hit this path. A backend that raised here would have
    turned a measurement into a crash.
    """
    assert _registry().search("lower back pain", 5) == []


@pytest.mark.integration
def test_search_results_carry_a_label():
    """Results are {'code', 'label'}. The rung 6 desk assumed 'term' and showed
    bare SCTIDs to a reviewer for six records before anyone noticed."""
    hits = _registry().search("nausea", 3)
    assert hits, "expected 'nausea' to resolve"
    for h in hits:
        assert set(h) >= {"code", "label"}, f"unexpected shape: {h}"
        assert h["label"], "a candidate with no label cannot be chosen"


# --------------------------------------------------------------------------
# the guards that have never fired
#
# Rungs 2, 3 and 5 each raise rather than skipping when their model is absent,
# with a comment explaining that "the rung did not help" and "the rung did not
# run" are different claims. Nothing has ever exercised them, so nothing knows
# whether they work.
# --------------------------------------------------------------------------

@pytest.mark.parametrize("rung_name", ["r2", "r3"])
def test_model_rungs_raise_without_a_model(rung_name):
    from ladder.rungs import r2, r3
    mod = {"r2": r2, "r3": r3}[rung_name]
    with pytest.raises(RuntimeError, match="(?i)model|llm"):
        mod.apply([], {}, {"registry": None})


def test_voting_refuses_temperature_zero():
    """k samples at temperature 0 pay k times for one answer repeated k times."""
    from ladder.rungs import r3
    with pytest.raises((ValueError, RuntimeError)):
        r3.apply([], {}, {"llm": lambda *a, **k: ("", {}), "k": 3,
                          "temperature": 0.0})


def test_voting_refuses_k_below_two():
    from ladder.rungs import r3
    with pytest.raises((ValueError, RuntimeError)):
        r3.apply([], {}, {"llm": lambda *a, **k: ("", {}), "k": 1,
                          "temperature": 0.7})


def test_judge_refuses_to_judge_its_own_extractor():
    """A model judging its own output measures self-consistency and reports it
    as verification. The manifest requires a different family; this asserts the
    code enforces it rather than trusting the manifest."""
    from ladder.rungs import r4
    with pytest.raises((RuntimeError, ValueError)):
        r4.apply([], {}, {"judge_llm": lambda *a, **k: ("", {}),
                          "extractor_model": "same:model",
                          "judge_model": "same:model"})


# --------------------------------------------------------------------------
# two entry points, one rung
#
# ladder/rungs/r0.py has run() and apply(). They do the same work through
# different loops, and until today only apply() wrote a ledger row — so every
# script, all of which use run(), reported rung 0 as free. The row existed and
# was correct, on the path nothing takes.
#
# This is the test that would have caught it. It is also the test that will
# catch the two paths drifting again.
# --------------------------------------------------------------------------

@pytest.mark.integration
def test_rung0_entry_points_agree():
    from ladder.ledger import Ledger
    from ladder.rungs.r0 import run, apply
    from ladder import stub_llm as S

    man = _manifest()
    if not pathlib.Path(man["corpus"]["cadec_root"]).exists():
        pytest.skip("no corpus")
    reg = _registry()
    items = S.load_items(man["corpus"]["splits_dir"])[:2]
    if not items:
        pytest.skip("no split items")
    sources = {i["doc_id"]: i["text"] for i in items}

    import tempfile
    with tempfile.TemporaryDirectory() as d:
        la = Ledger(pathlib.Path(d) / "a.jsonl", run_id="via-run")
        lb = Ledger(pathlib.Path(d) / "b.jsonl", run_id="via-apply")

        # The corpus and the registry are guarded above; the MODEL is the
        # third prerequisite and was not. stub_llm defaults to
        # granite4:micro-h and a machine that pulled it under another tag
        # (ibm/granite4:micro-h) gets a 404, which stub_llm raises as
        # RuntimeError — a red suite for an environmental difference, which
        # is how a suite stops being read. Same guard as
        # test_ledger_coverage.py, and for the same reason.
        try:
            recs_run, _ = run(items, "A", S.stub,
                              {"registry": reg, "ledger": la,
                               "rung0_offsets": "search"})
            recs_apply, _ = apply([], sources,
                                  {"registry": reg, "ledger": lb, "llm": S.stub,
                                   "rung0_offsets": "search"})
        except (RuntimeError, OSError) as exc:
            pytest.skip(f"no reachable model for rung 0: {exc}")
        la.close(); lb.close()

        rows_a = [r for r in la.rows if r.rung == 0]
        rows_b = [r for r in lb.rows if r.rung == 0]

    assert rows_a, "run() wrote no rung 0 ledger rows — the log line is on a " \
                   "path nothing calls, which is how this hid for months"
    assert len(rows_a) == len(rows_b), (
        f"run() wrote {len(rows_a)} rows, apply() wrote {len(rows_b)}. Two "
        "entry points to one rung that account differently is a divergence "
        "waiting to be measured wrong."
    )
    assert {r.extra.get("denominator") for r in rows_a} == \
           {r.extra.get("denominator") for r in rows_b}


def test_the_judge_is_sent_the_post_exactly_once():
    """Rung 4's template embeds the post, and Caller appends `text` as a POST
    section — so passing the source through both sent every post TWICE.
    Measured 2026-08-25 on the 240-record re-judge: doubled judge prompts
    (median 582 tokens) are past where BioMistral-7B stops answering (it EOSes
    after "{" above ~430 tokens, answers at ~312). The post goes in the
    template, and nothing else carries it."""
    from ladder.rungs import r4
    from ladder.schema import Record

    seen = {}

    def spy_llm(prompt, text, mode, **kw):
        seen["prompt"], seen["text"] = prompt, text
        return '{"span_ok":true,"code_ok":true,"confidence":0.5,"why":"x"}', {}

    rec = Record(doc_id="D.1", entity_type="reaction", text="rash",
                 spans=[(22, 26)], sct="271807003", record_id="D.1#0")
    source = "the whole forum post — rash and all — appears here once"
    r4.apply([rec], {"D.1": source}, {
        "judge_llm": spy_llm,
        "extractor_model": "family/a", "judge_model": "family/b"})
    combined = seen["prompt"] + seen["text"]
    assert combined.count(source) == 1, "the post must reach the judge once"
    assert seen["text"] == "", "r4 embeds the post itself; text adds a second copy"


def test_rung_2_is_sent_the_post_exactly_once():
    """Same defect as rung 4's, same fix: r2's PROMPT embeds the post, and
    Caller appends `text` as a POST section — so passing the source through
    both doubled every correction prompt. Caller sends the bare prompt when
    text is empty (test_an_empty_text_sends_the_bare_prompt); the post goes
    in the template, and nothing else carries it."""
    from ladder.rungs import r2
    from ladder.schema import R_CODE_UNKNOWN, Record, ZONE_REJECT

    seen = {}

    def spy_llm(prompt, text, mode, **kw):
        seen["prompt"], seen["text"] = prompt, text
        # Same code and spans back -> "reasserted", so no registry is needed.
        return ('{"span_text":"rash","start":22,"end":26,'
                '"code":"999999","confidence":0.5}'), {}

    rec = Record(doc_id="D.1", entity_type="reaction", text="rash",
                 spans=[(22, 26)], sct="999999", record_id="D.1#0")
    rec.checks["r1_verdict"] = ZONE_REJECT
    rec.checks["r1_reason"] = R_CODE_UNKNOWN
    source = "the whole forum post — rash and all — appears here once"
    r2.apply([rec], {"D.1": source}, {"llm": spy_llm})
    combined = seen["prompt"] + seen["text"]
    assert combined.count(source) == 1, "the post must reach rung 2 once"
    assert seen["text"] == "", "r2 embeds the post itself; text adds a second copy"

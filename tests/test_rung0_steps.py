"""Rung 0's four extraction steps — the prompt-engineering study.

Scope is IDENTICAL in all four. What varies is how the code is obtained:

    S0  label and code from memory, offsets from the model
    S1  label from memory, code from the KEYWORD TABLE, offsets from a tool
    S2  label picked from a retrieved shortlist

S3 — a pick from one fixed keyword list — was dropped 2026-08-24. See
docs/decisions.md: the best ontology-native printed list caps at 48.7%, the
full table cannot be printed, and per-mention retrieval is S2 by another name.

The record written to disk has the same shape in every step, or the four are
not comparable and the study reports nothing.

No network and no release download: the LLM is a scripted callable and the
vocabulary is the nine-concept index from test_registry_lookup.
"""

import json

import pytest

from ladder.rungs import r0
from ladder.schema import CONCEPT_LESS, REACTION
from tests.test_registry_lookup import reg  # noqa: F401  (fixture)

SOURCE = (
    "Hospitalization due extreme rectal bleed that required blood transfusion.\n"
    "I was extremely sick and initially felt I might not survive.\n"
)
SOURCES = {"D1": SOURCE}


class FakeLLM:
    """Replies from a scripted queue and records every prompt it was given."""

    def __init__(self, *replies):
        self.replies = list(replies)
        self.prompts = []

    def __call__(self, prompt, text, mode, **kw):
        self.prompts.append(prompt)
        raw = self.replies.pop(0) if self.replies else "{}"
        if not isinstance(raw, str):
            raw = json.dumps(raw)
        return raw, {"in": 10, "out": 5}


def keyword_table(**mapping):
    from ladder.keywords import KeywordTable

    return KeywordTable.from_mapping({k: list(v) for k, v in mapping.items()})


#: The keyword table rung 0 resolves names through — findings and disorders
#: only. Note what is NOT in it: 82249009 |California chicken (organism)| is
#: in the registry fixture and real, and rung 0 must not be able to reach it.
KW = keyword_table(**{
    "rectal hemorrhage": ["12063002"],
    "generally unwell": ["213257006"],
    "drowsy": ["271782001"],
})


def cfg(reg, step, **kw):  # noqa: F811
    """A rung 0 config. The keyword table is injected by default because
    every step that resolves a NAME needs one; pass keywords=None to run
    without it."""
    return {
        "rung0_step": step,
        "registry": reg,
        "llm": kw.pop("llm", None),
        "keywords": kw.pop("keywords", KW),
        **kw,
    }


FIND = {"mentions": [
    {"span_text": "extreme rectal bleed", "context": "due", "confidence": 0.9},
    {"span_text": "extremely sick", "context": "I was", "confidence": 0.8},
]}


# --- the fixed record contract ----------------------------------------------


@pytest.mark.parametrize("step", ["S0", "S1", "S2"])
def test_every_step_writes_the_same_record_keys(reg, step):  # noqa: F811
    llm = FakeLLM(
        {"mentions": [{"span_text": "extreme rectal bleed", "context": "due",
                       "start": 20, "end": 40, "sct_label": ["Rectal hemorrhage"],
                       "sct_code": "12063002", "confidence": 0.9}]},
        {"picks": [{"i": 0, "choice": 0}]},
    )
    recs, _ = r0.apply([], SOURCES, cfg(reg, step, llm=llm, keywords=KW))
    assert recs, f"{step} produced nothing"
    d = recs[0].to_dict()
    for key in ("doc_id", "entity_type", "text", "spans", "sct", "sct_label",
                "meddra", "confidence", "zone", "record_id", "checks"):
        assert key in d, f"{step} record is missing {key}"
    assert d["checks"]["rung0_step"] == step


# --- S0: everything from memory ---------------------------------------------


def test_s0_takes_the_code_from_the_model(reg):  # noqa: F811
    llm = FakeLLM({"mentions": [{
        "span_text": "extreme rectal bleed", "start": 20, "end": 40,
        "sct_label": ["Rectal hemorrhage"], "sct_code": "999999", "confidence": 0.9}]})
    recs, _ = r0.apply([], SOURCES, cfg(reg, "S0", llm=llm))
    assert recs[0].sct == "999999"
    assert recs[0].checks["code_source"] == "memory"


def test_s0_asks_for_a_code_and_for_offsets(reg):  # noqa: F811
    llm = FakeLLM({"mentions": []})
    r0.apply([], SOURCES, cfg(reg, "S0", llm=llm))
    assert "sct_code" in llm.prompts[0]
    assert "start" in llm.prompts[0]


def test_s0_still_locates_spans_deterministically(reg):  # noqa: F811
    """Offsets are asked for, and thrown away: the model's arithmetic is wrong
    at every model size while its quoting is verbatim 77% of the time."""
    llm = FakeLLM({"mentions": [{
        "span_text": "extremely sick", "start": 999, "end": 1200,
        "sct_label": ["Generally unwell"], "sct_code": "213257006", "confidence": 0.9}]})
    recs, _ = r0.apply([], SOURCES, cfg(reg, "S0", llm=llm))
    assert recs[0].spans == [(80, 94)]


# --- S1: label from memory, code from the vocabulary ------------------------


def test_s1_does_not_ask_the_model_for_a_code_or_offsets(reg):  # noqa: F811
    llm = FakeLLM({"mentions": []})
    r0.apply([], SOURCES, cfg(reg, "S1", llm=llm))
    assert "sct_code" not in llm.prompts[0]
    assert "start,end" not in llm.prompts[0]


def test_s1_resolves_the_code_from_the_label(reg):  # noqa: F811
    llm = FakeLLM({"mentions": [{
        "span_text": "extreme rectal bleed", "context": "due",
        "sct_label": ["Rectal hemorrhage"], "confidence": 0.9}]})
    recs, _ = r0.apply([], SOURCES, cfg(reg, "S1", llm=llm))
    assert recs[0].sct == "12063002"
    assert recs[0].sct_label == "Rectal hemorrhage"
    assert recs[0].checks["code_source"] == "keyword_table"


def test_s1_walks_the_label_list_and_reports_the_rank(reg):  # noqa: F811
    """One guess is not enough: the patient's own words miss SNOMED 57.1% of
    the time. Which rank won is a finding about the model."""
    llm = FakeLLM({"mentions": [{
        "span_text": "extreme rectal bleed", "context": "due",
        "sct_label": ["Extreme rectal bleed", "Rectal hemorrhage"], "confidence": 0.9}]})
    recs, _ = r0.apply([], SOURCES, cfg(reg, "S1", llm=llm))
    assert recs[0].sct == "12063002"
    assert recs[0].checks["label_rank"] == 1


def test_s1_leaves_no_code_when_nothing_resolves(reg):  # noqa: F811
    """A dead end is NOT CONCEPT_LESS: the model never asserted no code fits."""
    llm = FakeLLM({"mentions": [{
        "span_text": "extreme rectal bleed", "context": "due",
        "sct_label": ["Extreme rectal bleed"], "confidence": 0.9}]})
    recs, _ = r0.apply([], SOURCES, cfg(reg, "S1", llm=llm))
    assert recs[0].sct is None
    assert recs[0].checks["label_unresolved"] is True


def test_s1_passes_concept_less_through(reg):  # noqa: F811
    llm = FakeLLM({"mentions": [{
        "span_text": "extremely sick", "context": "I was",
        "sct_label": [CONCEPT_LESS], "confidence": 0.5}]})
    recs, _ = r0.apply([], SOURCES, cfg(reg, "S1", llm=llm))
    assert recs[0].sct == CONCEPT_LESS


def test_s1_uses_context_to_locate_the_span(reg):  # noqa: F811
    llm = FakeLLM({"mentions": [{
        "span_text": "extremely sick", "context": "I was",
        "sct_label": ["Generally unwell"], "confidence": 0.9}]})
    recs, _ = r0.apply([], SOURCES, cfg(reg, "S1", llm=llm))
    assert recs[0].spans == [(80, 94)]
    assert recs[0].checks["offsets"].startswith("context")


def test_s1_is_one_model_call_per_document(reg):  # noqa: F811
    """Same call count as S0, so the two stay comparable."""
    llm = FakeLLM(FIND)
    _, agg = r0.apply([], SOURCES, cfg(reg, "S1", llm=llm))
    assert len(llm.prompts) == 1
    assert agg["api_calls"] == 1


# --- S2: label picked from a retrieved shortlist ----------------------------


def test_s2_shows_the_model_a_shortlist_and_takes_its_index(reg):  # noqa: F811
    llm = FakeLLM(FIND, {"picks": [{"i": 0, "choice": 0}, {"i": 1, "choice": None}]})
    recs, _ = r0.apply([], SOURCES, cfg(reg, "S2", llm=llm,
                                        rung0_retrieval="lexical"))
    assert recs[0].checks["label_source"] == "shortlist"
    assert recs[0].sct is not None
    assert len(llm.prompts) == 2


def test_s2_candidates_are_recorded_for_audit(reg):  # noqa: F811
    llm = FakeLLM(FIND, {"picks": [{"i": 0, "choice": 0}, {"i": 1, "choice": 0}]})
    recs, _ = r0.apply([], SOURCES, cfg(reg, "S2", llm=llm))
    assert recs[0].checks["candidates"]
    assert "fsn" in recs[0].checks["candidates"][0]


def test_s2_null_choice_is_concept_less(reg):  # noqa: F811
    """Shown every candidate the vocabulary has and declining is an assertion."""
    llm = FakeLLM(FIND, {"picks": [{"i": 0, "choice": None}, {"i": 1, "choice": None}]})
    recs, _ = r0.apply([], SOURCES, cfg(reg, "S2", llm=llm))
    assert recs[0].sct == CONCEPT_LESS


def test_s2_out_of_range_index_is_refused_not_clamped(reg):  # noqa: F811
    llm = FakeLLM(FIND, {"picks": [{"i": 0, "choice": 99}, {"i": 1, "choice": 0}]})
    recs, _ = r0.apply([], SOURCES, cfg(reg, "S2", llm=llm))
    assert recs[0].sct is None
    assert recs[0].checks["bad_pick"] == 99


# --- shared behaviour -------------------------------------------------------


def test_an_unknown_step_is_refused(reg):  # noqa: F811
    with pytest.raises(ValueError, match="rung0_step"):
        r0.apply([], SOURCES, cfg(reg, "S9", llm=FakeLLM()))


def test_a_parse_failure_is_counted_never_repaired(reg):  # noqa: F811
    llm = FakeLLM("not json at all")
    recs, agg = r0.apply([], SOURCES, cfg(reg, "S1", llm=llm))
    assert recs == []
    assert agg["parse_failed"] == 1


def test_a_span_absent_from_the_source_is_kept_and_flagged(reg):  # noqa: F811
    """Rung 0 does not silently drop what it cannot ground — rung 1 rejects it."""
    llm = FakeLLM({"mentions": [{
        "span_text": "purple monkey dishwasher", "context": "",
        "sct_label": ["Generally unwell"], "confidence": 0.9}]})
    recs, _ = r0.apply([], SOURCES, cfg(reg, "S1", llm=llm))
    assert recs[0].checks["offsets"] == "not_in_source"
    assert recs[0].spans == [(-1, -1)]


def test_rung0_refuses_a_populated_record_list(reg):  # noqa: F811
    from ladder.schema import Record

    existing = [Record(doc_id="D1", entity_type=REACTION, text="x", spans=[(0, 1)])]
    with pytest.raises(RuntimeError, match="CREATES"):
        r0.apply(existing, SOURCES, cfg(reg, "S1", llm=FakeLLM()))


# --- the study has to be runnable without editing the manifest --------------


def test_run_py_exposes_a_rung0_step_flag():
    """Three dev runs, three commands. Editing the manifest between runs is
    how two runs end up labelled the same."""
    from ladder.run import main

    with pytest.raises(SystemExit):
        main(["ladder", "--rung0-step", "S9", "--split", "dev"])


def test_the_cli_no_longer_accepts_s3():
    """Dropped 2026-08-24. A flag that still takes it would fail deep inside
    run_step instead of at the command line."""
    from ladder.run import main

    with pytest.raises(SystemExit):
        main(["ladder", "--rung0-step", "S3", "--split", "dev"])


def test_the_step_flag_reaches_the_rung_config(monkeypatch):
    from ladder import run as run_mod

    seen = {}

    def fake(man, split, rungs, records, sources, registry, out_dir, run_id, meddra=None):
        seen.update(man["rungs"]["0"])
        raise SystemExit(0)

    monkeypatch.setattr(run_mod, "run_ladder", fake)
    with pytest.raises(SystemExit):
        run_mod.main(["ladder", "--rung0-step", "S2", "--split", "dev", "--limit", "1"])
    assert seen.get("rung0_step") == "S2"


# --- the pick menu has to be unambiguous ------------------------------------
#
# Measured on ARTHROTEC.107: with mentions numbered "0." and candidates
# numbered "0)", granite4:micro-h replied {"i":17,"choice":17} and
# {"i":11,"choice":"Bleeding"} — it conflated the two numbering systems and
# then answered with a name. Every record came back no_pick. That is a prompt
# defect, not a model finding, so the menu uses two different notations and the
# reply key says what it refers to.


def test_the_menu_does_not_number_mentions_and_candidates_alike():
    from ladder.schema import Record

    r = Record(doc_id="D1", entity_type=REACTION, text="extremely sick", spans=[(80, 94)])
    blocks = r0._blocks([(r, [{"i": 0, "fsn": "Generally unwell (finding)"}])])
    assert "reaction 0" in blocks
    assert "[0]" in blocks
    assert "0)" not in blocks


def test_a_pick_may_name_the_reaction_key(reg):  # noqa: F811
    llm = FakeLLM(FIND, {"picks": [{"reaction": 0, "choice": 0}]})
    recs, _ = r0.apply([], SOURCES, cfg(reg, "S2", llm=llm))
    assert recs[0].sct is not None


def test_the_old_i_key_still_works(reg):  # noqa: F811
    llm = FakeLLM(FIND, {"picks": [{"i": 0, "choice": 0}]})
    recs, _ = r0.apply([], SOURCES, cfg(reg, "S2", llm=llm))
    assert recs[0].sct is not None


def test_a_named_choice_is_recorded_as_a_bad_pick(reg):  # noqa: F811
    """Answering |Myalgia| when asked for a number is a measurable failure."""
    llm = FakeLLM(FIND, {"picks": [{"reaction": 0, "choice": "Myalgia"}]})
    recs, _ = r0.apply([], SOURCES, cfg(reg, "S2", llm=llm))
    assert recs[0].checks["bad_pick"] == "Myalgia"


# --- scope must not drift between steps -------------------------------------


def test_every_step_asks_for_spans_in_the_same_words():
    """Scope is fixed across the study. Measured: an earlier FIND prompt that
    added 'Finding it is the whole task here' made the model return whole
    SENTENCES as spans, which is a different task from the one S0 and S1 did.
    """
    for prompt in (r0.S0_PROMPT, r0.S1_PROMPT, r0.FIND_PROMPT):
        assert r0._ASK in prompt
    assert "whole task" not in r0.FIND_PROMPT


def test_an_unparseable_pick_reply_is_distinguishable_from_declining(reg):  # noqa: F811
    """Measured on ARTHROTEC.107 at S3: a 666-item menu costs 16.9k prompt
    tokens and came back as 14 completion tokens of malformed JSON. Landing
    that as no_pick would read as 'the model saw the menu and declined', which
    is the opposite of what happened.
    """
    llm = FakeLLM(FIND, '{"picks":[{"reaction":0,"choice":1}]}"')
    recs, agg = r0.apply([], SOURCES, cfg(reg, "S2", llm=llm))
    assert recs[0].checks["pick_parse_failed"] is True
    assert "no_pick" not in recs[0].checks
    assert agg["pick_parse_failed"] == 1


def test_a_clean_reply_leaves_no_pick_failure_flag(reg):  # noqa: F811
    llm = FakeLLM(FIND, {"picks": [{"reaction": 0, "choice": 0}]})
    recs, agg = r0.apply([], SOURCES, cfg(reg, "S2", llm=llm))
    assert "pick_parse_failed" not in recs[0].checks
    assert agg["pick_parse_failed"] == 0


# --- one menu per mention ---------------------------------------------------
#
# S2's shortlists genuinely differ per mention, so each one has to be shown.
# `_blocks(pairs, shared=...)`, which printed one identical menu once, went
# with S3 — it had no other caller, and dead scaffolding in a measurement
# harness is scaffolding somebody will later mistake for a code path in use.


def test_per_mention_menus_are_shown_per_mention():
    from ladder.schema import Record

    r1 = Record(doc_id="D1", entity_type=REACTION, text="a", spans=[(0, 1)])
    r2 = Record(doc_id="D1", entity_type=REACTION, text="b", spans=[(0, 1)])
    blocks = r0._blocks([(r1, [{"i": 0, "fsn": "Pain"}]), (r2, [{"i": 0, "fsn": "Nausea"}])])
    assert "[0] Pain" in blocks and "[0] Nausea" in blocks


def test_s2_still_sends_a_menu_per_mention(reg):  # noqa: F811
    llm = FakeLLM(FIND, {"picks": [{"reaction": 0, "choice": 0}]})
    r0.apply([], SOURCES, cfg(reg, "S2", llm=llm))
    assert llm.prompts[1].count("reaction ") >= 2


# --- prompt rules, each one measured against the corpus before writing ------


def test_every_step_excludes_treatments_and_procedures():
    """Measured: 1 of 7,311 gold reaction mentions names a procedure (0.01%).
    Sonnet 5 emitted "required blood transfusion" as a reaction in BOTH S2 and
    the retired S3 — a false positive in each. The rule is safe to state as
    prose because the corpus is near-unanimous.
    """
    for prompt in (r0.S0_PROMPT, r0.S1_PROMPT, r0.FIND_PROMPT):
        assert "treatment" in prompt.lower()


def test_no_step_tells_the_model_to_drop_intensifiers():
    """Measured: 506 gold mentions (6.9%) START with an intensifier and KEEP
    it — "severe stomach pain", "extreme stomach pain", "extremely sick". An
    earlier plan to add "quote the reaction, not the intensifier" would have
    broken those to fix a minority case. CADEC's own boundary convention is
    not stateable as prose; it is a job for examples.
    """
    for prompt in (r0.S0_PROMPT, r0.S1_PROMPT, r0.FIND_PROMPT):
        low = prompt.lower()
        assert "intensifier" not in low
        assert "not the words around it" not in low


# --- S3 is gone, and stays gone ---------------------------------------------
#
# Dropped 2026-08-24 on measurement. S3 was closed-set assignment over a
# PRINTED list, and no printable list works:
#
#   * the MedDRA list it used is the answer key's own inventory (all 666 codes
#     appear in the gold, none do not), so it measured a ceiling, not a method
#   * the best ontology-native alternative — SNOMED's Clinical manifestation
#     refset, 743 codes — caps at 48.7% of gold
#   * the real table is 227,554 keywords and cannot be printed at all
#   * a per-mention retrieved list IS S2
#
# The mechanism it left behind went with it: `_blocks(shared=...)` and the
# MedDRA CSV, neither of which had another caller.


def test_the_study_has_three_steps():
    assert r0.STEPS == ("S0", "S1", "S2")


def test_s3_is_refused_like_any_unknown_step(reg):  # noqa: F811
    with pytest.raises(ValueError, match="rung0_step"):
        r0.apply([], SOURCES, cfg(reg, "S3", llm=FakeLLM()))


@pytest.mark.parametrize("gone", ["keyword_list", "keyword_meddra", "KEYWORD_CSV"])
def test_the_fixed_list_machinery_is_removed(gone):
    assert not hasattr(r0, gone)


def test_rung_0_never_reads_the_meddra_csv():
    """The MedDRA table is a rung 1 cross-check, at `reference` mode. Rung 0
    reaching for it made the answer key's inventory a retrieval source."""
    import inspect

    src = inspect.getsource(r0)
    assert "meddra_codes.csv" not in src


# --- the keyword table is where rung 0's codes come from --------------------
#
# `Registry.resolve` searched every description in the release — organisms,
# products, substances and qualifiers included. That is the class that
# produced |California chicken (organism)| for a rectal bleed. rung 0 now
# resolves against data/keywords.csv, which is findings and disorders only.
#
# The registry stays in cfg: rung 1 needs exists / is_active / finding_status
# / terms over the WHOLE release, and 82249009 is real, active, and absent
# from the keyword table by design.


def test_s1_resolves_through_the_keyword_table(reg):  # noqa: F811
    llm = FakeLLM({"mentions": [
        {"span_text": "extreme rectal bleed", "context": "due",
         "sct_label": ["Rectal hemorrhage"], "confidence": 0.9},
    ]})
    recs, _ = r0.apply([], SOURCES, cfg(reg, "S1", llm=llm))
    assert recs[0].sct == "12063002"
    assert recs[0].checks["code_source"] == "keyword_table"


def test_s1_does_not_fall_back_to_the_registry(reg):  # noqa: F811
    """A name absent from the keyword table is UNRESOLVED, not looked up in
    the release. Falling back would reinstate exactly the search the table
    exists to replace, and hide which one answered."""
    assert reg.resolve(["California chicken"], findings_only=False)["code"] == "82249009"
    llm = FakeLLM({"mentions": [
        {"span_text": "extreme rectal bleed", "context": "due",
         "sct_label": ["California chicken"], "confidence": 0.9},
    ]})
    recs, _ = r0.apply([], SOURCES, cfg(reg, "S1", llm=llm))
    assert recs[0].sct is None
    assert recs[0].checks["label_unresolved"] is True


def test_a_missing_keyword_table_is_refused_loudly(reg):  # noqa: F811
    """Silently resolving nothing would report a build step nobody ran as a
    model that named no concepts."""
    llm = FakeLLM({"mentions": [
        {"span_text": "extreme rectal bleed", "context": "due",
         "sct_label": ["Rectal hemorrhage"], "confidence": 0.9},
    ]})
    with pytest.raises(RuntimeError, match="ladder.keywords --build"):
        r0.apply([], SOURCES, cfg(reg, "S1", llm=llm, keywords=None,
                                  keyword_table="data/no-such-table.csv"))


# --- S2's retrieval is a declared choice ------------------------------------
#
# Two retrieval paths, one flag, and the LEXICAL one stays the default until a
# measurement moves it. `rung0_retrieval` is in the manifest for the same
# reason `lexical_mode` and `span_match` are: a number produced under one
# retrieval is not comparable to a number produced under the other, so the
# choice has to be recorded beside the results rather than remembered.


class FakeDense:
    """An embedding index, without ollama or a 350 MB matrix."""

    def __init__(self):
        self.queries = []

    def search(self, text, k=20):
        self.queries.append((text, k))
        return [{"i": 0, "code": "12063002", "label": "Rectal hemorrhage",
                 "fsn": "Rectal hemorrhage", "score": 0.91, "via": "dense"}]


def test_dense_is_the_default_after_the_measurement(reg):  # noqa: F811
    """Measured 2026-08-24 over the same 6,595 gold mentions, same k, same
    answer key: lexical recall@20 = 61.8%, dense = 86.1%. Dense's TOP HIT
    alone (63.8%) beats the lexical top-20. The default moved on that, and on
    nothing else."""
    assert r0.DEFAULTS["rung0_retrieval"] == "dense"


def test_lexical_stays_reachable(reg):  # noqa: F811
    """The retired path is kept, not deleted: a number produced under one
    retriever is only interpretable next to the other."""
    llm = FakeLLM(FIND, {"picks": [{"reaction": 0, "choice": 0}]})
    recs, _ = r0.apply([], SOURCES, cfg(reg, "S2", llm=llm,
                                        rung0_retrieval="lexical"))
    assert recs[0].checks["candidates"][0]["via"] == "shortlist"
    assert recs[0].checks["rung0_retrieval"] == "lexical"


def test_dense_retrieval_is_used_when_declared(reg):  # noqa: F811
    dense = FakeDense()
    llm = FakeLLM(FIND, {"picks": [{"reaction": 0, "choice": 0}]})
    recs, _ = r0.apply([], SOURCES, cfg(reg, "S2", llm=llm,
                                        rung0_retrieval="dense", dense=dense))
    assert recs[0].sct == "12063002"
    assert recs[0].checks["candidates"][0]["via"] == "dense"
    assert dense.queries and dense.queries[0][1] == 20


def test_the_retrieval_choice_is_recorded_on_the_record(reg):  # noqa: F811
    """Which retriever produced the menu must be readable from the record, or
    two runs with different retrieval look identical on disk."""
    llm = FakeLLM(FIND, {"picks": [{"reaction": 0, "choice": 0}]})
    recs, _ = r0.apply([], SOURCES, cfg(reg, "S2", llm=llm,
                                        rung0_retrieval="dense", dense=FakeDense()))
    assert recs[0].checks["rung0_retrieval"] == "dense"


def test_an_unknown_retriever_is_refused(reg):  # noqa: F811
    llm = FakeLLM(FIND, {"picks": []})
    with pytest.raises(ValueError, match="rung0_retrieval"):
        r0.apply([], SOURCES, cfg(reg, "S2", llm=llm, rung0_retrieval="magic"))


def test_dense_without_an_index_says_how_to_build_it(reg):  # noqa: F811
    llm = FakeLLM(FIND, {"picks": []})
    with pytest.raises(RuntimeError, match="ladder.embed --build"):
        r0.apply([], SOURCES, cfg(reg, "S2", llm=llm, rung0_retrieval="dense",
                                  embed_prefix="ladder/cache/no-such-index"))


def test_the_two_retrievers_hand_back_the_same_shape(reg):  # noqa: F811
    """S2's pick logic reads `i`, `code` and `fsn`/`label`. A retriever that
    returned a different shape would fail at the pick, not at the swap."""
    llm = FakeLLM(FIND, {"picks": [{"reaction": 0, "choice": 0}]})
    lex, _ = r0.apply([], SOURCES, cfg(reg, "S2", llm=llm))
    llm = FakeLLM(FIND, {"picks": [{"reaction": 0, "choice": 0}]})
    den, _ = r0.apply([], SOURCES, cfg(reg, "S2", llm=llm,
                                       rung0_retrieval="dense", dense=FakeDense()))
    keys = {"i", "code", "label", "fsn", "via"}
    assert keys <= set(lex[0].checks["candidates"][0])
    assert keys <= set(den[0].checks["candidates"][0])


# --- what the model PROPOSED, not just what resolved -------------------------
#
# `_resolve_labels` wrote `label_unresolved: True` and nothing else, so a
# failed resolution recorded THAT it failed and not WHAT was said. Two very
# different failures then looked identical on disk:
#
#     the model named nothing usable       -> a MODEL failure
#     the model named a real concept the
#     keyword table happens not to carry   -> a TABLE failure
#
# Measured on ARTHROTEC.107 with granite4:micro-h, S1: the model answered
# sct_label: ["AFTERPROMPT"] — a prompt artifact, not a clinical term. That is
# emphatically the first kind, and it was invisible in the record.
#
# It also makes the lookup-vs-retrieval comparison impossible: you cannot
# measure whether dense retrieval rescues an imperfect label if the imperfect
# label was discarded.


def test_the_proposed_labels_are_recorded_even_when_none_resolves(reg):  # noqa: F811
    llm = FakeLLM({"mentions": [{
        "span_text": "extreme rectal bleed", "context": "due",
        "sct_label": ["AFTERPROMPT", "Not a concept"], "confidence": 0.9}]})
    recs, _ = r0.apply([], SOURCES, cfg(reg, "S1", llm=llm))
    assert recs[0].sct is None
    assert recs[0].checks["label_unresolved"] is True
    assert recs[0].checks["labels_proposed"] == ["AFTERPROMPT", "Not a concept"]


def test_the_proposed_labels_are_recorded_when_one_does_resolve(reg):  # noqa: F811
    """Kept on success too. Which RANK won is only interpretable next to what
    the losing names were."""
    llm = FakeLLM({"mentions": [{
        "span_text": "extreme rectal bleed", "context": "due",
        "sct_label": ["Not a concept", "Rectal hemorrhage"], "confidence": 0.9}]})
    recs, _ = r0.apply([], SOURCES, cfg(reg, "S1", llm=llm))
    assert recs[0].sct == "12063002"
    assert recs[0].checks["labels_proposed"] == ["Not a concept", "Rectal hemorrhage"]
    assert recs[0].checks["label_rank"] == 1


def test_a_bare_string_label_is_recorded_as_a_list(reg):  # noqa: F811
    """The prompt asks for up to three names and models sometimes send one
    string. One shape on disk, or the column cannot be read."""
    llm = FakeLLM({"mentions": [{
        "span_text": "extreme rectal bleed", "context": "due",
        "sct_label": "Rectal hemorrhage", "confidence": 0.9}]})
    recs, _ = r0.apply([], SOURCES, cfg(reg, "S1", llm=llm))
    assert recs[0].checks["labels_proposed"] == ["Rectal hemorrhage"]


def test_no_labels_proposed_is_an_empty_list_not_a_missing_key(reg):  # noqa: F811
    """'the model named nothing' is a fact worth recording, and an absent key
    reads as 'this run predates the column'."""
    llm = FakeLLM({"mentions": [{
        "span_text": "extreme rectal bleed", "context": "due", "confidence": 0.9}]})
    recs, _ = r0.apply([], SOURCES, cfg(reg, "S1", llm=llm))
    assert recs[0].checks["labels_proposed"] == []


# --- the DECIDE step, shared by S1 and S2 -----------------------------------
#
# Multi-label exists to raise the chance that SOMETHING maps. What was missing
# is the second half: once several names map, the model has to say which
# candidate matches the ORIGINAL text.
#
# Measured on the real keyword table — the model proposes three names for
# "extreme rectal bleed" and all three map:
#
#     'rectal pain'       -> 77880009   <- WON, on list position alone
#     'rectal bleeding'   -> 12063002   <- right, mapped fine, discarded
#     'rectal hemorrhage' -> 12063002   <- right, mapped fine, discarded
#
# `resolve()` walks the list and returns the FIRST hit, so the span text is
# never consulted at the decision point. Multi-label was not three shots at a
# mapping; it was one shot with two spares that fire only on a total miss.
#
# S2 already had this step. S1 now uses the SAME one — not a new rung 0 step,
# because the thing that distinguishes S0/S1/S2 is where the CODE comes from
# and that is unchanged.


def test_s1_pools_every_label_that_maps_instead_of_taking_the_first(reg):  # noqa: F811
    """The measured defect, pinned. All three map; the pick decides."""
    kw = keyword_table(**{
        "rectal pain": ["77880009"],
        "rectal bleeding": ["12063002"],
        "rectal hemorrhage": ["12063002"],
    })
    llm = FakeLLM(
        {"mentions": [{"span_text": "extreme rectal bleed", "context": "due",
                       "sct_label": ["rectal pain", "rectal bleeding",
                                     "rectal hemorrhage"], "confidence": 0.9}]},
        {"picks": [{"reaction": 0, "choice": 1}]},
    )
    recs, _ = r0.apply([], SOURCES, cfg(reg, "S1", llm=llm, keywords=kw))
    assert recs[0].sct == "12063002", "the pick must beat list position"
    assert len(recs[0].checks["candidates"]) == 2, "12063002 appears once, deduped"


def test_s1_shows_the_original_text_in_the_pick(reg):  # noqa: F811
    """The whole point: the decision is against the SPAN, not against the
    model's own first guess."""
    kw = keyword_table(**{"rectal pain": ["77880009"], "rectal bleeding": ["12063002"]})
    llm = FakeLLM(
        {"mentions": [{"span_text": "extreme rectal bleed", "context": "due",
                       "sct_label": ["rectal pain", "rectal bleeding"],
                       "confidence": 0.9}]},
        {"picks": [{"reaction": 0, "choice": 1}]},
    )
    r0.apply([], SOURCES, cfg(reg, "S1", llm=llm, keywords=kw))
    assert "extreme rectal bleed" in llm.prompts[1]


def test_s1_does_not_pay_for_a_pick_when_there_is_nothing_to_decide(reg):  # noqa: F811
    """One candidate is not a choice. A second call for it is pure cost."""
    kw = keyword_table(**{"rectal bleeding": ["12063002"]})
    llm = FakeLLM({"mentions": [{"span_text": "extreme rectal bleed", "context": "due",
                                 "sct_label": ["rectal bleeding"], "confidence": 0.9}]})
    recs, agg = r0.apply([], SOURCES, cfg(reg, "S1", llm=llm, keywords=kw))
    assert recs[0].sct == "12063002"
    assert agg["api_calls"] == 1


def test_s1_pools_an_ambiguous_keywords_own_candidates(reg):  # noqa: F811
    """A keyword naming two concepts is a decision too, and `resolve` used to
    take hits[0] silently. 9.8% of keywords named more than one concept before
    the build picked an owner."""
    kw = keyword_table(**{"coma": ["371632003", "50061006"]})
    llm = FakeLLM(
        {"mentions": [{"span_text": "extreme rectal bleed", "context": "due",
                       "sct_label": ["coma"], "confidence": 0.9}]},
        {"picks": [{"reaction": 0, "choice": 1}]},
    )
    recs, _ = r0.apply([], SOURCES, cfg(reg, "S1", llm=llm, keywords=kw))
    assert recs[0].sct == "50061006"


def test_s1_still_reports_nothing_when_no_label_maps(reg):  # noqa: F811
    kw = keyword_table(**{"rectal bleeding": ["12063002"]})
    llm = FakeLLM({"mentions": [{"span_text": "extreme rectal bleed", "context": "due",
                                 "sct_label": ["AFTERPROMPT"], "confidence": 0.9}]})
    recs, agg = r0.apply([], SOURCES, cfg(reg, "S1", llm=llm, keywords=kw))
    assert recs[0].sct is None
    assert recs[0].checks["label_unresolved"] is True
    assert agg["api_calls"] == 1, "nothing to decide, so nothing to pay for"


def test_s1_concept_less_needs_no_pick(reg):  # noqa: F811
    kw = keyword_table(**{"rectal bleeding": ["12063002"]})
    llm = FakeLLM({"mentions": [{"span_text": "extremely sick", "context": "I was",
                                 "sct_label": [CONCEPT_LESS], "confidence": 0.5}]})
    recs, agg = r0.apply([], SOURCES, cfg(reg, "S1", llm=llm, keywords=kw))
    assert recs[0].sct == CONCEPT_LESS
    assert agg["api_calls"] == 1


def test_s1_declining_the_menu_is_concept_less(reg):  # noqa: F811
    """Shown every concept its own names reached and declining is an assertion
    that none fits — the same reading S2 already gives choice: null."""
    kw = keyword_table(**{"rectal pain": ["77880009"], "rectal bleeding": ["12063002"]})
    llm = FakeLLM(
        {"mentions": [{"span_text": "extreme rectal bleed", "context": "due",
                       "sct_label": ["rectal pain", "rectal bleeding"],
                       "confidence": 0.9}]},
        {"picks": [{"reaction": 0, "choice": None}]},
    )
    recs, _ = r0.apply([], SOURCES, cfg(reg, "S1", llm=llm, keywords=kw))
    assert recs[0].sct == CONCEPT_LESS


def test_s1_records_which_label_reached_the_chosen_code(reg):  # noqa: F811
    """Which of the model's names won is the finding multi-label exists to
    produce. It has to survive onto the record."""
    kw = keyword_table(**{"rectal pain": ["77880009"], "rectal bleeding": ["12063002"]})
    llm = FakeLLM(
        {"mentions": [{"span_text": "extreme rectal bleed", "context": "due",
                       "sct_label": ["rectal pain", "rectal bleeding"],
                       "confidence": 0.9}]},
        {"picks": [{"reaction": 0, "choice": 1}]},
    )
    recs, _ = r0.apply([], SOURCES, cfg(reg, "S1", llm=llm, keywords=kw))
    assert recs[0].checks["label_rank"] == 1
    assert recs[0].checks["labels_proposed"] == ["rectal pain", "rectal bleeding"]
    assert recs[0].checks["code_source"] == "keyword_table"


def test_s1_batches_the_pick_into_one_call_per_document(reg):  # noqa: F811
    """Two mentions needing a decision is ONE second call, not two — the same
    batching S2 uses, or S1's cost stops being comparable to it."""
    kw = keyword_table(**{
        "rectal pain": ["77880009"], "rectal bleeding": ["12063002"],
        "generally unwell": ["213257006"], "feeling unwell": ["267036007"],
    })
    llm = FakeLLM(
        {"mentions": [
            {"span_text": "extreme rectal bleed", "context": "due",
             "sct_label": ["rectal pain", "rectal bleeding"], "confidence": 0.9},
            {"span_text": "extremely sick", "context": "I was",
             "sct_label": ["generally unwell", "feeling unwell"], "confidence": 0.8},
        ]},
        {"picks": [{"reaction": 0, "choice": 1}, {"reaction": 1, "choice": 0}]},
    )
    recs, agg = r0.apply([], SOURCES, cfg(reg, "S1", llm=llm, keywords=kw))
    assert agg["api_calls"] == 2
    assert [r.sct for r in recs] == ["12063002", "213257006"]


def test_s1_mixes_decided_and_undecided_mentions_without_shifting_indices(reg):  # noqa: F811
    """Only the ambiguous mentions go in the menu, so menu position is NOT
    mention position. Getting that wrong assigns one mention's pick to
    another, silently."""
    kw = keyword_table(**{
        "rectal bleeding": ["12063002"],
        "generally unwell": ["213257006"], "feeling unwell": ["267036007"],
    })
    llm = FakeLLM(
        {"mentions": [
            {"span_text": "extreme rectal bleed", "context": "due",
             "sct_label": ["rectal bleeding"], "confidence": 0.9},   # 1 candidate
            {"span_text": "extremely sick", "context": "I was",
             "sct_label": ["generally unwell", "feeling unwell"], "confidence": 0.8},
        ]},
        {"picks": [{"reaction": 0, "choice": 1}]},   # menu index 0 == mention 1
    )
    recs, _ = r0.apply([], SOURCES, cfg(reg, "S1", llm=llm, keywords=kw))
    assert recs[0].sct == "12063002", "decided without a pick"
    assert recs[1].sct == "267036007", "the pick belongs to the SECOND mention"


def test_s1_records_the_models_own_words_as_sct_label(reg):  # noqa: F811
    """`sct_label` is "what the MODEL said that code means" (schema.py), and
    rung 1's label_check compares it against the vocabulary's own terms for
    that code. Filling it FROM the vocabulary makes the check vacuous — it
    could never fail. The menu shows the vocabulary's words so the model can
    judge the concept; the RECORD keeps the model's."""
    kw = keyword_table(**{"rectal pain": ["77880009"], "rectal bleed": ["12063002"]})
    llm = FakeLLM(
        {"mentions": [{"span_text": "extreme rectal bleed", "context": "due",
                       "sct_label": ["rectal pain", "rectal bleed"],
                       "confidence": 0.9}]},
        {"picks": [{"reaction": 0, "choice": 1}]},
    )
    recs, _ = r0.apply([], SOURCES, cfg(reg, "S1", llm=llm, keywords=kw))
    assert recs[0].sct == "12063002"
    assert recs[0].sct_label == "rectal bleed", "the model's words, not the FSN"


def test_the_menu_shows_the_vocabularys_words_not_the_models(reg):  # noqa: F811
    """Showing the model its own wording back invites it to prefer whichever
    it wrote first, which is the bias the decide step exists to remove."""
    kw = keyword_table(**{"rectal haemorrhage": ["12063002"], "rectal pain": ["77880009"]})
    llm = FakeLLM(
        {"mentions": [{"span_text": "extreme rectal bleed", "context": "due",
                       "sct_label": ["rectal haemorrhage", "rectal pain"],
                       "confidence": 0.9}]},
        {"picks": [{"reaction": 0, "choice": 0}]},
    )
    r0.apply([], SOURCES, cfg(reg, "S1", llm=llm, keywords=kw))
    menu = llm.prompts[1]
    assert "Rectal hemorrhage (finding)" in menu, "the vocabulary's FSN"


def test_label_check_can_still_fail_on_an_s1_record(reg):  # noqa: F811
    """The regression this guards: a model that names one concept and lands on
    another must still be catchable by rung 1."""
    from ladder.rungs import r1
    from tests.test_ladder_rungs import StubVocab

    kw = keyword_table(**{"california chicken": ["271782001"], "drowsy": ["999999999"]})
    llm = FakeLLM({"mentions": [{"span_text": "bit drowsy", "context": "feel a",
                                 "sct_label": ["california chicken"], "confidence": 0.9}]})
    recs, _ = r0.apply([], {"D1": "I feel a bit drowsy today."},
                       cfg(reg, "S1", llm=llm, keywords=kw))
    assert recs[0].sct == "271782001"
    assert recs[0].sct_label == "california chicken"
    _, _, checks = r1.zone(recs[0], "I feel a bit drowsy today.", StubVocab(), {})
    assert checks["label_verified"] is False, "label_check must still be able to fail"


# --- truncated is not the same as malformed ---------------------------------
#
# Measured 2026-08-24: gpt-oss:20b at S0 burned all 16,000 completion tokens
# and returned an empty string. The ledger said parse_failed / json_decode,
# which is the number rung 0 exists to report — the harness's own cap
# published as the model's JSON reliability.


class TruncatedLLM(FakeLLM):
    def __call__(self, prompt, text, mode, **kw):
        self.prompts.append(prompt)
        return "", {"in": 10, "out": 16000, "usd": 0.0, "truncated": True}


def test_a_truncated_reply_is_flagged_as_truncated_not_just_parse_failed(reg):  # noqa: F811
    _, agg = r0.apply([], SOURCES, cfg(reg, "S1", llm=TruncatedLLM()))
    assert agg["truncated"] == 1


def test_a_truncated_reply_still_counts_as_a_parse_failure(reg):  # noqa: F811
    """It IS one — nothing usable came back. The two counts overlap on
    purpose; what must not happen is the cause being unrecoverable."""
    _, agg = r0.apply([], SOURCES, cfg(reg, "S1", llm=TruncatedLLM()))
    assert agg["parse_failed"] == 1


def test_the_ledger_row_carries_the_reason(reg):  # noqa: F811
    """`reason` is what a report groups by. json_decode and truncated are
    different findings and must not share a label."""
    from ladder.ledger import Ledger
    import json as _json, pathlib, tempfile

    with tempfile.TemporaryDirectory() as d:
        led = Ledger(pathlib.Path(d) / "l.jsonl", run_id="t")
        r0.apply([], SOURCES, cfg(reg, "S1", llm=TruncatedLLM(), ledger=led))
        led.flush()
        rows = [_json.loads(x) for x in (pathlib.Path(d) / "l.jsonl").read_text().splitlines() if x.strip()]
        assert rows[0]["reason"] == "truncated"


def test_an_ordinary_bad_reply_is_still_json_decode(reg):  # noqa: F811
    from ladder.ledger import Ledger
    import json as _json, pathlib, tempfile

    class Garbage(FakeLLM):
        def __call__(self, prompt, text, mode, **kw):
            self.prompts.append(prompt)
            return "not json at all", {"in": 10, "out": 5, "usd": 0.0}

    with tempfile.TemporaryDirectory() as d:
        led = Ledger(pathlib.Path(d) / "l.jsonl", run_id="t")
        _, agg = r0.apply([], SOURCES, cfg(reg, "S1", llm=Garbage(), ledger=led))
        led.flush()
        rows = [_json.loads(x) for x in (pathlib.Path(d) / "l.jsonl").read_text().splitlines() if x.strip()]
        assert rows[0]["reason"] == "json_decode"
        assert agg["truncated"] == 0

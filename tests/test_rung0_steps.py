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

import pathlib

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


class FakeDense:
    """An embedding index, without ollama, numpy or a 350 MB matrix.

    S2's default retriever is `dense`, which loads ladder/cache/keywords.*
    through ladder.embed and therefore needs numpy. Both are local-only
    extras: CI installs requirements.txt, which pins pyyaml and nothing else,
    and a fresh clone has no index. Sixteen tests that are about the PICK
    logic — menu indices, bad picks, declining, parse failures — were failing
    on a retriever they do not test.

    So the pick tests are handed a retriever. It returns the same shape the
    real one does (`i`, `code`, `label`, `fsn`, `via`), which is the contract
    _step_pick actually reads.
    """

    def __init__(self, hits=None):
        self.queries = []
        self._hits = hits

    def search(self, text, k=20):
        self.queries.append((text, k))
        if self._hits is not None:
            return self._hits
        return [{"i": 0, "code": "12063002", "label": "Rectal hemorrhage",
                 "fsn": "Rectal hemorrhage", "score": 0.91, "via": "dense"}]


def cfg(reg, step, **kw):  # noqa: F811
    """A rung 0 config.

    The keyword table is injected by default because every step that resolves
    a NAME needs one; pass keywords=None to run without it. A FakeDense is
    injected for the same reason — S2 defaults to dense retrieval, which needs
    numpy and a built index, and neither exists in CI. Pass dense=None to
    exercise the real loader.
    """
    dense = kw.pop("dense", "default")
    out = {
        "rung0_step": step,
        "registry": reg,
        "llm": kw.pop("llm", None),
        "keywords": kw.pop("keywords", KW),
        **kw,
    }
    if dense == "default":
        out.setdefault("dense", FakeDense())
    elif dense is not None:
        out["dense"] = dense
    return out


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


def test_a_menu_decline_is_not_concept_less(reg):  # noqa: F811
    """REVISED 2026-08-25. Declining the menu used to write CONCEPT_LESS on
    the theory that the model was "shown every candidate the vocabulary has".
    It was shown k of 227,554 — the menu misses the gold code for 13.0% of
    coded mentions even deduped — so a decline asserts "none of THESE", not
    "no concept exists". The scorer credits CONCEPT_LESS as CORRECT against
    concept-less gold, so the old behaviour scored a claim the model never
    made. The decline now degrades to None (abstained), flagged and counted.
    """
    llm = FakeLLM(FIND, {"picks": [{"i": 0, "choice": None}, {"i": 1, "choice": None}]})
    recs, agg = r0.apply([], SOURCES, cfg(reg, "S2", llm=llm))
    assert recs[0].sct is None
    assert recs[0].sct_label is None
    assert recs[0].checks["declined_shortlist"] is True
    assert agg["declined_shortlist"] == 2


def test_pick_failures_reach_the_run_summary(reg):  # noqa: F811
    """no_pick and bad_pick were per-record flags only, so a run where the
    model fumbled every menu still printed a clean summary. They aggregate
    like every other failure counter now."""
    llm = FakeLLM(FIND, {"picks": [{"i": 0, "choice": 99}]})
    recs, agg = r0.apply([], SOURCES, cfg(reg, "S2", llm=llm))
    assert agg["bad_pick"] == 1
    assert agg["no_pick"] == 1


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
    """main() loads the corpus before it reaches run_ladder and returns 2
    rather than raising when it is absent, so CI never reaches the flag."""
    import json as _json

    man = _json.loads(pathlib.Path("manifest.json").read_text())
    if not (pathlib.Path(man["corpus"]["cadec_root"]) / "text").is_dir():
        pytest.skip("no corpus — this test drives run.main()")
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


def test_every_step_asks_for_every_occurrence():
    """Measured 2026-08-25: 385 gold mentions (5.6%, exclusions applied) are
    an exact repeat of an earlier span in the same document — CADEC annotates
    every occurrence. The model dedupes unless told otherwise: on the frozen
    S2 it reported "spotting" once where gold has "spotting" and "spotting
    problems". Safe to state as prose because the convention is unanimous:
    a repeat is never left unannotated.
    """
    for prompt in (r0.S0_PROMPT, r0.S1_PROMPT, r0.FIND_PROMPT):
        assert "every time" in prompt.lower() or "each time" in prompt.lower()


def test_every_step_says_vague_states_count():
    """Gold codes general malaise — "extremely sick" is 213257006 — and the
    frozen S2 skipped it on the very first dev document. Stated as prose
    because it widens recall without touching span boundaries."""
    for prompt in (r0.S0_PROMPT, r0.S1_PROMPT, r0.FIND_PROMPT):
        assert "vague" in prompt.lower() or "general" in prompt.lower()


def test_every_step_scopes_to_all_conditions_not_only_adrs():
    """The answer key is WIDER than "adverse reaction": CADEC's Symptom,
    Disease and Finding annotations all map to REACTION (schema.py
    CADEC_TYPE_MAP), so gold includes the condition the drug was taken for —
    "Lower back pain" in dev doc ARTHROTEC.139. Measured on the 2026-08-25
    arm-2 dev run: 20 of 68 false negatives were these non-ADR mentions. A
    prompt that says only "adverse reaction" tells the model to skip a fifth
    of its misses."""
    for prompt in (r0.S0_PROMPT, r0.S1_PROMPT, r0.FIND_PROMPT):
        assert "taken for" in prompt.lower()


def test_every_step_demands_the_whole_list():
    """Measured on the arm-2 dev run: false negatives concentrate in
    symptom-dense posts — docs with 12-14 gold mentions got 5-8 from the
    model, which stops partway through comma-lists like "drowsiness,
    grogginess, memory loss, loss of stamina". """
    for prompt in (r0.S0_PROMPT, r0.S1_PROMPT, r0.FIND_PROMPT):
        assert "whole post" in prompt.lower()


def test_the_pick_prompt_states_the_base_concept_rule():
    """The single biggest dev failure: 45 of 226 mentions (20%) had the gold
    code ON the menu and the model picked a more specific sibling — gold is
    |Abdominal pain| for "Very very severe abdonimal pain", |Neck pain| for
    "neck pain while turning head". CADEC codes the plain base concept."""
    low = r0.PICK_PROMPT.lower()
    assert "plain" in low


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


# --- the few-shot arm --------------------------------------------------------
#
# CADEC's span conventions are not all stateable as prose (the intensifier
# test above is the proof), so a worked example is the remaining lever. It is
# an ARM, not the default: rung0_fewshot defaults to False and the example
# block reaches the prompt only when a run turns it on, so its effect is
# measurable against the frozen S2 rather than folded into it.


def test_fewshot_is_off_by_default(reg):  # noqa: F811
    llm = FakeLLM(FIND, {"picks": [{"reaction": 0, "choice": 0}]})
    r0.apply([], SOURCES, cfg(reg, "S2", llm=llm))
    assert r0.FEWSHOT not in llm.prompts[0]


@pytest.mark.parametrize("step,replies", [
    ("S0", [{"mentions": []}]),
    ("S1", [{"mentions": []}]),
    ("S2", [{"mentions": []}]),
])
def test_fewshot_reaches_every_extraction_prompt(reg, step, replies):  # noqa: F811
    llm = FakeLLM(*replies)
    r0.apply([], SOURCES, cfg(reg, step, llm=llm, rung0_fewshot=True))
    assert r0.FEWSHOT in llm.prompts[0]


def test_the_fewshot_example_is_synthetic():
    """CADEC is non-transferable and prompts are tracked files, so the worked
    example must never quote the corpus. Spot-checked against the corpus text
    this suite already carries plus the drug names of every CADEC forum."""
    low = r0.FEWSHOT.lower()
    for leaked in ("rectal bleed", "spotting", "arthrotec", "lipitor",
                   "voltaren", "extremely sick", "not survive"):
        assert leaked not in low


def test_the_fewshot_example_keeps_its_intensifier():
    """The dominant gold convention (6.8% keep vs 2.2% drop) — the example
    must model it, not fight it."""
    assert "terrible cramps" in r0.FEWSHOT.lower()


# --- the no_concept pick ------------------------------------------------------


def test_no_concept_pick_is_concept_less(reg):  # noqa: F811
    """`"choice": "no_concept"` is the explicit assertion the decline change
    removed: not "none of these candidates" but "this is not a codable
    reaction". 10 of 226 dev gold mentions (4%) are concept-less, and after
    the decline fix S2 had no way to ever answer them."""
    llm = FakeLLM(FIND, {"picks": [{"reaction": 0, "choice": "no_concept"},
                                   {"reaction": 1, "choice": 0}]})
    recs, agg = r0.apply([], SOURCES, cfg(reg, "S2", llm=llm))
    assert recs[0].sct == CONCEPT_LESS
    assert recs[0].sct_label == CONCEPT_LESS
    assert agg["declined_shortlist"] == 0
    assert recs[1].sct is not None


def test_a_null_choice_still_declines_not_asserts(reg):  # noqa: F811
    llm = FakeLLM(FIND, {"picks": [{"reaction": 0, "choice": None},
                                   {"reaction": 1, "choice": 0}]})
    recs, _ = r0.apply([], SOURCES, cfg(reg, "S2", llm=llm))
    assert recs[0].sct is None
    assert recs[0].checks["declined_shortlist"] is True


def test_the_pick_prompt_offers_no_concept():
    assert "no_concept" in r0.PICK_PROMPT


# --- pool-derived few-shot ----------------------------------------------------
#
# The synthetic example teaches span mechanics; only real CADEC examples can
# teach CADEC's own conventions (base-concept coding, exhaustive lists, the
# treated condition counting). They are rendered AT RUNTIME from data/ — the
# corpus is non-transferable and never committed; only doc IDs are. Examples
# must come from the POOL split: a dev example would put its own gold answers
# in the prompt while that document is being scored.


def test_render_fewshot_shows_post_and_every_mention():
    block = r0.render_fewshot([
        ("Got cramps. Then cramps again.", ["cramps", "cramps"]),
    ])
    assert "Got cramps. Then cramps again." in block
    assert block.count('"cramps"') == 2
    assert "again" in block.lower()  # the repeat is annotated as a repeat


def test_pool_fewshot_docs_reach_the_prompt(reg):  # noqa: F811
    llm = FakeLLM({"mentions": []})
    r0.apply([], SOURCES, cfg(reg, "S2", llm=llm, rung0_fewshot=True,
                              rung0_fewshot_block="POOLBLOCK-SENTINEL"))
    assert "POOLBLOCK-SENTINEL" in llm.prompts[0]
    assert r0.FEWSHOT not in llm.prompts[0]


def test_fewshot_docs_must_come_from_the_pool(tmp_path):
    """A dev or test example doc would leak its gold into the prompt of a
    scored run. Refused, not warned."""
    import json as _json
    (tmp_path / "pool.json").write_text(
        _json.dumps({"split": "pool", "doc_ids": ["ARTHROTEC.1"]}))
    man = {"corpus": {"splits_dir": str(tmp_path), "cadec_root": "unused"}}
    with pytest.raises(ValueError, match="pool"):
        r0.pool_fewshot_block(man, ["ARTHROTEC.107"], loader=lambda root: {})


# --- name-augmented retrieval (S2) -------------------------------------------
#
# The MACHINERY: when a FIND reply carries sct_label names, the retriever
# queries the span AND each name and merges the menus. Built for arm 4
# (2026-08-25) because 35 of 226 arm-3 mentions never had the gold code on a
# span-only menu ("extremely sick" cannot surface |Generally unwell|).
#
# THE PROMPT NO LONGER ASKS FOR NAMES — a measured retreat, not an oversight.
# Arm 4 (k=40) and 4b (k=20) both asked, and both LOST to arm 3 (F1 exact
# 0.236 / 0.232 vs 0.289): retrieval misses fell 35 -> 23 but the find step
# emitted fewer, worse-bounded mentions and the pick step erred more. The
# merge stays because it is exercised by any reply that carries labels and
# is inert otherwise.


def test_find_does_not_ask_for_names():
    """Asking FIND for concept names cost more at extraction than the better
    menus bought back — see the section comment. The field must not creep
    back into the prompt without a new measurement."""
    assert "sct_label" not in r0.FIND_PROMPT


def test_s2_retrieves_on_span_and_proposed_names(reg):  # noqa: F811
    dense = FakeDense()
    llm = FakeLLM(
        {"mentions": [{"span_text": "extremely sick", "context": "I was",
                       "sct_label": ["Generally unwell"], "confidence": 0.9}]},
        {"picks": [{"reaction": 0, "choice": 0}]},
    )
    r0.apply([], SOURCES, cfg(reg, "S2", llm=llm, dense=dense))
    queried = [q for q, _ in dense.queries]
    assert "extremely sick" in queried
    assert "Generally unwell" in queried


def test_s2_merged_menu_dedupes_by_code_and_caps_at_k(reg):  # noqa: F811
    span_hits = [{"i": 0, "code": "39104002", "label": "sickness",
                  "fsn": "sickness", "score": 0.9, "via": "dense"}]
    label_hits = [{"i": 0, "code": "39104002", "label": "illness",
                   "fsn": "illness", "score": 0.8, "via": "dense"},
                  {"i": 1, "code": "213257006", "label": "generally unwell",
                   "fsn": "generally unwell", "score": 0.7, "via": "dense"}]

    class TwoQueryDense(FakeDense):
        def search(self, text, k=20):
            self.queries.append((text, k))
            return list(span_hits) if text == "extremely sick" else list(label_hits)

    llm = FakeLLM(
        {"mentions": [{"span_text": "extremely sick", "context": "I was",
                       "sct_label": ["Generally unwell"], "confidence": 0.9}]},
        {"picks": [{"reaction": 0, "choice": 1}]},
    )
    recs, _ = r0.apply([], SOURCES, cfg(reg, "S2", llm=llm,
                                        dense=TwoQueryDense(),
                                        rung0_shortlist_k=2))
    cands = recs[0].checks["candidates"]
    codes = [c["code"] for c in cands]
    assert codes == ["39104002", "213257006"]      # deduped, capped at k=2
    assert [c["i"] for c in cands] == [0, 1]       # renumbered for the menu
    assert recs[0].checks["labels_proposed"] == ["Generally unwell"]
    assert recs[0].sct == "213257006"              # the label-only hit is pickable


def test_the_pick_prompt_shows_a_no_concept_example():
    """Arm 3 offered no_concept and the model used it zero times in 77 calls.
    A hatch nobody is shown being used is decoration; the prompt now carries
    one worked line."""
    assert r0.PICK_PROMPT.count("no_concept") >= 2


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
    """Exercises the REAL loader, so it needs numpy — a local-only extra.
    Without it ladder.embed raises about numpy first and the message under
    test never runs."""
    pytest.importorskip("numpy")
    llm = FakeLLM(FIND, {"picks": []})
    with pytest.raises(RuntimeError, match="ladder.embed --build"):
        r0.apply([], SOURCES, cfg(reg, "S2", llm=llm, dense=None, rung0_retrieval="dense",
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


def test_s1_declining_the_menu_is_not_concept_less(reg):  # noqa: F811
    """REVISED 2026-08-25 with S2's decline. The menu is only the codes the
    model's OWN names reached — declining it says "none of my names' codes
    fits the span", which may just mean the names were bad. CONCEPT_LESS in
    S1 stays what it always was: the model asserting the sentinel in
    sct_label, which still passes through untouched."""
    kw = keyword_table(**{"rectal pain": ["77880009"], "rectal bleeding": ["12063002"]})
    llm = FakeLLM(
        {"mentions": [{"span_text": "extreme rectal bleed", "context": "due",
                       "sct_label": ["rectal pain", "rectal bleeding"],
                       "confidence": 0.9}]},
        {"picks": [{"reaction": 0, "choice": None}]},
    )
    recs, agg = r0.apply([], SOURCES, cfg(reg, "S1", llm=llm, keywords=kw))
    assert recs[0].sct is None
    assert recs[0].checks["declined_shortlist"] is True
    assert agg["declined_shortlist"] == 1


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


# --- S0 asked for ONE code and models answer with several --------------------
#
# `_step_s0` did `str(code) if code is not None else None`. A model answering
#
#     "sct_code": ["21456007", "38485006", "42481009"]
#
# got `sct = "['21456007', '38485006', '42481009']"` — a string that can never
# be a valid code, so the mention scored 0 by construction even when the first
# id was right. Measured on ARTHROTEC.107 with granite4:micro-h.
#
# A RECORDING defect, not a model one: it made "the model named three codes"
# indistinguishable from "the model emitted garbage", and the first is a real
# thing a model does. The prompt asks for "the id matching sct_label[0]", so
# the FIRST is taken and the schema violation is COUNTED rather than thrown
# away — it is a reliability fact about the model, which is what S0 measures.


def test_s0_takes_the_first_code_when_the_model_returns_several(reg):  # noqa: F811
    llm = FakeLLM({"mentions": [{
        "span_text": "extreme rectal bleed", "context": "due", "start": 20, "end": 40,
        "sct_label": ["Rectal hemorrhage", "Gastrointestinal hemorrhage"],
        "sct_code": ["12063002", "38485006"], "confidence": 0.9}]})
    recs, _ = r0.apply([], SOURCES, cfg(reg, "S0", llm=llm))
    assert recs[0].sct == "12063002", "the id matching sct_label[0], as asked"


def test_s0_counts_the_schema_violation(reg):  # noqa: F811
    """Never silently repaired. How often a model ignores 'one code' is a
    reliability fact about the model, which is what S0 exists to measure."""
    llm = FakeLLM({"mentions": [{
        "span_text": "extreme rectal bleed", "context": "due", "start": 20, "end": 40,
        "sct_label": ["Rectal hemorrhage"], "sct_code": ["12063002", "38485006"],
        "confidence": 0.9}]})
    recs, agg = r0.apply([], SOURCES, cfg(reg, "S0", llm=llm))
    assert recs[0].checks["sct_code_multi"] == ["12063002", "38485006"]
    assert agg["multi_code"] == 1


def test_s0_never_stringifies_a_list_into_the_code(reg):  # noqa: F811
    """The regression itself. `sct` must always be a code, CONCEPT_LESS or
    None — never a repr of a container."""
    llm = FakeLLM({"mentions": [{
        "span_text": "extreme rectal bleed", "context": "due", "start": 20, "end": 40,
        "sct_label": ["x"], "sct_code": ["12063002", "38485006"], "confidence": 0.9}]})
    recs, _ = r0.apply([], SOURCES, cfg(reg, "S0", llm=llm))
    assert "[" not in str(recs[0].sct)


def test_s0_is_unchanged_for_a_single_code(reg):  # noqa: F811
    llm = FakeLLM({"mentions": [{
        "span_text": "extreme rectal bleed", "context": "due", "start": 20, "end": 40,
        "sct_label": ["Rectal hemorrhage"], "sct_code": "12063002", "confidence": 0.9}]})
    recs, agg = r0.apply([], SOURCES, cfg(reg, "S0", llm=llm))
    assert recs[0].sct == "12063002"
    assert "sct_code_multi" not in recs[0].checks
    assert agg["multi_code"] == 0


def test_s0_an_empty_code_list_is_no_answer(reg):  # noqa: F811
    llm = FakeLLM({"mentions": [{
        "span_text": "extreme rectal bleed", "context": "due", "start": 20, "end": 40,
        "sct_label": ["x"], "sct_code": [], "confidence": 0.9}]})
    recs, _ = r0.apply([], SOURCES, cfg(reg, "S0", llm=llm))
    assert recs[0].sct is None


def test_a_timed_out_call_is_labelled_timed_out_not_truncated(reg):  # noqa: F811
    """One runaway document costs one record, not the run. `truncated` and
    `timed_out` overlap — nothing usable came back either way — but the causes
    differ and only one is a property of this machine."""
    from ladder.ledger import Ledger
    import json as _json, pathlib, tempfile

    class TimedOut(FakeLLM):
        def __call__(self, prompt, text, mode, **kw):
            self.prompts.append(prompt)
            return "", {"in": 0, "out": 0, "usd": 0.0,
                        "truncated": True, "timed_out": True}

    with tempfile.TemporaryDirectory() as d:
        led = Ledger(pathlib.Path(d) / "l.jsonl", run_id="t")
        _, agg = r0.apply([], SOURCES, cfg(reg, "S1", llm=TimedOut(), ledger=led))
        led.flush()
        rows = [_json.loads(x) for x in (pathlib.Path(d) / "l.jsonl").read_text().splitlines() if x.strip()]
        assert rows[0]["reason"] == "timed_out"
        assert agg["timed_out"] == 1
        assert agg["truncated"] == 1


# --- S0 needs a legal way to say "I do not recall the id" -------------------
#
# S0 asks the model to recall a nine-digit SNOMED identifier from its own
# WEIGHTS — no lookup, no tool. That is the point of `rung0_mode: recall`.
#
# The prompt offered three options and none fits "I know the concept but not
# its number":
#
#     CONCEPT_LESS        means NO SNOMED CONCEPT EXISTS for this reaction.
#                         False for "rectal bleeding", which plainly has one.
#     give a code         forbidden by "Do not invent a concept id".
#     (nothing else)
#
# So the model deliberated. Measured on the dev split: 10% of calls ran to the
# 8,000-token cap and returned NOTHING, on two-line forum posts, at a healthy
# 52 tok/s. It was not thinking hard; it had been given a question with no
# legal answer.
#
# A null code is that answer. It also separates two facts S0 exists to
# measure and could not previously tell apart: how often the model NAMES the
# right concept, and how often it RECALLS the right id.


def test_s0_offers_a_null_code_as_a_legal_answer():
    assert "null" in r0.S0_PROMPT.lower()
    assert "sct_code" in r0.S0_PROMPT


def test_s0_still_forbids_inventing_an_id():
    """The exit must not become permission to guess — an invented id is the
    failure rung 1 exists to catch, and it must stay countable."""
    assert "invent" in r0.S0_PROMPT.lower()


def test_concept_less_still_means_no_concept_exists():
    """The two abstentions are different claims and the prompt must keep them
    apart, or a model with a bad memory looks like a gap in the vocabulary."""
    low = r0.S0_PROMPT.lower()
    assert "no snomed ct concept describes" in low


def test_s0_records_a_named_concept_whose_id_is_unknown(reg):  # noqa: F811
    llm = FakeLLM({"mentions": [{
        "span_text": "extreme rectal bleed", "context": "due", "start": 20, "end": 40,
        "sct_label": ["Rectal hemorrhage"], "sct_code": None, "confidence": 0.9}]})
    recs, agg = r0.apply([], SOURCES, cfg(reg, "S0", llm=llm))
    assert recs[0].sct is None
    assert recs[0].sct_label == "Rectal hemorrhage", "the NAME survives"
    assert recs[0].checks["code_unknown"] is True
    assert agg["code_unknown"] == 1


def test_s0_distinguishes_that_from_concept_less(reg):  # noqa: F811
    """CONCEPT_LESS is a claim about the VOCABULARY; a null code is a claim
    about the model's own memory."""
    llm = FakeLLM({"mentions": [{
        "span_text": "extremely sick", "context": "I was", "start": 80, "end": 94,
        "sct_label": [CONCEPT_LESS], "sct_code": CONCEPT_LESS, "confidence": 0.5}]})
    recs, agg = r0.apply([], SOURCES, cfg(reg, "S0", llm=llm))
    assert recs[0].sct == CONCEPT_LESS
    assert "code_unknown" not in recs[0].checks
    assert agg["code_unknown"] == 0


def test_a_recalled_code_is_not_flagged_unknown(reg):  # noqa: F811
    llm = FakeLLM({"mentions": [{
        "span_text": "extreme rectal bleed", "context": "due", "start": 20, "end": 40,
        "sct_label": ["Rectal hemorrhage"], "sct_code": "12063002", "confidence": 0.9}]})
    recs, agg = r0.apply([], SOURCES, cfg(reg, "S0", llm=llm))
    assert recs[0].sct == "12063002"
    assert agg["code_unknown"] == 0


def test_the_span_instruction_is_still_identical_across_steps():
    """Scope parity is the whole study design. A change to S0's code section
    must not touch how any step is told to quote a span."""
    for a, b in ((r0.S0_PROMPT, r0.S1_PROMPT), (r0.S1_PROMPT, r0.FIND_PROMPT)):
        assert r0._ASK in a and r0._ASK in b
        assert r0._RULES in a and r0._RULES in b


# --- the frozen step ---------------------------------------------------------
#
# The prompt-engineering study is finished and S2 is the answer. Measured on
# the dev split, 40 documents, 226 scorable gold reaction mentions,
# gpt-oss:20b at reasoning_effort=low:
#
#             F1 exact  F1 overlap  calls  tokens  parse fails
#     S0        0.018      0.018      40   43,998    5 of 40
#     S1        0.171      0.305      57   36,079    0
#     S2        0.209      0.310      75   68,906    0
#
# S2 wins exact F1 by 3.8 points and ties S1 on overlap within half a point,
# for 1.9x the tokens. That is a real cost and it is not hidden: rungs 1-6 are
# now all measured against S2, so a later change of step invalidates every
# number above it. Which is exactly why it is frozen here rather than passed
# per run.


def test_the_manifest_freezes_s2():
    """`rung0_step: null` means the pre-study A/B path, not "the default step".
    Leaving it null after the study would have run the ladder on a rung 0 that
    no measurement describes."""
    import json as _json

    man = _json.loads(pathlib.Path("manifest.json").read_text())
    assert man["rungs"]["0"]["rung0_step"] == "S2"


def test_the_frozen_step_is_a_real_step():
    import json as _json

    man = _json.loads(pathlib.Path("manifest.json").read_text())
    assert man["rungs"]["0"]["rung0_step"] in r0.STEPS


def test_the_step_flag_still_overrides_the_frozen_choice():
    """Freezing must not remove the ability to rerun one step. --rung0-step is
    how the study is reproduced, and it writes the choice into the manifest
    copy saved beside the results."""
    from ladder.run import apply_rung0_step

    man = _json_manifest()
    assert man["rungs"]["0"]["rung0_step"] == "S2", "frozen"
    out = apply_rung0_step(man, "S0")
    assert out["rungs"]["0"]["rung0_step"] == "S0"


def test_no_flag_leaves_the_frozen_step_alone():
    from ladder.run import apply_rung0_step

    out = apply_rung0_step(_json_manifest(), None)
    assert out["rungs"]["0"]["rung0_step"] == "S2"


def _json_manifest():
    import json as _json

    return _json.loads(pathlib.Path("manifest.json").read_text())


# --- negation: denied reactions are EXTRACTED, flagged, and kept (Phase B) ---
#
# The old rule — "Do not report anything they say they did NOT have" — fought
# the answer key. Measured (2026-08-22 negation note): CADEC annotates a
# mention regardless of polarity, 427 gold mentions (4.7%) are denied
# reactions, and DICLOFENAC-SODIUM.5's "no stomach pains" is gold. So the
# model now reports denied reactions WITH a "negated": true flag, in all
# three steps (scope parity), and rung 1's cue-based check stays untouched
# as the deterministic cross-check.


def test_no_step_tells_the_model_to_skip_denied_reactions():
    """The rule that contradicted the answer key must be gone from every
    extraction prompt. The new rule mentions denial too — what must not
    survive is the instruction NOT TO REPORT it."""
    for prompt in (r0.S0_PROMPT, r0.S1_PROMPT, r0.FIND_PROMPT):
        assert "Do not report anything" not in prompt
        assert "Report only reactions the writer actually experienced" not in prompt


def test_every_step_asks_for_the_negated_flag():
    """Scope is identical across steps by design — the flag has to be in all
    three prompts and all three JSON templates."""
    for prompt in (r0.S0_PROMPT, r0.S1_PROMPT, r0.FIND_PROMPT):
        assert '"negated"' in prompt, "the JSON template must carry the field"
        assert "negated" in prompt.lower()


def test_a_denied_mention_carries_the_models_flag(reg):  # noqa: F811
    llm = FakeLLM(
        {"mentions": [{"span_text": "extremely sick", "context": "I was",
                       "negated": True, "confidence": 0.8}]},
        {"picks": [{"reaction": 0, "choice": 0}]},
    )
    recs, _ = r0.apply([], SOURCES, cfg(reg, "S2", llm=llm))
    assert recs[0].checks["negated"] is True
    assert recs[0].checks["r0_negated"] is True


def test_negated_defaults_to_false_when_the_model_omits_it(reg):  # noqa: F811
    """An absent flag is 'not denied', never a missing column: every record
    must be readable on the same key."""
    llm = FakeLLM(FIND, {"picks": [{"reaction": 0, "choice": 0},
                                   {"reaction": 1, "choice": 0}]})
    recs, _ = r0.apply([], SOURCES, cfg(reg, "S2", llm=llm))
    assert recs[0].checks["negated"] is False
    assert recs[0].checks["r0_negated"] is False


@pytest.mark.parametrize("step,reply", [
    ("S0", {"mentions": [{"span_text": "extremely sick", "context": "I was",
                          "start": 80, "end": 94, "sct_label": ["Generally unwell"],
                          "sct_code": "213257006", "negated": True,
                          "confidence": 0.8}]}),
    ("S1", {"mentions": [{"span_text": "extremely sick", "context": "I was",
                          "sct_label": ["Generally unwell"], "negated": True,
                          "confidence": 0.8}]}),
])
def test_the_flag_lands_in_every_step_not_only_s2(reg, step, reply):  # noqa: F811
    llm = FakeLLM(reply)
    recs, _ = r0.apply([], SOURCES, cfg(reg, step, llm=llm))
    assert recs[0].checks["negated"] is True


def test_the_models_negation_claim_survives_rung_1(reg):  # noqa: F811
    """Rung 1's cue check writes checks["negated"] too (r1.apply does
    rec.checks.update), so in a full-ladder run the cue OVERWRITES the model's
    claim on that key. The claim is duplicated to r0_negated at creation so
    the cross-check — model says denied vs cue fired — stays readable from
    disk after every rung has run. Rung 1 itself is untouched."""
    from ladder.rungs import r1

    llm = FakeLLM(
        {"mentions": [{"span_text": "extremely sick", "context": "I was",
                       "negated": True, "confidence": 0.8}]},
        {"picks": [{"reaction": 0, "choice": 0}]},
    )
    recs, _ = r0.apply([], SOURCES, cfg(reg, "S2", llm=llm))
    r1.apply(recs, SOURCES, {"registry": reg})
    # no denial cue precedes "extremely sick" in SOURCE, so the cue disagrees
    assert recs[0].checks["negated"] is False        # rung 1's cue verdict
    assert recs[0].checks["r0_negated"] is True      # the model's claim, kept
    assert recs[0].checks["negation_cue"] is None

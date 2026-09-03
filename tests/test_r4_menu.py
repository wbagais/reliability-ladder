"""Plan item 14 (2026-09-02): THE JUDGE WAS NEVER SHOWN WHAT IT WAS JUDGING.

`r4.judge` formatted `source, text, start, end, sct` and nothing else, so the
judge was handed `code: 1003722009` — a bare nine-digit number — and asked
"is this the right SNOMED CT concept?". It cannot answer that; every rung 4
number in the article is a measurement of a question that could not be
answered. On FiNER `rec.sct` IS the tag name, which is the whole reason the
judge engaged there — identifier readability, not context size.

The redesign is the standard LLM-as-judge setup: show the judge what the
extractor was shown (the menu) and what it answered (the pick), and let it
say `best` — the line it would have chosen, or null for "the right answer is
not on this list". That last verdict is one the system could not express.

`rungs.4.menu` is `off | ranked | shuffled`, OFF by default: every published
rung 4 figure was produced blind and the arm must be paired against it.
`shuffled` permutes the menu under a fixed seed, per record, because the
slot-0 attractor has been found three times and a judge shown a ranked list
may simply ratify line 0. Safe here where it was unsafe in rung 0 (B4): the
judge sees ONE record per call, so there is no index aliasing across a batch.
"""

import json
import pathlib

import pytest

from ladder.schema import REACTION, Record, ZONE_NEW

_ROOT = pathlib.Path(__file__).resolve().parent.parent

SOURCE = "I was a bit drowsy and had no gastric problems."


def rec(**kw):
    base = dict(
        doc_id="D1", entity_type=REACTION, text="bit drowsy", spans=[(8, 18)],
        sct="271782001", sct_label="Drowsy", zone=ZONE_NEW, record_id="D1#0",
    )
    base.update(kw)
    r = Record(**base)
    r.checks["candidates"] = [
        {"i": 0, "code": "271782001", "fsn": "Drowsy (finding)", "label": "Drowsy"},
        {"i": 1, "code": "206005", "fsn": "Somnolence (finding)", "label": "Somnolence"},
        {"i": 2, "code": "84229001", "fsn": "Fatigue (finding)", "label": "Fatigue"},
    ]
    return r


def stub(reply: dict):
    calls = []

    def llm(prompt, text, mode):
        calls.append(prompt)
        return json.dumps(reply), {"in": 10, "out": 5, "seconds": 0.01}

    llm.calls = calls
    return llm


# --- off is byte-identical to the blind judge ---------------------------------


def test_menu_off_is_the_blind_prompt_unchanged():
    from ladder.rungs import r4

    r = rec()
    llm = stub({"span_ok": True, "code_ok": True, "confidence": 0.9, "why": "x"})
    r4.judge(r, SOURCE, llm, {**r4.DEFAULTS, "menu": "off"})
    blind = r4.judge_prompt(None).format(source=SOURCE, text="bit drowsy",
                                          start=8, end=18, sct="271782001")
    assert llm.calls[0] == blind
    assert r.checks.get("r4_menu") == "off"


def test_the_default_is_off():
    from ladder.rungs import r4

    assert r4.DEFAULTS["menu"] == "off"


def test_an_unknown_menu_setting_is_refused():
    from ladder.rungs import r4

    with pytest.raises(ValueError):
        r4.judge(rec(), SOURCE, stub({}), {**r4.DEFAULTS, "menu": "random"})


# --- ranked: the menu, the pick, and a third verdict --------------------------


def test_ranked_shows_the_menu_and_names_the_pick():
    from ladder.rungs import r4

    r = rec(sct="206005", sct_label="Somnolence")
    llm = stub({"span_ok": True, "code_ok": False, "best": 0, "confidence": 0.8, "why": "x"})
    r4.judge(r, SOURCE, llm, {**r4.DEFAULTS, "menu": "ranked"})
    p = llm.calls[0]
    assert "[0] Drowsy (finding)" in p and "[1] Somnolence (finding)" in p
    assert "[2] Fatigue (finding)" in p
    assert "[1] Somnolence (finding)" in p.split("chose")[1], "the pick is named as a line"
    assert '"best"' in p, "the judge is asked which line it would choose"
    assert "206005" in p, "the identifier still appears — the judge grades a code"
    assert p.index("The filing excerpt" if False else SOURCE) < p.index("[0] Drowsy"), \
        "post first, then the menu — the same order the extractor saw"


def test_ranked_parses_best_and_maps_it_to_a_code():
    from ladder.rungs import r4

    r = rec(sct="206005")
    v, _ = r4.judge(r, SOURCE, stub({"span_ok": True, "code_ok": False, "best": 0,
                                     "confidence": 0.8, "why": "x"}),
                    {**r4.DEFAULTS, "menu": "ranked"})
    assert v["best"] == 0
    assert v["best_code"] == "271782001"
    assert v["menu_missing"] is False


def test_a_null_best_is_the_verdict_the_system_could_not_express():
    """'The right answer is not in the menu' separates a bad pick from a bad
    menu — opposite fixes, and until now one ambiguous failure."""
    from ladder.rungs import r4

    v, _ = r4.judge(rec(), SOURCE, stub({"span_ok": True, "code_ok": False, "best": None,
                                         "confidence": 0.5, "why": "x"}),
                    {**r4.DEFAULTS, "menu": "ranked"})
    assert v["best"] is None and v["best_code"] is None
    assert v["menu_missing"] is True


def test_an_out_of_range_best_is_recorded_as_bad_never_clamped():
    from ladder.rungs import r4

    v, _ = r4.judge(rec(), SOURCE, stub({"span_ok": True, "code_ok": True, "best": 17,
                                         "confidence": 0.5, "why": "x"}),
                    {**r4.DEFAULTS, "menu": "ranked"})
    assert v["best"] is None and v["best_code"] is None
    assert v["best_bad"] == 17


def test_a_denied_mention_carries_the_marker_the_pick_step_needed():
    """Phase B: without `[denied]` the pick declined every denied mention. The
    judge had no such instruction and was failing spans CADEC marks correct.
    Same trap, one rung up."""
    from ladder.rungs import r4

    r = rec(text="gastric problems", spans=[(31, 47)])
    r.checks["r0_negated"] = True
    llm = stub({"span_ok": True, "code_ok": True, "best": 0, "confidence": 0.5, "why": "x"})
    r4.judge(r, SOURCE, llm, {**r4.DEFAULTS, "menu": "ranked"})
    assert "[denied]" in llm.calls[0]
    assert "still" in llm.calls[0].lower(), "the prompt says a denied mention is still coded"


def test_a_record_without_a_menu_gets_the_blind_prompt_and_says_so():
    """S0 and S1 records carry no candidates. The arm couples rung 4 to S2 —
    stated, and degraded to the blind prompt rather than a crash."""
    from ladder.rungs import r4

    r = rec()
    r.checks.pop("candidates")
    llm = stub({"span_ok": True, "code_ok": True, "confidence": 0.5, "why": "x"})
    v, _ = r4.judge(r, SOURCE, llm, {**r4.DEFAULTS, "menu": "ranked"})
    assert "[0]" not in llm.calls[0]
    assert r.checks["r4_menu"] == "none"
    assert v["menu_missing"] is None


def test_candidates_are_an_allowed_check_key_and_the_answer_key_is_not():
    from ladder.rungs import r4

    assert "candidates" in r4.ALLOWED_CHECK_KEYS
    assert "r0_negated" in r4.ALLOWED_CHECK_KEYS
    assert "meddra_term" not in r4.ALLOWED_CHECK_KEYS


# --- shuffled: a fixed permutation per record ----------------------------------


def test_shuffled_is_a_pure_function_of_seed_and_record_id():
    from ladder.rungs import r4

    a = r4.menu_order(rec(), "shuffled", seed=42)
    b = r4.menu_order(rec(), "shuffled", seed=42)
    c = r4.menu_order(rec(record_id="D1#7"), "shuffled", seed=42)
    d = r4.menu_order(rec(), "shuffled", seed=43)
    assert a == b
    assert sorted(a) == [0, 1, 2]
    assert c != a or d != a, "a different record or seed must be able to move the menu"
    assert r4.menu_order(rec(), "ranked", seed=42) == [0, 1, 2]


def test_shuffled_renders_the_permuted_menu_and_maps_best_back():
    from ladder.rungs import r4

    r = rec(sct="206005")
    order = r4.menu_order(r, "shuffled", seed=42)
    # ask for whatever line the shuffled menu shows FIRST
    llm = stub({"span_ok": True, "code_ok": True, "best": 0, "confidence": 0.5, "why": "x"})
    v, _ = r4.judge(r, SOURCE, llm, {**r4.DEFAULTS, "menu": "shuffled",
                                     "manifest": {"seed": 42}})
    first_code = r.checks["candidates"][order[0]]["code"]
    assert v["best_code"] == first_code
    lines = [l for l in llm.calls[0].splitlines() if l.strip().startswith("[0]")]
    assert lines and r.checks["candidates"][order[0]]["fsn"] in lines[0]
    assert r.checks["r4_menu"] == "shuffled"
    assert r.checks["r4_menu_order"] == order


def test_apply_counts_menu_verdicts(tmp_path):
    from ladder.ledger import Ledger
    from ladder.rungs import r4

    a, b = rec(), rec(record_id="D1#1", sct="206005")
    replies = iter([
        {"span_ok": True, "code_ok": True, "best": 0, "confidence": 0.9, "why": "x"},
        {"span_ok": True, "code_ok": False, "best": None, "confidence": 0.9, "why": "x"},
    ])

    def llm(prompt, text, mode):
        return json.dumps(next(replies)), {"in": 1, "out": 1, "seconds": 0.0}

    ledger = Ledger(tmp_path / "l.jsonl", run_id="t")
    _, agg = r4.apply([a, b], {"D1": SOURCE}, {
        "judge_llm": llm, "judge_model": "j", "extractor_model": "e",
        "ledger": ledger, "menu": "ranked", "manifest": {"seed": 1},
    })
    ledger.close()
    assert agg["menu"] == "ranked"
    assert agg["menu_missing"] == 1
    assert agg["best_is_pick"] == 1
    assert a.checks["r4_best_code"] == "271782001"
    assert b.checks["r4_best_code"] is None and b.checks["r4_menu_missing"] is True
    rows = [e for e in ledger.rows if e.rung == 4]
    assert rows[1].extra["menu_missing"] is True


# --- the arm manifests ---------------------------------------------------------


def _walk(x, y, path=""):
    if isinstance(x, dict) and isinstance(y, dict):
        for k in sorted(set(x) | set(y)):
            yield from _walk(x.get(k), y.get(k), f"{path}.{k}")
    elif x != y:
        yield path


@pytest.mark.parametrize("base,arm,value", [
    ("manifest.json", "manifest.judgemenu.json", "ranked"),
    ("manifest.json", "manifest.judgeshuffle.json", "shuffled"),
    ("manifest.finer.json", "manifest.finer.judgemenu.json", "ranked"),
    ("manifest.finer.json", "manifest.finer.judgeshuffle.json", "shuffled"),
])
def test_each_menu_arm_differs_from_its_base_by_exactly_one_key(base, arm, value):
    a = json.load(open(_ROOT / base))
    b = json.load(open(_ROOT / arm))
    for k in [k for k in b if k.startswith("_") and "note" in k and k not in a]:
        b.pop(k)
    assert list(_walk(a, b)) == [".rungs.4.menu"]
    assert a["rungs"]["4"]["menu"] == "off"
    assert b["rungs"]["4"]["menu"] == value


def test_both_shipped_manifests_declare_the_judge_menu_off():
    for name in ("manifest.json", "manifest.finer.json"):
        m = json.load(open(_ROOT / name))
        assert m["rungs"]["4"]["menu"] == "off", f"{name}: rungs.4.menu must be declared off"
        assert "menu_note" in m["rungs"]["4"]


# --- what the extractor was TOLD, not only what it was shown --------------------


def test_the_judge_sees_the_pick_guidance_the_extractor_was_given():
    """Smoke run 2026-09-03: shown the menu, the judge failed a correct pick
    of |Rectal bleeding| for "extreme rectal bleed" because the code "does not
    capture the severity". That is CADEC's own convention — the extractor was
    told to choose the PLAIN concept and drop severity — and the judge was
    grading against a rule it had never been given. "What the extractor was
    given" includes the guidance, corpus-slotted like everything else."""
    from ladder.rungs import r0, r4

    llm = stub({"span_ok": True, "code_ok": True, "best": 0, "confidence": 0.5, "why": "x"})
    r4.judge(rec(), SOURCE, llm, {**r4.DEFAULTS, "menu": "ranked"})
    guidance = r0.resolve(None)["pick_guidance"].strip().splitlines()[0]
    assert guidance in llm.calls[0]
    assert llm.calls[0].index(guidance) < llm.calls[0].index("[0] Drowsy"), \
        "the guidance comes before the menu, as it did for the extractor"


def test_a_corpus_supplies_its_own_guidance_to_the_judge():
    from ladder.rungs import r4

    llm = stub({"span_ok": True, "code_ok": True, "best": 0, "confidence": 0.5, "why": "x"})
    slots = {"pick_guidance": "Choose the tag that names WHAT KIND OF QUANTITY this is.",
             "entity_short": "fact", "vocabulary": "US-GAAP XBRL tag"}
    r4.judge(rec(), SOURCE, llm, {**r4.DEFAULTS, "menu": "ranked", "prompt_slots": slots})
    assert "WHAT KIND OF QUANTITY" in llm.calls[0]
    assert "PLAIN concept" not in llm.calls[0]

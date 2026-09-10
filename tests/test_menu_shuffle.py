"""B4 — breaking FiNER's slot-0 position prior by permuting the menu.

THE FINDING UNDER ATTACK (docs/decisions.md, 2026-08-30). FiNER's pick menu is
`sorted(set(tags))`, so `AccrualForEnvironmentalLossContingencies` is
alphabetically first and sits at slot 0 in EVERY record. It is predicted 57
times in 292 against 2 in gold — 19.5% of all predictions are the list's first
line. The context arm settled that this is POSITION and not meaning: move the
tag to median slot 92 and it is predicted 3 times, all 3 in the records where
the ranking happened to put it first. The model takes line one iff it is line
one.

WHY A PERMUTATION AND NOT A SENTINEL. The two candidate mechanisms were a slot 0
that is never a valid answer, and a per-mention permutation under a fixed seed.
The permutation ships first because it changes ORDER ONLY: the answer set is
untouched, menu recall stays 1.000 by construction, and nothing new can be
picked. A sentinel line adds an option that is not a valid answer, so a pick of
it has to be mapped to a null code — which mixes a position effect with an
abstention effect and makes a null unreadable. It is also the literature's own
mitigation for option-order bias.

WHAT IT MUST NOT DO. Drop a candidate, depend on process-salted hashing, or
differ between two runs of the same configuration. A permutation nobody can
reproduce is not a measurement.
"""

import pytest

from ladder.menuorder import permuted


def menu(n=139, first="AccrualForEnvironmentalLossContingencies"):
    """A stand-in for FiNER's alphabetical menu: the attractor at slot 0."""
    rest = [f"us-gaap:Tag{i:03d}" for i in range(n - 1)]
    return [{"i": n, "code": c, "label": c}
            for n, c in enumerate([f"us-gaap:{first}", *rest])]


# --- the permutation itself --------------------------------------------------


def test_the_permutation_drops_nothing_so_menu_recall_stays_one():
    """The whole arm is about ORDER. A menu that loses a candidate is a
    retrieval change wearing an ordering label, and its result would not be
    attributable to position."""
    src = menu()
    out = permuted(src, key="D1#0", seed=0)
    assert len(out) == len(src)
    assert {c["code"] for c in out} == {c["code"] for c in src}


def test_the_permutation_renumbers_because_the_pick_indexes_what_it_is_shown():
    out = permuted(menu(20), key="D1#0", seed=0)
    assert [c["i"] for c in out] == list(range(20))


def test_the_same_key_gives_the_same_order_so_a_run_reproduces():
    a = permuted(menu(), key="D7#3", seed=0)
    b = permuted(menu(), key="D7#3", seed=0)
    assert [c["code"] for c in a] == [c["code"] for c in b]


def test_the_seed_is_not_python_s_salted_hash():
    """`hash()` is randomised per process, so a permutation built on it would
    differ between two runs of the same configuration and no draw could be
    paired with another."""
    import subprocess
    import sys

    prog = (
        "from ladder.menuorder import permuted;"
        "print([c['code'] for c in permuted("
        "[{'i': i, 'code': 'us-gaap:T%d' % i} for i in range(40)],"
        " key='D1#0', seed=0)])"
    )
    runs = {subprocess.run([sys.executable, "-c", prog], capture_output=True,
                           text=True, env={"PYTHONHASHSEED": s, "PATH": "/usr/bin"},
                           check=True).stdout
            for s in ("0", "1", "12345")}
    assert len(runs) == 1, "the order moved with PYTHONHASHSEED"


def test_the_permutation_is_PER_MENTION_and_not_one_shuffle_for_the_run():
    """One shuffle for the whole run just moves the attractor to a new tag and
    leaves it there. The prior is broken only if slot 0 changes per mention."""
    firsts = {permuted(menu(), key=f"D1#{i}", seed=0)[0]["code"]
              for i in range(60)}
    assert len(firsts) > 30, f"only {len(firsts)} distinct slot-0 tags in 60 menus"


def test_the_attractor_reaches_slot_0_at_about_the_chance_rate():
    """THE POINT OF THE ARM. Under `sorted(set(tags))` the attractor is at slot
    0 in 100% of records. Under the permutation it must be there at roughly
    1/139, and certainly nowhere near a rate that could reproduce 57 picks."""
    tag = "us-gaap:AccrualForEnvironmentalLossContingencies"
    hits = sum(permuted(menu(), key=f"D{i // 8}#{i % 8}", seed=0)[0]["code"] == tag
               for i in range(600))
    assert hits / 600 < 0.05, f"attractor at slot 0 in {hits}/600 menus"


def test_the_permutation_is_uniform_enough_that_no_slot_is_a_new_attractor():
    """A permutation that systematically favours some INPUT position would swap
    one positional artefact for another. 800 draws over a 40-line menu is 20
    expected per input slot; the bound is ~5 sd."""
    n = 40
    counts = [0] * n
    for i in range(800):
        counts[permuted(menu(n), key=f"D{i // 8}#{i % 8}", seed=0)[0]["shuffled_from"]] += 1
    assert max(counts) < 43, f"input slot over-represented at slot 0: {max(counts)}"


def test_every_candidate_records_the_slot_it_came_from():
    """The ablation pins detection and the base is held fixed, so a dead arm and
    a working one both print delta 0.000. `shuffled_from` is what makes "the
    menu actually moved" checkable on the artifacts rather than assumed."""
    out = permuted(menu(20), key="D1#0", seed=0)
    assert sorted(c["shuffled_from"] for c in out) == list(range(20))
    assert [c["shuffled_from"] for c in out] != list(range(20)), "identity permutation"


def test_a_different_seed_gives_a_different_permutation():
    a = [c["code"] for c in permuted(menu(), key="D1#0", seed=0)]
    b = [c["code"] for c in permuted(menu(), key="D1#0", seed=17)]
    assert a != b


def test_no_key_leaves_the_menu_alone_rather_than_raising():
    """`_order_menu` runs per mention inside the document loop. An ordering
    that cannot be computed must cost the ORDER, never the document."""
    src = menu(5)
    assert permuted(src, key=None, seed=0) == src
    assert permuted(src, key="", seed=0) == src


def test_an_empty_menu_is_not_an_error():
    assert permuted([], key="D1#0", seed=0) == []


# --- wired into rung 0 as an off-by-default arm ------------------------------


def test_shuffle_is_a_declared_menu_order_and_is_not_the_default():
    from ladder.rungs import r0

    assert "shuffle" in r0.MENU_ORDERS
    assert r0.DEFAULTS["rung0_menu_order"] == "score"


def test_order_menu_permutes_when_the_arm_is_on():
    from ladder.rungs import r0

    src = menu(40)
    out = r0._order_menu(src, "shuffle", key="D1#0", seed=0)
    assert [c["code"] for c in out] != [c["code"] for c in src], "arm is a no-op"
    assert {c["code"] for c in out} == {c["code"] for c in src}
    assert [c["i"] for c in out] == list(range(40))


def test_order_menu_without_a_key_leaves_the_menu_alone():
    from ladder.rungs import r0

    src = menu(5)
    assert r0._order_menu(src, "shuffle") == src


def test_the_shipped_manifests_do_not_carry_the_arm():
    import json
    import pathlib

    root = pathlib.Path(__file__).resolve().parents[1]
    for name in ("manifest.json", "manifest.finer.json"):
        man = json.load(open(root / name))
        assert man["rungs"]["0"].get("rung0_menu_order", "score") == "score", (
            f"{name} must ship the measured menu order, not the new arm")


def test_the_shufflemenu_manifest_differs_by_exactly_the_menu_order():
    """Same rule as manifest.finer.ctxmenu.json and manifest.sapbertarm.json:
    an arm manifest that drifts from its base is two experiments in one name."""
    import json
    import pathlib

    root = pathlib.Path(__file__).resolve().parents[1]
    a = json.load(open(root / "manifest.finer.json"))
    b = json.load(open(root / "manifest.finer.shufflemenu.json"))
    b.pop("_shufflemenu_note", None)
    b["rungs"]["0"].pop("rung0_menu_order_note", None)

    def walk(x, y, path=""):
        if isinstance(x, dict) and isinstance(y, dict):
            for k in sorted(set(x) | set(y)):
                yield from walk(x.get(k), y.get(k), f"{path}.{k}")
        elif x != y:
            yield path

    assert list(walk(a, b)) == [".rungs.0.rung0_menu_order"]
    assert b["rungs"]["0"]["rung0_menu_order"] == "shuffle"


def test_the_arm_seed_comes_from_the_manifest_so_it_is_declared():
    """One-key diff means the permutation cannot bring its own new key. It
    reads the manifest's existing top-level `seed`."""
    from ladder.rungs import r0

    src = menu(40)
    cfg_a = {"rung0_menu_order": "shuffle", "manifest": {"seed": 0}}
    cfg_b = {"rung0_menu_order": "shuffle", "manifest": {"seed": 99}}
    a = r0._order_menu(src, "shuffle", key="D1#0", seed=r0._menu_seed(cfg_a))
    b = r0._order_menu(src, "shuffle", key="D1#0", seed=r0._menu_seed(cfg_b))
    assert [c["code"] for c in a] != [c["code"] for c in b]
    assert r0._menu_seed({"manifest": {}}) == 0
    assert r0._menu_seed({}) == 0


# --- the call site, because a wired-looking arm can still be dead ------------


class FakeTagVocab:
    """FiNER's vocabulary shape: it enumerates itself, and the menu is
    `sorted(set(tags))` — which is exactly what puts one tag at slot 0 in
    every record."""

    def __init__(self, codes):
        self._codes = sorted(codes)

    def all_codes(self):
        return list(self._codes)

    def preferred(self, code):
        return code


class ReplayLLM:
    def __init__(self, *replies):
        self.replies = list(replies)
        self.prompts = []

    def __call__(self, prompt, text, mode, **kw):
        self.prompts.append(prompt)
        import json as _json

        raw = self.replies.pop(0) if self.replies else "{}"
        return (raw if isinstance(raw, str) else _json.dumps(raw)), {"in": 10, "out": 5}


def pick_run(menu_order, seed=0):
    """One S2 document through the real `_step_pick`, arm on or off."""
    import json as _json

    from ladder.rungs import r0

    codes = ["AccrualForEnvironmentalLossContingencies"] + [
        f"Tag{i:03d}" for i in range(138)]
    find = {"mentions": [
        {"span_text": "4.5", "context": "rate of", "confidence": 0.9},
        {"span_text": "11.16", "context": "price of", "confidence": 0.9},
    ]}
    llm = ReplayLLM(_json.dumps(find), _json.dumps({"picks": [
        {"reaction": 0, "choice": 0}, {"reaction": 1, "choice": 0}]}))
    cfg = {**r0.DEFAULTS, "rung0_step": "S2", "rung0_retrieval": "full",
           "rung0_shortlist_k": 139, "rung0_menu_order": menu_order,
           "registry": FakeTagVocab(codes), "manifest": {"seed": seed}}
    meta = {"tokens_in": 0, "tokens_out": 0, "api_calls": 0}
    recs = r0._step_pick("D1", "the rate of 4.5 and the price of 11.16", llm,
                         cfg, meta, "S2")
    return recs, llm


def test_the_arm_reaches_the_real_pick_path_and_moves_the_menu():
    """The wiring test the unit tests cannot give: `_order_menu` could be
    correct and `_step_pick` could never pass it a key."""
    base, _ = pick_run("score")
    arm, _ = pick_run("shuffle")
    for rec in base:
        assert [c["code"] for c in rec.checks["candidates"]] == sorted(
            c["code"] for c in rec.checks["candidates"])
    for rec in arm:
        got = [c["code"] for c in rec.checks["candidates"]]
        assert got != sorted(got), "the menu reached the pick still alphabetical"
        assert len(got) == 139, "the arm changed the menu's CONTENTS"


def test_the_attractor_is_off_slot_0_and_the_two_mentions_differ():
    """The mechanism, stated as the run sees it: the alphabetically-first tag
    owns slot 0 in every base record, and in neither arm record — and the two
    mentions in ONE document get different menus, which is what makes the
    permutation per-mention rather than per-run."""
    tag = "AccrualForEnvironmentalLossContingencies"
    base, _ = pick_run("score")
    arm, _ = pick_run("shuffle")
    assert [r.checks["candidates"][0]["code"] for r in base] == [tag, tag]
    assert tag not in [r.checks["candidates"][0]["code"] for r in arm]
    assert (arm[0].checks["candidates"][0]["code"]
            != arm[1].checks["candidates"][0]["code"])


def test_the_run_records_which_order_produced_it():
    arm, _ = pick_run("shuffle")
    assert all(r.checks["rung0_menu_order"] == "shuffle" for r in arm)
    assert all("shuffled_from" in c for c in arm[0].checks["candidates"])


def test_the_pick_prompt_shows_the_permuted_menu_not_the_retrieval_order():
    """The record could be permuted after the prompt was rendered, which would
    make the arm a relabelling of the base rather than a different run."""
    _, llm = pick_run("shuffle")
    pick_prompt = llm.prompts[-1]
    first_line = [ln for ln in pick_prompt.splitlines() if ln.strip().startswith("[0]")]
    assert first_line, "no menu in the pick prompt"
    assert not any("AccrualForEnvironmentalLossContingencies" in ln
                   for ln in first_line)


def test_the_call_site_reads_the_manifest_seed_and_not_a_literal():
    """A hardcoded `seed=0` at the call site passes every test written at seed
    0. The declaration has to be reachable from the run, or it is the
    `manifest.model.temperature` defect again: declared, never read, agreeing
    with reality by accident."""
    a, _ = pick_run("shuffle", seed=0)
    b, _ = pick_run("shuffle", seed=99)
    assert ([c["code"] for c in a[0].checks["candidates"]]
            != [c["code"] for c in b[0].checks["candidates"]])

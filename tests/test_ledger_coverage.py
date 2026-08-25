"""Ledger coverage — the tests that were missing.

Eight ledger call sites across three rungs called a method that did not exist,
with a required argument missing, guarded by a condition that was never true.
The suite passed 93 tests before that was found, after it was fixed, and after
every subsequent revision, because no test ever constructed a rung with a
ledger attached.

These tests are deliberately dumb. They do not check accuracy, cost, or any
model behaviour. They check that the accounting path executes and that its
invariants hold:

  1. Every record entering a rung produces exactly one ledger row.
  2. Every row names the denominator its rate belongs to.
  3. `evaluable` is one of exactly three values, never a boolean.
  4. Rows whose outcome means "could not evaluate" say could_not_run.

(1) is the one that matters most. A rung that logs only its successes reports
its failure rate as zero.

No network, no model, no corpus: the fake LLM below returns canned responses.
"""
import json
import pathlib
import pytest

from ladder.ledger import Ledger

EVALUABLE = {"pass", "fail", "could_not_run"}


def _unreachable() -> tuple[type[BaseException], ...]:
    """Exception classes that mean "no model is reachable on this machine".

    The guards below were written as (RuntimeError, SystemExit, OSError) and
    that is not what an OpenAI-compatible endpoint raises when the model name in
    the manifest is not the tag the local ollama actually holds: it raises
    openai.NotFoundError, which is neither. The suite went red on a merge that
    changed the manifest's model strings to the ones resolving on ANOTHER
    machine — an environmental difference reported as a code failure.

    Deliberately NOT openai.APIError: a 400 means we sent a bad payload, which
    is our bug and must stay a failure. Only "cannot get there from here"
    skips.
    """
    errs: list[type[BaseException]] = [RuntimeError, SystemExit, OSError]
    try:
        import openai
    except ImportError:
        return tuple(errs)
    errs += [openai.APIConnectionError, openai.NotFoundError,
             openai.AuthenticationError, openai.PermissionDeniedError]
    return tuple(errs)


UNREACHABLE = _unreachable()


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------

@pytest.fixture
def ledger(tmp_path):
    """A real Ledger writing to a temp file. Closed by the test."""
    return Ledger(tmp_path / "test.jsonl", run_id="test")


def rows_of(ledger, rung=None):
    """Rows as dicts, read back from disk rather than from memory.

    Reading the file rather than ledger.rows is deliberate: the JSONL is what
    survives the run, and a field present in memory but absent on disk is a
    field that does not exist for anyone reading results later.
    """
    ledger.flush()
    out = []
    for line in pathlib.Path(ledger.path).read_text().splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        if rung is None or r["rung"] == rung:
            out.append(r)
    return out


def assert_ledger_invariants(rows, expected_n, label):
    """The four invariants, checked together so a failure names the rung."""
    assert len(rows) == expected_n, (
        f"{label}: {len(rows)} ledger rows for {expected_n} records. "
        "A rung that logs only some of its records reports the rest as "
        "having never happened."
    )
    for r in rows:
        extra = r.get("extra") or {}
        assert extra.get("denominator"), (
            f"{label}: row {r['record_id']} has no denominator. A rate "
            "without the set it is over cannot be interpreted."
        )
        ev = extra.get("evaluable")
        assert ev in EVALUABLE, (
            f"{label}: row {r['record_id']} has evaluable={ev!r}, expected one "
            f"of {sorted(EVALUABLE)}. Two values collapse 'could not run' "
            "into a pass or a fail."
        )
    assert all(r["doc_id"] for r in rows), f"{label}: a row has no doc_id"


# --------------------------------------------------------------------------
# the ledger itself
# --------------------------------------------------------------------------

def test_ledger_has_no_write_method():
    """Regression: three rungs called ledger.write() for weeks. It never existed.

    If a `write` alias is ever added, delete this test and the reason for it —
    but do it deliberately, not by accident.
    """
    assert not hasattr(Ledger, "write"), (
        "Ledger.write exists. Three rungs used to call it; it was never "
        "defined, and the calls were unreachable so nothing raised."
    )
    assert hasattr(Ledger, "log")


def test_ledger_requires_doc_id(ledger):
    """Every dead call site omitted doc_id. log() must not accept that."""
    with pytest.raises(TypeError):
        ledger.log(rung=1, record_id="D1#0", zone="NEW", outcome="x")
    ledger.close()


def test_extra_kwargs_survive_to_disk(ledger):
    """denominator and evaluable ride in **extra. They must reach the file."""
    ledger.log(rung=1, doc_id="D1", record_id="D1#0", zone="NEW",
               outcome="judged", denominator="r1_offered", evaluable="fail")
    rows = rows_of(ledger)
    ledger.close()
    assert rows[0]["extra"]["denominator"] == "r1_offered"
    assert rows[0]["extra"]["evaluable"] == "fail"


# --------------------------------------------------------------------------
# per-rung coverage
#
# These are marked integration because they need the registry and corpus.
# Run them before any release; they are the only tests that execute the
# accounting path at all.
# --------------------------------------------------------------------------

pytestmark_integration = pytest.mark.integration


@pytest.mark.integration
@pytest.mark.parametrize("rung_name", ["r2", "r3", "r4"])
def test_every_record_produces_a_ledger_row(rung_name, ledger, tmp_path):
    """The invariant that eight dead call sites violated silently.

    Needs the corpus, the registry AND a reachable model, so it SKIPS rather
    than fails when any is absent — CI has none of the three. Each guard is
    explicit: a test that errors on a missing prerequisite tells you nothing
    about the code, and a suite that is red for environmental reasons stops
    being read.

    Models come from the manifest through `ladder.llm.for_rung`, never from a
    name written here. A test that hard-codes a model is a second place the
    model is chosen.
    """
    pytest.importorskip("ladder.registry")
    man_path = pathlib.Path("manifest.json")
    if not man_path.exists():
        pytest.skip("no manifest.json — run from the repo root")

    from ladder.llm import for_rung
    from ladder.registry import Registry
    from ladder.rungs import r2, r3, r4
    from ladder.rungs.r0 import run
    from ladder import stub_llm as S

    man = json.loads(man_path.read_text())
    db = pathlib.Path(man["vocabulary"]["snomed_db"])
    if not db.exists():
        pytest.skip(f"no vocabulary index at {db}")
    if not pathlib.Path(man["corpus"]["cadec_root"]).exists():
        pytest.skip("no corpus — this test reads real documents")

    reg = Registry(str(db))
    items = S.load_items(man["corpus"]["splits_dir"])[:2]
    if not items:
        pytest.skip("no split items")
    src = {i["doc_id"]: i["text"] for i in items}

    try:
        extractor = for_rung(0, man)
        recs, _ = run(items, "A", extractor, {"registry": reg,
                                              "rung0_offsets": "search"})
    except UNREACHABLE as exc:
        pytest.skip(f"no reachable model for rung 0: {exc}")
    if not recs:
        pytest.skip("rung 0 produced no records")

    mod = {"r2": r2, "r3": r3, "r4": r4}[rung_name]
    cfg = {"registry": reg, "ledger": ledger}
    try:
        if rung_name == "r2":                       # self-correction
            cfg["llm"] = for_rung(2, man)
        elif rung_name == "r3":                     # voting
            cfg.update(llm=for_rung(3, man).sampler(0.7), k=3)
        else:                                       # r4, the judge
            judge, extract = for_rung(4, man), for_rung(0, man)
            if judge.spec == extract.spec:
                pytest.skip("judge and extractor are the same model; rung 4 "
                            "refuses to self-judge, which is the point")
            cfg.update(judge_llm=judge, extractor_model=extract.spec,
                       judge_model=judge.spec)
    except UNREACHABLE as exc:
        pytest.skip(f"no reachable model for {rung_name}: {exc}")

    try:
        out = mod.apply(recs, src, cfg)
    except UNREACHABLE as exc:
        pytest.skip(f"{rung_name} could not reach its model: {exc}")
    records = out[0] if isinstance(out, tuple) else out

    rows = rows_of(ledger, rung=int(rung_name[1]))
    ledger.close()

    # Voting (rung 3) also writes one row per DOCUMENT for the k sampling
    # calls, which is a real cost paid whether or not any record is re-found.
    # Those are not record rows and must not be counted as such.
    if rung_name == "r3":
        doc_rows = [r for r in rows if r["outcome"] == "sampled"]
        rows = [r for r in rows if r["outcome"] != "sampled"]
        assert doc_rows, (
            "rung 3 logged no document rows. The k calls are paid up front; "
            "without a row for them a run where nothing matched reports "
            "voting as free."
        )

    assert_ledger_invariants(rows, len(records), rung_name)


@pytest.mark.integration
def test_unevaluable_outcomes_say_so(ledger):
    """Parse failures and not-re-found records are not passes and not fails.

    Three separate rungs had the ledger call sitting BELOW an early return, so
    the records that could not be evaluated were exactly the records that left
    no trace. This asserts the category exists and is used.
    """
    ledger.log(rung=4, doc_id="D1", record_id="D1#0", zone="NEW",
               outcome="parse_failed", api_calls=1,
               denominator="r4_offered", evaluable="could_not_run")
    ledger.log(rung=5, doc_id="D1", record_id="D1#1", zone="NEW",
               outcome="not_resampled", api_calls=0,
               denominator="r5_voted_on", evaluable="could_not_run")
    rows = rows_of(ledger)
    ledger.close()
    assert {r["extra"]["evaluable"] for r in rows} == {"could_not_run"}
    assert all(r["extra"]["denominator"] for r in rows)

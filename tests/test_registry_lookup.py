"""Candidate retrieval — what rung 0 is shown before it commits to a code.

No release download: these build a nine-concept index by hand, so they run in
CI where the 365 MB SNOMED SQLite is absent.

Three measurements over CADEC gold shape every test here:

  * exact search on the patient's own words returns nothing 57.1% of the time,
    which is why `shortlist` exists at all
  * where it DOES return something, 15% of the time the gold code is absent and
    the hits are semantic junk — 'gas' returns |Gaseous substance|, and rung 0
    once emitted |California chicken (organism)| for a rectal bleed. Hence
    `findings_only`.
  * 76.8% of multi-candidate sets contain two concepts sharing an IDENTICAL
    label, so a model that answers with a label string is ambiguous more often
    than not. Candidates therefore carry an index, and the model returns that.
"""

import sqlite3

import pytest

from ladder.registry import Registry

# id, active, is_finding, fsn, synonyms
CONCEPTS = [
    ("12063002", 1, 1, "Rectal hemorrhage (finding)", ["Rectal hemorrhage", "Rectal haemorrhage"]),
    ("197220006", 1, 1, "Rectal haemorrhage (disorder)", ["Rectal haemorrhage"]),
    ("82249009", 1, 0, "California chicken (organism)", ["California chicken"]),
    ("74947009", 1, 0, "Gaseous substance (substance)", ["Gas"]),
    ("162076009", 0, 1, "Excessive upper gastrointestinal gas (finding)", ["Gas"]),
    ("213257006", 1, 1, "Generally unwell (finding)", ["Generally unwell"]),
    ("34436003", 1, 1, "Blood in urine (finding)", ["Blood clots in urine"]),
    ("37771000087101", 1, 1, "Blood clots in urine (finding)", ["Blood clots in urine"]),
    ("271782001", 1, 1, "Drowsy (finding)", ["Drowsy", "Bit drowsy"]),
]


@pytest.fixture
def reg(tmp_path):
    path = tmp_path / "mini.sqlite"
    db = sqlite3.connect(path)
    db.execute("CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT)")
    db.execute("CREATE TABLE concept(id TEXT PRIMARY KEY, active INT, is_finding INT, is_finding_hist INT)")
    db.execute("CREATE TABLE description(concept_id TEXT, term TEXT, norm TEXT, fsn INT)")
    db.execute("INSERT INTO meta VALUES('release','TEST')")
    from ladder.registry import normalise_term

    for cid, active, finding, fsn, syns in CONCEPTS:
        db.execute("INSERT INTO concept VALUES(?,?,?,?)", (cid, active, finding, finding))
        db.execute(
            "INSERT INTO description VALUES(?,?,?,1)", (cid, fsn, normalise_term(fsn))
        )
        for s in syns:
            db.execute(
                "INSERT INTO description VALUES(?,?,?,0)", (cid, s, normalise_term(s))
            )
    db.commit()
    db.close()
    return Registry(path)


# --- search_labelled: candidates the model can actually reason about --------


def test_candidates_carry_the_fsn_with_its_semantic_tag():
    """A bare preferred term hides the difference between a finding and a chicken."""


def test_search_labelled_returns_fsn_and_tag(reg):
    hits = reg.search_labelled("California chicken")
    assert hits[0]["fsn"] == "California chicken (organism)"
    assert hits[0]["tag"] == "organism"


def test_search_labelled_indexes_every_candidate(reg):
    """The model answers with an index, because labels collide 76.8% of the time."""
    hits = reg.search_labelled("Blood clots in urine")
    assert [h["i"] for h in hits] == [0, 1]
    assert len({h["code"] for h in hits}) == 2


def test_findings_only_drops_the_chicken(reg):
    assert reg.search_labelled("California chicken", findings_only=True) == []


def test_findings_only_keeps_a_retired_finding(reg):
    """11% of CADEC's codes are retired. Retired is not the same as wrong."""
    hits = reg.search_labelled("Gas", findings_only=True)
    assert [h["code"] for h in hits] == ["162076009"]


def test_search_labelled_misses_layperson_wording(reg):
    """The 57.1% that returns nothing — the reason shortlist exists."""
    assert reg.search_labelled("extreme rectal bleed") == []


# --- shortlist: token overlap, for when exact match finds nothing -----------


def test_shortlist_finds_what_exact_match_missed(reg):
    hits = reg.shortlist("extreme rectal bleed", k=5)
    assert "12063002" in {h["code"] for h in hits}


def test_shortlist_is_findings_only_by_default(reg):
    assert all(h["tag"] == "finding" or h["tag"] == "disorder" for h in reg.shortlist("gas", k=5))


def test_shortlist_respects_k(reg):
    assert len(reg.shortlist("rectal haemorrhage bleed", k=1)) == 1


def test_shortlist_ranks_more_overlap_first(reg):
    hits = reg.shortlist("blood clots in urine sample", k=5)
    assert hits[0]["code"] in {"34436003", "37771000087101"}


def test_shortlist_of_nonsense_is_empty(reg):
    assert reg.shortlist("zzzz qqqq", k=5) == []


def test_shortlist_reindexes_from_zero(reg):
    hits = reg.shortlist("rectal bleed", k=5)
    assert [h["i"] for h in hits] == list(range(len(hits)))


# --- resolve: an ordered list of labels -> one code -------------------------


def test_resolve_takes_the_first_label_that_hits(reg):
    got = reg.resolve(["Extreme rectal bleed", "Rectal hemorrhage"])
    assert got["code"] == "12063002"
    assert got["rank"] == 1


def test_resolve_reports_rank_zero_for_a_first_guess(reg):
    assert reg.resolve(["Generally unwell"])["rank"] == 0


def test_resolve_returns_no_code_when_nothing_hits(reg):
    got = reg.resolve(["Extreme rectal bleed", "Feeling awful"])
    assert got["code"] is None
    assert got["rank"] is None


def test_resolve_flags_an_ambiguous_label(reg):
    """Two concepts, one identical label. The scorer must not pretend otherwise."""
    got = reg.resolve(["Blood clots in urine"])
    assert got["ambiguous"] is True
    assert got["code"] in {"34436003", "37771000087101"}


def test_resolve_is_not_ambiguous_when_one_concept_wins(reg):
    assert reg.resolve(["Generally unwell"])["ambiguous"] is False


def test_resolve_prefers_a_finding_over_a_substance(reg):
    """'Gas' is both a substance and a retired finding. Rung 0 codes findings."""
    assert reg.resolve(["Gas"])["code"] == "162076009"


def test_resolve_accepts_a_bare_string(reg):
    assert reg.resolve("Generally unwell")["code"] == "213257006"


def test_resolve_of_concept_less_is_not_a_lookup(reg):
    """CONCEPT_LESS is an answer, not a term to look up."""
    from ladder.schema import CONCEPT_LESS

    got = reg.resolve([CONCEPT_LESS])
    assert got["code"] == CONCEPT_LESS
    assert got["ambiguous"] is False


def test_resolve_of_an_empty_list_is_no_code(reg):
    assert reg.resolve([])["code"] is None

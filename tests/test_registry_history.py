"""Retired concepts and their successors — the "outdated, not wrong" axis.

A code the model emits may be a concept SNOMED once issued and has since
retired. That is not the same failure as inventing a nine-digit number: the
model named a real concept and simply did not have the current release. The
association refset is where SNOMED itself records which concept replaced which,
so "out of date" becomes a *measurable* third answer instead of a guess.

Only two association types are followed, and the exclusions are the point:

    SAME AS               900000000000527005   the successor. Followed.
    REPLACED BY           900000000000526001   the successor. Followed.
    POSSIBLY EQUIVALENT   900000000000523009   says "possibly". NOT followed.
    WAS A                 900000000000528000   a PARENT — broader, not the
                                               same concept. NOT followed.

Following the last two would let a scorer credit a near-miss as merely stale,
which is the quiet generosity this repo exists to refuse. 48,891 of the AU
release's active association rows are POSSIBLY EQUIVALENT TO and 12,919 are
WAS A, so the difference is not hypothetical.

No release download: a nine-row index is built by hand.
"""

import sqlite3

import pytest

from ladder.registry import (
    ASSOC_POSSIBLY_EQUIVALENT_TO,
    ASSOC_REPLACED_BY,
    ASSOC_SAME_AS,
    ASSOC_WAS_A,
    REPLACEMENT_REFSETS,
    Registry,
    normalise_term,
)

# id, active, fsn
CONCEPTS = [
    ("271782001", 1, "Drowsy (finding)"),
    ("162076009", 0, "Excessive upper gastrointestinal gas (finding)"),
    ("12063002", 1, "Rectal hemorrhage (finding)"),
    ("30473006", 0, "Retired, replaced twice, step one (finding)"),
    ("34436003", 0, "Retired, replaced twice, step two (finding)"),
    ("22253000", 1, "Pain (finding)"),
    ("68962001", 0, "Retired, only possibly equivalent (finding)"),
    ("213257006", 0, "Retired, only a parent recorded (finding)"),
    ("54329005", 0, "Retired, no successor at all (finding)"),
]

# source, target, refsetId, active
ASSOCIATIONS = [
    ("162076009", "12063002", ASSOC_REPLACED_BY, 1),
    ("30473006", "34436003", ASSOC_SAME_AS, 1),
    ("34436003", "22253000", ASSOC_SAME_AS, 1),
    ("68962001", "22253000", ASSOC_POSSIBLY_EQUIVALENT_TO, 1),
    ("213257006", "22253000", ASSOC_WAS_A, 1),
    # An inactive association row is a retracted claim, not a successor.
    ("54329005", "12063002", ASSOC_SAME_AS, 0),
]


def _index(path, with_association=True):
    db = sqlite3.connect(path)
    db.execute("CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT)")
    db.execute(
        "CREATE TABLE concept(id TEXT PRIMARY KEY, active INT, is_finding INT, "
        "is_finding_hist INT)"
    )
    db.execute("CREATE TABLE description(concept_id TEXT, term TEXT, norm TEXT, fsn INT)")
    db.execute("INSERT INTO meta VALUES('release','TEST')")
    for cid, active, fsn in CONCEPTS:
        db.execute("INSERT INTO concept VALUES(?,?,1,1)", (cid, active))
        db.execute(
            "INSERT INTO description VALUES(?,?,?,1)", (cid, fsn, normalise_term(fsn))
        )
    if with_association:
        db.execute("CREATE TABLE association(source TEXT, target TEXT, refset TEXT)")
        for src, tgt, refset, active in ASSOCIATIONS:
            if active:
                db.execute("INSERT INTO association VALUES(?,?,?)", (src, tgt, refset))
    db.commit()
    db.close()
    return Registry(path)


@pytest.fixture
def reg(tmp_path):
    return _index(tmp_path / "hist.sqlite")


@pytest.fixture
def old_reg(tmp_path):
    """An index built before the association table existed.

    The 365 MB SQLite is built once and shared between worktrees, so the
    upgrade is not simultaneous everywhere. A missing table must read as "no
    successors known", never as a crash in the middle of a scoring run.
    """
    return _index(tmp_path / "old.sqlite", with_association=False)


# --- which associations count -----------------------------------------------


def test_only_same_as_and_replaced_by_are_successors():
    assert set(REPLACEMENT_REFSETS) == {ASSOC_SAME_AS, ASSOC_REPLACED_BY}


def test_replaced_by_is_a_successor(reg):
    assert reg.replacements("162076009") == ["12063002"]


def test_possibly_equivalent_to_is_not_a_successor(reg):
    """'Possibly' is not 'is'. Crediting it would make outdated a wastebasket."""
    assert reg.replacements("68962001") == []


def test_was_a_is_not_a_successor(reg):
    """WAS A points at a PARENT. |Pain| is not a stale spelling of a headache."""
    assert reg.replacements("213257006") == []


def test_inactive_association_rows_are_ignored(reg):
    assert reg.replacements("54329005") == []


def test_a_chain_is_followed_to_the_end(reg):
    """SNOMED retires successors too. A one-hop lookup stops one release short."""
    assert reg.replacements("30473006") == ["22253000"]


def test_an_active_concept_has_no_successor(reg):
    """Nothing replaced it — it is still here. Never call a live code outdated."""
    assert reg.replacements("271782001") == []


def test_unknown_and_empty_codes_are_safe(reg):
    assert reg.replacements("999999") == []
    assert reg.replacements(None) == []
    assert reg.replacements("CONCEPT_LESS") == []


def test_replacement_returns_one_code_or_none(reg):
    assert reg.replacement("162076009") == "12063002"
    assert reg.replacement("271782001") is None


def test_an_index_without_the_table_reports_no_successors(old_reg):
    assert old_reg.replacements("162076009") == []
    assert old_reg.replacement("162076009") is None


# --- building the table from a release --------------------------------------


ASSOC_HEADER = (
    "id\teffectiveTime\tactive\tmoduleId\trefsetId\treferencedComponentId"
    "\ttargetComponentId\n"
)


def _release(tmp_path):
    """A three-row association refset, in RF2's own column order."""
    d = tmp_path / "SnomedCT_Release_TEST"
    content = d / "Snapshot" / "Refset" / "Content"
    content.mkdir(parents=True, exist_ok=True)
    f = content / "der2_cRefset_AssociationSnapshot_TEST_20260731.txt"
    rows = [
        ("a", "20260301", "1", "m", ASSOC_REPLACED_BY, "162076009", "12063002"),
        ("b", "20260301", "1", "m", ASSOC_POSSIBLY_EQUIVALENT_TO, "68962001", "22253000"),
        ("c", "20260301", "0", "m", ASSOC_SAME_AS, "54329005", "12063002"),
    ]
    f.write_text(ASSOC_HEADER + "".join("\t".join(r) + "\n" for r in rows))
    return d


def test_build_associations_upgrades_an_existing_index(tmp_path, old_reg):
    """The shared index is upgraded in place rather than rebuilt for hours."""
    from ladder.registry import build_associations

    assert old_reg.replacements("162076009") == []
    n = build_associations(_release(tmp_path), old_reg.path)
    assert n == 2  # the inactive row is not stored
    assert Registry(old_reg.path).replacements("162076009") == ["12063002"]


def test_build_associations_is_idempotent(tmp_path, old_reg):
    """Run twice, one row — not two. A doubled table doubles nothing useful
    but would make a future 'how many successors' count a lie."""
    from ladder.registry import build_associations

    build_associations(_release(tmp_path), old_reg.path)
    build_associations(_release(tmp_path), old_reg.path)
    reg = Registry(old_reg.path)
    assert reg.replacements("162076009") == ["12063002"]
    n = reg._db.execute("SELECT count(*) FROM association").fetchone()[0]
    assert n == 2


def test_build_associations_stores_the_refset_id(tmp_path, old_reg):
    """The refset is kept, not filtered at build time. Which associations count
    is a SCORING decision that must stay changeable without a rebuild."""
    from ladder.registry import build_associations

    build_associations(_release(tmp_path), old_reg.path)
    reg = Registry(old_reg.path)
    kinds = {r[0] for r in reg._db.execute("SELECT refset FROM association")}
    assert kinds == {ASSOC_REPLACED_BY, ASSOC_POSSIBLY_EQUIVALENT_TO}

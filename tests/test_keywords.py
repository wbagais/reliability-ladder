"""The keyword -> code table. Two columns, built from the SNOMED release alone.

TERMS, NOT SENTENCES, AND SNOMED SAYS WHICH IS WHICH. Every concept carries a
Fully Specified Name — |Rectal hemorrhage (finding)| — which exists to
disambiguate, not to be said. The TERM is the Synonym row the language
reference set marks preferred, plus its acceptable variants. Measured
2026-08-24 over finding/disorder concepts:

    Synonym/preferred    197,537 rows   median 4 words
    Synonym/acceptable   135,949 rows   median 4 words
    FSN/preferred        188,459 rows   median 6 words   14.4% over 8 words

Building from all three put 42-word TNM staging text in the keyword column.
Building from Synonym rows alone costs NOTHING — every concept has a preferred
synonym, so gold coverage stays 99.90% and the reachable code count rises.

WHY IT IS ONTOLOGY-ONLY. A list topped up with the codes the answer key happens
to use scores well on this corpus and generalises to nothing — the defect of the
666-term MedDRA list CADEC ships. Nothing here consults CADEC in any form.

No release download: these build a small RF2 description file by hand.
"""

import pytest

from ladder.keywords import (
    CLINICAL_TAGS,
    build_keyword_table,
    load_keyword_table,
    lookup,
)

FSN, SYN = "900000000000003001", "900000000000013009"
COLS = "id\teffectiveTime\tactive\tmoduleId\tconceptId\tlanguageCode\ttypeId\tterm\tcaseSignificanceId"


def _row(i, cid, typeid, term, active="1"):
    return f"{i}\t20260731\t{active}\t900000000000207008\t{cid}\ten\t{typeid}\t{term}\t900000000000448009"


ROWS = [
    ("12063002", FSN, "Rectal hemorrhage (finding)"),
    ("12063002", SYN, "Rectal hemorrhage"),
    ("12063002", SYN, "Rectal haemorrhage"),
    ("213257006", FSN, "Generally unwell (finding)"),
    ("213257006", SYN, "Generally unwell"),
    ("213257006", SYN, "Feeling unwell"),
    ("38341003", FSN, "Hypertensive disorder, systemic arterial (disorder)"),
    ("38341003", SYN, "Hypertension"),
    ("38341003", SYN, "Hypertensive disorder, systemic arterial"),
    # not findings or disorders — must never become keywords
    ("82249009", FSN, "California chicken (organism)"),
    ("82249009", SYN, "California chicken"),
    ("74947009", FSN, "Gaseous substance (substance)"),
    ("74947009", SYN, "Gas"),
    ("255582007", FSN, "Rectal (qualifier value)"),
    ("255582007", SYN, "Rectal"),
    ("105449001", FSN, "Sick relative (person)"),
    ("105449001", SYN, "Sick relative"),
    # a genuine finding whose only synonym is a sentence
    ("9999001", FSN, "Staging description (finding)"),
    ("9999001", SYN,
     "pT2b: Tumor more than 2 cm, but not more than 5 cm, in greatest dimension, "
     "limited to dermis and not otherwise specified"),
]


@pytest.fixture
def release(tmp_path):
    d = tmp_path / "Snapshot" / "Terminology"
    d.mkdir(parents=True)
    f = d / "sct2_Description_Snapshot-en-au_TEST_20260731.txt"
    lines = [COLS] + [_row(i, c, t, term) for i, (c, t, term) in enumerate(ROWS, 1)]
    f.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return tmp_path


# --- shape ------------------------------------------------------------------


def test_the_table_is_two_columns(release, tmp_path):
    import csv

    out = tmp_path / "kw.csv"
    build_keyword_table(release, out)
    with out.open(newline="", encoding="utf-8") as fh:
        rows = list(csv.reader(fh))
    assert rows[0] == ["keyword", "code"]
    assert all(len(r) == 2 for r in rows[1:])


def test_a_keyword_containing_a_comma_survives_the_round_trip(release, tmp_path):
    """SNOMED terms carry commas — |Hypertensive disorder, systemic arterial|.
    A hand-rolled join would shred them, so this is real CSV with real quoting."""
    out = tmp_path / "kw.csv"
    build_keyword_table(release, out)
    kw = load_keyword_table(out)
    assert kw["hypertensive disorder, systemic arterial"] == ["38341003"]


# --- terms, not formal names ------------------------------------------------


def test_synonyms_become_keywords(release, tmp_path):
    out = tmp_path / "kw.csv"
    build_keyword_table(release, out)
    kw = load_keyword_table(out)
    assert kw["rectal hemorrhage"] == ["12063002"]
    assert kw["rectal haemorrhage"] == ["12063002"]
    assert kw["feeling unwell"] == ["213257006"]
    assert kw["hypertension"] == ["38341003"]


def test_the_fully_specified_name_is_not_a_keyword(release, tmp_path):
    """The FSN exists to disambiguate, not to be said. Its semantic tag would
    also never appear in anything a model writes."""
    out = tmp_path / "kw.csv"
    build_keyword_table(release, out)
    kw = load_keyword_table(out)
    assert "rectal hemorrhage (finding)" not in kw
    assert "generally unwell (finding)" not in kw


def test_dropping_the_fsn_loses_no_concept(release, tmp_path):
    """Every concept has a preferred synonym, so this costs nothing —
    measured on the real release: 99.90% either way."""
    out = tmp_path / "kw.csv"
    build_keyword_table(release, out)
    codes = {c for v in load_keyword_table(out).values() for c in v}
    assert {"12063002", "213257006", "38341003"} <= codes


# --- sentences --------------------------------------------------------------


def test_a_sentence_length_synonym_is_dropped(release, tmp_path):
    out = tmp_path / "kw.csv"
    stats = build_keyword_table(release, out, max_words=10)
    kw = load_keyword_table(out)
    assert not any(len(k.split()) > 10 for k in kw)
    assert stats["too_long"] >= 1


def test_the_length_cap_can_be_lifted(release, tmp_path):
    out = tmp_path / "kw.csv"
    build_keyword_table(release, out, max_words=None)
    assert any(len(k.split()) > 10 for k in load_keyword_table(out))


# --- what is excluded -------------------------------------------------------


def test_organisms_products_and_qualifiers_are_excluded(release, tmp_path):
    """|California chicken (organism)| was emitted by rung 0 for a rectal bleed,
    and |Gaseous substance| outranked the right answer for "gas"."""
    out = tmp_path / "kw.csv"
    build_keyword_table(release, out)
    kw = load_keyword_table(out)
    for junk in ("california chicken", "gas", "rectal", "sick relative"):
        assert junk not in kw, f"{junk!r} should not be a keyword"


def test_inactive_rows_are_ignored(tmp_path):
    d = tmp_path / "Snapshot" / "Terminology"
    d.mkdir(parents=True)
    (d / "sct2_Description_Snapshot-en-au_TEST_20260731.txt").write_text(
        "\n".join([
            COLS,
            _row(1, "12063002", FSN, "Rectal hemorrhage (finding)"),
            _row(2, "12063002", SYN, "Rectal hemorrhage"),
            _row(3, "12063002", SYN, "Withdrawn term", active="0"),
        ]) + "\n", encoding="utf-8")
    out = tmp_path / "kw.csv"
    build_keyword_table(tmp_path, out)
    assert "withdrawn term" not in load_keyword_table(out)


def test_the_tag_allowlist_is_declared_not_hidden():
    assert "finding" in CLINICAL_TAGS and "disorder" in CLINICAL_TAGS
    assert "organism" not in CLINICAL_TAGS and "product" not in CLINICAL_TAGS


# --- collisions -------------------------------------------------------------


def test_two_builds_produce_an_identical_file(release, tmp_path):
    a, b = tmp_path / "a.csv", tmp_path / "b.csv"
    build_keyword_table(release, a)
    build_keyword_table(release, b)
    assert a.read_text() == b.read_text()


def test_the_build_reports_what_it_wrote(release, tmp_path):
    stats = build_keyword_table(release, tmp_path / "kw.csv")
    assert stats["keywords"] > 0 and stats["codes"] > 0
    assert stats["ambiguous"] >= 0 and stats["too_long"] >= 0


# --- lookup -----------------------------------------------------------------


def test_lookup_is_case_and_space_insensitive(release, tmp_path):
    out = tmp_path / "kw.csv"
    build_keyword_table(release, out)
    kw = load_keyword_table(out)
    assert lookup(kw, "  Rectal   Hemorrhage ") == ["12063002"]
    assert lookup(kw, "RECTAL HAEMORRHAGE") == ["12063002"]
    assert lookup(kw, "no such thing") == []


def test_a_missing_table_says_how_to_build_it(tmp_path):
    with pytest.raises(FileNotFoundError, match="ladder.keywords"):
        load_keyword_table(tmp_path / "absent.csv")


# --- Read Code migration artifacts ------------------------------------------
#
# SNOMED carries legacy CTV3/Read descriptions as synonyms: "#radius &/or ulna",
# "([provider initiated encounter] or [patient asked to come in]) or". They are
# valid rows and they are not TERMS — no model writes them. Measured
# 2026-08-24: 6,285 such rows (2.2%), and dropping them costs 0 gold mentions
# (0.000%). The 3,369 codes reachable only through one were unreachable in
# practice anyway.


@pytest.mark.parametrize("term", [
    "#radius &/or ulna",
    "([provider initiated encounter] or [patient asked to come in]) or",
    "flatulence &/or wind",
    "(acquired deformity of toe nos) or (acquired overlapping toe) or",
])
def test_legacy_read_code_syntax_is_not_a_keyword(tmp_path, term):
    d = tmp_path / "Snapshot" / "Terminology"
    d.mkdir(parents=True)
    (d / "sct2_Description_Snapshot-en-au_TEST_20260731.txt").write_text(
        "\n".join([
            COLS,
            _row(1, "12063002", FSN, "Rectal hemorrhage (finding)"),
            _row(2, "12063002", SYN, "Rectal hemorrhage"),
            _row(3, "12063002", SYN, term),
        ]) + "\n", encoding="utf-8")
    out = tmp_path / "kw.csv"
    stats = build_keyword_table(tmp_path, out)
    kw = load_keyword_table(out)
    assert "rectal hemorrhage" in kw
    assert " ".join(term.lower().split()) not in kw
    assert stats["legacy"] >= 1


def test_an_ordinary_term_with_a_hyphen_or_slash_survives(tmp_path):
    """The filter must target legacy SYNTAX, not ordinary punctuation."""
    d = tmp_path / "Snapshot" / "Terminology"
    d.mkdir(parents=True)
    (d / "sct2_Description_Snapshot-en-au_TEST_20260731.txt").write_text(
        "\n".join([
            COLS,
            _row(1, "1", FSN, "Test concept (finding)"),
            _row(2, "1", SYN, "Non-Hodgkin lymphoma"),
            _row(3, "1", SYN, "Nausea and/or vomiting"),
            _row(4, "1", SYN, "Type 2 diabetes mellitus"),
        ]) + "\n", encoding="utf-8")
    out = tmp_path / "kw.csv"
    build_keyword_table(tmp_path, out)
    kw = load_keyword_table(out)
    for good in ("non-hodgkin lymphoma", "nausea and/or vomiting", "type 2 diabetes mellitus"):
        assert good in kw, f"{good!r} is an ordinary term and must survive"


@pytest.mark.parametrize("term", [
    "absence of artery nec",          # not elsewhere classified
    "a/n care provider nos",          # not otherwise specified
    "aa - alopecia areata",           # Read abbreviation prefix
    "bilious vomit on examination",   # clinician observation phrasing
    "c/o - a back symptom",           # complains of
    "cns disorder (& h/o) or h/o: brain disorder",
    "a/n u/s scan for ? abnormality",
    "beta thalassaemia:",             # trailing punctuation
])
def test_read_classification_cruft_is_not_a_keyword(tmp_path, term):
    """Read/CTV3 clerical phrasing. Nobody describing a symptom writes "nos",
    "nec", "o/e" or "aa - ". Measured: 19,053 rows, 0 gold codes lost."""
    d = tmp_path / "Snapshot" / "Terminology"
    d.mkdir(parents=True)
    (d / "sct2_Description_Snapshot-en-au_TEST_20260731.txt").write_text(
        "\n".join([
            COLS,
            _row(1, "12063002", FSN, "Rectal hemorrhage (finding)"),
            _row(2, "12063002", SYN, "Rectal hemorrhage"),
            _row(3, "12063002", SYN, term),
        ]) + "\n", encoding="utf-8")
    out = tmp_path / "kw.csv"
    build_keyword_table(tmp_path, out)
    kw = load_keyword_table(out)
    assert "rectal hemorrhage" in kw
    assert " ".join(term.lower().split()) not in kw


@pytest.mark.parametrize("term", [
    "nosebleed",              # contains "nos" but is not the abbreviation
    "necrotising fasciitis",  # contains "nec" but is not the abbreviation
    "back pain on exertion",
    "non-hodgkin lymphoma",
])
def test_ordinary_terms_are_not_caught_by_the_cruft_filter(tmp_path, term):
    """The abbreviations are whole words. A substring rule would delete
    |nosebleed| — which is exactly the kind of term this task needs."""
    d = tmp_path / "Snapshot" / "Terminology"
    d.mkdir(parents=True)
    (d / "sct2_Description_Snapshot-en-au_TEST_20260731.txt").write_text(
        "\n".join([COLS, _row(1, "1", FSN, "Test (finding)"), _row(2, "1", SYN, term)]) + "\n",
        encoding="utf-8")
    out = tmp_path / "kw.csv"
    build_keyword_table(tmp_path, out)
    assert " ".join(term.lower().split()) in load_keyword_table(out)


def test_ordering_still_works_without_a_concept_file(release, tmp_path):
    """The concept file is optional: without it nothing is known to be
    retired, so ordering falls back to numeric and coverage is unchanged."""
    out = tmp_path / "kw.csv"
    build_keyword_table(release, out)
    assert load_keyword_table(out)["rectal hemorrhage"] == ["12063002"]


def test_retired_concepts_are_excluded_from_the_table(tmp_path):
    """One row per keyword is the goal, and retired duplicates are what
    prevented it: |Abdominal discomfort| is 43364001 plus two retired copies.
    Dropping inactive concepts takes ambiguous keywords from 23,334 to 103.
    The CADEC mentions that answer with a retired code are excluded to match —
    see ladder/clean.py."""
    d = tmp_path / "Snapshot" / "Terminology"
    d.mkdir(parents=True)
    (d / "sct2_Description_Snapshot-en-au_TEST_20260731.txt").write_text(
        "\n".join([
            COLS,
            _row(1, "139312000", FSN, "Abdominal discomfort (finding)"),
            _row(2, "139312000", SYN, "Abdominal discomfort"),
            _row(3, "43364001", FSN, "Abdominal discomfort (finding)"),
            _row(4, "43364001", SYN, "Abdominal discomfort"),
        ]) + "\n", encoding="utf-8")
    (d / "sct2_Concept_Snapshot_TEST_20260731.txt").write_text(
        "id\teffectiveTime\tactive\tmoduleId\tdefinitionStatusId\n"
        "139312000\t20260731\t0\tm\td\n43364001\t20260731\t1\tm\td\n", encoding="utf-8")
    out = tmp_path / "kw.csv"
    stats = build_keyword_table(tmp_path, out)
    assert load_keyword_table(out)["abdominal discomfort"] == ["43364001"]
    assert stats["retired"] == 1
    assert stats["ambiguous"] == 0


def test_a_keyword_appears_exactly_once(tmp_path):
    """One row per keyword. After retired concepts are dropped only 103
    keywords still name two live concepts; resolving them leaves 32 codes with
    no keyword, none of which CADEC uses."""
    d = tmp_path / "Snapshot" / "Terminology"
    d.mkdir(parents=True)
    (d / "sct2_Description_Snapshot-en-au_TEST_20260731.txt").write_text(
        "\n".join([
            COLS,
            _row(1, "205258009", FSN, "Acrocephalosyndactyly (disorder)"),
            _row(2, "205258009", SYN, "Acrocephalosyndactyly"),
            _row(3, "205258009", SYN, "Apert syndrome"),
            _row(4, "268262006", FSN, "Acrocephalosyndactyly (disorder)"),
            _row(5, "268262006", SYN, "Acrocephalosyndactyly"),
        ]) + "\n", encoding="utf-8")
    out = tmp_path / "kw.csv"
    build_keyword_table(tmp_path, out)
    kw = load_keyword_table(out)
    assert all(len(v) == 1 for v in kw.values())
    # 268262006 owns no other keyword, so the shared one goes to it rather
    # than leaving it unreachable
    assert kw["acrocephalosyndactyly"] == ["268262006"]
    assert kw["apert syndrome"] == ["205258009"]


def test_neither_column_is_ever_blank(tmp_path):
    """A row with an empty keyword or an empty code is unusable. A description
    that normalises to nothing — punctuation only, or a bare semantic tag —
    must be dropped at build time rather than written as a blank."""
    d = tmp_path / "Snapshot" / "Terminology"
    d.mkdir(parents=True)
    (d / "sct2_Description_Snapshot-en-au_TEST_20260731.txt").write_text(
        "\n".join([
            COLS,
            _row(1, "12063002", FSN, "Rectal hemorrhage (finding)"),
            _row(2, "12063002", SYN, "Rectal hemorrhage"),
            _row(3, "12063002", SYN, "   "),        # whitespace only
            _row(4, "12063002", SYN, "(finding)"),  # nothing left after the tag
            _row(5, "", SYN, "Orphan term"),        # no concept id
        ]) + "\n", encoding="utf-8")
    out = tmp_path / "kw.csv"
    build_keyword_table(tmp_path, out)
    rows = [r for r in out.read_text(encoding="utf-8").splitlines()[1:]]
    assert rows, "expected at least one row"
    for r in rows:
        kw, _, code = r.rpartition(",")
        assert kw.strip() and code.strip(), f"blank field in {r!r}"
    assert "orphan term" not in load_keyword_table(out)


@pytest.mark.parametrize("mapping", [
    {"": "12063002"},
    {"   ": "12063002"},
    {"rectal hemorrhage": ""},
    {"rectal hemorrhage": "  "},
])
def test_the_build_refuses_to_write_a_blank_field(mapping):
    """Defence in depth. Three earlier filters already drop empty and
    non-alphabetic keywords, so nothing should reach this check — which is why
    it exists: a future filter change must fail the build rather than ship a
    half-empty row for something downstream to trip over."""
    from ladder.keywords import check_no_blanks

    with pytest.raises(ValueError, match="blank"):
        check_no_blanks(mapping)


def test_a_well_formed_mapping_passes_the_check():
    from ladder.keywords import check_no_blanks

    check_no_blanks({"rectal hemorrhage": "12063002"})


def test_a_blank_row_in_an_existing_file_is_refused(tmp_path):
    path = tmp_path / "kw.csv"
    path.write_text("keyword,code\nrectal hemorrhage,12063002\n,999\n", encoding="utf-8")
    with pytest.raises(ValueError, match="blank"):
        load_keyword_table(path)


# --- KeywordTable: the resolution step behind rung 0 -------------------------
#
# Rung 0 named concepts and `Registry.resolve` turned the name into a code by
# searching every description in the release — organisms, products, substances,
# qualifiers and all. The keyword table is the filtered, ontology-only version
# of that same step, and it is what rung 0 resolves against now.
#
# The registry does NOT go away. Rung 1 needs exists / is_active /
# finding_status / terms over the WHOLE release, and the keyword table is
# deliberately filtered — 82249009 |California chicken| is a real, active
# concept that rung 1 must be able to look up and rung 0 must never reach.


def table(**mapping):
    from ladder.keywords import KeywordTable

    return KeywordTable.from_mapping({k: list(v) for k, v in mapping.items()})


T = table(
    **{
        "rectal hemorrhage": ["12063002"],
        "generally unwell": ["213257006"],
        "coma": ["371632003", "50061006"],
    }
)


def test_resolve_returns_the_code_for_a_name():
    assert T.resolve(["Rectal hemorrhage"])["code"] == "12063002"


def test_resolve_is_case_and_tag_insensitive():
    """The model writes "Rectal hemorrhage"; the release stores it with a
    semantic tag. Both have to reach the same row."""
    assert T.resolve(["RECTAL HEMORRHAGE (finding)"])["code"] == "12063002"


def test_resolve_walks_the_label_list_and_reports_the_rank():
    """Rung 0 proposes up to three names. Walking them is not a retry loop —
    no second model call happens. Rank is worth reporting: if rank 1 wins
    often, the model's first instinct is systematically wrong."""
    got = T.resolve(["Not a concept", "Generally unwell"])
    assert (got["code"], got["rank"]) == ("213257006", 1)


def test_resolve_reports_an_unresolved_label():
    got = T.resolve(["Not a concept at all"])
    assert got["code"] is None and got["rank"] is None


def test_resolve_passes_concept_less_through_without_a_lookup():
    from ladder.schema import CONCEPT_LESS

    got = T.resolve([CONCEPT_LESS])
    assert got["code"] == CONCEPT_LESS
    assert got["ambiguous"] is False


def test_resolve_of_nothing_is_no_code():
    assert T.resolve([])["code"] is None
    assert T.resolve(None)["code"] is None
    assert T.resolve("")["code"] is None


def test_resolve_accepts_a_bare_string():
    assert T.resolve("Generally unwell")["code"] == "213257006"


def test_an_ambiguous_keyword_is_reported_as_ambiguous():
    """9.8% of keywords named more than one concept before the build picked an
    owner per keyword. The table can still express it, and resolve must say so
    rather than pick silently."""
    got = T.resolve(["coma"])
    assert got["ambiguous"] is True
    assert got["candidates"] == ["371632003", "50061006"]
    assert got["code"] == "371632003"


def test_an_unambiguous_keyword_carries_no_candidate_list():
    assert T.resolve(["Rectal hemorrhage"])["ambiguous"] is False


def test_the_table_reports_its_own_size():
    assert len(T) == 3


def test_a_table_loads_from_the_csv_the_build_writes(release, tmp_path):
    from ladder.keywords import KeywordTable

    out = tmp_path / "kw.csv"
    build_keyword_table(release, out)
    t = KeywordTable(out)
    assert t.resolve(["Rectal hemorrhage"])["code"] == "12063002"


def test_a_missing_csv_says_how_to_build_it(tmp_path):
    from ladder.keywords import KeywordTable

    with pytest.raises(FileNotFoundError, match="ladder.keywords --build"):
        KeywordTable(tmp_path / "nope.csv")

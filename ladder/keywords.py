"""The keyword -> code table: two columns, built from the SNOMED release alone.

    python -m ladder.keywords --build

Rung 0 deals in WORDS. It names the concept it thinks it found; this table maps
that name to a SNOMED code. The model never emits a nine-digit integer, so it
never mistypes one, and "did it name the right concept" becomes separable from
"did it recall the right id" — which are different failures with different
fixes.

ONTOLOGY ONLY, AND THAT IS THE POINT
------------------------------------
Nothing here reads CADEC, the gold annotations, or the train split. A list
topped up with the codes the answer key happens to use scores well on this
corpus and generalises to nothing — which is exactly the defect of the 666-term
MedDRA list CADEC ships (all 666 of its codes appear in the gold, none do not).
Coverage against gold is REPORTED below; it never chooses the contents.

TERMS, NOT SENTENCES, AND SNOMED SAYS WHICH IS WHICH. Every concept carries a
Fully Specified Name — |Rectal hemorrhage (finding)| — whose job is to
disambiguate, not to be said. The TERM is the Synonym row. Measured 2026-08-24
over finding/disorder concepts:

    Synonym/preferred    197,537 rows   median 4 words
    Synonym/acceptable   135,949 rows   median 4 words
    FSN/preferred        188,459 rows   median 6 words   14.4% over 8 words

Building from all three put 42-word TNM staging text in the keyword column
("pT2b: Tumor more than 2 cm, but not more than 5 cm, in greatest dimension,
limited to dermis..."). Synonym rows alone cost nothing — every concept has a
preferred synonym.

RETIRED CONCEPTS ARE DROPPED, AND THAT IS WHAT MAKES A KEYWORD A KEY. A
retired concept is almost always a duplicate superseded by a live one, and
keeping them made 23,334 keywords ambiguous against 103 without them. With
them gone the table is one row per keyword — 227,554 keywords, 227,554 rows,
127,515 codes — and the 103 remaining collisions go to whichever concept owns
the FEWEST other keywords, so a concept is not left unreachable merely because
it shares its only term. 32 codes end up with no keyword; none is used by
CADEC.

An earlier build kept retired concepts and let a keyword repeat (279,059
keywords, 313,780 rows, 180,446 codes). It reached 99.90% of coded gold
mentions against this build's 94.11% — but the 5.8pt difference is ENTIRELY
the 407 mentions whose every gold code is retired, and `ladder/clean.py`
excludes those from the denominator for the same reason this build drops them.
Measured 2026-08-24 with the exclusions applied, which is how the ladder
actually reads gold:

    coded gold reaction mentions   6,595
    reachable through the table    6,592   99.95%

The three misses are 1806006, 183202003 and 251377007 — one mention each.
That 99.95% is the ceiling for ANY release-derived table: three of CADEC's
distinct gold codes are absent from this SNOMED release entirely (annotation
typos, see ladder/registry.py). Restricting to findings and disorders costs
nothing further while removing every organism, product, substance and
qualifier — the class that produced |California chicken (organism)| for a
rectal bleed and let |Gaseous substance| outrank the right answer for "gas".

`lookup()` still returns a LIST even though this build never puts two codes
under one keyword. Ambiguity is a property of vocabularies rather than of one
filter setting, and a signature that changes when a filter changes is a
signature that will be wrong again the next time one does. |coma| really is
both 371632003 and 50061006.

IT IS A LOOKUP, NOT A PROMPT LIST. At 227,554 rows it is far too large to show
a model. It is the resolution step behind rung 0, not a menu — which is one of
the reasons S3, a pick from one printed list, was dropped on 2026-08-24.

WHERE IT LIVES. `data/keywords.csv` — cleaned data, not a cache. It is produced
once, before any rung runs, and a run whose keyword table changed is a different
run, so it belongs with the corpus and the splits rather than beside a
disposable index.

LICENCE: derived from the SNOMED CT release, which is affiliate-licensed, and
the derived form is the same content in another shape. `.gitignore` ignores
`data/*` and re-includes only `data/splits/`, so this file is unpublished by
default exactly like `snomed.sqlite`. Verify with `scripts/preflight.py`.
"""

from __future__ import annotations

import argparse
import csv
import re
from pathlib import Path

#: Semantic tags a rung 0 answer may carry. A reaction normalises to a clinical
#: finding or a disorder; measured on CADEC gold, 917 of 923 codes are one of
#: these two and the remaining six cost 0.08% of mentions. Declared here rather
#: than buried in a query so that widening it is a visible decision.
CLINICAL_TAGS = frozenset({"finding", "disorder"})

#: RF2 description typeIds. The FSN is read only to find each concept's
#: semantic tag; it never becomes a keyword.
FSN_TYPE = "900000000000003001"
SYNONYM_TYPE = "900000000000013009"

#: Longest keyword kept. SNOMED synonyms include 42-word TNM staging text,
#: which is a description rather than anything a model would write. Costs
#: 0.00% of gold mentions at 10 words; None lifts the cap.
DEFAULT_MAX_WORDS = 10

#: Read/CTV3 migration artifacts carried as SNOMED synonyms: "#radius &/or
#: ulna", "([provider initiated encounter] or [patient asked to come in]) or".
#: Valid rows, but not terms — no model writes them. Measured: 6,285 rows
#: (2.2%), costing 0 gold mentions. Note "&/or" is legacy syntax while the
#: ordinary "and/or" is not, so the two are matched separately.
_LEGACY = re.compile(r"\[|\]|&/or|^\(|\bor$")

#: A keyword has to look like something a person would write. Read-legacy
#: synonyms include quoted colloquialisms ('"glue ear"', '"nerves"') and bare
#: measurements ("1/3 meter", "1/24", "1/1/2036"). Requiring a leading letter
#: and no quote mark removes 1,199 rows and 0.00% of gold mentions. Digits
#: INSIDE a term are fine — "Type 2 diabetes mellitus", "COVID-19".
_NOT_A_TERM = re.compile(r'^[^a-z]|"')

#: Read/CTV3 clerical phrasing carried into SNOMED as synonyms. Nobody
#: describing a symptom writes "nos", "nec", "o/e" or "aa - alopecia areata".
#: The abbreviations are matched as WHOLE WORDS so |nosebleed| and
#: |necrotising fasciitis| survive. Measured 2026-08-24: 19,053 rows removed,
#: 0 gold codes lost.
_CRUFT = re.compile(
    r"\b(nos|nec)\b"       # not otherwise specified / not elsewhere classified
    r"|\bon examination\b"
    r"|^o/e"
    r"|^(h/o|c/o|fh:|sh:)"  # history of / complains of / family / social history
    r"|\(&"
    r"|[?!]"
    r"|[-:,;/]\s*$"         # trailing punctuation, a truncated description
    r"|^[a-z]{1,5} - "      # Read abbreviation prefix
)

#: Cleaned data, not a cache: the ladder reads it, it is produced once
#: before any rung runs, and a run whose keyword table changed is a
#: different run. `data/` is gitignored except for `data/splits/`, which
#: keeps the SNOMED-derived content unpublished exactly as required.
DEFAULT_OUT = Path("data/keywords.csv")
_TAG = re.compile(r"\s*\(([^()]*)\)\s*$")


def _normalise(s: str) -> str:
    """Lowercase, drop a trailing semantic tag, squash whitespace.

    The model writes "Rectal hemorrhage", the release stores
    "Rectal hemorrhage (finding)". Both have to reach the same row.
    """
    s = _TAG.sub("", s or "")
    return " ".join(s.lower().split())


def _description_file(release: str | Path) -> Path:
    hits = sorted(Path(release).glob("Snapshot/Terminology/sct2_Description_Snapshot*.txt"))
    if not hits:
        raise FileNotFoundError(
            f"no sct2_Description_Snapshot*.txt under {release}/Snapshot/Terminology.\n"
            "SNAPSHOT, not Full: Full carries every historical revision of every "
            "row (4.17M lines against 2.24M), so indexing it resurrects renamed "
            "terms. Snapshot is current-state and still contains inactive rows, "
            "which is what lets exists() mean 'present, active or retired'."
        )
    return hits[0]


def check_no_blanks(mapping: dict) -> None:
    """Both columns are required. Raises rather than writing an unusable row.

    Defence in depth: three earlier filters already drop empty, too-short and
    non-alphabetic keywords, so nothing should reach here. That is exactly why
    it is checked — a future filter change must fail the build, not ship a
    half-empty row for something downstream to trip over.
    """
    blank = [k for k, v in mapping.items() if not str(k).strip() or not str(v).strip()]
    if blank:
        raise ValueError(
            f"{len(blank)} row(s) would have a blank keyword or code. Both "
            "columns are required — a row missing either half cannot be used, "
            "and writing it defers the failure to whatever reads the file."
        )


def build_keyword_table(
    release: str | Path,
    out_path: str | Path = DEFAULT_OUT,
    max_words: int | None = DEFAULT_MAX_WORDS,
) -> dict:
    """Write a `keyword,code` CSV, one row per distinct keyword. Returns stats.

    COLLISIONS ARE REAL AND UNFIXABLE HERE. 76.8% of multi-candidate sets over
    CADEC gold contain two concepts sharing an identical label — |Blood clots
    in urine| is both 34436003 and 37771000087101. A two-column table cannot
    express that, so the tie is broken by NUMERICALLY lowest concept id, which prefers the core
    international concept over an extension: stable, defensible, because a table that reshuffled between builds would move every
    number derived from it. The collision count is reported so the loss is
    visible rather than silent.
    """
    path = _description_file(release)

    # Concept activity. Retired concepts are DROPPED: they are duplicates
    # superseded by a live concept, and keeping them made 23,334 keywords
    # ambiguous against 103 without them. The CADEC mentions whose gold code
    # is retired are excluded to match, in ladder/clean.py — 410 mentions
    # (5.6%). Absent concept file: nothing is known to be retired, keep all.
    active: dict[str, bool] = {}
    for cf in sorted(Path(release).glob("Snapshot/Terminology/sct2_Concept_Snapshot*.txt")):
        with cf.open(encoding="utf-8") as fh:
            next(fh)
            for line in fh:
                f = line.rstrip("\n").split("\t")
                if len(f) >= 3:
                    active[f[0]] = f[2] == "1"
        break
    release_name = path.name.split("_Description")[0].replace("sct2", "").strip("_") or path.name

    # Pass 1: the FSN carries the semantic tag, and nothing else does. It is
    # read ONLY to decide which concepts are clinical — never as a keyword.
    keep: set[str] = set()
    with path.open(encoding="utf-8") as fh:
        next(fh)
        for line in fh:
            f = line.rstrip("\n").split("\t")
            if len(f) < 8 or f[2] != "1" or f[6] != FSN_TYPE:
                continue
            m = _TAG.search(f[7] or "")
            if m and m.group(1).strip().lower() in CLINICAL_TAGS:
                keep.add(f[4])

    # Pass 2: Synonym rows only. These are the terms.
    # keyword -> the codes that carry it. NOT a unique key: forcing one code
    # per keyword cost 10.05% of gold mentions, because |coma| belongs to two
    # concepts and CADEC uses the one a tiebreak discarded. Still two columns;
    # a keyword simply appears on more than one row.
    table: dict[str, set[str]] = {}
    too_long = legacy = retired = 0
    with path.open(encoding="utf-8") as fh:
        next(fh)
        for line in fh:
            f = line.rstrip("\n").split("\t")
            if len(f) < 8 or f[2] != "1" or f[6] != SYNONYM_TYPE or f[4] not in keep:
                continue
            cid, kw = f[4], _normalise(f[7])
            # Neither column may be blank: a row missing either half is
            # unusable, and writing one would push the failure into whatever
            # reads the file later.
            if not kw or not cid.strip():
                continue
            if max_words and len(kw.split()) > max_words:
                too_long += 1
                continue
            if len(kw) < 3 or _LEGACY.search(kw) or _NOT_A_TERM.search(kw) or _CRUFT.search(kw):
                legacy += 1
                continue
            if active and not active.get(cid, True):
                retired += 1
                continue
            table.setdefault(kw, set()).add(cid)

    # ONE ROW PER KEYWORD. A keyword naming two live concepts is rare once
    # retired duplicates are gone (103 of 227,554). The row goes to whichever
    # concept owns the FEWEST other keywords, so a concept is not left
    # unreachable just because it shares its only term. Measured: 32 codes end
    # up with no keyword, none of them used by CADEC.
    owns: dict[str, int] = {}
    for codes in table.values():
        for c in codes:
            owns[c] = owns.get(c, 0) + 1
    chosen = {
        kw: min(codes, key=lambda c: (owns[c], int(c)))
        for kw, codes in table.items()
    }
    ambiguous = sum(1 for v in table.values() if len(v) > 1)

    check_no_blanks(chosen)

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    # Real CSV, real quoting: SNOMED terms carry commas and brackets, so a
    # hand-rolled join would shred |Hypertensive disorder, systemic arterial|.
    with out_path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["keyword", "code"])
        for kw in sorted(chosen):
            w.writerow([kw, chosen[kw]])

    return {
        "release": release_name,
        "keywords": len(chosen),
        "rows": len(chosen),
        "codes": len(set(chosen.values())),
        "ambiguous": ambiguous,
        "unreachable": len({c for v in table.values() for c in v}) - len(set(chosen.values())),
        "retired": retired,
        "too_long": too_long,
        "legacy": legacy,
        "path": str(out_path),
    }


def load_keyword_table(path: str | Path = DEFAULT_OUT) -> dict[str, str]:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(
            f"{path} missing. Build it once with:\n"
            f"    python -m ladder.keywords --build\n"
            "It is derived from the SNOMED release and gitignored for the same "
            "reason snomed.sqlite is."
        )
    out: dict[str, list[str]] = {}
    with path.open(encoding="utf-8", newline="") as fh:
        r = csv.reader(fh)
        header = next(r, None)
        if header != ["keyword", "code"]:
            raise ValueError(f"{path} is not a keyword table (header {header!r})")
        for n, row in enumerate(r, start=2):
            if len(row) != 2 or not row[0].strip() or not row[1].strip():
                raise ValueError(
                    f"{path} line {n}: blank keyword or code ({row!r}). Both "
                    "columns are required; rebuild with "
                    "`python -m ladder.keywords --build`."
                )
            out.setdefault(row[0], []).append(row[1])
    return out


def lookup(table: dict[str, list[str]], keyword: str | None) -> list[str]:
    """The model's words -> every code carrying them. Never guesses, never fuzzy.

    A LIST because a keyword is not a unique key: 9.8% of keywords name more
    than one concept. One element is the common case (90.2%); more than one is
    a disambiguation rung 0 must make rather than a coin the table flips.
    """
    if not keyword:
        return []
    return list(table.get(_normalise(keyword), ()))


class KeywordTable:
    """The table as rung 0 uses it: names in, one code out, plus the audit.

    Mirrors `Registry.resolve`'s return shape on purpose — the two are
    interchangeable at the call site, so the difference between "resolve
    against every description in the release" and "resolve against the
    filtered ontology table" is one line in rung 0 and not a rewrite. The
    keys are `code`, `rank`, `ambiguous`, `label`, `candidates`.

    THE REGISTRY DOES NOT GO AWAY. Rung 1 needs exists / is_active /
    finding_status / terms over the WHOLE release, and this table is
    deliberately filtered: 82249009 |California chicken (organism)| is real
    and active, rung 1 must be able to look it up, and rung 0 must never be
    able to reach it.
    """

    def __init__(self, path: str | Path = DEFAULT_OUT):
        self.path = Path(path)
        self._t = load_keyword_table(self.path)

    @classmethod
    def from_mapping(cls, mapping: dict[str, list[str]]) -> "KeywordTable":
        """Build one in memory. For tests and for callers holding the dict."""
        obj = cls.__new__(cls)
        obj.path = None
        obj._t = {_normalise(k): list(v) for k, v in mapping.items()}
        return obj

    def __len__(self) -> int:
        return len(self._t)

    def lookup(self, keyword: str | None) -> list[str]:
        return lookup(self._t, keyword)

    def resolve(self, labels) -> dict:
        """An ordered list of proposed NAMES -> one code.

        Rung 0 answers with up to three names, best first, because one guess
        is not enough: the patient's own words exact-match no SNOMED
        description 57.1% of the time. Walking the list is NOT a retry loop —
        no second model call happens, and a failure stated back as a fact is
        rung 2's job.

        `rank` is the position of the name that won. If rank 1 and 2 win
        often, the model's first instinct is systematically wrong, which is a
        finding about the model rather than about the vocabulary.
        """
        from ladder.schema import CONCEPT_LESS

        if isinstance(labels, str):
            labels = [labels]
        labels = [str(x) for x in (labels or []) if x is not None and str(x).strip()]
        none = {"code": None, "rank": None, "ambiguous": False,
                "label": None, "candidates": []}
        for rank, label in enumerate(labels):
            if label.strip().upper() == CONCEPT_LESS:
                return {**none, "code": CONCEPT_LESS, "rank": rank, "label": CONCEPT_LESS}
            hits = self.lookup(label)
            if not hits:
                continue
            # First, not "best": the table has no ranking to offer and
            # inventing one here would hide the ambiguity rather than report
            # it. `candidates` carries the rest.
            return {
                "code": hits[0],
                "rank": rank,
                "ambiguous": len(hits) > 1,
                "label": label,
                "candidates": hits if len(hits) > 1 else [],
            }
        return none


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--build", action="store_true")
    ap.add_argument("--release", default=None,
                    help="defaults to manifest.vocabulary.snomed_release_dir")
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    ap.add_argument("--max-words", type=int, default=DEFAULT_MAX_WORDS,
                    help="0 lifts the cap")
    a = ap.parse_args(argv)
    if not a.build:
        ap.error("nothing to do — pass --build")

    release = a.release
    if release is None:
        from ladder.manifest import load_manifest

        release = load_manifest("manifest.json")["vocabulary"]["snomed_release_dir"]
    stats = build_keyword_table(release, a.out, a.max_words or None)
    print(
        f"[keywords] {stats['release']}\n"
        f"  {stats['keywords']:,} keywords -> {stats['codes']:,} codes"
        f"  ({stats['rows']:,} rows)\n"
        f"  {stats['ambiguous']:,} keywords named two live concepts; "
        f"{stats['unreachable']:,} codes left with no keyword\n"
        f"  {stats['too_long']:,} dropped as too long, "
        f"{stats['legacy']:,} as legacy Read syntax, "
        f"{stats['retired']:,} as retired\n"
        f"  wrote {stats['path']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""SNOMED CT lookup — the critical-path dependency for rung 1.

Rung 1 needs to answer three questions about a code with no model call and no
network round-trip:

    exists(code)      is this a real SNOMED concept at all?
    is_finding(code)  is it a descendant of |Clinical finding|, i.e. in the
                      right slot for a bodily experience?
    terms(code)       what words does the vocabulary use for it? (lexical match)

The plan reaches for the BioPortal API. A local RF2 release is strictly better:
no key, no rate limit, no network in the measurement loop, and a version pin
that is a directory name rather than a promise. This module builds a ~200 MB
SQLite index once from the release and answers from it in microseconds.

    python -m ladder.registry --build

Three release facts that change what rung 1 may reject
------------------------------------------------------
Measured on AU1000036_20260731 against the 1,046 distinct SCT codes CADEC uses:

    927  active in the release
    115  present but INACTIVE — retired from SNOMED since CADEC was coded in 2015
      4  absent entirely (three annotation typos, one code CADEC got wrong)

So an `exists` check written as "active in the current release" would reject
11% of the gold standard's own answers. `exists()` therefore means "present in
the release, active or not", and inactivity is reported as its own audit fact.
Whether inactive codes are rejected is a manifest setting, not a hard-coded
opinion, because it is exactly the kind of choice that silently moves the rung 1
rejection rate. See docs/decisions.md 2026-08-22.

Third, and the one that actually bites: when SNOMED retires a concept it also
retires that concept's is-a relationships. So a hierarchy walk over ACTIVE
relationships alone reports every retired concept as "not a clinical finding" —
not because it is in the wrong slot, but because it has no slot any more.
Measured on CADEC gold, that alone accounted for 413 of 416 apparent
wrong-semantic-type rejections: |Knee pain|, |Bloating symptom|, |Tiredness
symptom| and friends, all retired, all clinically correct.

The index therefore stores TWO hierarchy answers — one over active is-a rows and
one over every is-a row ever published — and `finding_status()` returns
"finding" / "not_finding" / "unknown" instead of a bool. Rung 1 may only reject
on a positive "not_finding"; absence of evidence is not evidence of a wrong slot.
"""

from __future__ import annotations

import argparse
import os
import re
import sqlite3
import sys
from pathlib import Path

from ladder.schema import CLINICAL_FINDING

IS_A = "116680003"
SNOMED_ROOT = "138875005"

DEFAULT_CACHE = Path(__file__).parent / "cache"

#: SNOMED terms carry a semantic tag in trailing parentheses —
#: "Blurred vision (finding)". It is metadata, never something a patient writes.
_SEMANTIC_TAG = re.compile(r"\s*\([^()]*\)\s*$")
_PUNCT = re.compile(r"[^\w\s]+")


def normalise_term(s: str) -> str:
    """Lowercase, drop the semantic tag, squash punctuation and whitespace."""
    s = _SEMANTIC_TAG.sub("", s or "")
    s = _PUNCT.sub(" ", s.lower())
    return " ".join(s.split())


class Registry:
    """Read-only view over the SQLite index. Cheap to construct, safe to share."""

    def __init__(self, db_path: str | os.PathLike):
        db_path = Path(db_path)
        if not db_path.exists():
            raise FileNotFoundError(
                f"{db_path} missing. Build it once with:\n"
                f"    python -m ladder.registry --build --release <SnomedCT_Release_dir>"
            )
        self._db = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, check_same_thread=False)
        self._db.row_factory = None
        self.release: str = self._meta("release")
        self._cache: dict[str, tuple[bool, bool] | None] = {}

    def _meta(self, key: str) -> str:
        row = self._db.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return row[0] if row else ""

    # -- the three rung-1 questions -----------------------------------------

    def _concept(self, code: str) -> tuple[bool, bool, bool] | None:
        """(active, is_finding, is_finding_hist) or None if in no release."""
        if code in self._cache:
            return self._cache[code]
        row = self._db.execute(
            "SELECT active, is_finding, is_finding_hist FROM concept WHERE id=?", (str(code),)
        ).fetchone()
        got = (bool(row[0]), bool(row[1]), bool(row[2])) if row else None
        self._cache[code] = got
        return got

    def exists(self, code: str | None) -> bool:
        """Present in the release — active OR inactive. See the module note."""
        return bool(code) and self._concept(str(code)) is not None

    def is_active(self, code: str | None) -> bool:
        c = self._concept(str(code)) if code else None
        return bool(c and c[0])

    def is_finding(self, code: str | None) -> bool:
        """Descendant-or-self of |Clinical finding| in the ACTIVE hierarchy."""
        c = self._concept(str(code)) if code else None
        return bool(c and c[1])

    def finding_status(self, code: str | None) -> str:
        """"finding" | "not_finding" | "unknown".

        A retired concept keeps no active is-a rows, so the active hierarchy
        cannot place it. Falling back to the historical hierarchy answers for
        most of them; anything neither graph can place is "unknown", and rung 1
        is not allowed to reject on it.
        """
        c = self._concept(str(code)) if code else None
        if c is None:
            return "unknown"
        active, finding, finding_hist = c
        if finding:
            return "finding"
        if active:
            return "not_finding"
        return "finding" if finding_hist else "unknown"

    # -- lexical -------------------------------------------------------------

    def terms(self, code: str | None) -> list[str]:
        if not code:
            return []
        return [
            r[0]
            for r in self._db.execute(
                "SELECT term FROM description WHERE concept_id=?", (str(code),)
            )
        ]

    def preferred(self, code: str | None) -> str | None:
        if not code:
            return None
        row = self._db.execute(
            "SELECT term FROM description WHERE concept_id=? AND fsn=1 LIMIT 1", (str(code),)
        ).fetchone()
        if row:
            return _SEMANTIC_TAG.sub("", row[0])
        row = self._db.execute(
            "SELECT term FROM description WHERE concept_id=? LIMIT 1", (str(code),)
        ).fetchone()
        return row[0] if row else None

    def lexical_match(self, text: str, code: str | None, mode: str = "exact") -> bool:
        """Does the quoted span use words the vocabulary uses for this code?

        `exact`     normalised span == a normalised term
        `contained` normalised span's tokens are a subset of a term's, or vice
                    versa — catches "little blurred vision" vs "Blurred vision"

        This is the ACCEPT/BAND divider, never a rejection: patient language is
        colloquial, so a miss means "unverifiable by string comparison", not
        "wrong". Rung 1 is not allowed to claim a code is right.
        """
        want = normalise_term(text)
        if not want:
            return False
        toks = set(want.split())
        for term in self.terms(code):
            got = normalise_term(term)
            if got == want:
                return True
            if mode == "contained" and got:
                other = set(got.split())
                if toks <= other or other <= toks:
                    return True
        return False

    def codes_for_term(self, text: str) -> list[str]:
        """Reverse lookup — every concept with this exact normalised term."""
        return [
            r[0]
            for r in self._db.execute(
                "SELECT concept_id FROM description WHERE norm=?", (normalise_term(text),)
            )
        ]

    def stats(self) -> dict[str, str]:
        return {k: v for k, v in self._db.execute("SELECT key, value FROM meta")}


class MeddraTable:
    """MedDRA code -> term, from a CSV with `meddra_code` and `meddra_term`.

    KNOW WHAT THIS TABLE IS BEFORE YOU TRUST A NUMBER FROM IT. The only MedDRA
    artefact available to this project is the code list CADEC ships alongside
    the corpus, and it is derived FROM the corpus. Measured 2026-08-22:

        666  codes in the table
        666  of them appear in CADEC's gold annotations
          0  of them do not

    It is the answer key's code inventory, not a vocabulary — roughly 3% of
    MedDRA's preferred terms. Used as an existence check it answers "is this one
    of the 666 codes the annotators happened to use?", so it rejects hallucinated
    codes trivially (any code outside the list) AND rejects real MedDRA codes the
    annotators did not reach for. Both directions inflate what rung 1 looks like
    it can do. Stripping the `occurrences` / `posts` / `example_mentions` columns
    removes the evidence of derivation, not the derivation.

    So `meddra_check` defaults to "flag": the verdict is recorded and counted in
    rung 1's comparison, and is not a rejection reason. `"reject"` is one
    manifest line away, and `leakage()` prints the caveat wherever the number
    appears. A subscription MedDRA release would make all of this moot; point
    `meddra_csv` at one and the caveat goes away with it.
    """

    def __init__(self, path: str | os.PathLike, name: str = ""):
        import csv

        self.path = Path(path)
        self.name = name or self.path.name
        self.terms_by_code: dict[str, str] = {}
        self.types: dict[str, str] = {}
        with self.path.open(encoding="utf-8-sig", newline="") as fh:
            for row in csv.DictReader(fh):
                code = (row.get("meddra_code") or "").strip()
                if not code:
                    continue
                self.terms_by_code[code] = (row.get("meddra_term") or "").strip()
                self.types[code] = (row.get("term_type") or "").strip()

    def __len__(self) -> int:
        return len(self.terms_by_code)

    def exists(self, code: str | None) -> bool:
        return bool(code) and str(code) in self.terms_by_code

    def term(self, code: str | None) -> str | None:
        return self.terms_by_code.get(str(code)) if code else None

    def lexical_match(self, text: str, code: str | None, mode: str = "exact") -> bool:
        term = self.term(code)
        if not term:
            return False
        want, got = normalise_term(text), normalise_term(term)
        if not want or not got:
            return False
        if got == want:
            return True
        if mode == "contained":
            a, b = set(want.split()), set(got.split())
            return a <= b or b <= a
        return False

    def leakage(self, gold_codes: set[str]) -> dict[str, object]:
        """How much of this table is just the answer key? Report it, always."""
        codes = set(self.terms_by_code)
        outside = codes - gold_codes
        return {
            "table": self.name,
            "n_codes": len(codes),
            "n_also_in_gold": len(codes & gold_codes),
            "n_independent_of_gold": len(outside),
            "derived_from_gold": not outside,
            "caveat": (
                "every code in this table appears in the gold annotations and none "
                "do not: it is the answer key's code inventory, not a vocabulary"
            )
            if not outside
            else "",
        }


# --- index builder ----------------------------------------------------------


def _snapshot_files(release: Path) -> tuple[Path, Path, Path]:
    term = release / "Snapshot" / "Terminology"
    if not term.is_dir():
        raise FileNotFoundError(f"{term} not found — is {release} an RF2 release directory?")

    def one(prefix: str) -> Path:
        hits = sorted(p for p in term.glob(f"{prefix}*.txt"))
        if not hits:
            raise FileNotFoundError(f"no {prefix}*.txt under {term}")
        return hits[0]

    return (
        one("sct2_Concept_Snapshot"),
        one("sct2_Relationship_Snapshot"),
        one("sct2_Description_Snapshot"),
    )


def build(release: str | os.PathLike, db_path: str | os.PathLike, force: bool = False) -> Path:
    """Build the SQLite index from an RF2 release. Takes a few minutes, once."""
    release = Path(release)
    db_path = Path(db_path)
    if db_path.exists() and not force:
        print(f"{db_path} already exists — pass --force to rebuild", file=sys.stderr)
        return db_path
    concept_f, rel_f, desc_f = _snapshot_files(release)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = db_path.with_suffix(".building")
    if tmp.exists():
        tmp.unlink()
    db = sqlite3.connect(tmp)
    db.executescript(
        """
        PRAGMA journal_mode=OFF; PRAGMA synchronous=OFF;
        CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT);
        CREATE TABLE concept(id TEXT PRIMARY KEY, active INT, is_finding INT, is_finding_hist INT);
        CREATE TABLE description(concept_id TEXT, term TEXT, norm TEXT, fsn INT);
        """
    )

    print(f"[registry] concepts   <- {concept_f.name}", file=sys.stderr)
    active: dict[str, int] = {}
    with concept_f.open(encoding="utf-8") as fh:
        next(fh)
        for line in fh:
            p = line.split("\t")
            active[p[0]] = 1 if p[2] == "1" else 0

    print(f"[registry] is-a graph <- {rel_f.name}", file=sys.stderr)
    children: dict[str, list[str]] = {}
    children_hist: dict[str, list[str]] = {}
    with rel_f.open(encoding="utf-8") as fh:
        next(fh)
        for line in fh:
            p = line.split("\t")
            if p[7] != IS_A:
                continue
            children_hist.setdefault(p[5], []).append(p[4])
            if p[2] == "1":
                children.setdefault(p[5], []).append(p[4])

    def descendants(graph: dict[str, list[str]]) -> set[str]:
        seen = {CLINICAL_FINDING}
        stack = [CLINICAL_FINDING]
        while stack:
            for child in graph.get(stack.pop(), ()):
                if child not in seen:
                    seen.add(child)
                    stack.append(child)
        return seen

    findings = descendants(children)
    findings_hist = descendants(children_hist)
    print(
        f"[registry] |Clinical finding| descendants: {len(findings):,} active, "
        f"{len(findings_hist):,} including retired",
        file=sys.stderr,
    )

    db.executemany(
        "INSERT INTO concept VALUES (?,?,?,?)",
        (
            (cid, a, 1 if cid in findings else 0, 1 if cid in findings_hist else 0)
            for cid, a in active.items()
        ),
    )

    print(f"[registry] descriptions <- {desc_f.name}", file=sys.stderr)
    FSN = "900000000000003001"

    def rows():
        with desc_f.open(encoding="utf-8") as fh:
            next(fh)
            for line in fh:
                p = line.split("\t")
                if p[2] != "1":
                    continue
                yield (p[4], p[7], normalise_term(p[7]), 1 if p[6] == FSN else 0)

    db.executemany("INSERT INTO description VALUES (?,?,?,?)", rows())
    db.executescript(
        "CREATE INDEX d_concept ON description(concept_id);"
        "CREATE INDEX d_norm ON description(norm);"
    )
    n_desc = db.execute("SELECT count(*) FROM description").fetchone()[0]
    db.executemany(
        "INSERT INTO meta VALUES (?,?)",
        [
            ("release", release.name),
            ("concepts", str(len(active))),
            ("active_concepts", str(sum(active.values()))),
            ("clinical_findings", str(len(findings))),
            ("descriptions", str(n_desc)),
        ],
    )
    db.commit()
    db.close()
    tmp.replace(db_path)
    print(f"[registry] wrote {db_path} ({db_path.stat().st_size / 1e6:.0f} MB)", file=sys.stderr)
    return db_path


def default_db(cache_dir: str | os.PathLike = DEFAULT_CACHE) -> Path:
    return Path(cache_dir) / "snomed.sqlite"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--build", action="store_true")
    ap.add_argument("--release", help="RF2 release directory (SnomedCT_Release_...)")
    ap.add_argument("--db", default=str(default_db()))
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--check", nargs="*", help="codes to look up")
    a = ap.parse_args(argv)
    if a.build:
        if not a.release:
            ap.error("--build needs --release")
        build(a.release, a.db, force=a.force)
    if a.check is not None:
        reg = Registry(a.db)
        print(reg.stats())
        for code in a.check or [CLINICAL_FINDING, "162031009", "999999999"]:
            print(
                f"{code:20s} exists={reg.exists(code)!s:5s} active={reg.is_active(code)!s:5s} "
                f"finding={reg.is_finding(code)!s:5s} {reg.preferred(code)}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

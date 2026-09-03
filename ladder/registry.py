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

from ladder.schema import CLINICAL_FINDING, CONCEPT_LESS
from schemas.vocabulary import NOT_FINDING

IS_A = "116680003"

# --- historical associations ------------------------------------------------
# SNOMED never deletes a concept; it retires one and records what took its
# place, in the association reference set. That record is what makes "the model
# named a real concept from an older release" separable from "the model made a
# number up" — see ladder/score.py's `outdated` outcome.
ASSOC_SAME_AS = "900000000000527005"
ASSOC_REPLACED_BY = "900000000000526001"
ASSOC_POSSIBLY_EQUIVALENT_TO = "900000000000523009"
ASSOC_WAS_A = "900000000000528000"
ASSOC_MOVED_TO = "900000000000524003"
ASSOC_ALTERNATIVE = "900000000000530003"

#: The only two SNOMED states as THE successor. Deliberately narrow.
#: POSSIBLY EQUIVALENT TO says "possibly" — 48,891 active rows in the AU
#: release, and treating a maybe as a yes turns `outdated` into a wastebasket
#: for near misses. WAS A points at a PARENT, which is a broader concept and
#: not the same one; MOVED TO points at a module, not a concept at all.
REPLACEMENT_REFSETS = (ASSOC_SAME_AS, ASSOC_REPLACED_BY)

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
    """Read-only view over the SQLite index. Cheap to construct, safe to share.

    Implements `schemas.vocabulary.Vocabulary`. This is the non-lossy backend:
    it sees retired concepts and extension modules, both of which the OLS4
    backend cannot. See schemas/vocabulary.py for what that costs.
    """

    #: schemas.vocabulary.Vocabulary
    name = "local-rf2"
    lossy = False

    def __init__(self, db_path: str | os.PathLike):
        db_path = Path(db_path)
        if not db_path.exists():
            raise FileNotFoundError(
                f"{db_path} missing. Build it once with:\n"
                f"    python -m ladder.registry --build --release <SnomedCT_Release_dir>"
            )
        self.path = db_path
        self._db = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, check_same_thread=False)
        self._db.row_factory = None
        self.release: str = self._meta("release")
        self._cache: dict[str, tuple[bool, bool] | None] = {}
        self._assoc: bool | None = None

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

    # -- history: what replaced a retired concept ----------------------------

    def _has_association(self) -> bool:
        """Does this index carry the association table?

        The 365 MB SQLite is built once and shared, so an index built before
        this table existed is a normal state, not an error. It reads as "no
        successors known" — which degrades `outdated` back into `incorrect`,
        the conservative direction. `python -m ladder.registry --associations`
        adds the table to an existing index in place.
        """
        if self._assoc is None:
            self._assoc = bool(
                self._db.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name='association'"
                ).fetchone()
            )
        return self._assoc

    def replacements(self, code: str | None) -> list[str]:
        """The concept(s) that replaced a retired one. Empty for a live code.

        Follows SAME AS / REPLACED BY to the END of the chain: SNOMED retires
        successors too, so a single hop can stop one release short and report
        a code as unreplaced when a current equivalent exists. Cycles are
        guarded because the release is data, not a promise.

        An ACTIVE concept is never given a successor even if a stray row
        names one — nothing replaced it, it is still here.
        """
        if not code or code == CONCEPT_LESS or not self._has_association():
            return []
        code = str(code)
        if self._concept(code) is None or self.is_active(code):
            return []
        marks = ",".join("?" * len(REPLACEMENT_REFSETS))
        seen, frontier, out = {code}, [code], []
        while frontier:
            rows = self._db.execute(
                f"SELECT target FROM association WHERE source=? AND refset IN ({marks})",
                (frontier.pop(), *REPLACEMENT_REFSETS),
            ).fetchall()
            for (target,) in rows:
                if target in seen:
                    continue
                seen.add(target)
                # A successor that was itself retired is a waypoint, not an
                # answer: keep walking rather than reporting a dead code.
                if self.is_active(target):
                    out.append(target)
                else:
                    frontier.append(target)
        return sorted(out, key=lambda c: (len(c), c))

    def replacement(self, code: str | None) -> str | None:
        """The single successor, or None. Ties broken as in `replacements`."""
        got = self.replacements(code)
        return got[0] if got else None

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

    def label(self, code: str | None) -> str | None:
        """Alias for `preferred`, for parity with the OLS4 backend's surface."""
        return self.preferred(code)

    def search(self, term: str, rows: int = 5) -> list[dict]:
        """Exact-term retrieval over the local index. Rung 0 mode B only.

        Exact rather than fuzzy: a local index has no relevance ranking, and a
        fuzzy local search would quietly become a different experiment from the
        OLS4 one it is meant to be comparable with.
        """
        out = []
        for code in dict.fromkeys(self.codes_for_term(term)):
            if len(out) >= rows:
                break
            out.append({"code": code, "label": self.preferred(code)})
        return out

    # -- candidate retrieval: what rung 0 is SHOWN ---------------------------
    #
    # `search()` above answers "does the vocabulary use exactly these words".
    # These three answer a different question: "what could this mention be?"
    # Measured over CADEC gold, that difference is most of the task —
    # exact-matching the patient's own words returns nothing 57.1% of the time,
    # and where it returns something the gold code is absent 15% of the time.

    def fsn(self, code: str | None) -> str | None:
        """The fully specified name, semantic tag intact.

        `preferred()` strips the tag. The tag is the cheapest signal there is
        for telling |Rectal hemorrhage (finding)| from |California chicken
        (organism)|, so candidates shown to a model keep it.
        """
        if not code:
            return None
        row = self._db.execute(
            "SELECT term FROM description WHERE concept_id=? AND fsn=1 LIMIT 1", (str(code),)
        ).fetchone()
        return row[0] if row else None

    def semantic_tag(self, code: str | None) -> str:
        fsn = self.fsn(code) or ""
        m = _SEMANTIC_TAG.search(fsn)
        return m.group(0).strip().strip("()").strip() if m else ""

    #: The keys EVERY retriever must return, whichever one built the menu.
    #: rung 0's pick logic reads `i`, `code` and `fsn`/`label`, and the audit
    #: reads `via`; a retriever returning a different shape fails at the PICK
    #: rather than at the swap, which is a long way from the cause. Extras are
    #: allowed and are retriever-specific: `tag`/`active` here, `score` from
    #: the dense index in ladder/embed.py.
    CANDIDATE_KEYS = ("i", "code", "label", "fsn", "via")

    def _candidate(self, code: str, i: int, via: str = "") -> dict:
        return {
            "i": i,
            "code": code,
            # The FSN carries the semantic tag — |Rectal hemorrhage (finding)|
            # — and the label does not. Both, because the menu shows one and a
            # later comparison against the model's own words wants the other.
            "label": self.preferred(code) or "",
            "fsn": self.fsn(code) or self.preferred(code) or "",
            "tag": self.semantic_tag(code),
            "active": self.is_active(code),
            "via": via,
        }

    def search_labelled(
        self, term: str, rows: int = 20, findings_only: bool = False, via: str = "term"
    ) -> list[dict]:
        """Exact-term hits, each carrying its FSN, tag and an INDEX.

        The index is the point. 76.8% of multi-candidate sets over CADEC gold
        contain two concepts with an identical label, so a model that replies
        with a label string is ambiguous more often than not. It reads the
        words and answers with the index.

        `findings_only` filters on `finding_status`, which is deliberately not
        `is_active and is_finding`: 11% of CADEC's codes are retired, and
        SNOMED retires a concept's is-a rows along with the concept, so an
        active-only walk calls every retired finding "not a finding".
        """
        out = []
        for code in dict.fromkeys(self.codes_for_term(term)):
            if findings_only and self.finding_status(code) == NOT_FINDING:
                continue
            out.append(self._candidate(code, len(out), via))
            if len(out) >= rows:
                break
        return out

    def shortlist(self, text: str, k: int = 20, findings_only: bool = True) -> list[dict]:
        """Token-overlap candidates, for when exact match found nothing.

        This is the ONLY fuzzy retrieval in the registry, and it is confined to
        rung 0's candidate display: it never decides whether a code exists.
        Ranked by how much of the query a term covers, longer terms losing ties
        so that |Gas| beats |Gaseous substance quality of something| for "gas".
        """
        want = set(normalise_term(text).split())
        if not want:
            return []
        scored: dict[str, tuple[float, int]] = {}
        # PREFILTER, added for the GeoNames arm. The scan below is O(rows) and
        # SNOMED has 1.8M of them (~1s); GeoNames has 13.4M and the same call
        # measured 8.0s, which put rung 0 at 100 minutes a run. A row sharing no
        # token with the query scores zero and is skipped, so restricting to
        # rows whose norm CONTAINS one of the query tokens returns exactly the
        # same candidates. Uses no index — LIKE %x% cannot — but moves the
        # filter into SQLite, which is ~50x faster than the Python loop.
        clause = " OR ".join(["norm LIKE ?"] * len(want))
        params = [f"%{w}%" for w in want]
        rows = self._db.execute(
            f"SELECT concept_id, norm FROM description WHERE {clause}", params)
        for cid, norm in rows:
            got = set((norm or "").split())
            shared = want & got
            if not shared:
                continue
            score = len(shared) / len(want | got)
            if score > scored.get(cid, (0.0, 0))[0]:
                scored[cid] = (score, len(norm or ""))
        ranked = sorted(scored.items(), key=lambda kv: (-kv[1][0], kv[1][1], kv[0]))
        out = []
        for cid, _ in ranked:
            if findings_only and self.finding_status(cid) == NOT_FINDING:
                continue
            out.append(self._candidate(cid, len(out), "shortlist"))
            if len(out) >= k:
                break
        return out

    def resolve(self, labels, findings_only: bool = True) -> dict:
        """An ordered list of proposed labels -> one code.

        Rung 0 answers with up to three labels, best first, because a single
        guess is not enough: MedDRA's own preferred terms fail to exact-match
        any SNOMED description 36.2% of the time, and the patient's words fail
        57.1% of the time. Walking the list is NOT a retry loop — no second
        model call happens, and a retry stated as a fact is rung 2's job.

        `rank` is the position of the label that won, and is worth reporting:
        if rank 1 and 2 win often, the model's first instinct is systematically
        wrong, which is a finding about the model rather than the vocabulary.
        """
        if isinstance(labels, str):
            labels = [labels]
        labels = [str(x) for x in (labels or []) if x is not None and str(x).strip()]
        none = {"code": None, "rank": None, "ambiguous": False, "label": None, "candidates": []}
        for rank, label in enumerate(labels):
            if label.strip().upper() == CONCEPT_LESS:
                return {**none, "code": CONCEPT_LESS, "rank": rank, "label": CONCEPT_LESS}
            hits = self.search_labelled(label, findings_only=findings_only)
            if not hits:
                continue
            # Prefer an active concept when several share the term, but never
            # drop a retired one that is the only candidate — retired is not
            # the same as wrong, and 11% of CADEC's gold is retired.
            best = next((h for h in hits if h["active"]), hits[0])
            return {
                "code": best["code"],
                "rank": rank,
                "ambiguous": len(hits) > 1,
                "label": label,
                "candidates": hits,
            }
        return none

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

    `mode` makes the same choice explicit for RETRIEVAL, which is the sharper
    end of it:

      "reference"    (default) the list only cross-checks a code the model
                     produced by other means. Never used for search, never used
                     to reject. The task stays open-vocabulary.
      "answer_space" the task IS closed-set assignment over this list. That is
                     legitimate and much easier — and it is a different task,
                     so it has to be declared in the manifest and in the method
                     section. `search()` requires it.
    """

    MODES = ("reference", "answer_space")

    def __init__(self, path: str | os.PathLike, name: str = "", mode: str = "reference"):
        if mode not in self.MODES:
            raise ValueError(f"mode must be one of {self.MODES}, got {mode!r}")
        self.mode = mode
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

    def search(self, text: str, k: int = 5) -> list[dict]:
        """Closed-set retrieval. Requires mode="answer_space" — see the note above.

        Refusing to search in "reference" mode is the whole safeguard: a list
        derived from the answer key makes retrieval trivially correct, and the
        refusal is what stops that happening by accident.
        """
        if self.mode != "answer_space":
            raise RuntimeError(
                "MeddraTable.search() needs mode='answer_space'. In 'reference' mode "
                "the list may only cross-check a code produced by other means — "
                "searching it would be retrieving from the answer key."
            )
        want = set(normalise_term(text).split())
        if not want:
            return []
        scored = []
        for code, term in self.terms_by_code.items():
            got = set(normalise_term(term).split())
            if not got:
                continue
            j = len(want & got) / len(want | got)
            if j > 0:
                scored.append((j, code))
        scored.sort(key=lambda x: (-x[0], x[1]))
        return [
            {"code": c, "label": self.terms_by_code[c], "score": round(j, 3)}
            for j, c in scored[:k]
        ]

    def agrees_with_sct(self, meddra_code: str | None, sct_code: str | None, snomed) -> bool | None:
        """Cross-vocabulary agreement — reference mode's real job.

        Compares the two preferred terms lexically. Weak, but it costs nothing,
        needs no mapping table, and unlike an existence check it compares two
        PREDICTIONS rather than a prediction against the answer key — so it
        carries no leakage. None when either term is unavailable.
        """
        m, s = self.term(meddra_code), snomed.preferred(sct_code) if snomed else None
        if not m or not s:
            return None
        return bool(set(normalise_term(m).split()) & set(normalise_term(s).split()))

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


def _association_file(release: Path) -> Path:
    content = release / "Snapshot" / "Refset" / "Content"
    hits = sorted(content.glob("der2_cRefset_AssociationSnapshot*.txt"))
    if not hits:
        raise FileNotFoundError(
            f"no der2_cRefset_AssociationSnapshot*.txt under {content}"
        )
    return hits[0]


def _load_associations(db: sqlite3.Connection, release: Path) -> int:
    """Fill the association table from the release. Returns rows written.

    ACTIVE rows only: an inactive association row is a claim SNOMED has since
    retracted, and honouring it would credit a successor the release no longer
    stands behind.

    The refsetId is STORED, not filtered here. Which association types count as
    a successor is a scoring decision (`REPLACEMENT_REFSETS`), and burning it
    into a table that takes minutes to rebuild would make revisiting it
    expensive enough that nobody would.
    """
    assoc_f = _association_file(release)
    print(f"[registry] associations <- {assoc_f.name}", file=sys.stderr)
    db.executescript(
        "DROP TABLE IF EXISTS association;"
        "CREATE TABLE association(source TEXT, target TEXT, refset TEXT);"
    )

    def rows():
        with assoc_f.open(encoding="utf-8") as fh:
            next(fh)
            for line in fh:
                p = line.rstrip("\n").split("\t")
                if p[2] != "1":
                    continue
                yield (p[5], p[6], p[4])

    db.executemany("INSERT INTO association VALUES (?,?,?)", rows())
    db.execute("CREATE INDEX a_source ON association(source)")
    return db.execute("SELECT count(*) FROM association").fetchone()[0]


def build_associations(release: str | os.PathLike, db_path: str | os.PathLike) -> int:
    """Add (or refresh) the association table on an EXISTING index, in place.

    The full build reads 1.8 M concepts and walks the is-a graph twice; this
    reads one refset file and takes seconds. It exists because the index is
    built once and shared between checkouts, so `build(force=True)` would mean
    rebuilding — and, where the index is reached through a symlink, would
    replace the symlink with a private copy and silently fork the two.
    """
    release, db_path = Path(release), Path(db_path)
    if not db_path.exists():
        raise FileNotFoundError(f"{db_path} missing — build the index first")
    db = sqlite3.connect(db_path)
    try:
        n = _load_associations(db, release)
        db.commit()
    finally:
        db.close()
    print(f"[registry] {n:,} active association rows in {db_path}", file=sys.stderr)
    return n


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
    n_assoc = _load_associations(db, release)
    n_desc = db.execute("SELECT count(*) FROM description").fetchone()[0]
    db.executemany(
        "INSERT INTO meta VALUES (?,?)",
        [
            ("release", release.name),
            ("concepts", str(len(active))),
            ("active_concepts", str(sum(active.values()))),
            ("clinical_findings", str(len(findings))),
            ("descriptions", str(n_desc)),
            ("associations", str(n_assoc)),
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
    ap.add_argument(
        "--associations",
        action="store_true",
        help="add the retired->replacement table to an EXISTING index, in place",
    )
    ap.add_argument("--release", help="RF2 release directory (SnomedCT_Release_...)")
    ap.add_argument("--db", default=str(default_db()))
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--check", nargs="*", help="codes to look up")
    a = ap.parse_args(argv)
    if a.build:
        if not a.release:
            ap.error("--build needs --release")
        build(a.release, a.db, force=a.force)
    if a.associations:
        if not a.release:
            ap.error("--associations needs --release")
        build_associations(a.release, a.db)
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

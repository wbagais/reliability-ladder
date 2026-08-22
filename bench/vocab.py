"""
vocab.py — the vocabulary resource. THE global resource, injected once per run.

Two consumers, deliberately separated:

  SEARCH  — used by rung 0 in option B. The model calls this before answering.
  CHECKS  — used by rung 1. Deterministic, no model, never calls search.

TWO BACKENDS, AND THEY ARE NOT EQUIVALENT
------------------------------------------
`select()` returns whichever is available, preferring the local one:

  local-rf2  a SNOMED CT RF2 release indexed to SQLite (ladder/registry.py).
             Needs the download and an affiliate licence. Sees retired concepts
             and extension modules.
  ols4       EBI OLS4 over the network, below. Free, no key, nothing to
             download — but it serves ACTIVE INTERNATIONAL SNOMED ONLY.

Measured over CADEC's 8,666 coded gold mentions
(`python -m ladder.vocab_crosscheck --live 40`):

    an OLS4-backed exists() reports 23.9% of the ANSWER KEY as codes that do
    not exist — 7.5% retired, 16.4% AU-extension. The local index reports 5.
    Reactions 5.9% affected; drug mentions 100%, because CADEC codes drugs to
    AMT, which the international release does not contain at all.

That is a property of the source, not a defect here, and no configuration of
OLS4 closes it. The backend is therefore recorded in the manifest, and a rung-1
rejection rate is not comparable across backends.

The module-level functions below are the stable surface: they delegate to the
selected backend, so `ladder_ab.py`, the CI smoke test and anything else that
already imports them keep working unchanged.

Every OLS4 response is disk-cached, so a re-run costs nothing and the ladder's
token/latency numbers are not polluted by repeated network calls.
"""
from __future__ import annotations
import json, os, re, time, urllib.parse, urllib.request  # noqa: F401
from pathlib import Path

OLS = "https://www.ebi.ac.uk/ols4/api"
CACHE = Path(os.environ.get("VOCAB_CACHE", "cache/vocab"))
CLINICAL_FINDING = "SNOMED:404684003"
TIMEOUT = 25

# ---------------------------------------------------------------- transport
def _get(url: str, key: str) -> dict:
    CACHE.mkdir(parents=True, exist_ok=True)
    f = CACHE / (re.sub(r"[^A-Za-z0-9_.-]", "_", key)[:180] + ".json")
    if f.exists():
        return json.loads(f.read_text())
    req = urllib.request.Request(url, headers={"Accept": "application/json",
                                               "User-Agent": "reliability-ladder/1.0"})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                data = json.loads(r.read().decode())
            f.write_text(json.dumps(data))
            return data
        except Exception:
            if attempt == 2:
                raise
            time.sleep(1.5 * (attempt + 1))
    return {}


def _iri(code: str) -> str:
    """OLS4 wants the IRI double-URL-encoded."""
    raw = f"http://snomed.info/id/{code}"
    return urllib.parse.quote(urllib.parse.quote(raw, safe=""), safe="")


# ------------------------------------------------------- SEARCH (rung 0, B)
# These four are the OLS4 IMPLEMENTATION. The public `search` / `exists` /
# `label` / `is_finding` further down delegate to the SELECTED backend, which
# is the local release when one is built. Calling these directly bypasses that
# choice and gets you the lossy answer — see the module docstring.
def _ols_search(term: str, rows: int = 5) -> list[dict]:
    """Candidate concepts for a surface term. THE MODEL CALLS THIS."""
    q = urllib.parse.quote(term)
    d = _get(f"{OLS}/search?q={q}&ontology=snomed&rows={rows}", f"search_{term}_{rows}")
    out = []
    for doc in d.get("response", {}).get("docs", []):
        oid = doc.get("obo_id") or ""
        if not oid.startswith("SNOMED:"):
            continue
        out.append({"code": oid.split(":", 1)[1], "label": doc.get("label", "")})
    return out


# --------------------------------------------------------- CHECKS (rung 1)
def _ols_exists(code: str) -> bool:
    """Check 4. Binary. A hallucinated code fails outright."""
    if not re.fullmatch(r"\d{6,18}", str(code or "")):
        return False
    d = _get(f"{OLS}/search?q={code}&ontology=snomed&rows=1", f"exists_{code}")
    docs = d.get("response", {}).get("docs", [])
    return any(x.get("obo_id") == f"SNOMED:{code}" for x in docs)


def _ols_label(code: str) -> str | None:
    d = _get(f"{OLS}/search?q={code}&ontology=snomed&rows=1", f"exists_{code}")
    for x in d.get("response", {}).get("docs", []):
        if x.get("obo_id") == f"SNOMED:{code}":
            return x.get("label")
    return None


def _ols_is_finding(code: str) -> bool:
    """Check 5. Is it a descendant of |Clinical finding|? Catches right-code-wrong-slot."""
    if not _ols_exists(code):
        return False
    d = _get(f"{OLS}/ontologies/snomed/terms/{_iri(code)}/hierarchicalAncestors?size=200",
             f"anc_{code}")
    ids = {t.get("obo_id") for t in d.get("_embedded", {}).get("terms", [])}
    return CLINICAL_FINDING in ids or f"SNOMED:{code}" == CLINICAL_FINDING


_STOP = {"the", "a", "an", "of", "my", "and", "or", "in", "on", "to", "was", "is",
         "were", "had", "have", "so", "very", "bit", "little", "some", "no", "not"}


def _toks(s: str) -> set[str]:
    return {w for w in re.findall(r"[a-z]+", (s or "").lower()) if w not in _STOP}


def lexical_overlap(span_text: str, code: str) -> float:
    """
    Check 6. Does the reporter's wording overlap the concept's label?
    NOT a pass/fail. Zero overlap is normal and expected — see the note below.
    """
    lab = preferred(code)
    if not lab:
        return 0.0
    a, b = _toks(span_text), _toks(lab)
    return 0.0 if not a or not b else len(a & b) / len(a | b)


# ------------------------------------------- CHECKS that need no vocabulary
def negated(source: str, span: tuple[int, int], window: int = 45) -> bool:
    """Check 3. 'so far no gastric problems' — costs nothing, needs no vocabulary.

    Delegates to ladder.negation, which adds three things this needed: a cue
    inside the mention is part of the complaint ("no energy" IS the symptom),
    pseudo-negations ("no doubt", "not sure") do not fire, and terminators
    ("but", "however") end the scope. `window` is now in TOKENS, not characters.

    A fire is an audit flag, not a rejection: CADEC annotates a mention
    regardless of polarity, so rejecting on it costs 427 gold-correct mentions.
    See ladder/rungs/r1.py `negation_action`.
    """
    return _is_negated(source, [tuple(span)], window=max(1, window // 7))[0]


def grounded(source: str, span: tuple[int, int], span_text: str) -> bool:
    """Check 2. Pure string comparison. The cheapest check on the ladder.

    Delegates to Record.valid(), which compares a case- and order-insensitive
    token bag rather than an exact substring. Measured on CADEC gold: exact
    comparison false-rejects 725 of 9,111 mentions (8.0%), because 1,066 are
    discontinuous and 45 quote their segments in reading order rather than
    offset order. The token bag false-rejects 4.

    For a discontinuous mention pass the Record to `grounded_record` instead —
    a single (start, end) pair cannot express one.
    """
    try:
        s, e = span
    except (TypeError, ValueError):
        return False
    if not (isinstance(s, int) and isinstance(e, int) and 0 <= s < e <= len(source)):
        return False
    return _Record(doc_id="", entity_type="reaction", text=span_text,
                   spans=[(s, e)]).valid(source)[0]


# ---------------------------------------------- option B only: tool fidelity
def honoured_tool(emitted_code: str, tool_results: list[dict]) -> bool | None:
    """
    Check 7 — exists ONLY in option B, and is the most interesting one.

    The model searched, got candidates back, then emitted a code. Did it emit
    one of them, or override its own lookup with something invented?
    Returns None when no search was made for this record.
    """
    if not tool_results:
        return None
    return str(emitted_code) in {str(r["code"]) for r in tool_results}


# ============================================================================
# BACKENDS — one contract, two implementations. See schemas/vocabulary.py.
# ============================================================================
import sys as _sys
import warnings as _warnings

from schemas.vocabulary import FINDING, NOT_FINDING, UNKNOWN, conforms


class Ols4Vocabulary:
    """The functions above, behind the Vocabulary contract.

    LOSSY. OLS4 indexes active international SNOMED, so every retired concept
    and every extension-module concept answers `exists() == False` — which a
    validation gate reads as "hallucinated code". Read the module docstring
    before reporting any number this backend produced.
    """

    name = "ols4"
    lossy = True
    release = "EBI OLS4 (live service — no pinned release)"

    def exists(self, code):  return _ols_exists(str(code)) if code else False
    def is_active(self, code):  return self.exists(code)   # OLS4 has only active concepts
    def is_finding(self, code):  return _ols_is_finding(str(code)) if code else False
    def terms(self, code):
        lab = _ols_label(str(code)) if code else None
        return [lab] if lab else []
    def preferred(self, code):  return _ols_label(str(code)) if code else None

    def finding_status(self, code):
        """Two-valued in practice: a code this backend cannot see does not exist."""
        if not self.exists(code):
            return UNKNOWN
        return FINDING if self.is_finding(code) else NOT_FINDING

    def lexical_match(self, text, code, mode="exact"):
        want = " ".join((text or "").lower().split())
        for term in self.terms(code):
            got = " ".join((term or "").lower().split())
            if got == want:
                return True
            if mode == "contained" and got:
                a, b = set(want.split()), set(got.split())
                if a and b and (a <= b or b <= a):
                    return True
        return False

    def search(self, term, rows=5):  return _ols_search(term, rows)


_SELECTED = None


def select(manifest: dict | None = None, prefer: str | None = None, quiet: bool = False):
    """The run's vocabulary. Local release when present, OLS4 otherwise.

    `prefer` ("local-rf2" | "ols4") overrides the default, so the A/B between
    backends is a flag rather than an edit. Memoised per process.
    """
    global _SELECTED
    if _SELECTED is not None and prefer is None:
        return _SELECTED

    db = None
    if manifest:
        db = manifest.get("vocabulary", {}).get("snomed_db")
    if db is None:
        from ladder.registry import default_db
        db = default_db()

    backend = None
    if prefer != "ols4":
        try:
            from ladder.registry import Registry
            backend = Registry(db)
        except FileNotFoundError:
            if prefer == "local-rf2":
                raise

    if backend is None:
        backend = Ols4Vocabulary()
        if not quiet:
            _warnings.warn(
                "vocabulary backend = OLS4 (active international SNOMED only). "
                "Measured on CADEC gold, this reports 23.9% of the answer key as "
                "nonexistent codes — 100% of drug mentions, which are AMT. "
                "Build the local index for a comparable rung 1 rejection rate:\n"
                "  python -m ladder.registry --build --release <SnomedCT_Release_dir>",
                stacklevel=2,
            )
            print(f"[vocab] backend=ols4 (lossy) — see {__name__}.__doc__", file=_sys.stderr)

    missing = conforms(backend)
    if missing:
        raise TypeError(f"{backend.name} does not satisfy the Vocabulary contract: {missing}")
    if prefer is None:
        _SELECTED = backend
    return backend


# ---------------------------------------------------------------------------
# THE PUBLIC SURFACE — delegates to the selected backend.
# Stable signatures: ladder_ab.py, the CI smoke test and anything else that
# already imports these keep working, and now get the non-lossy answer when a
# local release is built.
# ---------------------------------------------------------------------------


def exists(code: str) -> bool:
    return select(quiet=True).exists(code)


def is_finding(code: str) -> bool:
    return select(quiet=True).finding_status(code) == FINDING


def label(code: str) -> str | None:
    return select(quiet=True).preferred(code)


def preferred(code: str) -> str | None:
    return select(quiet=True).preferred(code)


def search(term: str, rows: int = 5) -> list[dict]:
    return select(quiet=True).search(term, rows)


# The two checks that need NO vocabulary live with the record they check, and
# are re-exported here so `vocab` stays the single import for rung 1.
#
# Both replace earlier local versions, on measurement. Over CADEC's 9,111 gold
# mentions the exact-string span check false-rejected 725 (8.0%) — 1,066 of them
# are discontinuous, and a single (start,end) pair cannot express that — against
# 4 (0.04%) for the token-bag comparison in Record.valid(). And the earlier
# negation check rejected 427 gold-correct mentions, because CADEC annotates a
# mention regardless of polarity; it is now a flag, not a rejection.
from ladder.negation import is_negated as _is_negated  # noqa: E402
from ladder.schema import Record as _Record  # noqa: E402


def grounded_record(rec, source: str) -> bool:
    """Span grounding for a full Record — handles discontinuous spans."""
    return rec.valid(source)[0]


# ============================================================================
# MedDRA — one implementation, in ladder/registry.py.
#
# It was written twice, once here and once there, with the same leakage
# analysis reached independently. `MeddraTable` is the surviving one because it
# also carries `leakage()`, which turns that analysis into a number: measured on
# the CADEC-derived list, 666 codes, all 666 present in the gold annotations and
# none absent. `MedDRA` stays as an alias so existing imports keep working, and
# `mode` keeps the "reference" / "answer_space" distinction this file
# introduced — which is the sharper half of the argument.
# ============================================================================
from ladder.registry import MeddraTable  # noqa: E402

MedDRA = MeddraTable

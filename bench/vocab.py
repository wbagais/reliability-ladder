"""
vocab.py — the vocabulary resource.

Two consumers, deliberately separated:

  SEARCH  — used by rung 0 in option B. The model calls this before answering.
  CHECKS  — used by rung 1. Deterministic, no model, never calls search.

Backed by EBI OLS4: free, no API key, no licence gate.
Every response is disk-cached, so a re-run costs nothing and the ladder's
token/latency numbers are not polluted by repeated network calls.
"""
from __future__ import annotations
import json, os, re, time, urllib.parse, urllib.request
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
        except Exception as e:
            if attempt == 2:
                raise
            time.sleep(1.5 * (attempt + 1))
    return {}


def _iri(code: str) -> str:
    """OLS4 wants the IRI double-URL-encoded."""
    raw = f"http://snomed.info/id/{code}"
    return urllib.parse.quote(urllib.parse.quote(raw, safe=""), safe="")


# ------------------------------------------------------- SEARCH (rung 0, B)
def search(term: str, rows: int = 5) -> list[dict]:
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
def exists(code: str) -> bool:
    """Check 4. Binary. A hallucinated code fails outright."""
    if not re.fullmatch(r"\d{6,18}", str(code or "")):
        return False
    d = _get(f"{OLS}/search?q={code}&ontology=snomed&rows=1", f"exists_{code}")
    docs = d.get("response", {}).get("docs", [])
    return any(x.get("obo_id") == f"SNOMED:{code}" for x in docs)


def label(code: str) -> str | None:
    d = _get(f"{OLS}/search?q={code}&ontology=snomed&rows=1", f"exists_{code}")
    for x in d.get("response", {}).get("docs", []):
        if x.get("obo_id") == f"SNOMED:{code}":
            return x.get("label")
    return None


def is_finding(code: str) -> bool:
    """Check 5. Is it a descendant of |Clinical finding|? Catches right-code-wrong-slot."""
    if not exists(code):
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
    lab = label(code)
    if not lab:
        return 0.0
    a, b = _toks(span_text), _toks(lab)
    return 0.0 if not a or not b else len(a & b) / len(a | b)


# ------------------------------------------- CHECKS that need no vocabulary
NEG_CUES = ["no", "not", "never", "without", "denies", "denied", "free of",
            "negative for", "ruled out", "didn't", "did not", "don't", "does not",
            "nor", "none"]


def negated(source: str, span: tuple[int, int], window: int = 45) -> bool:
    """Check 3. 'so far no gastric problems' — costs nothing, needs no vocabulary."""
    s, e = span
    left = (source[max(0, s - window):s]).lower()
    if re.search(r"[.;!?]", left):                      # cue must be in the same clause
        left = re.split(r"[.;!?]", left)[-1]
    return any(re.search(rf"\b{re.escape(c)}\b", left) for c in NEG_CUES)


def grounded(source: str, span: tuple[int, int], span_text: str) -> bool:
    """Check 2. Pure string comparison. The cheapest check on the ladder."""
    try:
        s, e = span
    except (TypeError, ValueError):
        return False
    if not (isinstance(s, int) and isinstance(e, int) and 0 <= s < e <= len(source)):
        return False
    return source[s:e] == span_text


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
# MedDRA — local resource, loaded from a CSV of (code, term)
# ============================================================================
import csv as _csv

class MedDRA:
    """
    A local MedDRA list.

    LEAKAGE WARNING. If this CSV was derived from CADEC gold, it is the answer
    key. Using it as an existence check would accept exactly the right codes and
    reject everything else, and the rejection rate would mean nothing.

    So the mode is an explicit, manifest-recorded choice:

      mode="answer_space"  the task IS closed-set assignment over this list.
                           Legitimate, easier, and it must be declared in the
                           method section. Search and existence both use it.

      mode="reference"     the list is used ONLY to cross-check a code the model
                           produced by other means. Never used for search, never
                           used to reject. Keeps the task open-vocabulary.
    """
    def __init__(self, path="data/meddra_codes.csv", mode="reference"):
        assert mode in ("answer_space", "reference"), mode
        self.mode = mode
        self.by_code, self.by_term = {}, {}
        with open(path, newline="", encoding="utf-8") as f:
            for r in _csv.DictReader(f):
                c, t = r["meddra_code"].strip(), r["meddra_term"].strip()
                self.by_code[c] = t
                self.by_term[t.lower()] = c

    def exists(self, code) -> bool:
        return str(code) in self.by_code

    def term(self, code):
        return self.by_code.get(str(code))

    def search(self, text, k=5):
        """Only meaningful in answer_space mode — closed-set retrieval."""
        if self.mode != "answer_space":
            raise RuntimeError("search() needs mode='answer_space'; see the leakage note")
        q = _toks(text)
        if not q:
            return []
        scored = []
        for term, code in self.by_term.items():
            t = _toks(term)
            if not t:
                continue
            j = len(q & t) / len(q | t)
            if j > 0:
                scored.append((j, code, self.by_term and term))
        scored.sort(reverse=True)
        return [{"code": c, "label": self.by_code[c], "score": round(j, 3)}
                for j, c, _ in scored[:k]]

    def agrees_with_sct(self, meddra_code, sct_code) -> bool | None:
        """
        Cross-vocabulary agreement, reference mode's real job.
        Compares the two preferred labels lexically — weak, but it is a signal
        that costs nothing and needs no mapping table.
        """
        m, s = self.term(meddra_code), label(sct_code)
        if not m or not s:
            return None
        a, b = _toks(m), _toks(s)
        return bool(a & b)

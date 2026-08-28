"""The 139 XBRL tags as a ladder vocabulary.

Implements `schemas.vocabulary.Vocabulary`, the same Protocol `Registry` and the
OLS4 backend implement, so `tests/test_contracts.py` covers it unchanged and no
rung branches on which vocabulary is loaded.

WHAT IS DIFFERENT, AND WHY IT MATTERS TO THE EXPERIMENT

Rung 1's three free checks were built for SNOMED. Here:

    exists()        membership in a set of 139 names. Still decidable, still
                    free — but a model that can SEE all 139 in its prompt can
                    barely fabricate one, so `code_unknown` should approach
                    zero. On CADEC it was 155 of 169.

    is_active()     vacuously true. XBRL types are versioned by taxonomy year,
                    not retired individually, and FiNER-139 pins one snapshot.
                    There is no retirement to check.

    is_finding()    vacuously true. There is no semantic-type hierarchy: all 139
                    are US-GAAP numeric facts. `wrong_semantic_type` cannot fire.

So two of rung 1's three checks are constants here and the third is nearly one.
**That is the finding, not a defect in this file.** The deterministic spine's
value on CADEC came from a vocabulary large enough to be fabricated against;
remove the knowledge gap and the free checks stop earning their place. Saying so
plainly is better than implementing hierarchy that does not exist so the numbers
look comparable.

`lossy` is False: unlike OLS4 against SNOMED, this backend sees every tag the
corpus can contain, because the corpus was built from exactly this set.
"""
from __future__ import annotations

import os
import re
from functools import lru_cache

# `is_finding` returns one of these three, matching schemas/vocabulary.py
FINDING, NOT_FINDING, UNKNOWN = "finding", "not_finding", "unknown"

_CAMEL = re.compile(r"(?<!^)(?=[A-Z])")
_PUNCT = re.compile(r"[^a-z0-9]+")


def normalise_term(s: str) -> str:
    """Lowercase, split camel case, squash punctuation.

    `DebtInstrumentFaceAmount` -> `debt instrument face amount`. The tag names
    ARE the labels here — there is no separate description table — so this is
    the only place a human-readable form comes from.
    """
    s = _CAMEL.sub(" ", s or "")
    return " ".join(_PUNCT.sub(" ", s.lower()).split())


class FinerVocabulary:
    """The tag set, in memory. 139 strings, not a database."""

    #: schemas.vocabulary.Vocabulary
    name = "finer-tags"
    lossy = False

    def __init__(self, tags: list[str]):
        if not tags:
            raise ValueError(
                "FinerVocabulary built with no tags. An empty vocabulary makes "
                "exists() false for everything and rung 1 rejects the whole run "
                "— which would look like a model failure and is not one."
            )
        self._tags = sorted(set(tags))
        self._norm = {normalise_term(t): t for t in self._tags}
        # token -> tags, for search(). Built once; 139 entries is nothing.
        self._index: dict[str, list[str]] = {}
        for t in self._tags:
            for tok in normalise_term(t).split():
                self._index.setdefault(tok, []).append(t)

    # -- the contract ------------------------------------------------------
    @staticmethod
    def _strip_ns(code: str | None) -> str:
        """`us-gaap:NotesPayable` -> `NotesPayable`.

        gpt-oss:20b emits the taxonomy namespace; FiNER's labels do not carry
        it. It is a namespace, not part of the name, and the concept is the same
        either way — so this is a format normalisation, not a leniency. Leaving
        it in would fail every code on punctuation and measure JSON conventions
        rather than the ladder.
        """
        c = str(code or "")
        return c.split(":", 1)[1] if ":" in c else c

    def exists(self, code: str | None) -> bool:
        return bool(code) and self._strip_ns(code) in set(self._tags)

    def is_active(self, code: str | None) -> bool:
        """Vacuously true for anything that exists.

        XBRL types are versioned by taxonomy year rather than retired
        individually, and this dataset pins one snapshot. There is nothing to
        check, and inventing a check would put a constant into a column that
        reads as a measurement.
        """
        return self.exists(code)

    def is_finding(self, code: str | None) -> bool:
        """Also vacuously true — all 139 are US-GAAP numeric facts."""
        return self.exists(code)

    def finding_status(self, code: str | None) -> str:
        return FINDING if self.exists(code) else UNKNOWN

    def terms(self, code: str | None) -> list[str]:
        """A tag has exactly one term: itself, and its readable form.

        SNOMED concepts carry many synonyms, which is what makes rung 1's
        lexical_match a real check there. Here it is close to a tautology, and
        the article should say so rather than reporting the two rates side by
        side as though they measured the same thing.
        """
        if not self.exists(code):
            return []
        return [str(code), normalise_term(str(code))]

    def preferred(self, code: str | None) -> str | None:
        return normalise_term(str(code)) if self.exists(code) else None

    def label(self, code: str | None) -> str | None:
        return self.preferred(code)

    def lexical_match(self, text: str, code: str | None, mode: str = "exact") -> bool:
        """Does the quoted text match a term for this tag?

        On CADEC this asks whether a patient's words match a SNOMED synonym, and
        the answer is usually no — 72% of test records landed in BAND for
        exactly this reason. Here the tagged token is a NUMBER ('47.6') and the
        tag is a concept name, so lexical_match is essentially always False.

        That is not a bug and it is not tunable. It means BAND will dominate
        here too, for a completely different reason, and a rejection rate
        compared across the two corpora without that caveat is meaningless.
        """
        if not self.exists(code):
            return False
        want = normalise_term(text)
        if not want:
            return False
        for term in self.terms(code):
            got = normalise_term(term)
            if got == want:
                return True
            if mode == "contained" and got:
                a, b = set(want.split()), set(got.split())
                if a and b and (a <= b or b <= a):
                    return True
        return False

    def search(self, term: str, rows: int = 5) -> list[dict]:
        """Token-overlap ranking over 139 names.

        NOT exact-term equality, unlike Registry.search — and the difference is
        declared rather than incidental. Registry is exact because a fuzzy local
        index has no relevance ranking and would stop being comparable with the
        OLS4 backend it is measured against. There is no second backend here and
        nothing to stay comparable with, so ranking 139 candidates by overlap is
        both possible and honest.

        Consequence for the comparison: CADEC's exact-term retrieval returned
        nothing for 202 of 343 gold spans, a 59% ceiling on every rung that
        depends on lookup. There is no such ceiling here. Any retrieval
        difference between the two arms is partly this choice, not only the
        vocabulary size.
        """
        want = set(normalise_term(term).split())
        if not want:
            return []
        scored = []
        for tag in self._tags:
            got = set(normalise_term(tag).split())
            inter = want & got
            if inter:
                scored.append((len(inter) / len(want | got), tag))
        scored.sort(key=lambda x: (-x[0], x[1]))
        return [{"code": t, "label": normalise_term(t), "score": round(s, 3)}
                for s, t in scored[:rows]]

    def shortlist(self, text: str, k: int = 20,
                  findings_only: bool = True) -> list[dict]:
        """Rung 0's candidate menu. `search` under the name the rung expects.

        `findings_only` is accepted and ignored: all 139 tags are US-GAAP
        numeric facts, so the filter has nothing to filter. Accepting the
        argument rather than dropping it keeps the call site identical for both
        backends.

        Note what this means for the experiment. CADEC retrieves 20 candidates
        from 129,675 concepts, and dense retrieval beat lexical by 21 points
        there. Here the whole vocabulary is 139 names and all of them fit in the
        prompt, so retrieval has almost nothing to do. That is the fifth thing
        that weakens when the knowledge gap closes.
        """
        return self.search(text, rows=k)

    def codes_for_term(self, text: str) -> list[str]:
        t = self._norm.get(normalise_term(text))
        return [t] if t else []

    def replacements(self, code: str | None) -> list[str]:
        """No retirement, so no successors. Empty, never None.

        `score_run`'s `outdated` outcome exists because SNOMED retires concepts.
        It cannot fire here, and returning [] rather than raising lets the
        shared scorer run unchanged — the outcome simply never appears, which is
        the truth about this corpus.
        """
        return []

    def stats(self) -> dict[str, str]:
        return {"backend": self.name, "tags": str(len(self._tags)),
                "lossy": "false", "hierarchy": "none",
                "note": "is_active and is_finding are vacuously true"}

    def __len__(self) -> int:
        return len(self._tags)


@lru_cache(maxsize=4)
def load(root: str | os.PathLike = "data/finer/extracted",
         split: str = "test") -> FinerVocabulary:
    """Build the vocabulary FROM THE CORPUS, not from a hardcoded list.

    A hardcoded 139 names would be a second place the tag set is defined, and
    the two would drift. Reading it from the data means exists() cannot disagree
    with what the gold actually contains.
    """
    from ladder.corpus_finer import tag_names
    return FinerVocabulary(tag_names(root, split))


if __name__ == "__main__":
    v = load()
    print(f"{len(v)} tags · {v.name} · lossy={v.lossy}")
    print()
    for code in ("DebtInstrumentFaceAmount", "NotARealTag"):
        print(f"  {code:34} exists={v.exists(code)}  "
              f"status={v.finding_status(code)}")
    print()
    print("  preferred:", v.preferred("EffectiveIncomeTaxRateContinuingOperations"))
    print("  lexical_match('47.6', tag):",
          v.lexical_match("47.6", "EffectiveIncomeTaxRateContinuingOperations"))
    print("     ^ always False on numeric spans — see the docstring")
    print()
    print("  search('interest rate'):")
    for h in v.search("interest rate", 3):
        print(f"    {h['score']}  {h['code']}")

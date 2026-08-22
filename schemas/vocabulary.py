"""Contract 4 — the vocabulary resource.

v17 §4 calls this "the one extension CADEC needs": SNOMED and MedDRA are
**global resources**, injected once per run, not per-item `trusted_record`
fields. This is that contract.

Two backends implement it, and they are not equivalent — see `docs/decisions.md`
and `python -m ladder.vocab_crosscheck`:

    LOCAL   ladder.registry.Registry   a SNOMED CT RF2 release, indexed to SQLite.
                                       Needs a ~5 GB download and an affiliate
                                       licence. Sees retired concepts and
                                       extension modules.
    OLS4    ladder.vocab.Ols4Vocabulary EBI OLS4 over the network. Free, no key,
                                       nothing to download. Serves ACTIVE
                                       INTERNATIONAL SNOMED only.

Measured on CADEC's 8,666 coded gold mentions, an OLS4-backed `exists()` reports
**23.9%** of the answer key as codes that do not exist — 7.5% retired, 16.4% in
the AU extension module (which is 100% of drug mentions, because CADEC codes
drugs to AMT). The local index reports 5. That is a property of the source, not
a defect in either implementation, and no configuration of OLS4 closes it.

So the backend is selected explicitly, recorded in the manifest, and warned
about when it is the lossy one. A rung-1 rejection rate is not comparable across
backends and must never be reported without saying which one produced it.

Three questions are NOT part of this contract, because they need no vocabulary
at all and belong to whatever produced the record:

    span grounding   ladder.schema.Record.valid()
    negation         ladder.negation.is_negated()
    schema validity  ladder.schema.Record.valid()
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

#: `finding_status` is three-valued on purpose. A retired SNOMED concept has no
#: active is-a rows, so the hierarchy cannot place it — which is not the same as
#: placing it in the wrong branch. Rung 1 may reject only on NOT_FINDING.
FINDING = "finding"
NOT_FINDING = "not_finding"
UNKNOWN = "unknown"


class SearchUnsupported(RuntimeError):
    """Raised by a backend that cannot do open-vocabulary retrieval."""


@runtime_checkable
class Vocabulary(Protocol):
    """What rung 1 — and rung 0 in search mode — may ask of a vocabulary."""

    #: Short backend id, e.g. "local-rf2" or "ols4". Goes in the manifest.
    name: str
    #: The exact release this answered from. A result without one is not
    #: reproducible: SNOMED ships twice a year and codes are inactivated.
    release: str
    #: True when the backend cannot see retired concepts or extension modules.
    lossy: bool

    def exists(self, code: str | None) -> bool:
        """Is this a real concept? Includes retired ones where the backend can see them."""

    def is_active(self, code: str | None) -> bool: ...

    def finding_status(self, code: str | None) -> str:
        """FINDING | NOT_FINDING | UNKNOWN. Only NOT_FINDING may cause a rejection."""

    def is_finding(self, code: str | None) -> bool: ...

    def terms(self, code: str | None) -> list[str]:
        """Every term the vocabulary uses for this concept."""

    def preferred(self, code: str | None) -> str | None: ...

    def lexical_match(self, text: str, code: str | None, mode: str = "exact") -> bool:
        """Does the quoted span use words the vocabulary uses for this concept?

        The ACCEPT/BAND divider, never a rejection: patient language is
        colloquial, so a miss means "unverifiable", not "wrong".
        """

    def search(self, term: str, rows: int = 5) -> list[dict[str, Any]]:
        """Candidate concepts for a surface term — rung 0 mode B only.

        May raise SearchUnsupported. Rung 1 must never call this: a check that
        looks up the right answer is not a check.
        """


REQUIRED = (
    "exists",
    "is_active",
    "finding_status",
    "is_finding",
    "terms",
    "preferred",
    "lexical_match",
)


def conforms(obj: object) -> list[str]:
    """Missing method names — [] when `obj` satisfies the contract."""
    return [m for m in REQUIRED if not callable(getattr(obj, m, None))]

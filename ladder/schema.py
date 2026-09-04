"""The A/B contract: one mention record, and the zones it can occupy.

FROZEN after the step-3 fixture gate. A silent change here is the one thing
that costs an hour nobody has — if it must change, everyone agrees
out loud first and the change is appended, never reordered.

Unit of evaluation is ONE MENTION, not one document. A document yields many
records; the ladder routes each independently.

Why a mention and not the plan's {drug_text, reaction_text} pair
----------------------------------------------------------------
The v16 plan's §1 example record pairs a drug span with a reaction span in one
object. That contradicts the plan's own safety constraint 3 ("drug and reaction
mentions extracted independently; never emits 'drug X causes Y'"), and CADEC
annotates them independently too. Pairing them in the record shape would make
the output a causal claim by construction. So: one record = one mention, with
an `entity_type` of "reaction" or "drug". See docs/decisions.md 2026-08-22.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any

# --- vocabulary sentinels ---------------------------------------------------

#: Gold label meaning "no code in the vocabulary is correct for this mention".
#: CADEC writes this literal in the sct/ and meddra/ annotation files. It is the
#: measurable target for rung 5's abstention.
CONCEPT_LESS = "CONCEPT_LESS"

#: SNOMED CT |Clinical finding (finding)| — the semantic-type gate in rung 1.
CLINICAL_FINDING = "404684003"

# --- zones ------------------------------------------------------------------
# A record's zone is where the ladder has routed it so far. Rungs mutate zone,
# reason and provenance; nothing else.

ZONE_NEW = "NEW"  # emitted by rung 0, nothing has looked at it
ZONE_ACCEPT = "ACCEPT"  # rung 1: passed validation AND the vocabulary knows these words
ZONE_BAND = "BAND"  # rung 1: passed validation, but unverifiable by code alone
ZONE_REJECT = "REJECT"  # rung 1: provably wrong (see REASONS)
ZONE_ABSTAIN = "ABSTAIN"  # rung 5: system declines to resolve
ZONE_ESCALATE = "ESCALATE"  # queued for a person
ZONE_VERIFIED = "VERIFIED"  # settled — by the ladder or by a person
ZONE_RESOLVED = "RESOLVED"  # rung 6: a person settled it

ZONES = (
    ZONE_NEW,
    ZONE_ACCEPT,
    ZONE_BAND,
    ZONE_REJECT,
    ZONE_ABSTAIN,
    ZONE_ESCALATE,
    ZONE_VERIFIED,
    ZONE_RESOLVED,
)

#: Zones a record may still leave. Everything else is terminal for a given run.
OPEN_ZONES = (ZONE_NEW, ZONE_ACCEPT, ZONE_BAND, ZONE_REJECT)

# --- rejection reasons ------------------------------------------------------
# Rung 1's whole value is in the breakdown, not the rate. Append new reasons at
# the end; never renumber or rename an existing one.

R_SCHEMA_INVALID = "schema_invalid"  # not a well-formed record at all
R_SPAN_UNGROUNDED = "span_ungrounded"  # quoted text is not at those offsets
R_SPAN_OUT_OF_RANGE = "span_out_of_range"  # offsets fall outside the document
R_NEGATED = "negated"  # the mention is explicitly denied in the source
R_CODE_UNKNOWN = "code_unknown"  # code is in no release of the vocabulary
R_CODE_INACTIVE = "code_inactive"  # code was real once; retired since. NOT a reject by default
R_WRONG_SEMANTIC_TYPE = "wrong_semantic_type"  # real code, wrong branch of the hierarchy
R_LOW_CONFIDENCE = "low_confidence"  # rung 5 only. RETIRED 2026-09-03 with the
#   confidence threshold (plan item 17d); kept because schemas are append-only
#   and old ledgers carry it. Nothing emits it.
R_UNRESOLVED = "unresolved"  # rung 5 only: still in BAND when the ladder ran out
# Appended 2026-08-22 with the MedDRA check. See registry.MeddraTable for why
# this is not a rejection reason by default.
R_MEDDRA_UNKNOWN = "meddra_code_unknown"  # code is not in the MedDRA table
# Appended 2026-08-23 with rung 0's sct_label. The model names the concept it
# thinks it coded; if the vocabulary uses none of those words for that code,
# the code and the label cannot both be right. A FLAG first, not a rejection —
# "rectal bleeding" against "Rectal hemorrhage" is the same concept in
# different words, and its false-rejection floor has not been measured yet.
R_LABEL_MISMATCH = "label_mismatch"  # model's own label does not match its code
# Appended 2026-08-24 with the association refset. DISTINCT from
# R_CODE_INACTIVE: inactive says the concept is retired, outdated says SNOMED
# has since named a CURRENT equivalent for it. A model that emits a retired
# code with a successor named a real concept and lacked the newer release,
# which is not the failure that inventing a number is — ladder/score.py scores
# it as its own outcome. A FLAG, like meddra_check and label_check; the reason
# exists so it is nameable and countable, not so it can reject.
R_CODE_OUTDATED = "code_outdated"  # retired, and SNOMED records what replaced it

#: The span's type contradicts the code's. Added for rung 7 (2026-09-02), which
#: exists because FiNER's lexical check is a STRUCTURAL zero — a numeral and an
#: English phrase share no token by construction, so ACCEPT was 0 of 704 and
#: rungs 2 and 5 went quiet with it. Both sides still carry a TYPE. Measured on
#: gold before the rung was written: 87.7% coverage at a 1.22% false-rejection
#: rate, against rung 1's 0.13% on CADEC. Append-only, per the note above.
R_TYPE_MISMATCH = "type_mismatch"

# R_JUDGE_FAIL: rung 5 only, and only under `abstain_on_judge_fail`. Appended
# 2026-08-30 when rung 4 was finally wired to a reader. It is NOT a REJECT
# reason: a second model disagreeing is evidence to withhold on, never proof
# the answer is wrong, and rung 1's REJECT_REASONS are the ones that carry a
# proof. Distinct from R_UNRESOLVED so the ledger can say which layer withdrew
# the answer — the whole point of the arm is to count what the judge adds over
# the free check, and one shared reason would make that uncountable.
R_JUDGE_FAIL = "judge_fail"

# R_UNREVIEWABLE: rung 6 only. Appended 2026-09-03 (plan item 17c). A queued
# record whose span is unlocated ((-1, -1)) or whose span key another queued
# record shares cannot be matched to a resolution by a span-keyed desk. It
# stayed ESCALATE under R_QUEUED at zero minutes, indistinguishable from a
# record the reviewer skipped; now it carries its own disposition and is
# counted in the aggregate in both modes.
R_UNREVIEWABLE = "unreviewable"

REJECT_REASONS = (
    R_SCHEMA_INVALID,
    R_SPAN_UNGROUNDED,
    R_SPAN_OUT_OF_RANGE,
    R_NEGATED,
    R_CODE_UNKNOWN,
    R_CODE_INACTIVE,
    R_WRONG_SEMANTIC_TYPE,
    R_MEDDRA_UNKNOWN,
    R_LABEL_MISMATCH,
    R_CODE_OUTDATED,
    R_TYPE_MISMATCH,
)

#: What rung 1 concluded about a record, independent of whether it acted on it.
VERDICTS = (ZONE_ACCEPT, ZONE_BAND, ZONE_REJECT)

# --- entity types -----------------------------------------------------------
# CADEC labels five types (ADR / Symptom / Disease / Finding / Drug). ADR is a
# causal attribution made by the annotator; asking a model to reproduce it would
# be asking for exactly the causal claim safety constraint 3 forbids. So the
# four clinical types collapse to "reaction" and only the drug/non-drug
# distinction is asked for or scored. See docs/decisions.md 2026-08-22.

REACTION = "reaction"
DRUG = "drug"
ENTITY_TYPES = (REACTION, DRUG)

#: CADEC entity label -> our entity type.
CADEC_TYPE_MAP = {
    "ADR": REACTION,
    "Symptom": REACTION,
    "Disease": REACTION,
    "Finding": REACTION,
    "Drug": DRUG,
}


Span = tuple[int, int]


@dataclass
class Record:
    """One mention, as it travels down the ladder.

    `spans` is a list because CADEC mentions are frequently discontinuous
    ("hair ... breakage", 11.7% of reaction mentions). A single-segment mention
    is just a list of length one.
    """

    doc_id: str
    entity_type: str  # REACTION | DRUG
    text: str  # the span exactly as written in the source
    spans: list[Span]  # character offsets into the source document
    sct: str | None = None  # SNOMED code, CONCEPT_LESS, or None (= no answer)
    #: What the model SAID that code means. Appended 2026-08-23. A bare code is
    #: an unverifiable claim; a code plus a label is checkable against the
    #: vocabulary with no extra model call. Never scored — the answer is `sct`.
    sct_label: str | None = None
    meddra: str | None = None  # secondary, never the primary scored target
    confidence: float | None = None

    zone: str = ZONE_NEW
    reason: str | None = None
    record_id: str = ""  # stable within a run: f"{doc_id}#{index}"
    provenance: list[dict[str, Any]] = field(default_factory=list)
    checks: dict[str, Any] = field(default_factory=dict)  # audit trail, never scored

    # -- span grounding ------------------------------------------------------

    def quoted(self, source: str) -> str:
        """The text actually sitting at `spans` in `source`."""
        return " ".join(source[a:b] for a, b in self.spans)

    def valid(self, source: str) -> tuple[bool, str | None]:
        """Rung 1 check 1+2: schema shape and span grounding.

        Pure string work — no vocabulary, no network. This fires before any
        lookup because it is the cheapest check on the ladder.

        Segment ORDER is not required to match. 45 of CADEC's own 9,109 gold
        mentions quote their discontinuous segments in reading order rather than
        offset order ("swelling feet" for spans [feet][swelling]); a
        concatenation-order check would call the gold standard ungrounded.
        """
        if self.entity_type not in ENTITY_TYPES:
            return False, R_SCHEMA_INVALID
        if not self.spans or not isinstance(self.text, str) or not self.text.strip():
            return False, R_SCHEMA_INVALID
        for a, b in self.spans:
            if not isinstance(a, int) or not isinstance(b, int) or a < 0 or b <= a:
                return False, R_SCHEMA_INVALID
            if b > len(source):
                return False, R_SPAN_OUT_OF_RANGE
        if _bag(self.quoted(source)) != _bag(self.text):
            return False, R_SPAN_UNGROUNDED
        return True, None

    # -- ledger/JSONL --------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["spans"] = [list(s) for s in self.spans]
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Record":
        d = dict(d)
        d["spans"] = [tuple(s) for s in d.get("spans", [])]
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in d.items() if k in known})

    def copy(self, **changes: Any) -> "Record":
        d = self.to_dict()
        d.update(changes)
        return Record.from_dict(d)

    def mark(self, rung: int, zone: str, reason: str | None = None, **extra: Any) -> None:
        """Record a zone transition. The only mutation a rung may perform."""
        if zone not in ZONES:
            raise ValueError(f"unknown zone {zone!r}")
        self.provenance.append(
            {"rung": rung, "from": self.zone, "to": zone, "reason": reason, **extra}
        )
        self.zone = zone
        self.reason = reason


def _bag(s: str) -> tuple[str, ...]:
    """Whitespace-insensitive, order-insensitive, case-insensitive token bag."""
    return tuple(sorted(s.lower().split()))


def dumps(records: list[Record]) -> str:
    return "\n".join(json.dumps(r.to_dict(), ensure_ascii=False) for r in records)


def loads(text: str) -> list[Record]:
    return [Record.from_dict(json.loads(line)) for line in text.splitlines() if line.strip()]

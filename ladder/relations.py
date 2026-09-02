"""The relation registry — what a free check can ask about a span and a code.

WHY THIS EXISTS

`scripts/preflight_rungs.py` tested ONE relation, lexical overlap, and when it
found no signal it said DON'T. That was measured to be too narrow on
2026-09-02: FiNER's lexical check is a structural zero — a numeral shares no
token with an English phrase, by construction, on every possible run — while a
TYPE COMPATIBILITY check on the same corpus reached 87.7% coverage at a 1.22%
false-rejection rate on gold.

The signal was there. The tool could not see it, because it only knew one way
to look.

So a relation becomes a first-class thing rather than a hardcoded check, and
the preflight reports which ones have signal on THIS data. That changes the
output's grammar from a diagnosis to a recommendation:

    before   rung 1 · ACCEPT lane · DON'T · the lane cannot fire here
    after    lexical overlap: no signal — the span is a numeral and the code is
             a phrase. Type compatibility: 87.7% coverage, 1.2% false
             rejection. Build that one instead.

Same measurement. Nobody's work is being called broken; they are being handed
the check that works on their data.

WHAT A RELATION IS

A pure function of (span text, its context, the code, the vocabulary) returning
one of three things, and the third is the one that matters:

    AGREE     the span and the code are consistent on this relation
    CONTRADICT the relation is VIOLATED — a proof of wrongness, which is the
               only thing rung 1 can ever establish
    SILENT    this relation cannot speak about this record

SILENT is not a pass. Collapsing it into AGREE is how a rate gets computed over
an unnamed set, which is the defect this whole project documents.

HOW A RELATION IS JUDGED, and the order is not negotiable

    1. FALSE-REJECTION RATE ON GOLD, first. Every CONTRADICT on a gold record
       is false by construction, because gold is right by definition. A check
       that rejects a perfect answer set is worse than no check. CADEC's own
       went from 9.3% to 0.13% by being measured this way.
    2. COVERAGE. A relation that speaks about 3% of records is not worth
       wiring in however precise it is.
    3. DISCRIMINATION. Does knowing the relation narrow the answer space?

THE WARNING THAT COST US A DAY

A relation validated only on GOLD can be far worse on MODEL OUTPUT. Measured
2026-09-02: the type relation scored 1.22% false rejections on gold and 35.71%
on model output, because gold spans sit exactly where the annotator put them
and model spans drift, so the context window is read wrongly and the relation
contradicts confidently on a misreading.

`measure()` therefore takes gold OR model records and the report says which.
A relation is not validated until it has been measured on both.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable

AGREE, CONTRADICT, SILENT = "agree", "contradict", "silent"

_PUNCT = re.compile(r"[^a-z0-9 ]")
_MONTHS = (r"january|february|march|april|may|june|july|august|september"
           r"|october|november|december")


def _tokens(s: str) -> set[str]:
    return set(_PUNCT.sub(" ", (s or "").lower()).split())


@dataclass
class Relation:
    """One deterministic thing a free check can ask.

    `applies` is separate from `judge` on purpose. A relation that cannot run
    on this vocabulary at all — because the vocabulary has no hierarchy, no
    types, no numeric ranges — must say so ONCE, rather than returning SILENT
    on every record and looking like a relation with poor coverage. Those are
    different states and reporting them the same way hides which one you are in.
    """

    name: str
    asks: str
    judge: Callable[..., str]
    applies: Callable[[Any], bool] = lambda vocab: True
    needs_context: bool = False
    note: str = ""


# ── the relations ───────────────────────────────────────────────────────

def _lexical(span: str, before: str, after: str, code: str, vocab) -> str:
    """Do the span's words appear among the code's own terms?

    The original and still the strongest where it applies: on CADEC the records
    it accepts are 80–89% correct across five model families. Its precondition
    is that both sides are drawn from the same language, which FiNER violates
    by construction and a gazetteer violates in a subtler way — see `unique`.
    """
    try:
        terms = vocab.terms(code) or []
    except Exception:
        return SILENT
    if not terms:
        return SILENT
    want = _tokens(span)
    if not want:
        return SILENT
    for t in terms:
        if want == _tokens(t):
            return AGREE
    # A lexical MISS is not a contradiction. Patients write "bit drowsy" for
    # |Drowsy| and the words genuinely differ; treating that as a proof of
    # wrongness would reject a large share of correct answers. This relation
    # can only ever endorse, which is why the lane it feeds is ACCEPT/BAND and
    # not ACCEPT/REJECT.
    return SILENT


def _exists(span: str, before: str, after: str, code: str, vocab) -> str:
    """Is the code in the vocabulary at all?

    The cheapest possible relation, and it went dead here for an instructive
    reason: once rung 0 picks from a retrieved menu of real codes it can no
    longer invent one, so `code_unknown` fires 0 times in 248. A relation can
    be perfectly sound and have nothing to do.
    """
    if not code:
        return SILENT
    try:
        return AGREE if vocab.exists(code) else CONTRADICT
    except Exception:
        return SILENT


def _semantic(span: str, before: str, after: str, code: str, vocab,
              entity_type: str | None = None) -> str:
    """Is the code the right KIND of thing?

    Needs a vocabulary with a hierarchy. SNOMED has one; a gazetteer and a flat
    tag set do not, and `applies` says so once rather than returning SILENT
    2,399 times.
    """
    # A DRUG is not a clinical finding and coding it to one would be wrong,
    # so this relation must not judge drug mentions. The first version did and
    # rejected 41 correctly-coded drugs on CADEC — 100% false, all of them
    # this bug.
    if entity_type and entity_type.lower() not in ("reaction", ""):
        return SILENT
    finding = getattr(vocab, "finding_status", None)
    if finding is None:
        return SILENT
    try:
        status = finding(code)
    except Exception:
        return SILENT
    if status is None:
        return SILENT
    return CONTRADICT if str(status).upper().endswith("NOT_FINDING") else AGREE


def _type_compat(span: str, before: str, after: str, code: str, vocab) -> str:
    """Does the span's SHAPE agree with the type the code's name claims?

    Built 2026-09-02 for the corpus where lexical overlap is a structural zero.
    Both sides carry a type and neither type is a word the other contains:
    tags say ...Percentage, ...Amount, ...Shares; spans sit next to %, $,
    "million", "shares".

    MEASURED, and the two numbers must be read together:
        on gold          87.7% coverage, 1.22% false rejection
        on model output  35.71% false rejection

    The gap is the finding. Gold spans sit where the annotator put them, so the
    context window is always right; model spans drift and the rules then read
    the wrong window. Kept in the registry BECAUSE of that, as the worked
    example of a relation that must be validated on both.
    """
    coder = getattr(vocab, "code_type", None)
    if coder is None or not code:
        return SILENT
    try:
        ct = coder(code)
    except Exception:
        return SILENT
    if ct is None:
        return SILENT
    st = span_shape(span, before, after)
    if st is None:
        return SILENT
    return AGREE if st == ct else CONTRADICT


def span_shape(text: str, before: str, after: str) -> str | None:
    """The span's type, from its own form and the characters either side.

    Conservative by design: returns None rather than guessing. Each rule below
    was added because a measured disagreement demanded it — the first draft
    contradicted 8.54% of a perfect answer set and three rules took it to 1.22%.
    """
    t = (text or "").strip()
    a = (after or "")[:24].lower()
    if re.match(rf"^({_MONTHS})\b", t.lower()) or re.match(r"^(19|20)\d{2}$", t):
        return "date"
    if re.match(r"^\s*%", after or "") or a[:12].lstrip().startswith("percent"):
        return "percent"
    if re.search(r"\byears?\b|\bmonths?\b|\bdays?\b", a[:14]):
        return "duration"
    # A currency symbol immediately before outranks any quantity word after:
    # "$ 6.1 billion in share repurchases" is money, and "share" three tokens
    # later does not make it a count.
    if re.search(r"\$\s*$", (before or "")[-4:]):
        return "money"
    # "per share" is a UNIT, not a quantity of shares.
    if re.search(r"\bper\s+(share|unit)\b", a[:18]):
        return "money"
    if re.search(r"\bshares?\b|\bunits?\b|\bsecurities\b|\bemployees\b"
                 r"|\bsegments\b|\bstores\b|\bproperties\b", a[:22]):
        return "count"
    if re.search(r"\b(million|billion|thousand)\b", a[:16]):
        return "money"
    return None


def _unique(span: str, before: str, after: str, code: str, vocab) -> str:
    """Does a matching name IDENTIFY one concept, or merely match?

    Not a check on a record so much as a WARNING about the lexical relation,
    and it exists because of a miss. On GeoWebNews the ACCEPT lane fired at
    39.8% and scored WORSE than BAND on all three models — 0.206/0.134/0.214
    against 0.250/0.330/0.370 — because "London" matching an entry named
    "London" says nothing about which London. 1,117 of 2,399 gold mentions
    carry a name more than one entry holds.

    Reported per record so the share can be measured; the verdict that matters
    is the TAIL, not the share — CADEC and GeoWebNews share names at 43.5% and
    41.9%, and the worst case is 16 against 3,295.
    """
    lookup = getattr(vocab, "codes_for_term", None)
    if lookup is None or not code:
        return SILENT
    try:
        name = vocab.preferred(code)
        holders = set(lookup(name) or [])
    except Exception:
        return SILENT
    if not holders:
        return SILENT
    # NOT a contradiction. This relation says nothing about whether THIS record
    # is right — a name shared by 200 places is still the right name. It is a
    # property of the VOCABULARY that weakens the lexical relation, and
    # implementing it as a per-record contradiction made it reject 126 correct
    # records on gold. Reported through `ambiguity()` instead.
    return AGREE


REGISTRY: list[Relation] = [
    Relation("exists", "is the code in the vocabulary at all?", _exists,
             note="Cheapest. Went dead here once retrieval stopped the model "
                  "inventing codes: 0 fires in 248."),
    Relation("lexical", "do the span's words appear in the code's own terms?",
             _lexical,
             note="Can only ENDORSE, never contradict — a patient's phrasing "
                  "differing from a clinical term is not proof of wrongness."),
    Relation("semantic", "is the code the right KIND of thing?", _semantic,
             applies=lambda v: hasattr(v, "finding_status"),
             note="Needs a hierarchy. Vacuous on a flat vocabulary."),
    Relation("type", "does the span's shape agree with the code's type?",
             _type_compat, needs_context=True,
             applies=lambda v: hasattr(v, "code_type"),
             note="1.22% false rejection on gold, 35.71% on model output. The "
                  "gap is why a relation must be measured on both."),
    Relation("unique", "does a matching name identify one concept?", _unique,
             applies=lambda v: hasattr(v, "codes_for_term"),
             note="Qualifies `lexical` rather than standing alone. A lane built "
                  "on shared names endorses where it knows least."),
]


# ── measurement ─────────────────────────────────────────────────────────

@dataclass
class Result:
    name: str
    asks: str
    applicable: bool = True
    agree: int = 0
    contradict: int = 0
    silent: int = 0
    false_contradictions: int = 0   # contradictions of records known correct
    examples: list = field(default_factory=list)
    note: str = ""

    @property
    def spoke(self) -> int:
        return self.agree + self.contradict

    @property
    def coverage(self) -> float:
        n = self.spoke + self.silent
        return self.spoke / n if n else 0.0

    @property
    def false_rate(self) -> float:
        return self.false_contradictions / self.contradict if self.contradict else 0.0

    def verdict(self, min_coverage=0.10, max_false=0.02) -> str:
        """Relations come in TWO kinds and one scale cannot judge both.

        An ENDORSING relation can only say "this looks right" — lexical overlap
        is one, because a patient's phrasing differing from a clinical term is
        not proof of wrongness. It feeds an ACCEPT lane, and on CADEC that lane
        is 80-89% correct across five model families.

        A REJECTING relation can prove wrongness — a retired code, a numeral
        against a percentage tag. It feeds a REJECT lane.

        The first version of this scale called "endorses only" a failure and so
        reported that CADEC had no usable signal — the tool contradicting the
        study that produced it. The two kinds are now named apart.
        """
        if not self.applicable:
            return "n/a"
        if self.coverage < min_coverage:
            return "no signal"
        if self.contradict and self.false_rate > max_false:
            return "BROKEN"
        if self.contradict == 0:
            # A relation that agrees with EVERYTHING has no discriminating
            # power. It is the ACCEPT lane on a gazetteer — endorsing where it
            # knows least, which the geo arm measured as WORSE than not
            # endorsing at all. Call it endorsing only if it also stays silent
            # sometimes: that is the evidence it is choosing rather than nodding.
            if self.agree and self.silent:
                return "endorses"
            return "vacuous" if self.agree else "silent"
        return "rejects"
def measure(records, sources, vocab, *, is_correct=None,
            relations=None) -> list[Result]:
    """Run every relation over a record set. No model calls.

    `records` may be gold mentions or model output — the caller says which, and
    the difference is not cosmetic: the type relation scores 1.22% false
    rejections on one and 35.71% on the other.

    `is_correct(record)` marks a record known to be right. On gold it is
    `lambda _: True`, which makes every contradiction false BY CONSTRUCTION and
    is the cheapest validation available. On model output it needs gold to
    compare against.
    """
    rels = relations or REGISTRY
    out = []
    for rel in rels:
        r = Result(rel.name, rel.asks, note=rel.note)
        try:
            r.applicable = bool(rel.applies(vocab))
        except Exception:
            r.applicable = False
        if not r.applicable:
            out.append(r)
            continue

        for rec in records:
            code = _code_of(rec)
            span = getattr(rec, "text", "") or ""
            before = after = ""
            if rel.needs_context:
                before, after = _context(rec, sources)
            try:
                kw = {}
                if rel.name == "semantic":
                    kw["entity_type"] = getattr(rec, "entity_type", None)
                v = rel.judge(span, before, after, code, vocab, **kw)
            except Exception:
                v = SILENT
            if v == AGREE:
                r.agree += 1
            elif v == CONTRADICT:
                r.contradict += 1
                if is_correct is not None and is_correct(rec):
                    r.false_contradictions += 1
                    if len(r.examples) < 4:
                        r.examples.append((span, code))
            else:
                r.silent += 1
        out.append(r)
    return out


def _code_of(rec):
    code = getattr(rec, "sct", None)
    if not code:
        checks = getattr(rec, "checks", None) or {}
        withheld = checks.get("withheld") or {}
        code = withheld.get("sct")
    if isinstance(code, (list, tuple)):
        code = code[0] if code else None
    return code


def _context(rec, sources) -> tuple[str, str]:
    spans = getattr(rec, "spans", None)
    if not spans:
        return "", ""
    doc = sources.get(getattr(rec, "doc_id", ""), "") if sources else ""
    i, j = spans[0][0], spans[0][1]
    return doc[max(0, i - 40):i], doc[j:j + 40]


def report(results: list[Result], on: str = "gold") -> str:
    """The recommendation, not the diagnosis.

    Ordered so the usable relations come FIRST. A tool whose output opens with
    what is broken is telling somebody their work is bad; one that opens with
    what works on their data is handing them a check. Same measurements.
    """
    order = {"rejects": 0, "endorses": 1, "BROKEN": 2, "vacuous": 3,
             "no signal": 3, "silent": 4, "n/a": 5}
    rows = sorted(results, key=lambda r: order.get(r.verdict(), 9))
    w = max(len(r.name) for r in rows)
    lines = [f"  relations available on this data  ·  measured on {on.upper()}, no model calls", ""]
    for r in rows:
        v = r.verdict()
        if v == "n/a":
            lines.append(f"  {r.name:<{w}}  —        this vocabulary cannot support it")
            continue
        detail = f"speaks about {r.coverage:5.1%}"
        if r.contradict:
            detail += f" · {r.contradict} contradictions, {r.false_rate:.2%} false"
        lines.append(f"  {r.name:<{w}}  {v:<13} {detail}")
        if r.examples:
            s, c = r.examples[0]
            lines.append(f"  {'':<{w}}  e.g. it rejects {s!r} against {str(c)[:40]} — and that was RIGHT")
    # Every verdict prints its own track record. A check with two misses on
    # file and a check never tested against an outcome must not look the same,
    # and before this they did.
    try:
        from ladder.calibration import caveat
    except Exception:
        caveat = None
    if caveat:
        lines.append("")
        for r in rows:
            if r.verdict() in ("n/a", "no signal"):
                continue
            c = caveat(r.name)
            if c:
                lines.append(f"  {r.name:<{w}}  {c}")

    usable = [r for r in rows if r.verdict() in ("rejects", "endorses")]
    lines.append("")
    if usable:
        lines.append(f"  → build on {', '.join(r.name for r in usable)}.")
    else:
        lines.append("  → no relation on this list has usable signal here. That is a real")
        lines.append("    answer: the free check has nothing to work with, and a paid layer")
        lines.append("    built on top of it will inherit that.")
    if on == "gold":
        lines.append("  Measured on GOLD. A relation can be far worse on model output —")
        lines.append("  measured once at 1.22% on gold and 35.71% on the model's own spans.")
    return "\n".join(lines)

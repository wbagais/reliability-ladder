"""The step-3 gate: ten hand-made records through ledger, registry and rung 1,
with several deliberately broken. "This gate is worth being late for."

The point is not coverage — tests/ does coverage. The point is that both owners
watch the same ten records go through the harness and agree that a broken record
comes out rejected with the RIGHT reason, before anybody writes a rung. A ledger
that is wrong poisons every number above it, and by the time you notice, every
rung has to be re-run.

    python -m ladder.run gate

The ten records use one real archived post so the span offsets are real; nothing
here is synthetic text pretending to be a patient report.
"""

from __future__ import annotations

from pathlib import Path

from ladder.corpus import load_corpus
from ladder.ledger import Ledger
from ladder.manifest import load_manifest
from ladder.registry import Registry
from ladder.rungs import r1, r2
from ladder.schema import (
    CONCEPT_LESS,
    DRUG,
    R_CODE_UNKNOWN,
    R_SPAN_UNGROUNDED,
    R_WRONG_SEMANTIC_TYPE,
    REACTION,
    Record,
    ZONE_ABSTAIN,
    ZONE_ACCEPT,
    ZONE_BAND,
    ZONE_REJECT,
    ZONE_VERIFIED,
)

FIXTURE_DOC = "ARTHROTEC.1"

#: (label, record kwargs, expected zone, expected reason)
#: Offsets are into ARTHROTEC.1, which begins:
#:   "I feel a bit drowsy & have a little blurred vision, so far no gastric
#:    problems. I've been on Arthrotec 50 for over 10 years ... Due to my
#:    arthritis getting progressively worse ..."
CASES = [
    (
        # 3723001's terms include "Arthritis" verbatim — the vocabulary uses
        # exactly this word, so rung 1 has string evidence and may say ACCEPT.
        "clean reaction, vocabulary uses exactly these words",
        dict(entity_type=REACTION, text="arthritis", spans=[(179, 188)], sct="3723001"),
        ZONE_ACCEPT,
        None,
    ),
    (
        # Same concept family, one hedge word away. Under lexical_mode="exact"
        # this is BAND, and that is the point: "bit drowsy" is not a term, so
        # rung 1 has no evidence and declines to have an opinion. Under
        # "contained" it would ACCEPT — along with 19% of planted near-miss
        # codes. See docs/decisions.md.
        "one hedge word away from a term — BAND, not ACCEPT",
        dict(entity_type=REACTION, text="bit drowsy", spans=[(9, 19)], sct="271782001"),
        ZONE_BAND,
        None,
    ),
    (
        # The plan's own worked example, and it lands in BAND: 246636008's terms
        # are Foggy/Hazy/Misty/Cloudy vision — the vocabulary does not use the
        # word "blurred" for it at all. Correct code, no lexical evidence.
        "colloquial wording — correct code the vocabulary cannot corroborate",
        dict(
            entity_type=REACTION,
            text="little blurred vision",
            spans=[(29, 50)],
            sct="246636008",
        ),
        ZONE_BAND,
        None,
    ),
    (
        "drug mention — product code, NOT a clinical finding, must not be rejected",
        dict(entity_type=DRUG, text="Arthrotec", spans=[(93, 102)], sct="3384011000036100"),
        ZONE_ACCEPT,
        None,
    ),
    (
        "BROKEN: span shifted by two characters",
        dict(entity_type=REACTION, text="bit drowsy", spans=[(11, 21)], sct="271782001"),
        ZONE_REJECT,
        R_SPAN_UNGROUNDED,
    ),
    (
        "BROKEN: hallucinated code",
        dict(entity_type=REACTION, text="bit drowsy", spans=[(9, 19)], sct="999999999"),
        ZONE_REJECT,
        R_CODE_UNKNOWN,
    ),
    (
        "BROKEN: real code, wrong slot (a procedure where a finding belongs)",
        dict(entity_type=REACTION, text="bit drowsy", spans=[(9, 19)], sct="71388002"),
        ZONE_REJECT,
        R_WRONG_SEMANTIC_TYPE,
    ),
    (
        "BROKEN: offsets past the end of the document",
        dict(entity_type=REACTION, text="bit drowsy", spans=[(99000, 99010)], sct="271782001"),
        ZONE_REJECT,
        "span_out_of_range",
    ),
    (
        "negated mention — flagged, NOT rejected (CADEC codes it too)",
        dict(
            entity_type=REACTION,
            text="gastric problems",
            spans=[(62, 78)],
            sct="162076009",
        ),
        ZONE_BAND,
        None,
    ),
    (
        "retired code — |Knee pain| 30989003, real and correct, must survive",
        dict(entity_type=REACTION, text="agony", spans=[(260, 265)], sct="30989003"),
        ZONE_BAND,
        None,
    ),
    (
        "CONCEPT_LESS — a positive answer, not an error and not an abstention",
        dict(entity_type=REACTION, text="feel a bit weird", spans=[(437, 453)], sct=CONCEPT_LESS),
        ZONE_BAND,
        None,
    ),
]


def build(doc_id: str = FIXTURE_DOC) -> list[Record]:
    return [
        Record(doc_id=doc_id, record_id=f"{doc_id}#fix{i}", confidence=0.9, **kw)
        for i, (_, kw, _, _) in enumerate(CASES)
    ]


def run_gate(manifest_path: str = "manifest.json") -> int:
    man = load_manifest(manifest_path)
    docs = load_corpus(man["corpus"]["cadec_root"])
    if FIXTURE_DOC not in docs:
        print(f"FAIL: fixture document {FIXTURE_DOC} not in the corpus")
        return 1
    source = docs[FIXTURE_DOC].text
    registry = Registry(man["vocabulary"]["snomed_db"])
    out = Path(man["output"]["dir"]) / "gate.ledger.jsonl"
    ledger = Ledger(out, run_id="gate")

    records = build()
    cfg = {**man["rungs"].get("1", {}), "ledger": ledger, "registry": registry}
    r1.apply(records, {FIXTURE_DOC: source}, cfg)

    failures = 0
    print(f"fixture: {FIXTURE_DOC} ({len(source)} chars), vocabulary {registry.release}\n")
    for rec, (label, _, want_zone, want_reason) in zip(records, CASES):
        ok = rec.zone == want_zone and (want_reason is None or rec.reason == want_reason)
        failures += 0 if ok else 1
        flag = "  ok " if ok else "FAIL"
        got = f"{rec.zone}" + (f"/{rec.reason}" if rec.reason else "")
        want = f"{want_zone}" + (f"/{want_reason}" if want_reason else "")
        print(f"  {flag}  {got:34s} {'' if ok else '(want ' + want + ') '}{label}")
        if rec.checks.get("negated"):
            print(f"        flagged negated (cue {rec.checks.get('negation_cue')!r}) — audit only")

    # Rung 2 runs last: everything unresolved is withdrawn, nothing is deleted.
    cfg2 = {**man["rungs"].get("2", {}), "ledger": ledger}
    r2.apply(records, {FIXTURE_DOC: source}, cfg2)
    ledger.close()

    withheld = [r for r in records if r.zone == ZONE_ABSTAIN]
    verified = [r for r in records if r.zone == ZONE_VERIFIED]
    print(f"\nafter rung 2: {len(verified)} verified, {len(withheld)} abstained")
    for r in withheld:
        kept = r.checks.get("withheld", {}).get("sct")
        if kept is None and r.checks.get("withheld") is None:
            print(f"  FAIL  {r.record_id} abstained without preserving its answer")
            failures += 1
    if any(r.sct for r in withheld):
        print("  FAIL  an abstained record is still shipping an answer")
        failures += 1

    rows = Ledger.read(out)
    if len(rows) != 2 * len(CASES):
        print(f"  FAIL  ledger has {len(rows)} rows, expected {2 * len(CASES)}")
        failures += 1
    else:
        print(f"ledger: {len(rows)} rows, one per (rung, record) — {out}")

    print("\nGATE PASSED" if not failures else f"\nGATE FAILED ({failures})")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(run_gate())

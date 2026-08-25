"""Gold cleaning. Runs once, before any rung, and writes `data/exclusions.csv`.

    python -m ladder.clean --build

EXCLUDE, NEVER CORRECT
----------------------
Four of CADEC's 1,047 distinct gold codes are not SNOMED identifiers. It is
tempting to repair them — 21499005 is obviously 24199005 |Feeling agitated|,
81680008 is obviously 81680005 |Neck pain| — and that temptation is exactly the
thing to refuse. Editing an answer key so the system under test scores better
is how a benchmark stops being evidence. A mention that cannot be answered is
dropped from the denominator and COUNTED, so the shortfall appears in the
report instead of hiding inside an unexplained ceiling.

WHY THEY ARE CORRUPTION AND NOT RETIRED CONCEPTS
------------------------------------------------
Every SNOMED identifier ends in a Verhoeff check digit. All four failures fail
it, so none was ever issued — SNOMED inactivates concepts, it does not delete
them, and a retired concept still passes its own check digit. Measured
2026-08-24:

    20070731            NOT A CODE — the date 2007-07-31, in RF2's YYYYMMDD
                        effectiveTime format, sitting in the code column
    21499005            transposition of 24199005 |Feeling agitated|
    81680008            81680005 |Neck pain| with the check digit wrong
    21290011000036100   a mistyped AU extension (AMT) identifier, drug mention

Over the 7,311 gold REACTION mentions this excludes 3, because the fourth is
post-coordinated with a valid code and so remains answerable. A further 4 are
excluded because the quoted text does not sit at the quoted offsets.

Seven mentions in 7,311 is 0.10%. The point of writing it down is not the size;
it is that a ceiling of 99.90% now has a stated cause.
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

EXCLUDE_INVALID_CODE = "invalid_code"
EXCLUDE_SPAN_MISMATCH = "span_text_offset_mismatch"
EXCLUDE_RETIRED_CODE = "retired_code"

DEFAULT_OUT = Path("data/exclusions.csv")

# Verhoeff tables. The last digit of every SNOMED identifier is a check digit
# over the preceding ones, which is what lets "never issued" be distinguished
# from "issued and later retired".
_D = [
    [0, 1, 2, 3, 4, 5, 6, 7, 8, 9], [1, 2, 3, 4, 0, 6, 7, 8, 9, 5],
    [2, 3, 4, 0, 1, 7, 8, 9, 5, 6], [3, 4, 0, 1, 2, 8, 9, 5, 6, 7],
    [4, 0, 1, 2, 3, 9, 5, 6, 7, 8], [5, 9, 8, 7, 6, 0, 4, 3, 2, 1],
    [6, 5, 9, 8, 7, 1, 0, 4, 3, 2], [7, 6, 5, 9, 8, 2, 1, 0, 4, 3],
    [8, 7, 6, 5, 9, 3, 2, 1, 0, 4], [9, 8, 7, 6, 5, 4, 3, 2, 1, 0],
]
_P = [
    [0, 1, 2, 3, 4, 5, 6, 7, 8, 9], [1, 5, 7, 6, 2, 8, 3, 0, 9, 4],
    [5, 8, 0, 3, 7, 9, 6, 1, 4, 2], [8, 9, 1, 6, 0, 4, 3, 5, 2, 7],
    [9, 4, 5, 3, 1, 2, 6, 8, 7, 0], [4, 2, 8, 6, 5, 7, 3, 9, 0, 1],
    [2, 7, 9, 3, 8, 0, 6, 4, 1, 5], [7, 0, 4, 6, 9, 1, 3, 2, 5, 8],
]


def verhoeff_ok(code: str | None) -> bool:
    """Is this string a well-formed SNOMED identifier?

    Structural only — says nothing about whether the concept is in any release.
    A code that fails this was never issued; a code that passes but is absent
    is a different problem (wrong edition, wrong extension).
    """
    if not code or not str(code).isdigit():
        return False
    c = 0
    for i, ch in enumerate(reversed(str(code))):
        c = _D[c][_P[i % 8][int(ch)]]
    return c == 0


def _bag(s: str) -> set[str]:
    return set((s or "").lower().split())


def build_exclusions(mentions, sources: dict[str, str], vocab=None) -> list[dict]:
    """Which gold mentions cannot be answered, and why. Never mutates gold."""
    rows = []
    for m in mentions:
        codes = list(getattr(m, "sct", None) or [])
        # CONCEPT_LESS is an ANSWER, not corruption: no codes at all is fine.
        if codes and not any(verhoeff_ok(c) for c in codes):
            rows.append({
                "record_id": m.record_id,
                "doc_id": m.doc_id,
                "reason": EXCLUDE_INVALID_CODE,
                "detail": " ".join(codes),
            })
            continue

        # The keyword table holds active concepts only, so a mention whose
        # every gold code is retired cannot be answered through it.
        if vocab is not None and codes and not any(vocab.is_active(c) for c in codes):
            rows.append({
                "record_id": m.record_id,
                "doc_id": m.doc_id,
                "reason": EXCLUDE_RETIRED_CODE,
                "detail": " ".join(codes),
            })
            continue

        src = sources.get(m.doc_id)
        spans = list(getattr(m, "spans", None) or [])
        if src is not None and spans and getattr(m, "text", ""):
            quoted = " ".join(src[a:b] for a, b in spans)
            # Token bag, not concatenation: 45 gold mentions quote their
            # discontinuous segments in reading order, not offset order.
            if _bag(quoted) != _bag(m.text):
                rows.append({
                    "record_id": m.record_id,
                    "doc_id": m.doc_id,
                    "reason": EXCLUDE_SPAN_MISMATCH,
                    "detail": f"{m.text!r} != {quoted!r}",
                })
    return rows


def write_exclusions(rows: list[dict], path: str | Path = DEFAULT_OUT) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["record_id", "doc_id", "reason", "detail"])
        w.writeheader()
        for r in sorted(rows, key=lambda r: r["record_id"]):
            w.writerow(r)
    return path


def load_exclusions(path: str | Path = DEFAULT_OUT) -> set[str]:
    """Excluded record_ids. A MISSING file excludes nothing, deliberately:
    scoring everything is the honest default, and silently dropping an
    unknown set would be worse than dropping none."""
    path = Path(path)
    if not path.exists():
        return set()
    with path.open(encoding="utf-8", newline="") as fh:
        return {r["record_id"] for r in csv.DictReader(fh) if r.get("record_id")}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--build", action="store_true")
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    a = ap.parse_args(argv)
    if not a.build:
        ap.error("nothing to do — pass --build")

    from ladder import corpus as C
    from ladder.manifest import load_manifest
    from ladder.schema import REACTION

    man = load_manifest("manifest.json")
    docs = C.load_corpus(man["corpus"]["cadec_root"])
    sources = {d: doc.text for d, doc in docs.items()}
    mentions = [m for doc in docs.values() for m in doc.mentions if m.entity_type == REACTION]
    from ladder.registry import Registry

    vocab = None
    try:
        vocab = Registry(man["vocabulary"]["snomed_db"])
    except FileNotFoundError:
        print("  no vocabulary index — retired codes not checked")
    rows = build_exclusions(mentions, sources, vocab=vocab)
    path = write_exclusions(rows, a.out)

    by = {}
    for r in rows:
        by[r["reason"]] = by.get(r["reason"], 0) + 1
    print(f"[clean] {len(mentions):,} gold reaction mentions")
    for reason, n in sorted(by.items()):
        print(f"  excluded {n:4d}  {reason}")
    print(f"  excluded {len(rows):4d}  total  ({len(rows)/len(mentions):.2%})")
    print(f"  wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""
psytar_discontinuous.py — the 453 "absent" spans are discontinuous, not absent.

WHAT THE AUDIT ACTUALLY FOUND

`psytar_locate_audit.py` reported 453 spans (9.7%) that do not occur in their
review at all, and concluded a model arm would be scoring against our locator.
That conclusion was wrong, and the examples show why:

    span  'First 10 days, looong panic attack'
    sent  'First 10 days were HORRIBLE, like a looong panic attack with anxiety'

    span  'Crazy visions'
    sent  'Crazy dreams and visions, slight insomnia, my teeth are killing me'

The span is not missing. It is **discontinuous** — the annotators took two or
more non-adjacent fragments from one sentence and wrote them out joined, with a
comma where a comma helped and with nothing where it did not. `Crazy visions`
is `Crazy` + `visions` with `dreams and` skipped.

That is an annotation convention rather than a defect, and **CADEC has the same
one** — which is precisely why `GoldMention.spans` is a LIST of ranges and not
a pair. The ladder's schema already supports these mentions. Our locator did
not, and read a convention it did not know as data that did not exist.

Worth stating plainly because it is a general trap: **a span given as text
rather than as offsets carries an implicit convention, and the convention is
usually undocumented.** Whoever wrote the string search has to guess it, and a
wrong guess reads as missing data — 9.7% of a corpus, silently, with an
explanation that sounds reasonable.

THE LOCATOR

Ordered-subsequence matching over word positions: find the span's words in the
sentence in order, allowing gaps, then merge adjacent hits into as few ranges
as possible. Constraints that keep it honest rather than greedy:

    · every word of the span must be found, in order
    · the gaps together may not exceed `max_gap` words (default 6), so a
      match cannot be assembled from opposite ends of a long sentence
    · the result is reported as N RANGES, and a mention needing more than
      `max_parts` (default 3) is refused rather than stitched

Refusing loudly matters more than recovering everything. A locator that always
succeeds is one that has stopped being a check.

    PYTHONPATH=. python3 scripts/psytar_discontinuous.py            # audit only
    PYTHONPATH=. python3 scripts/psytar_discontinuous.py --patch    # write the fix
"""
from __future__ import annotations

import argparse
import pathlib
import re
import sys
from collections import Counter, defaultdict

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

_W = re.compile(r"\w+")


def words(s: str):
    return [(m.group(0).lower(), m.start(), m.end()) for m in _W.finditer(s or "")]


def locate(span: str, sent: str, max_gap: int = 6, max_parts: int = 3):
    """Ranges covering `span`'s words inside `sent`, or None.

    Returns a list of (start, end) character ranges — one if the span is
    contiguous, more if it is discontinuous.
    """
    sw = [w for w, _, _ in words(span)]
    tw = words(sent)
    if not sw or not tw:
        return None

    # Greedy left-to-right: the earliest match for each span word after the
    # previous one. Greedy is right here because a discontinuous annotation
    # reads the sentence in order — it never doubles back.
    hits, at = [], 0
    for w in sw:
        found = None
        for i in range(at, len(tw)):
            if tw[i][0] == w:
                found = i
                break
        if found is None:
            return None
        hits.append(found)
        at = found + 1

    gaps = sum(hits[i + 1] - hits[i] - 1 for i in range(len(hits) - 1))
    if gaps > max_gap:
        return None

    ranges, s, e, prev = [], tw[hits[0]][1], tw[hits[0]][2], hits[0]
    for i in hits[1:]:
        if i == prev + 1:
            e = tw[i][2]
        else:
            ranges.append((s, e))
            s, e = tw[i][1], tw[i][2]
        prev = i
    ranges.append((s, e))
    return ranges if len(ranges) <= max_parts else None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default="data/psytar")
    ap.add_argument("--entity", default="ADR")
    ap.add_argument("--patch", action="store_true",
                    help="write the locator into ladder/corpus_psytar.py")
    a = ap.parse_args()

    import openpyxl
    from ladder.corpus_psytar import SHEETS, _rows

    ident_sheet, _, _ = SHEETS[a.entity]
    wb = openpyxl.load_workbook(pathlib.Path(a.root) / "PsyTAR_dataset.xlsx",
                                read_only=True, data_only=True)
    sentences: dict[str, dict[int, str]] = defaultdict(dict)
    for r in _rows(wb["Sentence_Labeling"]):
        d = str(r.get("drug_id") or "").strip()
        try:
            i = int(str(r.get("sentence_index")).strip())
        except (TypeError, ValueError):
            continue
        sentences[d][i] = str(r.get("sentences") or "")

    cols = [f"{a.entity}{i}" for i in range(1, 11)]
    n = Counter()
    parts = Counter()
    shown = 0

    for r in _rows(wb[ident_sheet]):
        d = str(r.get("drug_id") or "").strip()
        try:
            i = int(str(r.get("sentence_index")).strip())
        except (TypeError, ValueError):
            continue
        sent = sentences.get(d, {}).get(i)
        if sent is None:
            continue
        for c in cols:
            txt = str(r.get(c) or "").strip()
            if not txt:
                continue
            n["total"] += 1
            if txt in sent:
                n["contiguous, exact"] += 1
                parts[1] += 1
                continue
            rr = locate(txt, sent)
            if rr is None:
                n["still not locatable"] += 1
                continue
            parts[len(rr)] += 1
            n["recovered, 1 range" if len(rr) == 1 else
              f"recovered, {len(rr)} ranges"] += 1
            if len(rr) > 1 and shown < 6:
                shown += 1
                got = " + ".join(repr(sent[s:e]) for s, e in rr)
                print(f"  {txt!r}\n    -> {got}")

    print(f"\n  PsyTAR · {a.entity} · {n['total']} annotated spans\n")
    for k in sorted(n, key=lambda k: -n[k]):
        if k == "total":
            continue
        mark = " !" if "not locatable" in k else "  "
        print(f"  {mark} {k:32} {n[k]:5}  {n[k]/n['total']:6.1%}")

    lost = n["still not locatable"]
    print(f"\n  {lost} of {n['total']} remain unplaceable ({lost/n['total']:.1%}).")
    if lost / n["total"] < 0.02:
        print("  → Under 2%. A model arm IS viable: these drop with a reason, the")
        print("    way GeoWebNews's two bad offsets did. The earlier conclusion")
        print("    that PsyTAR could not carry a span number was wrong, and it was")
        print("    wrong because our locator did not know the corpus's convention.")
    else:
        print("  → Still above 2%. The locator recovers most of it and not enough.")

    if a.patch:
        p = pathlib.Path("ladder/corpus_psytar.py")
        s = p.read_text()
        if "def locate(" in s:
            print("\n  already patched")
            return 0
        helper = pathlib.Path(__file__).read_text()
        block = helper[helper.index("_W = re.compile"):helper.index("def main()")]
        s = s.replace("def load_corpus(", block + "\ndef load_corpus(", 1)
        old = '''            hits = [m.start() for m in re.finditer(re.escape(txt), sent)]
            if not hits:'''
        new = '''            hits = [m.start() for m in re.finditer(re.escape(txt), sent)]
            if not hits:
                # DISCONTINUOUS, not absent. The annotators joined non-adjacent
                # fragments of one sentence — `Crazy visions` is `Crazy` +
                # `visions` with `dreams and` skipped — and CADEC uses the same
                # convention, which is why spans is a list of ranges. Reading
                # the convention as missing data lost 9.7% of this corpus.
                rr = locate(txt, sent)
                if rr:
                    off = starts[idx]
                    mentions.append(GoldMention(
                        doc_id=doc_id, index=len(mentions),
                        entity_type="reaction", cadec_type="", text=txt,
                        spans=[(off + s0, off + e0) for s0, e0 in rr],
                        sct=codes.get((drug.lower(), str(idx), txt.lower()), []),
                        gold_kind=entity.lower() + ("_discontinuous"
                                                    if len(rr) > 1 else ""),
                    ))
                    if not mentions[-1].sct:
                        mentions.pop()
                        dropped["span_without_code"] += 1
                    else:
                        dropped[f"discontinuous_{len(rr)}_ranges"] += 1
                    continue'''
        if old in s:
            s = s.replace(old, new, 1)
            p.write_text(s)
            print("\n  patched ladder/corpus_psytar.py — re-run the experiment")
        else:
            print("\n  ! could not find the locator block to patch", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""PsyTAR as a ladder corpus — the matched comparison section 11 asks for.

THE QUESTION THIS CORPUS ANSWERS

Section 11: *"The second corpus is a demonstration, not a matched comparison. A
third, with a lexical vocabulary, would test whether the 75-82% ACCEPT lane
belongs to controlled vocabularies in general or to SNOMED in particular."*

FiNER and GeoWebNews each change two things at once — the text AND the
vocabulary — so neither can separate those. PsyTAR changes **one**:

    same forum          askapatient.com, which is also where CADEC comes from
    same task           adverse drug reactions in patient prose
    same vocabulary     SNOMED CT
    different drugs     Zoloft, Lexapro, Cymbalta, Effexor XR
                        against CADEC's Diclofenac, Lipitor and ten others

That is as close to a controlled experiment as a second corpus gets, and it
makes the ACCEPT lane's rate directly comparable rather than merely adjacent.

WHAT IS IN IT

891 reviews, 6,009 sentences, 4,813 ADR mentions plus withdrawal symptoms,
signs and indications, mapped to 916 UMLS and 755 SNOMED concepts. CC BY 4.0.

THE ONE STRUCTURAL DIFFERENCE FROM CADEC, AND IT IS NOT COSMETIC

**PsyTAR has no character offsets.** Spans are given as text — `ADR1`..`ADR10`
columns beside the sentence they came from — so they must be LOCATED, and
locating is a source of error CADEC does not have. Three cases arise and all
three are counted rather than resolved silently:

    found once      the ordinary case
    found several   the same phrase twice in one sentence; the first is taken
                    and the record is flagged, because the annotators did not
                    say which
    not found       a normalisation difference between the span column and the
                    sentence. Dropped with a reason, never repaired

Rung 1's span-grounding check therefore measures OUR locator on this corpus,
not the model. Any grounding figure from PsyTAR carries that caveat.

THE OTHER DIFFERENCE, WHICH IS A REAL RISK TO THE COMPARISON

PsyTAR maps to **SNOMEDCT_US**; this project indexes the **AU** release. The
overlap is large and not total, and an id absent from the index is not a wrong
answer — it is a record outside the denominator. `stratify()` counts them
separately for that reason. If the absent share is large, the comparison with
CADEC is weakened and the honest response is to say so rather than to score
against a vocabulary that does not contain the answer.

SHAPE

    Sentence_Labeling   6,009 sentences · drug_id · sentence_index · text
    ADR_Identified      per sentence, up to 10 span TEXTS
    ADR_Mapped          per span, `Loss of hair (finding) [A3543141/SNOMEDCT_US/FN/278040002]`

A document here is one REVIEW — its sentences joined in order — because CADEC's
unit is a whole post and comparing per-sentence records against per-post ones
would compare two different tasks.
"""
from __future__ import annotations

import os
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

from ladder.corpus import Document, GoldMention
from ladder.corpus_geo import overlap_stratum, make_splits, write_splits, read_split  # noqa: F401

#: `... [A3543141/SNOMEDCT_US/FN/278040002]` — the last field is the concept id.
_SCT = re.compile(r"\[[^\]]*?/SNOMEDCT[^/\]]*/[^/\]]*/(\d+)\]")

#: Which sheet pair to read. ADRs are the analogue of CADEC's reactions and the
#: only class CADEC also annotates; the others are available and not scored.
SHEETS = {
    "ADR": ("ADR_Identified", "ADR_Mapped", "ADRs"),
    "WD":  ("WD_Identified", "WD-Mapped", "WDs"),
    "SSI": ("SSI_Identified", "SSI_Mapped", "SSIs"),
    "DI":  ("DI_Identified", "DI_Mapped", "DIs"),
}


def _rows(ws):
    """Rows as dicts — but DUPLICATE HEADERS ARE KEPT, both of them.

    `ADR_Mapped` has two columns called `SNOMED-CT`: position 5 is the mapping
    for UMLS1 and position 7 the mapping for UMLS2. A plain `dict(zip(...))`
    keeps only the last, which is blank on 4,469 of 5,010 rows — so the first
    version of this adapter read the secondary column, dropped 91% of the
    corpus, and reported an ACCEPT lane of 3.4% that was a fact about its own
    filter. Duplicates are suffixed instead, and `_snomed_cells` reads both.
    """
    it = ws.iter_rows(values_only=True)
    raw = [str(c).strip() if c is not None else "" for c in next(it)]
    seen, hdr = {}, []
    for h in raw:
        seen[h] = seen.get(h, 0) + 1
        hdr.append(h if seen[h] == 1 else f"{h}#{seen[h]}")
    for r in it:
        yield dict(zip(hdr, r))


def _snomed_cells(row: dict) -> list[str]:
    """Every SNOMED cell on the row, primary first."""
    return [str(row.get(k) or "").strip()
            for k in ("SNOMED-CT", "SNOMED-CT#2")
            if str(row.get(k) or "").strip()]


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



def load_corpus(root: str | os.PathLike, *, entity: str = "ADR",
                documents: int | None = None, **_) -> dict[str, Document]:
    """Read PsyTAR. `root` is the directory holding `PsyTAR_dataset.xlsx`."""
    import openpyxl

    if entity not in SHEETS:
        raise ValueError(f"entity must be one of {sorted(SHEETS)}, not {entity!r}")
    ident_sheet, map_sheet, span_col = SHEETS[entity]

    path = Path(root) / "PsyTAR_dataset.xlsx"
    if not path.is_file():
        raise FileNotFoundError(
            f"{path} not found. CC BY 4.0, redistributed with a preprocessor:\n"
            "    curl -sL https://raw.githubusercontent.com/basaldella/"
            "psytarpreprocessor/master/data/PsyTAR_dataset.xlsx -o PsyTAR_dataset.xlsx")

    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    dropped = Counter()

    # ── the codes, keyed by (review, sentence, span text) ────────────────
    codes: dict[tuple, list[str]] = defaultdict(list)
    for r in _rows(wb[map_sheet]):
        span = (r.get(span_col) or "").strip()
        if not span:
            continue
        cells = _snomed_cells(r)
        found = [m.group(1) for c in cells for m in [_SCT.search(c)] if m]
        if not found:
            # `No code` is the ANNOTATORS saying no SNOMED concept applies —
            # the corpus's own unresolvable class, counted apart from a row we
            # simply failed to parse. Both leave the denominator; only one is
            # our problem.
            if any(c.lower().startswith("no code") for c in cells):
                dropped["annotators_said_no_code"] += 1
            elif cells:
                dropped["snomed_cell_unparsed"] += 1
            else:
                dropped["no_snomed_mapping"] += 1
            continue
        key = (str(r.get("drug_id") or "").strip().lower(),
               str(r.get("sentence_index") or "").strip(),
               span.lower())
        codes[key].extend(found)

    # ── the sentences, per review, in order ──────────────────────────────
    sentences: dict[str, dict[int, str]] = defaultdict(dict)
    for r in _rows(wb["Sentence_Labeling"]):
        drug = str(r.get("drug_id") or "").strip()
        try:
            idx = int(str(r.get("sentence_index")).strip())
        except (TypeError, ValueError):
            continue
        sentences[drug][idx] = str(r.get("sentences") or "")

    # ── the spans, located in their sentence then in the joined review ───
    spans: dict[str, list] = defaultdict(list)
    span_cols = [f"{entity}{i}" for i in range(1, 11)]
    for r in _rows(wb[ident_sheet]):
        drug = str(r.get("drug_id") or "").strip()
        try:
            idx = int(str(r.get("sentence_index")).strip())
        except (TypeError, ValueError):
            continue
        sent = sentences.get(drug, {}).get(idx)
        if sent is None:
            dropped["sentence_not_found"] += 1
            continue
        for col in span_cols:
            txt = (r.get(col) or "")
            txt = str(txt).strip()
            if not txt:
                continue
            spans[drug].append((idx, txt))

    # ── build the documents ──────────────────────────────────────────────
    docs: dict[str, Document] = {}
    for drug in sorted(sentences):
        if documents is not None and len(docs) >= documents:
            break
        ordered = [sentences[drug][k] for k in sorted(sentences[drug])]
        # Offsets of each sentence within the joined review, so a span located
        # in a sentence can be placed in the document.
        starts, pos = {}, 0
        for k in sorted(sentences[drug]):
            starts[k] = pos
            pos += len(sentences[drug][k]) + 1
        text = "\n".join(ordered)
        doc_id = f"PSYTAR.{drug}"

        mentions = []
        for idx, txt in spans.get(drug, []):
            sent = sentences[drug].get(idx, "")
            hits = [m.start() for m in re.finditer(re.escape(txt), sent)]
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
                    continue
                # A normalisation difference between the span column and the
                # sentence. Dropped rather than fuzzy-matched: a span located
                # by approximation is a span whose grounding check is measuring
                # the approximation.
                dropped["span_not_located"] += 1
                continue
            if len(hits) > 1:
                dropped["span_ambiguous_first_taken"] += 1
            s = starts[idx] + hits[0]
            e = s + len(txt)
            if text[s:e] != txt:
                dropped["offset_mismatch"] += 1
                continue
            sct = codes.get((drug.lower(), str(idx), txt.lower()), [])
            if not sct:
                dropped["span_without_code"] += 1
                continue
            mentions.append(GoldMention(
                doc_id=doc_id,
                index=len(mentions),
                entity_type="reaction",
                cadec_type="",          # filled by stratify(); needs the vocabulary
                text=txt,
                spans=[(s, e)],
                sct=sct,
                gold_kind=entity.lower(),
            ))
        docs[doc_id] = Document(doc_id=doc_id, drug_group=drug.split(".")[0],
                                text=text, mentions=mentions)

    if dropped:
        print(f"[corpus_psytar:{entity}] dropped {dict(dropped)}", file=sys.stderr)
    return docs


def stratify(docs: dict[str, Document], registry) -> Counter:
    """The overlap stratum, against every term the vocabulary holds.

    Counts `not_in_vocabulary` separately and prominently: PsyTAR maps to
    SNOMEDCT_US and this project indexes AU. An id the index does not hold is a
    record outside the denominator, not a wrong answer, and folding the two
    together would make PsyTAR look worse than CADEC for a reason that has
    nothing to do with the lane.
    """
    rank = {"identical": 0, "subset": 1, "partial": 2, "none": 3, "empty": 4}
    stats = Counter()
    for d in docs.values():
        for m in d.mentions:
            terms = []
            for code in m.sct:
                try:
                    terms += registry.terms(code) or []
                except Exception:
                    pass
            if not terms:
                m.cadec_type = "empty"
                stats["not_in_vocabulary"] += 1
                continue
            m.cadec_type = min((overlap_stratum(m.text, t) for t in terms),
                               key=lambda k: rank.get(k, 9))
            stats[m.cadec_type] += 1
    return stats


def gold_records(docs: dict[str, Document], doc_ids: list[str]) -> list[GoldMention]:
    return [m for d in doc_ids for m in docs[d].mentions]


if __name__ == "__main__":
    import argparse
    import json

    ap = argparse.ArgumentParser(description="Inspect PsyTAR against the SNOMED index.")
    ap.add_argument("--root", default="data/psytar")
    ap.add_argument("--entity", default="ADR", choices=sorted(SHEETS))
    ap.add_argument("--manifest", default="manifest.json",
                    help="read the SNOMED index path from here")
    a = ap.parse_args()

    docs = load_corpus(a.root, entity=a.entity)
    gold = [m for d in docs.values() for m in d.mentions]
    print(f"\n  PsyTAR · {a.entity} · {len(docs)} reviews · {len(gold)} mentions")
    print(f"  {sum(1 for d in docs.values() if d.mentions)} reviews carry at least one\n")

    common = Counter(m.text.lower() for m in gold).most_common(8)
    print(f"  commonest spans: {', '.join(t for t, _ in common)}\n")

    man = json.load(open(a.manifest))
    db = (man.get("vocabulary") or {}).get("snomed_db")
    if not db or not Path(db).is_file():
        print(f"  SNOMED index not found at {db!r}", file=sys.stderr)
        raise SystemExit(1)
    from ladder.registry import Registry
    st = stratify(docs, Registry(db))
    n = sum(v for k, v in st.items() if k != "not_in_vocabulary")
    print("  lexical-overlap stratum, from gold alone:")
    for k in ("identical", "subset", "partial", "none"):
        if st.get(k):
            print(f"    {k:11} {st[k]:5}  {st[k]/n:6.1%}")
    if st.get("not_in_vocabulary"):
        miss = st["not_in_vocabulary"]
        tot = miss + n
        print(f"\n    NOT IN THIS INDEX  {miss:5}  ({miss/tot:.1%} of {tot})")
        print( "    PsyTAR maps to SNOMEDCT_US and this index is the AU release.")
        print( "    These are outside the denominator, not wrong answers.")
    print()

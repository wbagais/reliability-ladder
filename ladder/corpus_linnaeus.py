"""LINNAEUS as a ladder corpus — the fifth, and the third mechanism.

WHY IT IS WORTH AN AFTERNOON WHERE TWO MORE GEO CORPORA WERE NOT

The calibration set had three vocabulary shapes and three of its five corpora
were geoparsing. This adds a fourth shape — a **rank taxonomy** — and, more
usefully, a third mechanism for the no-overlap stratum:

    geography   demonyms and abbreviations    `French` -> Republic of France
    finance     a numeral against a phrase    `47.6` -> EffectiveIncomeTaxRate...
    species     VERNACULAR against LATIN      `mice` -> Mus musculus

Measured on the corpus before this file was written: 4,259 mentions, **zero
offsets that do not land** — cleaner than any of the other four — and the eight
commonest surface forms are `patients`, `human`, `mice`, `mouse`, `patient`,
`people`, `women`, `yeast`. Every one a common noun annotated to a binomial.

AND IT SETTLES A QUESTION THE GEO ARM COULD ONLY DEFER

`build_taxon_index.py` can include scientific names only, or common names and
synonyms too, and NCBI ships a name class on every row: taxon 4932 is
*Saccharomyces cerevisiae*, `baker's yeast`, `brewer's yeast` and `Candida
robusta`. So the lexical relation can be measured **both ways on the same
corpus**, which the GeoNames build could not do without a second index nobody
had time to justify. Here the corpus is made of exactly the mentions that
distinguish them.

    ladder/cache/taxonomy.sqlite       scientific names only  -> strict
    ladder/cache/taxonomy-all.sqlite   plus common + synonyms -> lenient

SHAPE

    tags.tsv    species:ncbi:4932 <TAB> pmcA102792 <TAB> 75 <TAB> 80 <TAB> yeast
    txt/<doc>.txt

`filtered_tags.tsv` ships alongside and is NOT used: it is the subset the
corpus authors kept after their own filtering, and starting from their filtered
set would make this corpus's denominator theirs rather than ours. `tags.tsv` is
everything they annotated.
"""
from __future__ import annotations

import os
import re
from collections import Counter
from pathlib import Path

from ladder.corpus import Document, GoldMention
from ladder.corpus_geo import overlap_stratum, make_splits, write_splits, read_split  # noqa: F401

REACTION = "reaction"          # the ladder's scored entity type

#: `species:ncbi:4932` — and occasionally a compound id for an ambiguous
#: mention, which is dropped rather than guessed at.
_ID = re.compile(r"^species:ncbi:(\d+)$")


def load_corpus(root: str | os.PathLike, *, documents: int | None = None,
                **_) -> dict[str, Document]:
    """Read LINNAEUS. `root` is the `manual-corpus-species-1.0` directory."""
    root = Path(root)
    tags = root / "tags.tsv"
    txt = root / "txt"
    if not tags.is_file():
        raise FileNotFoundError(
            f"{tags} not found. Download and extract:\n"
            "    curl -sL 'https://sourceforge.net/projects/linnaeus/files/"
            "Corpora/manual-corpus-species-1.0.tar.gz/download' -o linn.tar.gz\n"
            "    tar xzf linn.tar.gz")

    texts: dict[str, str] = {}
    per_doc: dict[str, list] = {}
    dropped = Counter()

    for line in tags.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.startswith("#") or not line.strip():
            continue
        f = line.split("\t")
        if len(f) < 5:
            dropped["malformed"] += 1
            continue
        raw_id, doc, start, end, phrase = f[0], f[1], f[2], f[3], f[4]

        m = _ID.match(raw_id.strip())
        if not m:
            # Compound ids like `species:ncbi:9606|species:ncbi:10090` mark a
            # mention the annotators could not resolve to one taxon. Dropped and
            # counted: an unresolvable mention is not a wrong answer, and
            # picking one of its ids would invent an answer key.
            dropped["ambiguous_or_unparsed_id"] += 1
            continue
        taxid = m.group(1)

        if doc not in texts:
            p = txt / f"{doc}.txt"
            if not p.is_file():
                dropped["no_text_file"] += 1
                texts[doc] = ""
                continue
            texts[doc] = p.read_text(encoding="utf-8", errors="replace")
        text = texts[doc]
        if not text:
            continue

        try:
            s, e = int(start), int(end)
        except ValueError:
            dropped["bad_offset"] += 1
            continue

        # Checked, not trusted — the discipline that found 2 bad spans in
        # GeoWebNews and 116 in TR-News. This corpus has none, and knowing that
        # is worth the check.
        if text[s:e] != phrase:
            dropped["offset_mismatch"] += 1
            continue

        per_doc.setdefault(doc, []).append((s, e, phrase, taxid))

    docs: dict[str, Document] = {}
    for doc in sorted(per_doc):
        if documents is not None and len(docs) >= documents:
            break
        text = texts[doc]
        doc_id = f"LINN.{doc}"
        mentions = []
        for s, e, phrase, taxid in sorted(per_doc[doc]):
            mentions.append(GoldMention(
                doc_id=doc_id,
                index=len(mentions),
                entity_type=REACTION,
                # The stratum is left EMPTY here and filled by `stratify()`,
                # because it needs the vocabulary: a species' canonical name is
                # in names.dmp, not in the corpus. On the geo corpora the answer
                # key carried the canonical name and this could be done inline.
                cadec_type="",
                text=phrase,
                spans=[(s, e)],
                sct=[taxid],
                gold_kind="species",
            ))
        docs[doc_id] = Document(doc_id=doc_id, drug_group="linnaeus",
                                text=text, mentions=mentions)

    if dropped:
        import sys
        print(f"[corpus_linnaeus] dropped {dict(dropped)}", file=sys.stderr)
    return docs


def stratify(docs: dict[str, Document], registry) -> Counter:
    """Fill the overlap stratum, which here needs the vocabulary.

    A taxon's canonical name lives in `names.dmp` rather than in the corpus, so
    the surface form can only be compared against it once a vocabulary is
    loaded. Which vocabulary matters: against SCIENTIFIC names `mice` shares no
    token with `Mus musculus`, and against ALL names it matches `mouse` exactly.
    That difference is the arm this corpus exists to run.
    """
    stats = Counter()
    for d in docs.values():
        for m in d.mentions:
            # The BEST overlap against ANY term the vocabulary holds, not
            # against the canonical name alone. Comparing only to `preferred()`
            # asked the wrong question and made the strict and lenient indexes
            # return identical numbers — `preferred(10090)` is `Mus musculus`
            # in both, while `terms(10090)` is `['Mus musculus']` in one and
            # `['house mouse', 'mouse', 'Mus musculus']` in the other. Rung 1's
            # lexical check reads every term, so the stratum must too.
            try:
                terms = registry.terms(m.sct[0]) or []
            except Exception:
                terms = []
            if not terms:
                m.cadec_type = "empty"
                stats["no_canonical_name"] += 1
                continue
            rank = {"identical": 0, "subset": 1, "partial": 2, "none": 3, "empty": 4}
            m.cadec_type = min((overlap_stratum(m.text, t) for t in terms),
                               key=lambda k: rank.get(k, 9))
            stats[m.cadec_type] += 1
    return stats


def gold_records(docs: dict[str, Document], doc_ids: list[str]) -> list[GoldMention]:
    return [m for d in doc_ids for m in docs[d].mentions]


if __name__ == "__main__":
    import argparse
    import sys

    ap = argparse.ArgumentParser(
        description="Inspect LINNAEUS, strict and lenient, on the same mentions.")
    ap.add_argument("--root", default="data/linnaeus/manual-corpus-species-1.0")
    ap.add_argument("--db", default="ladder/cache/taxonomy.sqlite")
    ap.add_argument("--db-all", default="ladder/cache/taxonomy-all.sqlite")
    a = ap.parse_args()

    docs = load_corpus(a.root)
    gold = [m for d in docs.values() for m in d.mentions]
    print(f"\n  LINNAEUS: {len(docs)} documents · {len(gold)} gold mentions")

    common = Counter(m.text for m in gold).most_common(8)
    print(f"  commonest surface forms: {', '.join(t for t, _ in common)}\n")

    from ladder.registry import Registry
    for label, db in (("scientific names only", a.db), ("plus common + synonyms", a.db_all)):
        if not Path(db).is_file():
            print(f"  {label:24} {db} not built", file=sys.stderr)
            continue
        st = stratify(docs, Registry(db))
        n = sum(v for k, v in st.items() if k != "no_canonical_name")
        print(f"  {label}")
        for k in ("identical", "subset", "partial", "none", "empty"):
            if st.get(k):
                print(f"    {k:11} {st[k]:5}  {st[k]/n:6.1%}")
        if st.get("no_canonical_name"):
            print(f"    {'unresolved':11} {st['no_canonical_name']:5}")
        print()

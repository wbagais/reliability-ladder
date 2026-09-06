"""BC5CDR as a ladder corpus — the second clinical one, and the first with two
entity types the vocabulary can actually check.

WHY IT WAS WORTH GOING BACK FOR

Two earlier attempts at this corpus failed and both were URL problems rather
than licence problems: BioCreative's own download returns a login page, and
`nlmpubs.nlm.nih.gov/projects/mesh/MESH_FILES/asciimesh/` answers a HEAD
request with 200 and a GET with an HTML "URL Not Found" page. The working paths
are a GitHub mirror of the corpus and `projects/mesh/<year>/asciimesh/` for the
vocabulary — both free, neither requiring registration.

WHAT IT ADDS THAT THE OTHER FIVE DO NOT

**A second clinical corpus.** CADEC carries most of the article's claims and
stands alone; section 11 lists that as an open question — *"a third, with a
lexical vocabulary, would test whether the 75-82% ACCEPT lane belongs to
controlled vocabularies in general or to SNOMED in particular."* This is the
corpus that answers it, on the same kind of text with a different vocabulary.

**Two entity types the vocabulary can adjudicate.** Every mention is annotated
`Chemical` or `Disease`, and MeSH's tree tells the two apart — the C tree is
Diseases, the D tree is Chemicals and Drugs. So rung 1's semantic check runs
**in both directions and can fail**, which it cannot on a gazetteer or a flat
tag set. It is also the same shape as CADEC's drug/reaction split, so the two
clinical corpora are comparable on it.

**A stated unresolvable class.** 226 of 28,785 mentions carry `-1` instead of a
MeSH id — the annotators marking a mention they could not resolve. Those leave
the denominator with a reason rather than being scored as errors, which is the
same discipline as CADEC's exclusion list.

**A third mechanism for the no-overlap stratum, probably.** Geography's is
demonyms; finance's is a numeral against a phrase; species' is vernacular
against Latin. Here it looks morphological — `hypertensive` annotated to
|Hypertension|, `hypotensive` to |Hypotension| — an adjective against the noun
the concept is named for. Measured rather than assumed: run this module.

SHAPE — PubTator, three files, already split

    227508|t|Naloxone reverses the antihypertensive effect of clonidine.
    227508|a|In unanesthetized, spontaneously hypertensive rats ...
    227508	0	8	Naloxone	Chemical	D009270
    227508	93	105	hypertensive	Disease	D006973
    227508	244	252	nalozone	Chemical	-1

Offsets index the title and abstract concatenated with a single newline —
verified here rather than assumed, because two corpora in this set have had
offsets that do not land.
"""
from __future__ import annotations

import os
import sys
from collections import Counter
from pathlib import Path

from ladder.corpus import Document, GoldMention
from ladder.corpus_geo import overlap_stratum, make_splits, write_splits, read_split  # noqa: F401

#: BC5CDR ships its own three-way split; `documents=` truncates within one.
FILES = {"train": "CDR_TrainingSet.PubTator.txt",
         "dev": "CDR_DevelopmentSet.PubTator.txt",
         "test": "CDR_TestSet.PubTator.txt"}

#: The ladder scores one entity type per arm. Chemicals are the larger class
#: (15,935 of 28,785) and the closer analogue of CADEC's drugs; diseases are
#: the closer analogue of its reactions. Both run; the arm picks.
TYPES = ("Chemical", "Disease")


def load_corpus(root: str | os.PathLike, *, part: str = "dev",
                entity: str = "Disease", documents: int | None = None,
                **_) -> dict[str, Document]:
    """Read one BC5CDR split. `root` is the `CDR.Corpus.v010516` directory.

    `entity` selects which annotations become gold. Both types are always
    parsed — the other becomes `entity_type` on the record, so a semantic check
    can be run in both directions — but only one is scored, because a rung that
    scores two vocabularies at once cannot say which one it failed on.
    """
    if entity not in TYPES:
        raise ValueError(f"entity must be one of {TYPES}, not {entity!r}")
    fname = FILES.get(part)
    if fname is None:
        raise ValueError(f"unknown part {part!r} — one of {sorted(FILES)}")
    path = Path(root) / fname
    if not path.is_file():
        raise FileNotFoundError(
            f"{path} not found. The corpus is a free GitHub mirror:\n"
            "    curl -sL https://raw.githubusercontent.com/JHnlp/"
            "BioCreative-V-CDR-Corpus/master/CDR_Data.zip -o CDR_Data.zip\n"
            "    unzip -q CDR_Data.zip")

    texts: dict[str, list[str]] = {}
    anns: dict[str, list] = {}
    dropped = Counter()

    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        if "|t|" in line[:20]:
            pmid, _, t = line.split("|", 2)
            texts.setdefault(pmid, ["", ""])[0] = t
            continue
        if "|a|" in line[:20]:
            pmid, _, a = line.split("|", 2)
            texts.setdefault(pmid, ["", ""])[1] = a
            continue
        f = line.split("\t")
        if len(f) == 4 and f[1] == "CID":
            # A chemical-induced-disease RELATION, not an entity annotation.
            # BC5CDR ships 1,012 of these in dev and they are a legitimate part
            # of the corpus that this task does not use. Counting them as
            # `malformed` reads as a data-quality problem in a corpus that does
            # not have one — the same distinction as could_not_run against fail.
            dropped["relation_annotation_not_used"] += 1
            continue
        if len(f) < 6:
            dropped["malformed"] += 1
            continue
        if len(f) > 6:
            # 89 rows carry a seventh field — an alternative identifier for the
            # same mention. Counted rather than silently sliced away.
            dropped["extra_field_ignored"] += 1
        pmid, start, end, phrase, kind, mesh = f[0], f[1], f[2], f[3], f[4], f[5].strip()
        if kind not in TYPES:
            dropped[f"other_type_{kind}"] += 1
            continue
        if mesh == "-1":
            # The annotators marking a mention they could not resolve. Out of
            # the denominator with a reason, never scored as an error.
            dropped["unresolvable_in_gold"] += 1
            continue
        if "|" in mesh:
            # A composite mention covering two concepts. Dropped rather than
            # split: taking the first would invent an answer key.
            dropped["composite_id"] += 1
            continue
        anns.setdefault(pmid, []).append((int(start), int(end), phrase, kind, mesh))

    docs: dict[str, Document] = {}
    for pmid in sorted(texts):
        if documents is not None and len(docs) >= documents:
            break
        title, abstract = texts[pmid]
        # PubTator offsets index title and abstract joined by ONE newline.
        text = f"{title}\n{abstract}"
        doc_id = f"CDR.{pmid}"
        mentions = []
        for s, e, phrase, kind, mesh in sorted(anns.get(pmid, [])):
            # Checked, not trusted. Two corpora in this set have had offsets
            # that do not land — GeoWebNews 2 of 2,401 and TR-News 116 of 1,275.
            if text[s:e] != phrase:
                dropped["offset_mismatch"] += 1
                continue
            if kind != entity:
                continue
            mentions.append(GoldMention(
                doc_id=doc_id,
                index=len(mentions),
                entity_type=kind.lower(),
                cadec_type="",          # filled by stratify(), which needs the vocabulary
                text=phrase,
                spans=[(s, e)],
                sct=[mesh],
                gold_kind=kind.lower(),
            ))
        docs[doc_id] = Document(doc_id=doc_id, drug_group=f"bc5cdr-{part}",
                                text=text, mentions=mentions)

    if dropped:
        print(f"[corpus_bc5cdr:{part}/{entity}] dropped {dict(dropped)}", file=sys.stderr)
    return docs


def stratify(docs: dict[str, Document], registry) -> Counter:
    """Fill the overlap stratum against EVERY term the vocabulary holds.

    Against `MH` alone, `hypertensive` shares no token with |Hypertension|.
    Against `ENTRY` synonyms it may. That difference is the arm, and comparing
    only to the preferred name would collapse it — which is exactly the bug
    that made two LINNAEUS indexes differing by 523,000 names return identical
    numbers until it was caught.
    """
    rank = {"identical": 0, "subset": 1, "partial": 2, "none": 3, "empty": 4}
    stats = Counter()
    for d in docs.values():
        for m in d.mentions:
            try:
                terms = registry.terms(m.sct[0]) or []
            except Exception:
                terms = []
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
    from pathlib import Path as P

    ap = argparse.ArgumentParser(
        description="Inspect BC5CDR, strict and lenient, on the same mentions.")
    ap.add_argument("--root", default="data/bc5cdr/CDR.Corpus.v010516")
    ap.add_argument("--part", default="dev", choices=sorted(FILES))
    ap.add_argument("--entity", default="Disease", choices=TYPES)
    ap.add_argument("--db", default="ladder/cache/mesh.sqlite")
    ap.add_argument("--db-all", default="ladder/cache/mesh-all.sqlite")
    a = ap.parse_args()

    docs = load_corpus(a.root, part=a.part, entity=a.entity)
    gold = [m for d in docs.values() for m in d.mentions]
    print(f"\n  BC5CDR {a.part} · {a.entity} · {len(docs)} documents · "
          f"{len(gold)} gold mentions")
    common = Counter(m.text for m in gold).most_common(8)
    print(f"  commonest surface forms: {', '.join(t for t, _ in common)}\n")

    from ladder.registry import Registry
    for label, db in (("MH only", a.db), ("plus ENTRY synonyms", a.db_all)):
        if not P(db).is_file():
            print(f"  {label:22} {db} not built", file=sys.stderr)
            continue
        st = stratify(docs, Registry(db))
        n = sum(v for k, v in st.items() if k != "not_in_vocabulary")
        print(f"  {label}")
        for k in ("identical", "subset", "partial", "none"):
            if st.get(k):
                print(f"    {k:11} {st[k]:5}  {st[k]/n:6.1%}")
        if st.get("not_in_vocabulary"):
            print(f"    {'absent':11} {st['not_in_vocabulary']:5}  "
                  f"— the id is not in this index")
        print()

"""LGL and TR-News as ladder corpora — two more points for the calibration set.

WHY THESE TWO

`scripts/preflight_rungs.py` and `ladder/relations.py` carry thresholds tuned on
three corpora: 2% false rejections, 10% minimum coverage, `worst > 50` for name
ambiguity. All are defensible and none is independently validated, and that is
the one weakness in this tooling that more work can actually close.

These are the cheapest two points available. Both ship in the GeoWebNews
repository's `data/Corpora/`, both use GeoNames, and the 13.4M-row index is
already built — so the marginal cost is an adapter and no download at all.

**They add points, not diversity.** Both are geoparsing, so they cannot say
whether a threshold holds outside geography; a biomedical or legal corpus would
be worth more per unit of effort. Stated here so the calibration record does not
read as five independent regimes when it is three.

BETTER SHAPED THAN GEOWEBNEWS, AND IT MATTERS

GeoWebNews gives a canonical NAME and coordinates and no identifier, so
`corpus_geo.resolve_ids` had to guess one — `codes_for_term(name)[0]` — and
picked a Brooklyn in South Africa. Scored against those invented ids, 97 of one
run's 240 "wrong" answers carried a label identical to gold's.

These two carry `<gaztag geonameid="4314550">` on every mention. **The answer key
supplies the answer**, which is what an answer key is for, and no resolution step
can go wrong because there is no resolution step.

    LGL       588 articles, local US news, deliberately ambiguous small places
    TR-News   118 articles, global and local news

SHAPE

    <article docid="...">
      <text><![CDATA[ ... ]]></text>
      <toponyms>
        <toponym>
          <start>0</start><end>10</end><phrase>Alexandria</phrase>
          <gaztag geonameid="4314550">
            <name>Alexandria</name><fclass>P</fclass><lat>31.3</lat>...

Offsets are into the CDATA text. Verified rather than trusted — see
`load_corpus`, which drops a mention whose span does not land and counts it.
"""
from __future__ import annotations

import os
import re
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

from ladder.corpus import Document, GoldMention
from ladder.corpus_geo import overlap_stratum, make_splits, write_splits, read_split  # noqa: F401

REACTION = "reaction"          # the ladder's scored entity type

#: Which file each corpus name maps to inside the Corpora directory.
FILES = {"lgl": "lgl.xml", "trnews": "TR-News.xml", "geovirus": "GeoVirus.xml"}


def load_corpus(root: str | os.PathLike, *, corpus: str = "lgl",
                documents: int | None = None, **_) -> dict[str, Document]:
    """Read one of the XML corpora. `root` is the `data/Corpora` directory.

    `corpus` selects the file. GeoVirus is listed and NOT recommended: it links
    to Wikipedia rather than GeoNames, so its ids cannot be checked against the
    index every other geo arm uses, and an arm whose vocabulary differs is not
    comparable with the arms it would sit beside.
    """
    fname = FILES.get(corpus)
    if fname is None:
        raise ValueError(f"unknown corpus {corpus!r} — one of {sorted(FILES)}")
    path = Path(root) / fname
    if not path.is_file():
        raise FileNotFoundError(
            f"{path} not found. These ship inside the GeoWebNews repository:\n"
            "    git clone --depth 1 https://github.com/milangritta/"
            "Pragmatic-Guide-to-Geoparsing-Evaluation")

    docs: dict[str, Document] = {}
    dropped = Counter()

    for i, art in enumerate(ET.parse(path).getroot().findall("article")):
        if documents is not None and len(docs) >= documents:
            break
        text_el = art.find("text")
        if text_el is None or not (text_el.text or "").strip():
            dropped["no_text"] += 1
            continue
        text = text_el.text
        doc_id = f"{corpus.upper()}.{art.get('docid') or i:0>6}"
        mentions: list[GoldMention] = []

        tops = art.find("toponyms")
        for top in (tops.findall("toponym") if tops is not None else []):
            phrase = (top.findtext("phrase") or "").strip()
            gaz = top.find("gaztag")
            gid = gaz.get("geonameid") if gaz is not None else None
            if not phrase or not gid:
                # A toponym with no gazetteer id is unanswerable rather than
                # wrong, and belongs outside the denominator with a reason.
                dropped["no_geonameid"] += 1
                continue
            try:
                start = int(top.findtext("start"))
                end = int(top.findtext("end"))
            except (TypeError, ValueError):
                dropped["bad_offset"] += 1
                continue

            # Grounding is CHECKED, not trusted. GeoWebNews had two offsets in
            # 2,401 that did not land, and finding that by hand is what made it
            # a check rather than an assumption.
            if text[start:end] != phrase:
                dropped["offset_mismatch"] += 1
                continue

            canonical = (gaz.findtext("name") or phrase).strip()
            mentions.append(GoldMention(
                doc_id=doc_id,
                index=len(mentions),
                entity_type=REACTION,
                # The overlap stratum, computed from the answer key alone. This
                # is the independent variable of the whole geo line of work and
                # it costs nothing to carry.
                cadec_type=overlap_stratum(phrase, canonical),
                text=phrase,
                spans=[(start, end)],
                sct=[gid],
                gold_kind="toponym",
            ))

        docs[doc_id] = Document(doc_id=doc_id, drug_group=corpus,
                                text=text, mentions=mentions)

    if dropped:
        import sys
        print(f"[corpus_geoxml:{corpus}] dropped {dict(dropped)}", file=sys.stderr)
    return docs


def gold_records(docs: dict[str, Document], doc_ids: list[str]) -> list[GoldMention]:
    return [m for d in doc_ids for m in docs[d].mentions]


if __name__ == "__main__":
    import argparse
    import sys

    ap = argparse.ArgumentParser(
        description="Inspect LGL / TR-News, and measure the stratum split on gold.")
    ap.add_argument("--root", default="data/gwn/Corpora")
    ap.add_argument("--corpus", default="lgl", choices=sorted(FILES))
    ap.add_argument("--db", default="ladder/cache/geonames.sqlite")
    a = ap.parse_args()

    docs = load_corpus(a.root, corpus=a.corpus)
    gold = [m for d in docs.values() for m in d.mentions]
    print(f"\n  {a.corpus}: {len(docs)} documents · {len(gold)} gold mentions\n")

    strata = Counter(m.cadec_type for m in gold)
    print("  lexical-overlap stratum, from gold alone:")
    for k in ("identical", "subset", "partial", "none", "empty"):
        if strata.get(k):
            print(f"    {k:11} {strata[k]:5}  {strata[k]/len(gold):6.1%}")

    if Path(a.db).is_file():
        from ladder.registry import Registry
        reg = Registry(a.db)
        present = sum(1 for m in gold if reg.exists(m.sct[0]))
        print(f"\n  ids present in the index: {present} of {len(gold)} "
              f"({present/len(gold):.1%})")
    else:
        print(f"\n  {a.db} not built — scripts/build_geo_index.py", file=sys.stderr)
    print()

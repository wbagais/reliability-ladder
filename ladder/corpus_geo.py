"""GeoWebNews as a ladder corpus — the third domain, and the first where the
lexical-overlap axis is a CONTROLLED VARIABLE rather than a comparison between
corpora.

WHY THIS CORPUS

CADEC and FiNER each sit at one point on the axis that decides whether rung 1's
free check can fire at all — how much the extracted span shares, as words, with
the concept's own name:

    CADEC        "chronic pain"  vs  |Chronic pain|                42% match
    FiNER-139    "47.6"          vs  |EffectiveIncomeTaxRate...|    0% match

Two points is a comparison between two tasks, two vocabularies and two prompts,
so the axis is confounded with everything else. GeoWebNews contains all four
regimes AT ONCE, under one model, one prompt and one check. Measured on the
2,401 gold mentions before any code was written:

    identical           "Washington Square" -> Washington Square       40.4%
    surface is subset   "Britain"           -> United Kingdom of ...   24.7%
    some shared words                                                   4.9%
    NO shared word      "French"            -> Republic of France      29.9%

That last group is not noise. It is four systematic phenomena:

    demonyms         French/Chinese/Nigerian -> the polity's official name
    abbreviations    US, UK, EU, DPRK, N.J., B.C., Calif.
    exonyms          Moscow -> Moskva; Italy -> Repubblica Italiana
    metonymy         Congress -> United States Capitol; Oval Office -> White House

The last of those is worth noticing before any number is read: the annotators
resolved the BUILDING an institution sits in. That is a defensible reading of
"where", and it is invisible to any string comparison, so it will land in BAND
and stay there no matter how good the model is.

WHAT THIS BUYS THAT A SECOND MEDICAL CORPUS WOULD NOT

Rung 1's ACCEPT lane is the one thing on this ladder that demonstrably paid —
80-89% correct across five model families spanning a factor of 2.8 in headline
F1. The open question is whether that is a property of SNOMED or of lexical
comparability. Here the lane's correctness can be computed PER STRATUM with the
model held constant, so the mechanism is measured rather than inferred.

If correctness is ~85% in the identical stratum and collapses in the no-overlap
stratum, the explanation holds. If it is FLAT across strata, lexical overlap is
not the mechanism and the 85% needs a different one — which would be the more
interesting outcome and must be reported as prominently.

SHAPE, and how it differs from the other two

  * Genuinely span-plus-code over real prose, which is CADEC's shape rather than
    FiNER's token-level IOB2. `sct` carries the GeoNames ID.
  * NO `vocab_geo.py` exists, deliberately. `ladder/registry.py`'s schema turned
    out to carry nothing SNOMED-specific, so a GeoNames index built into the
    same two tables is read by the SAME `Registry` class. The third corpus is
    therefore checked by the same code as the first — structurally, not merely
    by intention. See scripts/build_geo_index.py.
  * Two of rung 1's three free checks are VACUOUS here. GeoNames has no
    retirement and no semantic hierarchy, so `is_active` and `is_finding` are
    true by construction, exactly as on FiNER. Only `exists` and
    `lexical_match` do real work.
  * The vocabulary is 13,463,738 places against SNOMED's 129,675 — two orders of
    magnitude larger, so retrieval is a harder search rather than an easier one.

FIELD REUSE, the same wart as FiNER and for the same reason

`GoldMention` and `Document` are imported unchanged. Two fields are
CADEC-shaped and are reused rather than renamed, because renaming them would
touch every rung:

    cadec_type    carries the OVERLAP STRATUM — identical | subset | partial |
                  none. This is not a hack for its own sake: the stratum is the
                  independent variable of this whole arm, and putting it on the
                  gold record is what makes a per-stratum breakdown possible
                  without a second join.
    drug_group    carries the source document number.

`schemas/adapter.py` is listed in the plan as one of the three contracts and was
never written, so there is no declared corpus interface to conform to — only a
shape to imitate. That absence cost the FiNER port sixteen edits and it costs
this one the same reuse.

DATA, and the trap in it

Text lives in `data/Geocoding/files/N` numbered FROM ZERO, and line N of
`gwn_full.txt` corresponds to `files/N`. Gold offsets are computed against the
**UTF-8** decoding. This matters: the files round-trip byte-for-byte as latin-1,
which makes latin-1 look correct, and under it only 6 of the first document's 14
offsets land. Under UTF-8 all 14 do, because a multi-byte character counts as
one and the drift accumulates one per non-ASCII character passed. Measured over
all 200 documents: 2,399 of 2,401 offsets exact, the two failures both in
document 19 and both dropped with a counted reason rather than silently.

Licence GPL-3.0, so this arm is redistributable like FiNER and unlike CADEC.
"""
from __future__ import annotations

import json
import os
import random
import re
from collections import Counter
from pathlib import Path

from ladder.corpus import Document, GoldMention

REACTION = "reaction"          # the ladder's scored entity type; places have one

#: Fields in a gwn_full.txt record, ',,'-separated, '||'-joined per document.
_CANON, _SURFACE, _LAT, _LON, _START, _END = range(6)

_PUNCT = re.compile(r"[^a-z0-9 ]")


def _tokens(s: str) -> set[str]:
    """Same normalisation the offline stratum analysis used, kept here so the
    published distribution and the shipped code cannot drift apart."""
    return set(_PUNCT.sub(" ", (s or "").lower()).split())


def overlap_stratum(surface: str, canonical: str) -> str:
    """Which lexical regime this mention belongs to — the arm's independent
    variable.

    Computed from the ANSWER KEY, not from any model output, so it is a property
    of the corpus and is fixed before a single call is made.
    """
    a, b = _tokens(surface), _tokens(canonical)
    if not a or not b:
        return "empty"
    if a == b:
        return "identical"
    if a <= b:
        return "subset"
    if a & b:
        return "partial"
    return "none"


def load_corpus(root: str | os.PathLike, *, documents: int | None = None,
                geonames_db: str | os.PathLike | None = None,
                **_) -> dict[str, Document]:
    """Read the raw articles and their gold toponyms.

    `root` is the repository's `data/Geocoding` directory, holding `files/` and
    `gwn_full.txt`.
    """
    root = Path(root)
    gold_file = root / "gwn_full.txt"
    files_dir = root / "files"
    if not gold_file.is_file():
        raise FileNotFoundError(
            f"{gold_file} not found. Clone the corpus:\n"
            "    git clone https://github.com/milangritta/"
            "Pragmatic-Guide-to-Geoparsing-Evaluation")

    docs: dict[str, Document] = {}
    dropped = Counter()

    for i, line in enumerate(gold_file.read_text(encoding="utf-8").splitlines()):
        if documents is not None and len(docs) >= documents:
            break
        text_path = files_dir / str(i)
        if not text_path.is_file():
            dropped["no_text_file"] += 1
            continue

        # UTF-8, deliberately. See the module docstring: latin-1 round-trips the
        # bytes and silently shifts every offset after the first non-ASCII char.
        text = text_path.read_text(encoding="utf-8", errors="replace")
        doc_id = f"GWN.{i:03d}"
        mentions: list[GoldMention] = []

        for raw in line.strip().split("||"):
            f = raw.split(",,")
            if len(f) < 6:
                if raw.strip():
                    dropped["malformed_record"] += 1
                continue
            canonical = f[_CANON].strip()
            surface = f[_SURFACE].strip()
            try:
                start, end = int(f[_START]), int(f[_END])
            except ValueError:
                dropped["bad_offset_field"] += 1
                continue
            if not canonical or not surface:
                dropped["empty_name"] += 1
                continue

            # Grounding is checked here rather than trusted. Two of the 2,401
            # gold offsets do not land (both in document 19); they are counted,
            # not repaired, because a repaired offset is an invented one.
            if text[start:end] != surface:
                dropped["offset_mismatch"] += 1
                continue

            mentions.append(GoldMention(
                doc_id=doc_id,
                index=len(mentions),
                entity_type=REACTION,
                cadec_type=overlap_stratum(surface, canonical),
                text=surface,
                spans=[(start, end)],
                sct=[canonical],       # resolved to a GeoNames id below
                gold_kind="toponym",
            ))

        docs[doc_id] = Document(doc_id=doc_id, drug_group=str(i),
                                text=text, mentions=mentions)

    # Resolve canonical NAMES to GeoNames ids HERE, not in a separate step.
    # gwn_full.txt carries the name and coordinates but no geonameid, and an
    # earlier version left resolution to a helper only __main__ called — so
    # every other caller saw `sct` holding "Republic of France" and the free
    # existence check failed on 100% of a PERFECT answer set. A loader that
    # returns records the vocabulary cannot read is not loaded.
    db = geonames_db or "ladder/cache/geonames.sqlite"
    if Path(db).is_file():
        from ladder.registry import Registry
        dropped.update(resolve_ids(docs, Registry(db)))

    if dropped:
        import sys
        print(f"[corpus_geo] {dict(dropped)}", file=sys.stderr)
    return docs


def resolve_ids(docs: dict[str, Document], registry) -> Counter:
    """Turn canonical NAMES into GeoNames IDs, in place.

    `gwn_full.txt` carries the canonical name and coordinates but not the
    geonameid, so the id is looked up through the SAME registry rung 1 will use.
    A name the vocabulary does not hold leaves `sct` empty, which the ladder
    already models as concept_less — the honest state for "the answer is not in
    the answer space".

    Measured: 98.1% of the 575 distinct canonical names are present in the full
    allCountries index. A curated subset would have been far worse — 37.4% for
    cities15000 — which is why the full 13.4M-row dump was chosen.
    """
    stats = Counter()
    cache: dict[str, list[str]] = {}
    for d in docs.values():
        for m in d.mentions:
            name = m.sct[0] if m.sct else ""
            if name not in cache:
                try:
                    cache[name] = list(registry.codes_for_term(name) or [])
                except Exception:
                    cache[name] = []
            ids = cache[name]
            if ids:
                m.sct = [ids[0]]
                stats["resolved"] += 1
                if len(ids) > 1:
                    stats["ambiguous_name"] += 1
            else:
                m.sct = []
                stats["not_in_gazetteer"] += 1
    return stats


def make_splits(docs: dict[str, Document], *, n_dev: int = 40,
                n_test: int = 60, seed: int = 0, **_) -> dict[str, list[str]]:
    """Deterministic dev/test/pool.

    Sizes match CADEC's so the three arms are comparable at a glance. No
    stratification: CADEC stratifies by drug family because a drug group is a
    real confound there, and the obvious analogue here — stratifying by overlap
    regime — would be stratifying on the DEPENDENT variable, which would bias
    exactly the number this arm exists to measure. Saying that plainly beats
    inventing a scheme.
    """
    ids = sorted(docs)
    random.Random(seed).shuffle(ids)
    return {"dev": ids[:n_dev],
            "test": ids[n_dev:n_dev + n_test],
            "pool": ids[n_dev + n_test:]}


def write_splits(splits: dict[str, list[str]], out_dir: str | os.PathLike,
                 meta: dict) -> None:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    for name, ids in splits.items():
        (out / f"{name}.json").write_text(
            json.dumps({"doc_ids": ids, "meta": meta}, indent=2))


def read_split(out_dir: str | os.PathLike, name: str) -> list[str]:
    p = Path(out_dir) / f"{name}.json"
    if not p.is_file():
        raise FileNotFoundError(
            f"{p} not found — run `python -m ladder.run init "
            "--manifest manifest.geo.json` first")
    return json.loads(p.read_text())["doc_ids"]


def gold_records(docs: dict[str, Document], doc_ids: list[str]) -> list[GoldMention]:
    return [m for d in doc_ids for m in docs[d].mentions]


if __name__ == "__main__":
    import argparse
    import sys

    ap = argparse.ArgumentParser(description="Inspect the GeoWebNews arm")
    ap.add_argument("--root", default="data/gwn/Geocoding")
    ap.add_argument("--db", default="ladder/cache/geonames.sqlite")
    a = ap.parse_args()

    docs = load_corpus(a.root)
    gold = [m for d in docs.values() for m in d.mentions]
    print(f"{len(docs)} documents · {len(gold)} gold mentions\n")

    strata = Counter(m.cadec_type for m in gold)
    print("overlap stratum — the arm's independent variable, from gold alone:")
    for k in ("identical", "subset", "partial", "none", "empty"):
        if strata.get(k):
            print(f"   {k:11} {strata[k]:5}  {strata[k]/len(gold):6.1%}")

    if Path(a.db).is_file():
        from ladder.registry import Registry
        reg = Registry(a.db)
        print(f"\nresolving names against {reg.release}")
        print("  ", dict(resolve_ids(docs, reg)))
    else:
        print(f"\n{a.db} not built — run scripts/build_geo_index.py", file=sys.stderr)

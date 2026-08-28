"""FiNER-139 as a ladder corpus — the second domain.

The ladder was built on CADEC and every finding it produced was shaped by one
fact: the extractor did not know SNOMED, so it fabricated codes, and every
rung's bet was made against that gap. FiNER-139 has 139 tags. They fit in a
prompt. The gap is gone, and the odds on every rung change at once.

This module exposes the same five functions `ladder/corpus.py` does, so the
runner does not branch on which corpus is loaded:

    load_corpus(root)              -> {doc_id: Document}
    read_split(dir, name)          -> [doc_id]
    make_splits(...)               -> {name: [doc_id]}
    write_splits(splits, dir, meta)
    gold_records(docs, doc_ids)    -> [GoldMention]

`GoldMention` and `Document` are imported unchanged from ladder.corpus. Two of
their fields are CADEC-shaped and are reused rather than renamed, because
renaming them would touch every rung:

    cadec_type    carries the XBRL tag NAME without its IOB2 prefix
    drug_group    carries the source split (test/validation/train)

That reuse is a wart and it is deliberate. `schemas/adapter.py` is listed in the
plan as one of the three contracts and was never written, so there is no
declared corpus interface to conform to — only a shape to imitate. That absence
is the first finding of this port and it belongs in decisions.md.

SHAPE DIFFERENCES, all of which change what a number means:

  * Token-level IOB2, not span-plus-code. The tag IS the answer; there is no
    separate identifier to look up. `sct` carries the tag name, so rung 1's
    existence check becomes membership in a set of 139.
  * A "document" is N consecutive sentences, grouped here, because FiNER ships
    sentences and tags depend on context rather than on the token. Grouping is
    declared in the manifest, not assumed.
  * `text` is the tokens joined by single spaces — NOT the original filing.
    Tokenisation already separated punctuation upstream, so the original is not
    recoverable. Offsets are computed against the joined string, so grounding is
    internally consistent, which is what rung 1 actually checks.
  * Tagged tokens are numeric and meaningless alone: "47.6" is
    EffectiveIncomeTaxRateContinuingOperations only because of the sentence
    around it.
"""
from __future__ import annotations

import json
import os
import random
from pathlib import Path

from ladder.corpus import Document, GoldMention

REACTION = "reaction"          # the ladder's scored entity type; FiNER has one


def tag_names(root: str | os.PathLike, split: str = "test") -> list[str]:
    """The 139 type names, from the data rather than from a hardcoded list.

    IOB2 gives B- and I- variants of each type, so the raw label count is higher
    than 139 (154 distinct labels appear in test). Stripping the prefix and
    deduplicating recovers the type set, and reading it from the corpus means it
    cannot drift from what is actually there.
    """
    seen: set[str] = set()
    with open(Path(root) / f"{split}.jsonl", encoding="utf-8") as fh:
        for line in fh:
            for t in json.loads(line)["ner_tags"]:
                if t != "O":
                    seen.add(t.split("-", 1)[1] if "-" in t else t)
    return sorted(seen)


def _sentences(root: Path, split: str):
    with open(root / f"{split}.jsonl", encoding="utf-8") as fh:
        for line in fh:
            r = json.loads(line)
            if r.get("tokens"):
                yield r


def _spans_from_iob(tokens: list[str], tags: list[str]) -> list[tuple[int, int, str]]:
    """IOB2 -> [(char_start, char_end, tag_name)] over ' '.join(tokens).

    B- opens a span, I- extends the one before it, O closes. Almost every FiNER
    span is a single B- token, but I- is handled rather than assumed away — an
    adapter that silently dropped multi-token spans would under-count gold and
    nothing downstream would notice.
    """
    offsets, pos = [], 0
    for tok in tokens:
        offsets.append((pos, pos + len(tok)))
        pos += len(tok) + 1                       # the joining space

    out: list[tuple[int, int, str]] = []
    cur_start = cur_end = None
    cur_tag = None
    for i, tag in enumerate(tags):
        if tag == "O":
            if cur_tag is not None:
                out.append((cur_start, cur_end, cur_tag))
                cur_tag = None
            continue
        prefix, name = (tag.split("-", 1) + [""])[:2] if "-" in tag else ("B", tag)
        s, e = offsets[i]
        if prefix == "B" or cur_tag is None or name != cur_tag:
            if cur_tag is not None:
                out.append((cur_start, cur_end, cur_tag))
            cur_start, cur_end, cur_tag = s, e, name
        else:                                      # I- continuing the same type
            cur_end = e
    if cur_tag is not None:
        out.append((cur_start, cur_end, cur_tag))
    return out


def load_corpus(root: str | os.PathLike, *, split: str = "test",
                sentences_per_document: int = 10, documents: int | None = 100,
                order: str = "file_order", seed: int = 0,
                **_) -> dict[str, Document]:
    """Group consecutive sentences into pseudo-documents.

    Sampling is NATURAL RATE: sentences are taken in file order and grouped,
    tagged or not. 17.3% of test sentences carry any tag, so roughly a sixth of
    what the model sees has anything to find. Taking only tagged sentences would
    give the same gold volume for a fifth of the compute AND would remove the
    model's chance to correctly find nothing — which CADEC could never test,
    because every post has mentions.

    FILE ORDER, not random: consecutive sentences come from the same filing, so
    grouping preserves discourse context. Random grouping is a different task
    and would have to be declared as one.
    """
    root = Path(root)
    if not (root / f"{split}.jsonl").is_file():
        raise FileNotFoundError(
            f"{split}.jsonl not found under {root}. FiNER-139 is CC-BY-SA-4.0: "
            "download finer139.zip from huggingface.co/datasets/nlpaueb/finer-139 "
            "and unzip it there. Note that load_dataset() does NOT work — the "
            "canonical loader is a dataset script and datasets>=5 refuses to run "
            "those."
        )

    rows = list(_sentences(root, split))
    if order == "shuffled":
        random.Random(seed).shuffle(rows)
    elif order != "file_order":
        raise ValueError(f"order={order!r}; expected 'file_order' or 'shuffled'")

    docs: dict[str, Document] = {}
    n_docs = documents if documents is not None else len(rows) // sentences_per_document
    for d in range(n_docs):
        chunk = rows[d * sentences_per_document:(d + 1) * sentences_per_document]
        if not chunk:
            break
        doc_id = f"FINER.{split}.{d:04d}"

        tokens: list[str] = []
        tags: list[str] = []
        for r in chunk:
            tokens += r["tokens"]
            tags += r["ner_tags"]
        text = " ".join(tokens)

        mentions = []
        for i, (s, e, name) in enumerate(_spans_from_iob(tokens, tags)):
            mentions.append(GoldMention(
                doc_id=doc_id,
                index=i,
                entity_type=REACTION,
                cadec_type=name,        # the XBRL type name; field reused, see module docstring
                text=text[s:e],
                spans=[(s, e)],
                sct=[name],             # the tag IS the code
                gold_kind="single",     # no post-coordination, no disjunction
                meddra=[],
            ))
        docs[doc_id] = Document(
            doc_id=doc_id, drug_group=split, text=text, mentions=mentions
        )
    return docs


def make_splits(docs: dict[str, Document], *, n_dev: int = 40,
                n_test: int = 60, seed: int = 0, **_) -> dict[str, list[str]]:
    """Deterministic dev/test/pool over the pseudo-documents.

    No stratification. CADEC stratifies by drug family because a drug group is a
    real confound there; FiNER's grouping is already sequential over filings and
    there is no equivalent axis. Saying that plainly beats inventing one.
    """
    ids = sorted(docs)
    random.Random(seed).shuffle(ids)
    return {
        "dev": ids[:n_dev],
        "test": ids[n_dev:n_dev + n_test],
        "pool": ids[n_dev + n_test:],
    }


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
            "--manifest manifest.finer.json` first")
    return json.loads(p.read_text())["doc_ids"]


def gold_records(docs: dict[str, Document], doc_ids: list[str]) -> list[GoldMention]:
    return [m for d in doc_ids for m in docs[d].mentions]


if __name__ == "__main__":
    import argparse
    import collections

    ap = argparse.ArgumentParser(description="inspect the FiNER adapter")
    ap.add_argument("--root", default="data/finer/extracted")
    ap.add_argument("--split", default="test")
    ap.add_argument("--sentences", type=int, default=10)
    ap.add_argument("--documents", type=int, default=100)
    a = ap.parse_args()

    docs = load_corpus(a.root, split=a.split,
                       sentences_per_document=a.sentences, documents=a.documents)
    mentions = [m for d in docs.values() for m in d.mentions]
    types = collections.Counter(m.cadec_type for m in mentions)
    empty = sum(1 for d in docs.values() if not d.mentions)

    print(f"documents          {len(docs)}  ({a.sentences} sentences each)")
    print(f"gold mentions      {len(mentions)}")
    print(f"distinct tags      {len(types)} of {len(tag_names(a.root, a.split))} in the split")
    print(f"documents with none {empty}  <- the model's chance to correctly find nothing")
    print(f"multi-token spans  {sum(1 for m in mentions if ' ' in m.text)}")
    print()
    print("most frequent:")
    for t, n in types.most_common(5):
        print(f"  {n:4}  {t}")
    print()
    d0 = next(d for d in docs.values() if d.mentions)
    m0 = d0.mentions[0]
    s, e = m0.spans[0]
    print(f"grounding check on {m0.record_id}:")
    print(f"  quoted     {m0.text!r}")
    print(f"  at offsets {d0.text[s:e]!r}")
    print(f"  match      {d0.text[s:e] == m0.text}")

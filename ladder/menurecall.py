"""Menu recall@k — does the right answer reach S2's candidate list at all?

    python -m ladder.menurecall --prefix ladder/cache/keywords --k 1 20

WHY THIS EXISTS: rung 0's S2 does two things — RETRIEVE a menu, then PICK from
it. A pick can only ever recover what retrieval put on the menu, so the menu's
recall is a hard ceiling on the whole step and it is measurable with no model
call, no split and no run. That makes it the right first question to ask of any
retriever change: if gold does not reach the menu more often, there is nothing
for the pick to convert and the arm is not worth building.

THE THREE THINGS A RECALL NUMBER CAN BE SILENTLY WRONG ABOUT, all pinned by
tests in `tests/test_menu_recall.py`:

  DENOMINATOR  scorable CODED REACTION mentions with the manifest's exclusions
               applied - 6,595 over the whole CADEC corpus. A concept_less
               mention has no code for a menu to carry; a drug is outside the
               findings-and-disorders table by construction; an excluded
               mention is one the ladder does not score. Any of the three
               quietly in or out of the denominator moves every row.
  RANK         0-based, and recall@k counts rank < k. The off-by-one inflates
               every cell by one slot's worth.
  HIT RULE     ANY of a multi-code mention's gold codes counts. The menu's job
               is reachability, and an `all_of` mention is reachable as soon as
               one of its answers is on the list.

Queries are DEDUPED before searching - 6,595 mentions carry 3,272 distinct
strings and embedding the same span twice cannot change its ranking. The
dedupe is on the QUERY only, never on the (query, gold) pair: two mentions
sharing text and disagreeing on the answer are two separate hits or misses.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from typing import Any, Iterable, Sequence

from ladder.corpus import GoldMention

#: The ks the project's recorded baselines are quoted at.
DEFAULT_KS = (1, 5, 10, 20, 50)


def scorable_gold(
    mentions: Iterable[GoldMention], exclusions: set[str], entity_type: str = "reaction"
) -> list[GoldMention]:
    """The denominator: coded mentions of `entity_type`, exclusions applied."""
    return [
        m
        for m in mentions
        if m.entity_type == entity_type and m.sct and m.record_id not in exclusions
    ]


def rank_of_gold(hits: Sequence[dict], gold_codes: set[str]) -> int | None:
    """0-based position of the first candidate carrying a gold code, or None."""
    for i, hit in enumerate(hits):
        if str(hit.get("code")) in gold_codes:
            return i
    return None


def recall_at(ranks: Sequence[int], ks: Iterable[int], n: int) -> dict[int, float]:
    """Fraction of `n` mentions whose gold code sat at rank < k.

    `ranks` holds the HITS only; the misses live in `n`. Passing a denominator
    smaller than the hit count is a bookkeeping error, not a 100% recall, so it
    raises rather than reporting a number above one.
    """
    ranks = list(ranks)
    if n < len(ranks):
        raise ValueError(
            f"{len(ranks)} hits against a denominator of {n}. The denominator "
            "must count every mention, hit and miss alike."
        )
    return {int(k): (sum(1 for r in ranks if r < k) / n if n else 0.0) for k in ks}


def probe(index: Any, mentions: Sequence[GoldMention], ks: Iterable[int] = DEFAULT_KS,
          progress: bool = False) -> dict:
    """Search once per distinct query string, score once per mention."""
    ks = sorted(int(k) for k in ks)
    depth = max(ks) if ks else 20
    queries = sorted({m.text.strip() for m in mentions})
    menus: dict[str, list[dict]] = {}
    for i, q in enumerate(queries):
        menus[q] = list(index.search(q, k=depth))
        if progress and i and not i % 250:
            print(f"[menurecall] {i:,}/{len(queries):,}", file=sys.stderr)

    ranks, misses = [], []
    by_record: dict[str, int | None] = {}
    for m in mentions:
        r = rank_of_gold(menus.get(m.text.strip(), []), {str(c) for c in m.sct})
        by_record[m.record_id] = r
        if r is None:
            misses.append(m.record_id)
        else:
            ranks.append(r)
    return {
        "n": len(mentions),
        "queries": len(queries),
        "depth": depth,
        "hits": len(ranks),
        "recall": recall_at(ranks, ks, len(mentions)),
        "ranks": ranks,
        "misses": misses,
        "by_record": by_record,
    }


def paired_recall_bootstrap(
    a: dict[str, int | None],
    b: dict[str, int | None],
    mentions: Sequence[GoldMention],
    k: int = 20,
    n_boot: int = 1000,
    seed: int = 0,
    alpha: float = 0.05,
) -> dict[str, float | int]:
    """recall@k of arm A minus arm B, resampled over DOCUMENTS, paired.

    Two separate intervals cannot be compared: they do not use the same
    resampled documents, and the pairing is what makes the band usable. Each
    draw scores both arms over the SAME documents and reports `a - b`.

    DOCUMENTS, not mentions, for the same reason `score.bootstrap_ci` uses
    them: mentions inside one post share an author, a topic and a vocabulary,
    so resampling mentions would claim 6,595 independent draws and report a
    band too tight. Resampling is WITH REPLACEMENT and keeps multiplicity.

    Both arms must have answered the SAME mentions. A missing record_id is a
    pairing error, and pairing a gap silently is how one arm's easier subset
    becomes the other arm's improvement.
    """
    ids = [m.record_id for m in mentions]
    missing = [i for i in ids if i not in a or i not in b]
    if missing:
        raise ValueError(
            f"{len(missing)} mention(s) scored by only one arm "
            f"(first: {missing[0]}). Two arms that did not answer the same "
            "questions cannot be paired."
        )

    def hit(ranks: dict[str, int | None], rid: str) -> int:
        r = ranks[rid]
        return 1 if r is not None and r < k else 0

    per_doc: dict[str, list[int]] = {}
    for m in mentions:
        acc = per_doc.setdefault(m.doc_id, [0, 0, 0])
        acc[0] += hit(a, m.record_id)
        acc[1] += hit(b, m.record_id)
        acc[2] += 1
    doc_ids = sorted(per_doc)

    def delta(picks: Sequence[str]) -> float:
        ha = hb = n = 0
        for d in picks:
            x, y, c = per_doc[d]
            ha, hb, n = ha + x, hb + y, n + c
        return (ha - hb) / n if n else 0.0

    rng = random.Random(seed)
    draws = [delta(rng.choices(doc_ids, k=len(doc_ids))) for _ in range(n_boot)]
    draws_sorted = sorted(draws)

    def pct(q: float) -> float:
        i = min(int(q * len(draws_sorted)), len(draws_sorted) - 1)
        return draws_sorted[i]

    return {
        "k": int(k),
        "n": len(ids),
        "docs": len(doc_ids),
        "point": delta(doc_ids),
        "mean": sum(draws) / len(draws) if draws else 0.0,
        "lo": pct(alpha / 2),
        "hi": pct(1 - alpha / 2),
        "n_boot": int(n_boot),
        "seed": int(seed),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--prefix", default="ladder/cache/keywords",
                    help="dense index prefix (<prefix>.vectors.npy + .rows.json)")
    ap.add_argument("--model", default=None, help="embedder model for the queries")
    ap.add_argument("--cadec-root", default="data/cadec/data/cadec")
    ap.add_argument("--exclusions", default="data/exclusions.csv")
    ap.add_argument("--k", nargs="*", type=int, default=list(DEFAULT_KS))
    ap.add_argument("--json", default=None)
    a = ap.parse_args(argv)

    from ladder.clean import load_exclusions
    from ladder.corpus import gold_records, load_corpus
    from ladder.embed import EmbeddingIndex, ollama_embedder

    docs = load_corpus(a.cadec_root)
    mentions = scorable_gold(
        gold_records(docs, sorted(docs)), load_exclusions(a.exclusions)
    )
    idx = EmbeddingIndex(
        a.prefix, ollama_embedder(a.model) if a.model else None
    )
    out = probe(idx, mentions, a.k, progress=True)
    out["prefix"], out["model"], out["rows"] = a.prefix, a.model, len(idx)
    print(f"n={out['n']}  queries={out['queries']}  rows={out['rows']:,}")
    for k in sorted(out["recall"]):
        print(f"  recall@{k:<3} {out['recall'][k] * 100:.1f}%")
    if a.json:
        for key in ("ranks", "misses"):
            out.pop(key, None)
        with open(a.json, "w", encoding="utf-8") as fh:
            json.dump(out, fh, indent=2)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

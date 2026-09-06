#!/usr/bin/env python3
"""
gold_span_stats.py — what a prompt writer needs to know, measured not guessed.

WHY THIS RUNS BEFORE ANY PROMPT IS WRITTEN

GeoWebNews's prompt block records its own provenance: *"Derived from
GeoWebNews's own gold over 2,399 mentions in 200 documents, not invented. 20.7%
of surface forms are multi-token; 12.7% are abbreviated or dotted (U.S., UK, EU,
N.J.)"*. FiNER's does the same over 407 mentions. Those two arms work. The four
that inherited CADEC's wording do not.

So the fix is not to write four plausible prompts. It is to measure four corpora
and let the numbers say what the prompt has to tell the model. A prompt written
from an impression of a corpus is the same error as a rate over an unnamed set:
it sounds specific and it is not anchored to anything.

WHAT IT MEASURES, AND WHY EACH ONE CHANGES THE WORDING

    multi-token share      whether to say "a phrase" or "a word"
    dotted / abbreviated   whether U.S. and E. coli need an explicit rule
    capitalised share      whether case is a usable cue or a trap
    leading article        whether "the United States" includes the article
    length in characters   whether to warn against sentence-long spans
    repeated surface forms whether the same mention recurs and must be
                           reported each time, which CADEC's prompt says
                           explicitly and the geo arms had to restate
    discontinuous          whether a mention can be two pieces
    commonest forms        the concrete examples a prompt should carry

    PYTHONPATH=. python3 scripts/gold_span_stats.py
    PYTHONPATH=. python3 scripts/gold_span_stats.py --corpus lgl --examples 20
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys
from collections import Counter

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

ARMS = {
    "lgl": "manifest.lgl.json",
    "trnews": "manifest.trnews.json",
    "linnaeus": "manifest.linnaeus.json",
    "bc5cdr": "manifest.bc5cdr.json",
    # the two that already have prompts, for comparison
    "geo": "manifest.geo.json",
    "psytar": "manifest.psytar.json",
}

_DOTTED = re.compile(r"\b[A-Z]\.")
_ALLCAPS = re.compile(r"^[A-Z][A-Z.&-]+$")


def stats(name: str, manifest: str, n_examples: int) -> None:
    from ladder.run import _corpus_for, _corpus_opts, _corpus_root

    man = json.loads(pathlib.Path(manifest).read_text())
    mod = _corpus_for(man)
    docs = mod.load_corpus(_corpus_root(man), **_corpus_opts(man))
    gold = [m for d in docs.values() for m in d.mentions]
    if not gold:
        print(f"\n  {name}: no gold mentions\n")
        return

    n = len(gold)
    texts = [m.text for m in gold]
    toks = [t.split() for t in texts]

    multi = sum(1 for t in toks if len(t) > 1)
    dotted = sum(1 for t in texts if _DOTTED.search(t))
    allcaps = sum(1 for t in texts if _ALLCAPS.match(t.strip()))
    capped = sum(1 for t in texts if t[:1].isupper())
    article = sum(1 for t in toks if t and t[0].lower() in ("the", "a", "an"))
    disc = sum(1 for m in gold if len(m.spans) > 1)
    lens = sorted(len(t) for t in texts)
    p50, p95 = lens[len(lens)//2], lens[int(len(lens)*0.95)]
    longest = max(texts, key=len)

    counts = Counter(t.lower() for t in texts)
    repeated = sum(v for v in counts.values() if v > 1)

    print(f"\n  ── {name} · {len(docs)} documents · {n} gold mentions "
          f"· {len(counts)} distinct surface forms\n")
    def row(label, k, note=""):
        print(f"      {label:26} {k:6} {k/n:6.1%}   {note}")
    row("multi-token", multi, "say 'a phrase' if high, 'a word' if low")
    row("contains an initial + dot", dotted, "U.S., E. coli — needs a rule")
    row("all-caps", allcaps)
    row("starts capitalised", capped, "case is a cue only if this is high")
    row("starts with an article", article, "does 'the' belong in the span?")
    row("discontinuous (>1 range)", disc, "can a mention be two pieces?")
    row("a form used more than once", repeated, "must each occurrence be reported?")
    print(f"      {'length, median / p95':26} {p50:6} {p95:6}   characters")
    print(f"      {'longest':26} {longest[:60]!r}")
    print(f"\n      commonest: "
          + ", ".join(f"{t!r}" for t, _ in counts.most_common(n_examples)))
    # A prompt carries examples; these are the ones the corpus actually uses.
    mid = [t for t in texts if len(t.split()) > 1][:6]
    if mid:
        print(f"      multi-token examples: " + ", ".join(repr(t) for t in mid))
    print()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", choices=sorted(ARMS))
    ap.add_argument("--examples", type=int, default=12)
    a = ap.parse_args()
    names = [a.corpus] if a.corpus else list(ARMS)
    for name in names:
        m = ARMS[name]
        if not pathlib.Path(m).is_file():
            print(f"\n  {name}: {m} not found\n")
            continue
        try:
            stats(name, m, a.examples)
        except Exception as exc:
            print(f"\n  {name}: FAILED — {exc}\n")
    print("  A prompt written from these numbers can say what the corpus does.")
    print("  A prompt written from an impression of the corpus cannot.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""
relations_report.py — which free checks have signal on which corpus.

One command, three corpora, no model calls. Answers in one place the question
that took this project five months and three ports to reach: given a corpus and
a vocabulary, WHICH deterministic relations can a free check use?

    PYTHONPATH=. python3 scripts/relations_report.py
    PYTHONPATH=. python3 scripts/relations_report.py --manifest manifest.geo.json
    PYTHONPATH=. python3 scripts/relations_report.py --records out/finer/*.records.jsonl

WHY IT RUNS ON GOLD BY DEFAULT

Every contradiction of a gold record is FALSE by construction, so gold gives
the false-rejection rate for nothing — no model, no run, no GPU. That is the
cheapest validation available and it is the one this project keeps proving
matters: CADEC's rung 1 went from 9.3% to 0.13% by being measured this way.

With `--records` it runs on model output instead and compares against gold,
which is the OTHER half. A relation is not validated until both are known: the
type relation scored 1.22% on gold and 35.71% on the model's own spans, and
only the pair says so.
"""
from __future__ import annotations

import argparse
import glob
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from ladder import relations as R


def adapter(man):
    name = (man.get("corpus") or {}).get("adapter", "cadec")
    if name == "finer":
        from ladder import corpus_finer as mod
    elif name == "geo":
        from ladder import corpus_geo as mod
    else:
        from ladder import corpus as mod
    return mod


def vocabulary(man):
    backend = (man.get("vocabulary") or {}).get("backend")
    if backend == "finer-tags":
        from ladder.vocab_finer import load
        root = man["corpus"].get("root") or man["corpus"]["cadec_root"]
        return load(root)
    from ladder.registry import Registry
    return Registry(man["vocabulary"]["snomed_db"])


def load(manifest: str, split: str):
    man = json.loads(pathlib.Path(manifest).read_text())
    mod = adapter(man)
    sampling = {k: v for k, v in (man["corpus"].get("sampling") or {}).items()
                if not k.startswith("_")}
    root = man["corpus"].get("root") or man["corpus"]["cadec_root"]
    docs = mod.load_corpus(root, **sampling)
    ids = mod.read_split(man["corpus"]["splits_dir"], split)
    gold = [m for d in ids for m in docs[d].mentions]
    sources = {d: docs[d].text for d in ids}
    return man, gold, sources


class Row:
    """A model record, shaped like a gold mention so relations see one thing."""
    __slots__ = ("text", "spans", "sct", "checks", "doc_id")

    def __init__(self, d):
        self.text = d.get("text")
        self.spans = d.get("spans")
        self.checks = d.get("checks") or {}
        self.doc_id = d.get("doc_id")
        code = d.get("sct") or (self.checks.get("withheld") or {}).get("sct")
        self.sct = code


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", default="manifest.json")
    ap.add_argument("--split", default="dev")
    ap.add_argument("--records", help="model records to measure on instead of gold")
    a = ap.parse_args()

    man, gold, sources = load(a.manifest, a.split)
    vocab = vocabulary(man)
    name = (man.get("corpus") or {}).get("name", a.manifest)

    if a.records:
        files = sorted(glob.glob(a.records))
        if not files:
            print(f"no records at {a.records}"); return 1
        rows = [Row(json.loads(l)) for l in open(files[0])]
        rows = [r for r in rows if r.spans]
        key = {(m.doc_id, m.spans[0][0]): (m.sct[0] if m.sct else None)
               for m in gold}

        def is_correct(rec):
            g = key.get((rec.doc_id, rec.spans[0][0]))
            code = rec.sct[0] if isinstance(rec.sct, list) and rec.sct else rec.sct
            return g is not None and code == g

        print(f"\n  {name} · {len(rows)} MODEL records · {files[0].split('/')[-1]}")
        res = R.measure(rows, sources, vocab, is_correct=is_correct)
        print(R.report(res, on="model output", corpus=name))
    else:
        print(f"\n  {name} · {len(gold)} GOLD mentions · split {a.split}")
        # On gold every record is correct by definition, so every contradiction
        # is false. That is the whole trick and it costs nothing.
        res = R.measure(gold, sources, vocab, is_correct=lambda _: True)
        print(R.report(res, on="gold", corpus=name))
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

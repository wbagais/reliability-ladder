#!/usr/bin/env python3
"""
reproduce.py — the article's findings, re-derived by the tool that came out of it.

WHY THIS IS THE STRONGEST THING THE TOOL CAN DO

Every eval tool claims it will catch problems. This one can point at a
published study and say: *these conclusions, from these commands, on these
corpora, now.* Nobody else in this space can, because nobody else has done the
measurement.

It is also a regression test on the findings themselves. If a claim in the
article stops reproducing — because the code moved, or a corpus changed, or a
threshold was retuned — this says so, and a paper whose claims silently stop
holding is the failure the paper is about.

WHAT IT DOES NOT DO

It does not re-run any model. Every claim below is derived from gold, from a
committed ledger, or from records already on disk. A reproduction that needs a
GPU is not a reproduction anyone will run.

Claims needing a model run to verify are listed and marked, not faked.

    PYTHONPATH=. python3 scripts/reproduce.py
    PYTHONPATH=. python3 scripts/reproduce.py --claim accept_lane
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

GREEN, RED, AMBER, DIM = "\033[32m", "\033[31m", "\033[33m", "\033[90m"
OFF = "\033[0m"
TTY = sys.stdout.isatty()


def c(colour: str, s: str) -> str:
    return f"{colour}{s}{OFF}" if TTY else s


class Claim:
    """One statement from the article, and the code that checks it."""

    def __init__(self, key, says, where, check, needs=""):
        self.key, self.says, self.where = key, says, where
        self.check, self.needs = check, needs

    def run(self) -> tuple[str, str]:
        if self.needs and not pathlib.Path(self.needs).exists():
            return "skip", f"needs {self.needs}"
        try:
            return self.check()
        except Exception as exc:
            return "error", f"{type(exc).__name__}: {exc}"


# ── the claims ──────────────────────────────────────────────────────────

def _corpus(manifest, split="dev"):
    man = json.loads(pathlib.Path(manifest).read_text())
    name = (man.get("corpus") or {}).get("adapter", "cadec")
    if name == "finer":
        from ladder import corpus_finer as mod
    elif name == "geo":
        from ladder import corpus_geo as mod
    else:
        from ladder import corpus as mod
    sampling = {k: v for k, v in (man["corpus"].get("sampling") or {}).items()
                if not k.startswith("_")}
    root = man["corpus"].get("root") or man["corpus"]["cadec_root"]
    docs = mod.load_corpus(root, **sampling)
    ids = mod.read_split(man["corpus"]["splits_dir"], split)
    return man, docs, ids


def _vocab(man):
    if (man.get("vocabulary") or {}).get("backend") == "finer-tags":
        from ladder.vocab_finer import load
        return load(man["corpus"]["root"])
    from ladder.registry import Registry
    return Registry(man["vocabulary"]["snomed_db"])


def check_accept_lane_cadec():
    """§9 — the free check identifies a subset it can endorse."""
    man, docs, ids = _corpus("manifest.json")
    vocab = _vocab(man)
    gold = [m for d in ids for m in docs[d].mentions if m.sct]
    hits = sum(1 for m in gold
               if any(vocab.lexical_match(m.text, code) for code in m.sct))
    rate = hits / len(gold)
    ok = 0.35 < rate < 0.50
    return ("pass" if ok else "FAIL"), f"{hits} of {len(gold)} = {rate:.1%} (article: ~42%)"


def check_accept_lane_finer():
    """§9 — and it is a STRUCTURAL zero on a corpus of numerals."""
    man, docs, ids = _corpus("manifest.finer.json")
    vocab = _vocab(man)
    gold = [m for d in ids for m in docs[d].mentions if m.sct]
    hits = sum(1 for m in gold
               if any(vocab.lexical_match(m.text, code) for code in m.sct))
    return ("pass" if hits == 0 else "FAIL"), \
           f"{hits} of {len(gold)} — a numeral shares no token with a phrase"


def check_geo_ambiguity():
    """2026-09-02 — a gazetteer's ambiguity is heavy-tailed; an ontology's is not."""
    import statistics
    worst = {}
    for label, manifest in (("CADEC", "manifest.json"),
                            ("GeoWebNews", "manifest.geo.json")):
        man, docs, ids = _corpus(manifest)
        vocab = _vocab(man)
        counts = []
        for m in (x for d in ids for x in docs[d].mentions if x.sct):
            try:
                name = vocab.preferred(m.sct[0])
                counts.append(len(set(vocab.codes_for_term(name) or [])))
            except Exception:
                continue
        worst[label] = (statistics.median(counts) if counts else 0, max(counts, default=0))
    cm, cw = worst["CADEC"]
    gm, gw = worst["GeoWebNews"]
    ok = gw > 10 * cw
    return ("pass" if ok else "FAIL"), \
           (f"CADEC median {cm:.0f} worst {cw} · GeoWebNews median {gm:.0f} worst {gw} "
            f"— same median, {gw//max(cw,1)}x the tail")


def check_type_relation_gold():
    """2026-09-02 — a second relation exists where the first cannot fire."""
    from ladder import relations as R
    man, docs, ids = _corpus("manifest.finer.json", "test")
    vocab = _vocab(man)
    gold = [m for d in ids for m in docs[d].mentions]
    sources = {d: docs[d].text for d in ids}
    res = {r.name: r for r in R.measure(gold, sources, vocab, is_correct=lambda _: True)}
    t = res["type"]
    ok = t.coverage > 0.75
    return ("pass" if ok else "FAIL"), \
           (f"type speaks about {t.coverage:.1%} where lexical speaks about "
            f"{res['lexical'].coverage:.1%}")


def check_dead_fields():
    """The audit — rungs writing a verdict nothing downstream reads."""
    import re
    root = pathlib.Path("ladder")
    written, read = {}, {}
    srcs = {f: f.read_text(errors="replace") for f in root.rglob("*.py")
            if "__pycache__" not in str(f)}
    for f, src in srcs.items():
        for m in re.finditer(r'checks\[\s*["\']([A-Za-z0-9_]+)["\']\s*\]\s*=(?!=)', src):
            written.setdefault(m.group(1), set()).add(f.name)
    verdict = re.compile(r'^(r\d+_|.*_(verdict|declined|unanimous|rescued|agreed))$')
    orphans = []
    for field, writers in written.items():
        if not verdict.match(field):
            continue
        readers = set()
        for f, src in srcs.items():
            pat = (r'checks\.get\(\s*["\']' + re.escape(field) + r'["\']'
                   r'|checks\[\s*["\']' + re.escape(field) + r'["\']\s*\](?!\s*=[^=])')
            if re.search(pat, src):
                readers.add(f.name)
        if not (readers - writers):
            orphans.append(field)
    return ("pass" if orphans else "note"), \
           (f"{len(orphans)} verdict field(s) written and never read: "
            f"{', '.join(sorted(orphans))}" if orphans else
            "no orphaned verdict fields — the audit's finding has been fixed")


CLAIMS = [
    Claim("accept_lane", "The free check endorses a subset it can vouch for",
          "article §9 · CADEC ~42%", check_accept_lane_cadec),
    Claim("accept_lane_zero", "And it is a STRUCTURAL zero where span and code "
          "are drawn from different languages",
          "article §5 · FiNER 0 of 704", check_accept_lane_finer,
          needs="manifest.finer.json"),
    Claim("ambiguity", "A gazetteer's name ambiguity is heavy-tailed; an "
          "ontology's is not",
          "decisions 2026-09-02", check_geo_ambiguity,
          needs="manifest.geo.json"),
    Claim("second_relation", "A dead check does not mean a corpus has no signal",
          "decisions 2026-09-02", check_type_relation_gold,
          needs="manifest.finer.json"),
    Claim("dead_fields", "Rungs wrote verdicts nothing downstream read",
          "the audit · 3 fields", check_dead_fields),
]

#: Stated rather than faked. Each needs a model run, and a reproduction that
#: needs a GPU is not one anybody will run.
NEEDS_A_RUN = [
    ("Voting changes answers and improves none out of sample",
     "425,355 tokens, +5 on the tuning set, 0 held out"),
    ("The judge's verdict does not separate correct from incorrect",
     "1.23x held out, against the free check's 2.36-6.12x"),
    ("Self-correction rescues nothing",
     "0 of 158 on CADEC, 0 of 918 on FiNER"),
    ("The type relation is 1.22% false on gold and 35.7% on model output",
     "the reason rung 7 was rejected"),
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--claim", help="run one claim by key")
    a = ap.parse_args()

    claims = [c for c in CLAIMS if not a.claim or c.key == a.claim]
    print("\n  Reproducing the article's findings — no model calls\n")
    counts = {"pass": 0, "FAIL": 0, "skip": 0, "note": 0, "error": 0}
    for cl in claims:
        status, detail = cl.run()
        counts[status] = counts.get(status, 0) + 1
        mark = {"pass": c(GREEN, "✓"), "FAIL": c(RED, "✗"),
                "skip": c(DIM, "–"), "note": c(AMBER, "!"),
                "error": c(RED, "✗")}[status]
        print(f"  {mark} {cl.says}")
        print(f"    {c(DIM, cl.where)}")
        print(f"    {detail}\n")

    print(f"  {counts['pass']} reproduced · {counts['FAIL'] + counts['error']} failed "
          f"· {counts['skip']} skipped · {counts['note']} note\n")

    print(c(DIM, "  Claims that need a model run, and are NOT checked here:"))
    for says, evidence in NEEDS_A_RUN:
        print(c(DIM, f"    · {says}"))
        print(c(DIM, f"      {evidence}"))
    print()
    return 0 if not (counts["FAIL"] or counts["error"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())

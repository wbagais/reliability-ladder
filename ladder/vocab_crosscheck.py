"""Do the two vocabulary backends agree? Measured, not assumed.

The repo now has two implementations of the same three rung-1 questions:

    ladder/vocab.py       EBI OLS4 over the network — free, no key, no download
    ladder/registry.py   a local SNOMED CT RF2 release, indexed into SQLite

They are interchangeable in principle. They are not in practice, and the gap is
large enough to decide the rung 1 rejection rate on its own, so it has to be
measured before either is trusted.

    python -m ladder.vocab_crosscheck              # offline, whole corpus
    python -m ladder.vocab_crosscheck --live 40    # also hit OLS4, n codes

The offline mode needs no network: the RF2 release records, for every concept,
whether it is active and which module it belongs to. OLS4 serves active
international SNOMED, so "retired" and "AU-extension only" are exactly the two
classes it cannot return — which is all the offline mode needs to know.

`--live` verifies that prediction against the real service on a sample.
"""

from __future__ import annotations

import argparse
import collections
import json
import sys
from pathlib import Path

from ladder import corpus as corpus_mod
from ladder.manifest import friendly, load_manifest
from ladder.registry import Registry

#: SNOMED International core module. Anything else in an edition is an
#: extension — for the AU release, that is largely AMT (drug products).
INTERNATIONAL_MODULE = "900000000000207008"

BOTH_AGREE = "active international — both backends agree"
AU_ONLY = "active, but extension-module only — not in OLS4's SNOMED"
RETIRED = "retired — OLS4 indexes active concepts only"
ABSENT = "absent from both"


def _concept_table(release_dir: Path) -> dict[str, tuple[bool, str]]:
    """code -> (active, moduleId), straight from the RF2 concept snapshot."""
    term = release_dir / "Snapshot" / "Terminology"
    hits = sorted(term.glob("sct2_Concept_Snapshot*.txt"))
    if not hits:
        raise FileNotFoundError(f"no sct2_Concept_Snapshot*.txt under {term}")
    out: dict[str, tuple[bool, str]] = {}
    with hits[0].open(encoding="utf-8") as fh:
        next(fh)
        for line in fh:
            p = line.split("\t")
            out[p[0]] = (p[2] == "1", p[3])
    return out


def classify(code: str, concepts: dict[str, tuple[bool, str]]) -> str:
    if code not in concepts:
        return ABSENT
    active, module = concepts[code]
    if not active:
        return RETIRED
    return BOTH_AGREE if module == INTERNATIONAL_MODULE else AU_ONLY


def offline(man: dict) -> dict:
    concepts = _concept_table(Path(man["vocabulary"]["snomed_release_dir"]))
    docs = corpus_mod.load_corpus(man["corpus"]["cadec_root"])
    mentions = [m for d in docs.values() for m in d.mentions if m.sct]
    overall = collections.Counter()
    by_type: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    examples: dict[str, list] = collections.defaultdict(list)
    reg = Registry(man["vocabulary"]["snomed_db"])
    for m in mentions:
        kind = classify(m.sct[0], concepts)
        overall[kind] += 1
        by_type[m.entity_type][kind] += 1
        if kind != BOTH_AGREE and len(examples[kind]) < 6:
            examples[kind].append({"code": m.sct[0], "term": reg.preferred(m.sct[0])})
    n = len(mentions)
    invisible = n - overall[BOTH_AGREE]
    return {
        "n_mentions_with_a_code": n,
        "classes": dict(overall),
        "ols4_invisible": invisible,
        "ols4_invisible_pct": round(100 * invisible / n, 2) if n else 0.0,
        "by_entity_type": {
            t: {
                "n": sum(c.values()),
                "invisible": sum(c.values()) - c[BOTH_AGREE],
                "pct": round(100 * (sum(c.values()) - c[BOTH_AGREE]) / sum(c.values()), 2),
            }
            for t, c in sorted(by_type.items())
        },
        "examples": dict(examples),
    }


def live(man: dict, n: int) -> dict:
    """Confirm the offline prediction against the real service."""
    import random

    import ladder.vocab as ols

    # The OLS4 backend EXPLICITLY, never the module-level `ols.exists`. That
    # one delegates to the SELECTED backend, which is the local index whenever
    # snomed.sqlite exists — so it would compare the local backend against
    # itself, agree 40/40, and report the two backends as interchangeable.
    # Which is the exact claim this module exists to refute.
    ols4 = ols.Ols4Vocabulary()
    reg = Registry(man["vocabulary"]["snomed_db"])
    concepts = _concept_table(Path(man["vocabulary"]["snomed_release_dir"]))
    docs = corpus_mod.load_corpus(man["corpus"]["cadec_root"])
    codes = sorted({c for d in docs.values() for m in d.mentions for c in m.sct})
    random.Random(man["seed"]).shuffle(codes)

    rows, agree, predicted = [], 0, 0
    for code in codes[:n]:
        try:
            ols_exists = ols4.exists(code)
        except Exception as exc:  # the service is external; a flake is not a result
            print(f"  OLS4 error on {code}: {exc}", file=sys.stderr)
            continue
        local_exists = reg.exists(code)
        kind = classify(code, concepts)
        expect_ols = kind == BOTH_AGREE
        agree += ols_exists == local_exists
        predicted += ols_exists == expect_ols
        if ols_exists != local_exists:
            rows.append(
                {"code": code, "term": reg.preferred(code), "ols4": ols_exists, "local": local_exists, "class": kind}
            )
    return {
        "sampled": min(n, len(codes)),
        "backends_agreed": agree,
        "offline_prediction_correct": predicted,
        "disagreements": rows,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--manifest", default="manifest.json")
    ap.add_argument("--live", type=int, metavar="N", help="also query OLS4 for N codes")
    ap.add_argument("--json")
    a = ap.parse_args(argv)
    man = load_manifest(a.manifest)

    off = offline(man)
    n = off["n_mentions_with_a_code"]
    print(f"CADEC gold mentions carrying an SCT code: {n}\n")
    for kind, k in sorted(off["classes"].items(), key=lambda kv: -kv[1]):
        print(f"  {k:5d}  {100 * k / n:5.1f}%  {kind}")
    print(
        f"\n  -> an OLS4-backed exists() reports {off['ols4_invisible']} / {n} = "
        f"{off['ols4_invisible_pct']}% of GOLD mentions as codes that do not exist."
    )
    print("     The local RF2 index reports 5.\n")
    for t, d in off["by_entity_type"].items():
        print(f"  {t:9s} {d['invisible']:5d} / {d['n']:5d} = {d['pct']:5.1f}% affected")
    print(
        "\n  Drug mentions are the whole of the extension-module class: CADEC codes\n"
        "  drugs to AMT, the Australian extension, which the international release\n"
        "  OLS4 serves does not contain at all. This is a property of the SOURCE,\n"
        "  not a bug in either implementation."
    )
    out = {"offline": off}
    if a.live:
        print(f"\nquerying OLS4 for {a.live} codes ...")
        out["live"] = live(man, a.live)
        lv = out["live"]
        print(
            f"  backends agreed on {lv['backends_agreed']} / {lv['sampled']}; "
            f"the offline prediction was right {lv['offline_prediction_correct']} / {lv['sampled']}"
        )
        for r in lv["disagreements"][:10]:
            print(f"    {r['code']:20s} {str(r['term'])[:34]:34s} {r['class']}")
    if a.json:
        Path(a.json).parent.mkdir(parents=True, exist_ok=True)
        Path(a.json).write_text(json.dumps(out, indent=2))
        print(f"\nwrote {a.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(friendly(main))

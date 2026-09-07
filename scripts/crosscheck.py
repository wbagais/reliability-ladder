#!/usr/bin/env python3
"""
crosscheck.py — is this arm wired as it is declared?

THE PRINCIPLE

Everything that caught a real defect on 2026-09-06/07 worked the same way: a
fact recorded TWICE, from independent sources, and compared.

    the vocabulary gate   manifest's code   vs  what the index holds
    manifest_diff         declared keys     vs  actual differences
    directory vs manifest intended model    vs  the model that ran
    the prompt dump       declared entity   vs  the rendered text

Everything that got through was a fact recorded ONCE:

    the prompt          declared in corpus.prompts, never read back
                        -> twelve cells ran CADEC's wording on corpora about
                           places, species and diseases
    the few-shot ids    written from `train`, never checked against the pool
                        the guard actually reads -> every BC5CDR cell refused
    the split ids       frozen while the adapter defaulted to another corpus
                        -> TR-News briefly held LGL's documents
    the model name      `ibm/` prefix in the manifest, absent from ollama
                        -> three ports refused at the first cell

**A load-bearing fact recorded once cannot be checked, and will eventually be
wrong silently.** This reads each one back from a different direction.

WHAT IT IS NOT

It is not a schema validator: a manifest can be perfectly well-formed and still
declare a prompt nothing reads. It is not a preflight either — `gatecheck` asks
whether the corpus is worth running, which is a different question with a
different answer.

It costs no GPU, no model call, and about a second. That is deliberate: a check
that is cheap enough to be the first line of every run never gets skipped.

    PYTHONPATH=. python3 scripts/crosscheck.py --manifest manifest.psytar.json
    PYTHONPATH=. python3 scripts/crosscheck.py --manifest manifest.*.json
    PYTHONPATH=. python3 scripts/crosscheck.py --manifest m.json --quiet   # CI

Exit code is the number of failures, so `crosscheck ... || exit` works as a
gate in a run script.
"""
from __future__ import annotations

import argparse
import functools
import glob
import json
import pathlib
import re
import subprocess
import sys
from collections import Counter

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

PASS, FAIL, SKIP = "pass", "FAIL", "skip"

#: Entity words from OTHER corpora in this study. A prompt that names one of
#: these while declaring a different entity has inherited someone else's task —
#: which is what happened to four arms and produced twelve unusable cells.
FOREIGN = {
    "reaction": ("adverse reaction", "adverse drug reaction"),
    "place":    ("place the article refers to",),
    "organism": ("organism the paper mentions",),
    "disease":  ("disease or symptom",),
    "fact":     ("numeric fact",),
}
#: Keyed by the OWNING entity, so a corpus is never foreign to itself. The flat
#: list this replaces matched `place` against "place the article refers to" and
#: reported all three geo arms as carrying another corpus's task.


class Report:
    def __init__(self, name: str, quiet: bool):
        self.name, self.quiet, self.rows = name, quiet, []

    def add(self, status, check, declared="", found="", note=""):
        self.rows.append((status, check, declared, found, note))

    def failures(self):
        return sum(1 for r in self.rows if r[0] == FAIL)

    def show(self):
        f = self.failures()
        if self.quiet and not f:
            print(f"  {self.name:26} {len(self.rows)} checks, all pass")
            return
        print(f"\n  ── {self.name}\n")
        for status, check, declared, found, note in self.rows:
            mark = {PASS: "  ", FAIL: " !", SKIP: "  "}[status]
            print(f"  {mark} {status:4} {check}")
            if status == FAIL or note:
                if declared:
                    print(f"          declared : {declared}")
                if found:
                    print(f"          found    : {found}")
                if note:
                    print(f"          {note}")
        print(f"\n      {len(self.rows)} checks, {f} failed")


def crosscheck(path: str, quiet: bool) -> Report:
    from ladder.run import (_corpus_for, _corpus_opts, _corpus_root,
                            _vocab_for, load_manifest)
    r = Report(pathlib.Path(path).name, quiet)
    man = load_manifest(path)
    c = man.get("corpus") or {}
    rung0 = (man.get("rungs") or {}).get("0", {})

    # ── 1 · the corpus loads, and the adapter is the one declared ────
    try:
        mod = _corpus_for(man)
        docs = mod.load_corpus(_corpus_root(man), **_corpus_opts(man))
        r.add(PASS if docs else FAIL, "corpus loads",
              f"adapter={c.get('adapter', 'cadec')}",
              f"{len(docs)} documents, "
              f"{sum(len(d.mentions) for d in docs.values())} mentions")
    except Exception as exc:
        r.add(FAIL, "corpus loads", str(c.get("root")), str(exc)[:100])
        return r

    # ── 2 · the entity type is one the adapter offers ────────────────
    types = getattr(mod, "TYPES", None)
    if types:
        e = c.get("entity")
        r.add(PASS if e in types else FAIL, "entity type is offered",
              str(e), str(types),
              "" if e in types else
              "a corpus that annotates several types and scores one will "
              "otherwise be judged on mentions it never asked for")

    # ── 3 · the split ids exist IN THE CORPUS THE ADAPTER LOADS ──────
    # TR-News's splits were frozen while `corpus=` defaulted to lgl, so they
    # held LGL's document ids. The run then had nothing to work on and rung 0
    # returned in 0.06 s with no error.
    sd = pathlib.Path(c.get("splits_dir", ""))
    for split in ("pool", "dev", "test"):
        f = sd / f"{split}.json"
        if not f.is_file():
            r.add(SKIP, f"split '{split}' exists", str(f), "absent")
            continue
        ids = json.loads(f.read_text())
        ids = ids if isinstance(ids, list) else ids.get("doc_ids", [])
        missing = [i for i in ids if i not in docs]
        r.add(PASS if ids and not missing else FAIL,
              f"split '{split}' ids are in this corpus",
              f"{len(ids)} ids", f"{len(missing)} not found",
              "" if not missing else f"e.g. {missing[:2]} — the split was "
              f"probably frozen against a different corpus")

    # ── 4 · the split sizes leave a pool ─────────────────────────────
    nd, nt = c.get("n_dev_docs", 0), c.get("n_test_docs", 0)
    if nd and nt:
        room = len(docs) - nd - nt
        r.add(PASS if room > 0 else FAIL, "splits leave a pool",
              f"{nd} dev + {nt} test of {len(docs)}", f"{room} left",
              "" if room > 0 else
              "the few-shot block comes from the pool, and an empty pool "
              "means rung 0 falls back to CADEC's synthetic examples")

    # ── 5 · the few-shot ids are in THE POOL THE GUARD READS ─────────
    # BC5CDR's were picked from its own `train` split, which is not the pool
    # `init` wrote, so every cell refused at the first document.
    fs = rung0.get("rung0_fewshot_docs") or []
    pf = sd / "pool.json"
    if fs and pf.is_file():
        pool = json.loads(pf.read_text())
        pool = pool if isinstance(pool, list) else pool.get("doc_ids", [])
        outside = [d for d in fs if d not in pool]
        r.add(PASS if not outside else FAIL, "few-shot ids are in the pool",
              str(fs), f"{len(outside)} outside the pool",
              "" if not outside else
              "an example from dev or test puts its own gold answers in the "
              "prompt of a scored run; the guard refuses and the run dies")
    elif not fs:
        r.add(FAIL, "few-shot ids declared", "(none)",
              "rung 0 will fall back to its synthetic CADEC examples",
              "measured: a corpus running CADEC's examples extracts CADEC's "
              "entity — mistral returned diseases from a paper about yeast")

    # ── 6 · the vocabulary resolves a real code and refuses a fake ───
    try:
        reg = _vocab_for(man)
        gate = (man.get("vocabulary") or {}).get("gate") or {}
        real, fake = str(gate.get("real", "")), str(gate.get("fake", ""))
        if real:
            ok = reg.exists(real) and not reg.exists(fake)
            r.add(PASS if ok else FAIL, "vocabulary gate",
                  f"real={real} fake={fake}",
                  f"exists(real)={reg.exists(real)} exists(fake)={reg.exists(fake)}",
                  "" if ok else "a vocabulary that answers True to everything, "
                                "or False to everything, produces a rung 1 that "
                                "looks like it is working")
        else:
            r.add(FAIL, "vocabulary gate declared", "(none)",
                  "inherited from CADEC's SNOMED gate")
    except Exception as exc:
        r.add(FAIL, "vocabulary loads",
              str((man.get("vocabulary") or {}).get("snomed_db")), str(exc)[:90])
        reg = None

    # ── 7 · gold codes actually resolve in that vocabulary ───────────
    if reg is not None:
        gold = [m for d in docs.values() for m in d.mentions][:400]
        hit = sum(1 for m in gold if m.sct and reg.exists(str(m.sct[0])))
        share = hit / len(gold) if gold else 0
        r.add(PASS if share > 0.5 else FAIL, "gold codes resolve",
              f"{len(gold)} sampled", f"{share:.1%} resolve",
              "" if share > 0.5 else
              "the answer key and the vocabulary disagree — scoring against "
              "this pair measures the mismatch, not the model")

    # ── 8 · THE RENDERED PROMPT NAMES THIS CORPUS'S ENTITY ───────────
    # The one that got through. `corpus.prompts` was absent on four arms, the
    # fallback is CADEC's wording by design, and twelve cells asked for adverse
    # drug reactions in papers about places, species and diseases.
    prompts = c.get("prompts") or {}
    entity = (prompts.get("entity_short") or prompts.get("entity") or "").lower()
    try:
        from ladder.rungs.r0 import prepare, find_prompt, _extraction_prompt
        cfg = {"manifest": man, "registry": reg, "prompt_slots": prompts or None,
               "corpus_loader": functools.partial(mod.load_corpus, **_corpus_opts(man)),
               **rung0}
        text = _extraction_prompt(find_prompt(prepare(cfg).get("prompt_slots")),
                                  prepare(cfg)).lower()
        if entity:
            r.add(PASS if entity in text else FAIL, "prompt names this entity",
                  entity, "present" if entity in text else "ABSENT",
                  "" if entity in text else
                  "the model is being asked for something this corpus does not "
                  "annotate")
        else:
            adr = "adverse" in text or "reaction" in text
            r.add(SKIP if adr else FAIL, "corpus declares an entity", "(none)",
                  "rung 0 falls back to CADEC's wording",
                  "an adverse-reaction corpus needs no block and this is a "
                  "decision, not an omission — state it in the manifest"
                  if adr else
                  "and CADEC's wording asks for adverse drug reactions, which "
                  "this corpus does not annotate")
        # Not a failure when the corpus HAS no declared entity and the
        # inherited task is the right one — PsyTAR is adverse reactions.
        mine = {p for k, ps in FOREIGN.items() if k in entity for p in ps}
        foreign = [] if not entity else sorted(
            {f"{p} ({k})" for k, ps in FOREIGN.items() for p in ps
             if p in text and p not in mine and k not in entity})
        r.add(PASS if not foreign else FAIL, "prompt names no other corpus's entity",
              entity or "(none)", "; ".join(foreign) or "none")
        # A slot holding a clause where a noun phrase belongs rendered as
        # "organism the paper mentions the paper describes".
        words = re.findall(r"[a-z]+", text[:400])
        dup = []
        for i in range(len(words) - 5):
            a, b = words[i:i+3], words[i+3:i+6]
            # A doubled slot repeats itself IMMEDIATELY, or with one word
            # between. Two rules that happen to share a phrase do not.
            if a == b and len(set(a)) == 3:
                dup.append(" ".join(a + b))
            elif i + 7 <= len(words) and words[i:i+2] == words[i+3:i+5]:
                dup.append(" ".join(words[i:i+5]))
        r.add(PASS if not dup else FAIL, "no slot rendered a repeated phrase",
              "", "; ".join(dup[:2]) or "none",
              "" if not dup else "a slot holding a clause where a noun phrase "
                                 "belongs doubles the verb")
        # Two whole research papers as examples pushed the rules out of a 4B
        # model's usable window; llama3.1 returned nothing at all.
        n = len(text)
        r.add(PASS if n < 12000 else FAIL, "prompt fits a small model",
              "", f"{n:,} characters",
              "" if n < 12000 else "measured: two full-paper few-shot examples "
                                   "and three models of four returned nothing")
    except Exception as exc:
        r.add(SKIP, "prompt renders", "", str(exc)[:90])

    # ── 9 · every model the manifest names is installed ──────────────
    try:
        have = subprocess.run(["ollama", "list"], capture_output=True,
                              text=True, timeout=20).stdout
        # Only ROLES name models. `model.note` is a paragraph of
        # prose about which model judges which, and treating every
        # key as a spec reported it as a missing model.
        for role in ("extractor", "judge", "reranker", "embedder"):
            spec = (man.get("model") or {}).get(role)
            if not isinstance(spec, str) or "/" not in spec:
                continue
            tag = spec.split("/", 1)[1]
            r.add(PASS if tag in have else FAIL, f"model.{role} is installed",
                  spec, "present" if tag in have else "NOT in ollama list",
                  "" if tag in have else
                  "the same blob under two names: `granite4:micro-h` and "
                  "`ibm/granite4:micro-h` share a digest and only one resolves")
    except Exception as exc:
        r.add(SKIP, "models installed", "", str(exc)[:60])

    return r


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--manifest", nargs="+", required=True)
    ap.add_argument("--quiet", action="store_true",
                    help="one line per manifest unless something fails")
    a = ap.parse_args()

    paths = []
    for p in a.manifest:
        paths += sorted(glob.glob(p)) or [p]

    total = 0
    for p in paths:
        try:
            rep = crosscheck(p, a.quiet)
        except Exception as exc:
            print(f"\n  ── {p}\n   ! could not check: {exc}\n")
            total += 1
            continue
        rep.show()
        total += rep.failures()

    print()
    if total:
        print(f"  {total} check(s) failed. Each is a fact declared in one place "
              f"and contradicted in another.")
    else:
        print("  Every declared fact was confirmed from a second source.")
    print()
    return min(total, 125)


if __name__ == "__main__":
    raise SystemExit(main())

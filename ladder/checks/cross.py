"""ladder.checks.cross — every declared fact, read back from somewhere else.

THE SHAPE, AND WHY IT CHANGED

This was one 200-line function with nine checks inlined. Each is now a function
of `(Arm) -> Result | list[Result]`, collected in `CHECKS` at the bottom. Three
things follow:

  · a check can be tested alone, against a fixture arm
  · adding a tenth means writing a function, not editing the other nine
  · the list of what is checked is READABLE — it is the bottom of this file,
    not a paragraph of control flow

THE PRINCIPLE, unchanged: everything that caught a real defect on 2026-09-06/07
compared two independent records of one fact. Everything that got through was
recorded once.
"""
from __future__ import annotations

import re
import subprocess
from collections import Counter

from . import FAIL, PASS, SKIP, Arm, Result

#: Entity phrases owned by a corpus in this study, keyed by the owner's own
#: entity word. Keyed rather than flat because a flat list matched `place`
#: against "place the article refers to" and reported all three geo arms as
#: carrying another corpus's task.
FOREIGN: dict[str, tuple[str, ...]] = {
    "reaction": ("adverse reaction", "adverse drug reaction"),
    "place": ("place the article refers to",),
    "organism": ("organism the paper mentions",),
    "disease": ("disease or symptom",),
    "fact": ("numeric fact",),
}

#: Measured, not guessed: two full-paper few-shot examples plus the rules ran
#: past what a 4-8B model held usefully, and three models of four returned
#: nothing at all on LINNAEUS.
PROMPT_CHAR_LIMIT = 12_000


def corpus_loads(a: Arm) -> Result:
    if not a.docs:
        return Result(FAIL, "corpus loads", str(a.corpus.get("root")),
                      "no documents")
    return Result(PASS, "corpus loads", f"adapter={a.corpus.get('adapter', 'cadec')}",
                  f"{len(a.docs)} documents, {len(a.gold)} mentions")


def entity_type_offered(a: Arm) -> Result | None:
    """A corpus that annotates several types must say which one it scores."""
    types = getattr(getattr(a, "_mod", None), "TYPES", None)
    if not types:
        return None
    e = a.corpus.get("entity")
    return Result(PASS if e in types else FAIL, "entity type is offered",
                  str(e), str(types),
                  "" if e in types else
                  "a corpus that annotates several types and scores one will "
                  "otherwise be judged on mentions it never asked for")


def split_ids_are_in_this_corpus(a: Arm) -> list[Result]:
    """TR-News's splits were frozen while the adapter defaulted to another
    corpus, so they held LGL's document ids. Rung 0 then returned in 0.06 s
    with no error and no records, and three theories were wrong before the
    fourth was right."""
    out = []
    for name in ("pool", "dev", "test"):
        ids = a.split(name)
        if ids is None:
            out.append(Result(SKIP, f"split '{name}' exists", "", "absent"))
            continue
        missing = [i for i in ids if i not in a.docs]
        out.append(Result(PASS if ids and not missing else FAIL,
                          f"split '{name}' ids are in this corpus",
                          f"{len(ids)} ids", f"{len(missing)} not found",
                          "" if not missing else
                          f"e.g. {missing[:2]} — frozen against a different corpus"))
    return out


def splits_leave_a_pool(a: Arm) -> Result | None:
    """LINNAEUS has 95 documents and 40 dev + 60 test left nothing, so the
    few-shot block came back empty and rung 0 fell back to CADEC's synthetic
    examples."""
    nd, nt = a.corpus.get("n_dev_docs", 0), a.corpus.get("n_test_docs", 0)
    if not (nd and nt and a.docs):
        return None
    room = len(a.docs) - nd - nt
    return Result(PASS if room > 0 else FAIL, "splits leave a pool",
                  f"{nd} dev + {nt} test of {len(a.docs)}", f"{room} left",
                  "" if room > 0 else
                  "an empty pool means rung 0 uses CADEC's synthetic examples")


def fewshot_ids_are_in_the_pool(a: Arm) -> Result:
    """BC5CDR's were picked from its own `train` split, which is not the pool
    `init` wrote, so the guard refused every cell at the first document."""
    fs = a.rung0.get("rung0_fewshot_docs") or []
    if not fs:
        return Result(FAIL, "few-shot ids declared", "(none)",
                      "rung 0 falls back to its synthetic CADEC examples",
                      "measured: a corpus running CADEC's examples extracts "
                      "CADEC's entity — mistral returned diseases from a paper "
                      "about yeast")
    pool = a.split("pool")
    if pool is None:
        return Result(SKIP, "few-shot ids are in the pool", str(fs), "no pool split")
    outside = [d for d in fs if d not in pool]
    return Result(PASS if not outside else FAIL, "few-shot ids are in the pool",
                  str(fs), f"{len(outside)} outside the pool",
                  "" if not outside else
                  "an example from dev or test puts its own gold answers in "
                  "the prompt of a scored run")


def vocabulary_gate(a: Arm) -> Result:
    """A vocabulary that answers True to everything, or False to everything,
    produces a rung 1 that looks like it is working."""
    if a.registry is None:
        return Result(SKIP, "vocabulary gate", "", "vocabulary did not load")
    gate = a.vocabulary.get("gate") or {}
    real, fake = str(gate.get("real", "")), str(gate.get("fake", ""))
    if not real:
        return Result(FAIL, "vocabulary gate declared", "(none)",
                      "the gate runs on CADEC's SNOMED codes",
                      "which works by luck where the vocabulary is also SNOMED "
                      "and by accident where it is not")
    ok = a.registry.exists(real) and not a.registry.exists(fake)
    return Result(PASS if ok else FAIL, "vocabulary gate",
                  f"real={real} fake={fake}",
                  f"exists(real)={a.registry.exists(real)} "
                  f"exists(fake)={a.registry.exists(fake)}")


def gold_codes_resolve(a: Arm) -> Result | None:
    """The answer key and the vocabulary must be talking about the same thing.
    An OLS4-backed `exists()` once reported 23.9% of CADEC gold as codes that
    do not exist, because CADEC codes drugs to AMT."""
    if a.registry is None or not a.gold:
        return None
    sample = a.gold[:400]
    hit = sum(1 for m in sample if m.sct and a.registry.exists(str(m.sct[0])))
    share = hit / len(sample)
    return Result(PASS if share > 0.5 else FAIL, "gold codes resolve",
                  f"{len(sample)} sampled", f"{share:.1%} resolve",
                  "" if share > 0.5 else
                  "scoring against this pair measures the mismatch, not the model")


def prompt_names_this_entity(a: Arm, text: str) -> Result:
    """The one that got through: `corpus.prompts` was absent on four arms and
    twelve cells asked for adverse drug reactions in papers about places,
    species and diseases."""
    if not a.entity:
        adr = "adverse" in text or "reaction" in text
        return Result(SKIP if adr else FAIL, "corpus declares an entity",
                      "(none)", "rung 0 falls back to CADEC's wording",
                      "an adverse-reaction corpus needs no block and this is a "
                      "decision, not an omission — state it in the manifest"
                      if adr else
                      "and CADEC's wording asks for adverse drug reactions, "
                      "which this corpus does not annotate")
    ok = a.entity in text
    return Result(PASS if ok else FAIL, "prompt names this entity", a.entity,
                  "present" if ok else "ABSENT",
                  "" if ok else "the model is being asked for something this "
                                "corpus does not annotate")


def prompt_names_no_other_entity(a: Arm, text: str) -> Result:
    mine = {p for k, ps in FOREIGN.items() if k in a.entity for p in ps}
    foreign = [] if not a.entity else sorted(
        {f"{p} ({k})" for k, ps in FOREIGN.items() for p in ps
         if p in text and p not in mine and k not in a.entity})
    return Result(PASS if not foreign else FAIL,
                  "prompt names no other corpus's entity",
                  a.entity or "(none)", "; ".join(foreign) or "none")


def no_doubled_slot(a: Arm, text: str) -> Result:
    """A slot holding a clause where a noun phrase belongs doubles the verb:
    `entity: "organism the paper mentions"` rendered as *"organism the paper
    mentions the paper describes"*. Written into a SECOND manifest an hour
    after the first was found and explained — which is the argument for the
    check rather than for care.

    Adjacency is the discriminator. Two rules that happen to share a phrase are
    not a defect; a phrase repeating immediately after itself is.
    """
    words = re.findall(r"[a-z]+", text[:400].lower())
    dup = []
    for i in range(len(words) - 5):
        if words[i:i+3] == words[i+3:i+6] and len(set(words[i:i+3])) == 3:
            dup.append(" ".join(words[i:i+6]))
        elif words[i:i+2] == words[i+3:i+5]:
            dup.append(" ".join(words[i:i+5]))
    return Result(PASS if not dup else FAIL, "no slot rendered a repeated phrase",
                  "", "; ".join(sorted(set(dup))[:2]) or "none")


def prompt_fits_a_small_model(a: Arm, text: str) -> Result:
    n = len(text)
    return Result(PASS if n < PROMPT_CHAR_LIMIT else FAIL,
                  "prompt fits a small model", f"< {PROMPT_CHAR_LIMIT:,}",
                  f"{n:,} characters",
                  "" if n < PROMPT_CHAR_LIMIT else
                  "measured: two full-paper few-shot examples, and three models "
                  "of four returned nothing at all")


def models_are_installed(a: Arm) -> list[Result]:
    """`granite4:micro-h` and `ibm/granite4:micro-h` share a digest and only one
    resolves. Three ports refused at their first cell over it."""
    try:
        have = subprocess.run(["ollama", "list"], capture_output=True,
                              text=True, timeout=20).stdout
    except Exception as exc:
        return [Result(SKIP, "models installed", "", str(exc)[:60])]
    out = []
    # Only ROLES name models. `model.note` is a paragraph of prose.
    for role in ("extractor", "judge", "reranker", "embedder"):
        spec = (a.manifest.get("model") or {}).get(role)
        if not isinstance(spec, str) or "/" not in spec:
            continue
        tag = spec.split("/", 1)[1]
        # A model absent from THIS machine is not a wrong declaration — the
        # manifest may be correct and the model simply not pulled here. Both
        # matter, and they need different responses: one says fix the manifest,
        # the other says pull this before running. Reported as SKIP with the
        # command, so a genuine mismatch stays visible among them.
        out.append(Result(PASS if tag in have else SKIP,
                          f"model.{role} is installed", spec,
                          "present" if tag in have else
                          f"not on this machine — `ollama pull {tag}`"))
    return out


#: Checks needing only the arm. Order is the order they are reported in.
CHECKS = [
    corpus_loads,
    entity_type_offered,
    split_ids_are_in_this_corpus,
    splits_leave_a_pool,
    fewshot_ids_are_in_the_pool,
    vocabulary_gate,
    gold_codes_resolve,
    models_are_installed,
]

#: Checks needing the RENDERED prompt, which costs a corpus load and is done
#: once for all of them rather than once each.
PROMPT_CHECKS = [
    prompt_names_this_entity,
    prompt_names_no_other_entity,
    no_doubled_slot,
    prompt_fits_a_small_model,
]


def run(a: Arm) -> list[Result]:
    results: list[Result] = list(a.errors)
    for check in CHECKS:
        got = check(a)
        if got is None:
            continue
        results += got if isinstance(got, list) else [got]
    try:
        text = a.rendered_prompt().lower()
    except Exception as exc:
        results.append(Result(SKIP, "prompt renders", "", str(exc)[:100]))
        return results
    for check in PROMPT_CHECKS:
        results.append(check(a, text))
    return results

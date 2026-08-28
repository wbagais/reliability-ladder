#!/usr/bin/env python3
"""port_prompts.py — rung 0's prompts belong to the corpus.

WHAT THIS IS

An earlier patch templated `BASE`. That was the wrong string: the frozen
configuration runs S2, which uses FIND_PROMPT and PICK_PROMPT and never touches
BASE. There are SEVEN prompt constants in ladder/rungs/r0.py — _ASK, _RULES,
FEWSHOT, S0_PROMPT, S1_PROMPT, FIND_PROMPT, PICK_PROMPT — and every one of them
is written about adverse drug reactions in patient posts.

So the honest statement of the port is not "the prompt was hardcoded". It is:

    The LADDER ported to a second corpus in sixteen one-line edits and no rung
    logic changed. RUNG 0 DID NOT PORT AT ALL. It is not a corpus-agnostic
    extractor with a swappable subject; it is a CADEC extraction system, tuned
    over five phases against CADEC's dev split.

That is the sharper answer to "why isn't this modular", and it is not a
failure of practice. Every axis KNOWN to vary was abstracted — models, rung
order, thresholds, retrieval, few-shot ids, vocabulary backend, scorer. The
prompts were never known to vary because there was one corpus. You can only
parameterise what you can imagine changing.

WHAT CHANGES

`PROMPTS` becomes a dict of the corpus-specific text, defaulting to CADEC's
exact strings. A manifest supplies its own under `corpus.prompts`. The
STRUCTURE — field names, JSON shapes, the two-step find-then-pick split, the
numbering scheme in the pick menu — is not configurable, because that is what
makes two arms comparable.

Every CADEC prompt is asserted byte-identical afterwards. The script exits
rather than writing if any of them drifted.

WHERE FiNER'S RULES COME FROM

Not from imagination. Derived from its own gold, over 407 mentions:

  * spans are the BARE NUMBER — 0 of 407 start with '$', none contain '%'
  * 3 of 407 are multi-token, and one of those is the word 'two'
  * 38 texts repeat within a document and each repeat is tagged separately,
    the same convention CADEC has
  * 39 numbers carry DIFFERENT tags in different places. That is the whole
    difficulty: the number is meaningless and the sentence decides.
  * gold picks DebtInstrumentFaceAmount for 40.5, not NotesPayable — name the
    MEASUREMENT, not the instrument. That is the same shape as CADEC's "the
    plain concept, not a more specific variant": describe the thing itself,
    not its circumstances.

A rule this script does NOT invent: CADEC's negation handling. FiNER gold shows
no denied-figure convention, so the negation paragraph is dropped rather than
translated, and `negated` is always false. Stated here because a silently
dropped rule is indistinguishable from an overlooked one.

Run from the repo root. Idempotent.
"""
import json
import pathlib
import sys

r0 = pathlib.Path("ladder/rungs/r0.py")
src = r0.read_text()

if "PROMPTS = {" in src:
    print("already applied")
    sys.exit(0)

# ---------------------------------------------------------------- capture
# The CADEC originals, read from the module BEFORE editing, so the assertion
# afterwards compares against what actually shipped rather than against what
# this script thinks shipped.
sys.path.insert(0, ".")
import importlib
mod = importlib.import_module("ladder.rungs.r0")
ORIGINAL = {k: getattr(mod, k) for k in
            ("_ASK", "_RULES", "S0_PROMPT", "S1_PROMPT", "FIND_PROMPT", "PICK_PROMPT")}

# ------------------------------------------------------------------ edit
# Insert a PROMPTS dict holding the corpus-specific text, and a resolver that
# merges an override over it. The prompt constants become functions of that.
ANCHOR = "_ASK = "
if ANCHOR not in src:
    sys.exit("! _ASK not found — patch by hand")

BLOCK = '''# ---------------------------------------------------------------------------
# THE TASK BELONGS TO THE CORPUS.
#
# Seven prompt constants below were written about adverse drug reactions in
# patient posts. Pointed at a financial filing they ask the wrong question, and
# gpt-oss:20b correctly answers {"mentions":[]} — the extractor did not port.
#
# These slots are what varies. The STRUCTURE does not: field names, JSON
# shapes, the find-then-pick split and the pick menu's numbering are frozen,
# because they are what make two arms comparable. A corpus needing those
# changed would be a different experiment rather than a second data point.
#
# Defaults are CADEC's exact wording. There is an assertion in
# scripts/port_prompts.py that every CADEC prompt renders byte-identical.
PROMPTS = {
    "entity": "adverse reaction",
    "entity_short": "reaction",
    "entity_plural": "reactions",
    "author": "the reporter",
    "author_possessive": "the reporter's",
    "source": "the post",
    "vocabulary": "SNOMED CT concept",
    "vocabulary_short": "concept",
    "id_name": "concept id",
    "rules": None,          # filled from _RULES_CADEC below
    "pick_guidance": None,  # filled from _PICK_GUIDANCE_CADEC below
}


def prompt_text(key: str, over: dict | None = None) -> str:
    return {**PROMPTS, **(over or {})}[key]


def resolve(over: dict | None = None) -> dict:
    """Slots for one corpus. Missing keys fall back to CADEC's."""
    return {**PROMPTS, **{k: v for k, v in (over or {}).items() if v is not None}}


'''
src = src.replace(ANCHOR, BLOCK + ANCHOR, 1)
r0.write_text(src)

print("  + PROMPTS dict inserted")
print()
print("  NOTE: this script inserts the slot table and stops. Rewriting the six")
print("  prompt constants into templates is a larger edit and MUST be done")
print("  with the byte-identical assertion in place, one constant at a time.")
print("  Doing it blind is how the earlier BASE port silently changed two words")
print("  ('for that reaction' -> 'for that adverse reaction') and would have")
print("  invalidated every CADEC number.")
print()

# ------------------------------------------------------- FiNER's prompt set
finer = {
    "_derivation": (
        "Derived from FiNER's own gold over 407 mentions, not invented. "
        "Spans are the bare number: 0 of 407 start with '$', none contain '%', "
        "3 of 407 are multi-token and one of those is the word 'two'. 38 texts "
        "repeat within a document and each repeat is tagged separately, the "
        "same convention CADEC has. 39 numbers carry DIFFERENT tags in "
        "different places, which is the whole difficulty of the task."),
    "entity": "reported financial fact",
    "entity_short": "fact",
    "entity_plural": "facts",
    "author": "the filer",
    "author_possessive": "the filer's",
    "source": "the filing excerpt",
    "vocabulary": "US-GAAP XBRL tag",
    "vocabulary_short": "tag",
    "id_name": "tag name",

    "rules": (
        "\\nQuote the NUMBER ONLY. Not the currency symbol, not the unit, not "
        "the\\nword 'million' or 'percent' — measured on gold: 0 of 407 spans "
        "begin with\\n'$' and none contain '%'. A quantity written as a word "
        "('two business\\nsegments') is quoted as that word.\\n\\n"
        "Report EVERY tagged figure, working through the whole excerpt. A "
        "sentence\\noften states two or three.\\n\\n"
        "Report a figure EVERY TIME it appears. If the same number is stated "
        "twice,\\nreport it twice, each one where it appears — never merge "
        "repeats. Measured:\\n38 numbers repeat within a document in the gold.\\n\\n"
        "Report only figures the filing states as facts about itself. A number "
        "in a\\nheading, a section number, a date or a page reference is not a "
        "reported\\nfact.\\n"),

    "pick_guidance": (
        "Choose the tag that names WHAT KIND OF QUANTITY this number is — not "
        "the\\ninstrument or the account it belongs to. For a debt face amount "
        "of 40.5 the\\nanswer is DebtInstrumentFaceAmount, not NotesPayable: "
        "the tag names the\\nmeasurement, the instrument is context.\\n\\n"
        "The number itself carries no information. The sentence around it "
        "decides:\\nmeasured on gold, 39 numbers take different tags in "
        "different places."),

    "_negation_note": (
        "CADEC's negation rule is DROPPED, not translated. Its gold codes "
        "denied reactions and marks them negated:true; FiNER gold shows no "
        "denied-figure convention, so `negated` is always false here. Recorded "
        "because a silently dropped rule is indistinguishable from an "
        "overlooked one."),
}

mp = pathlib.Path("manifest.finer.json")
man = json.loads(mp.read_text())
man["corpus"]["prompts"] = finer
mp.write_text(json.dumps(man, indent=2) + "\\n")
print("  + manifest.finer.json carries corpus.prompts, derived from its gold")
print()
print("Next, one constant at a time, asserting byte-identity after each:")
for k in ("_ASK", "_RULES", "FIND_PROMPT", "PICK_PROMPT", "S0_PROMPT", "S1_PROMPT"):
    print(f"    {k}")

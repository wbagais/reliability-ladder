#!/usr/bin/env python3
"""add_full_retrieval.py — a third retriever, for a vocabulary that fits.

THE PROBLEM

Rung 0's pick step builds its menu from `shortlist(span_text)`, token overlap
against the vocabulary. On CADEC that works: the span is a phrase — "extreme
rectal bleed" — and the tokens match concept names.

On FiNER the span is a NUMBER. `shortlist("19.8")` tokenises to nothing that
appears in any tag name, so it returns [] and the pick step records
`declined_shortlist: True` and `sct: None`. All 22 records in the first
complete FiNER run came back with no code, and rung 1 called them BAND — not
because the codes were wrong, but because there were none.

**Retrieval by term overlap is meaningless when the span carries no terms.**
That is a property of the task, not a bug, and it was predictable from the
data shape.

THE FIX, AND WHY IT IS A REMOVAL RATHER THAN A TUNING

Retrieval exists because SNOMED has 129,675 concepts and they cannot go in a
prompt. FiNER has 139 tag names and they can. So `rung0_retrieval: "full"`
offers the entire vocabulary as the menu and does no ranking at all.

That removes a step rather than improving one. The alternative — retrieving on
the surrounding sentence instead of the span — would work, and it would also
introduce a retrieval strategy CADEC never used, making the arms differ in one
more way. Offering everything is the configuration a real deployment would
choose for a vocabulary this size, and it is honest about the fact that
retrieval has nothing to do here.

DECLARED, NOT SILENT

This is the second deviation from the frozen phase-F configuration, after
dense -> lexical. Both have the same cause: retrieval is a function of what is
being retrieved from, and the two corpora differ by three orders of magnitude.
Neither is a tuning of the ladder; both are consequences of the vocabulary.

The cost is stated too. A 139-item menu is a large prompt on every pick call,
where CADEC's is 20 items. Tokens per record will rise, and that belongs in the
cost column rather than being treated as free.

Run from the repo root. Idempotent.
"""
import json
import pathlib
import sys

r0 = pathlib.Path("ladder/rungs/r0.py")
s = r0.read_text()

if '"full"' in s and "RETRIEVERS" in s and "full" in s.split("RETRIEVERS")[1][:200]:
    print("already applied")
    sys.exit(0)

edits = 0


def sub(old, new, label):
    global s, edits
    if new in s:
        print(f"  = {label}: already applied")
        return
    if old not in s:
        print(f"  ! {label}: NOT FOUND — patch by hand")
        return
    s = s.replace(old, new, 1)
    edits += 1
    print(f"  + {label}")


# --- register the mode ----------------------------------------------------
for cand in ('RETRIEVERS = ("dense", "lexical")',
             'RETRIEVERS = ["dense", "lexical"]',
             'RETRIEVERS = {"dense", "lexical"}'):
    if cand in s:
        opener, closer = cand[cand.index("(" if "(" in cand else
                                         "[" if "[" in cand else "{")], ""
        sub(cand, cand.replace('"lexical"', '"lexical", "full"'),
            "RETRIEVERS accepts 'full'")
        break
else:
    print("  ! RETRIEVERS tuple not found — check its literal form")

# --- the retriever itself -------------------------------------------------
sub('''    index = cfg.get("dense")''',
    '''    if which == "full":
        # No ranking, no query: the whole vocabulary IS the menu. Correct when
        # it fits in a prompt, which is the case that makes retrieval
        # unnecessary rather than the case that makes it easy. The `text`
        # argument is ignored, deliberately — a number carries no terms to rank
        # on, and pretending otherwise is what produced an empty menu and a
        # null code for every record.
        reg = cfg.get("registry")
        if reg is None or not hasattr(reg, "all_codes"):
            raise RuntimeError(
                "rung0_retrieval='full' needs a vocabulary that can enumerate "
                "itself (an `all_codes()` method). It is meant for a tag set "
                "small enough to put in a prompt; SNOMED is not."
            )
        menu = [{"code": c, "label": reg.preferred(c) or c, "fsn": c,
                 "via": "full"} for c in reg.all_codes()]
        return (lambda text, k: menu), which

    index = cfg.get("dense")''',
    "the 'full' retriever")

r0.write_text(s)

# --- all_codes() on the FiNER vocabulary ----------------------------------
v = pathlib.Path("ladder/vocab_finer.py")
t = v.read_text()
if "def all_codes" not in t:
    anchor = "    def shortlist(self"
    add = '''    def all_codes(self) -> list[str]:
        """Every tag. Only sane for a vocabulary that fits in a prompt.

        `Registry` deliberately has no equivalent: enumerating 129,675 SNOMED
        concepts into a menu is not a retrieval strategy, it is a mistake, and
        the absence of the method is what stops rung0_retrieval='full' being
        set for CADEC by accident.
        """
        return list(self._tags)

'''
    if anchor in t:
        v.write_text(t.replace(anchor, add + anchor, 1))
        print("  + FinerVocabulary.all_codes()")
    else:
        print("  ! could not place all_codes — add it by hand")

# --- the manifest ---------------------------------------------------------
mp = pathlib.Path("manifest.finer.json")
m = json.loads(mp.read_text())
m["rungs"]["0"]["rung0_retrieval"] = "full"
m["rungs"]["0"]["rung0_retrieval_note_finer"] = (
    "DEVIATION FROM FROZEN, declared — the second, after dense -> lexical, and "
    "with the same cause. Retrieval is a function of what is being retrieved "
    "from, and the two corpora differ by three orders of magnitude. CADEC "
    "ranks 20 candidates out of 129,675 concepts because they cannot go in a "
    "prompt. FiNER's 139 tag names can, so 'full' offers all of them and does "
    "no ranking. MEASURED CAUSE: the FiNER span is a NUMBER, so "
    "shortlist('19.8') has no tokens to overlap on and returned [] for every "
    "record — 22 of 22 came back with declined_shortlist:true and sct:null, "
    "which rung 1 correctly read as BAND rather than as a wrong code. "
    "Retrieval by term overlap is meaningless when the span carries no terms. "
    "COST: a 139-item menu on every pick call against CADEC's 20. Tokens per "
    "record will rise and that belongs in the cost column, not treated as free.")
mp.write_text(json.dumps(mp.read_text() and m, indent=2) + "\n")
print("  + manifest: rung0_retrieval='full', deviation declared")

print(f"\n{edits} edit(s) in r0.py")
print("\nCheck:")
print("  python3 -c \"import ast;ast.parse(open('ladder/rungs/r0.py').read())\" && echo ok")
print("  grep -n 'RETRIEVERS' ladder/rungs/r0.py")
print("\nThen the run. Note rung 4's prompt is STILL CADEC's — its judge said")
print("'the text does not indicate a personal adverse reaction' about a")
print("financial filing. That is a seventh prompt constant, in r4.py.")

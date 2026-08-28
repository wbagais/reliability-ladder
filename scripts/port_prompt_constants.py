#!/usr/bin/env python3
"""port_prompt_constants.py — the six constants, with a guard that cannot be talked past.

Rewrites `_ASK`, `_RULES`, `S0_PROMPT`, `S1_PROMPT`, `FIND_PROMPT` and
`PICK_PROMPT` in ladder/rungs/r0.py to render from the `PROMPTS` slot table
already in the file.

THE GUARD

All six originals are captured from the imported module BEFORE the edit. After
the edit the module is re-imported and each CADEC rendering is compared
byte-for-byte against what was captured. **If any one differs the file is
restored from git and the diff is printed.** No partial write.

That guard is not ceremony. Templating `BASE` by hand earlier silently changed
"for that reaction" into "for that adverse reaction" — two words, in a prompt
tuned over five phases, and the only reason it was caught is that the same
assertion existed. Six constants at once without it would be reckless.

WHAT IS AND IS NOT A SLOT

Slots: the entity, who describes it, what the source is called, the vocabulary
and its id, plus two whole paragraphs — `rules` and `pick_guidance` — because
those are annotation conventions and cannot be produced by substitution.

NOT slots, deliberately: field names, JSON shapes, the find-then-pick split, the
menu numbering, `CONCEPT_LESS`, the null/"no_concept" answers. Those are the
ladder's structure. A corpus needing them changed would be a different
experiment rather than a second data point.

FEWSHOT IS NOT PORTED, and that is a decision rather than an omission. It is the
synthetic fallback used only when `rung0_fewshot_docs` is empty; FiNER's
manifest names real pool documents, so the fallback never fires there. Porting a
fallback nobody exercises is invented work. It stays CADEC-shaped and is
documented as such.

Run from the repo root. Idempotent.
"""
import difflib
import importlib
import pathlib
import subprocess
import sys

R0 = pathlib.Path("ladder/rungs/r0.py")
NAMES = ("_ASK", "_RULES", "S0_PROMPT", "S1_PROMPT", "FIND_PROMPT", "PICK_PROMPT")

src = R0.read_text()
if "_ASK_TEMPLATE" in src:
    print("already applied")
    sys.exit(0)
if "PROMPTS = {" not in src:
    sys.exit("! PROMPTS slot table not found — run scripts/port_prompts.py first")

# ---- capture the originals from the LIVE module --------------------------
sys.path.insert(0, ".")
mod = importlib.import_module("ladder.rungs.r0")
ORIGINAL = {n: getattr(mod, n) for n in NAMES}
print(f"captured {len(ORIGINAL)} originals")

# ---- the replacement block -----------------------------------------------
# _ASK and _RULES are fragments the others embed, so everything becomes a
# function of the slots and the constants are rendered with CADEC's defaults.
NEW = '''_ASK_TEMPLATE = """  span_text  - {author_possessive} exact words, copied character for character
  context    - the three or four words IMMEDIATELY BEFORE span_text, copied the
               same way, so the quote can be located when it appears twice
"""

#: CADEC's extraction conventions. Every paragraph is a rule about THIS corpus,
#: several with measurements behind them, so this is a whole-paragraph slot
#: rather than something substitution can produce. A second corpus supplies its
#: own under manifest corpus.prompts.rules.
_RULES_CADEC = """
Report a reaction the writer explicitly says they did NOT have as well, and
mark it "negated": true — a denied reaction is still recorded. Every other
mention is "negated": false. Only the writer's own reactions count either way.
A blanket statement of wellness — "no side effects", "I feel fine" — is not a
reaction and is not reported; report only a SPECIFIC denied reaction.

Report EVERY symptom, condition or health problem the writer says they
experienced — including the condition the drug was taken for, and conditions
they merely compare themselves to. Work through the WHOLE POST: posts often
list many reactions in one sentence, and every item in the list is reported
separately.

Report a reaction EVERY TIME it is described. If the writer mentions the same
reaction twice, report it twice, each one where it appears — never merge
repeat mentions into one.

Vague and general states count. Feeling sick, being unwell, exhaustion or
feeling terrible are reactions too — report them even when the writer names no
specific symptom.

Report the reaction, not the treatment for it. A transfusion, an operation, a
scan or a hospital admission is something done TO the writer, not something the
drug did to them. Measured: 1 of 7,311 gold mentions names a procedure.
"""

#: The pick step's guidance. Also a whole-paragraph slot: it encodes what
#: "the right concept" MEANS for this corpus, including a worked example.
_PICK_GUIDANCE_CADEC = """Choose the PLAIN concept that names the reaction itself. When the list has
both a plain concept and a more specific variant of it, the plain one is
correct — severity, timing and circumstances the writer added do not belong
in the concept."""

#: CADEC-only. Fires only when rung0_fewshot_docs is empty; a corpus that names
#: its own pool documents never reaches it. NOT ported to other corpora —
#: porting a fallback nobody exercises is invented work.
_PICK_EXTRA_CADEC = """Example of no_concept: for reaction "felt like my old self was gone" with a
list of mood and fatigue concepts, the writer is describing a personal state
no clinical concept names — the answer is "no_concept", not the nearest mood.

A reaction marked [denied] is one the writer says they did NOT have. It is
still coded: choose the concept for the reaction being denied, exactly as if
it were experienced — the denial is recorded separately. That the writer did
not have it is never a reason to answer null or "no_concept"."""

PROMPTS["rules"] = _RULES_CADEC
PROMPTS["pick_guidance"] = _PICK_GUIDANCE_CADEC
PROMPTS["pick_extra"] = _PICK_EXTRA_CADEC


def ask(over: dict | None = None) -> str:
    return _ASK_TEMPLATE.format(**resolve(over))


def rules(over: dict | None = None) -> str:
    return resolve(over)["rules"]


def s0_prompt(over: dict | None = None) -> str:
    s = resolve(over)
    return (
        f"Extract every {s['entity']} {s['author']} describes in {s['source']} below.\\n"
        "\\nFor each one return:\\n"
        + ask(over)
        + f"  start,end  - character offsets of span_text in {s['source']}\\n"
        + f"  sct_label  - up to three {s['vocabulary']} names for the {s['entity_short']}, best first\\n"
        + f"  sct_code   - the {s['vocabulary']} id matching sct_label[0]\\n"
        "  confidence - 0.0 to 1.0\\n"
        + rules(over)
        + "\\nTwo different answers, and they are not the same:\\n\\n"
        f"  If no {s['vocabulary']} describes the {s['entity_short']}, answer CONCEPT_LESS for both\\n"
        "  sct_label and sct_code.\\n\\n"
        f"  If you know which {s['vocabulary_short']} it is but do not recall its id, give sct_label and\\n"
        "  answer null for sct_code. That is a complete and acceptable answer.\\n\\n"
        f"Never invent a {s['vocabulary_short']} id, and do not spend effort trying to recall one — null\\n"
        "is better than a guess.\\n\\n"
        'Return JSON: {"mentions":[{"span_text":..,"context":..,"start":..,"end":..,'
        '"sct_label":[..],"sct_code":..,"negated":..,"confidence":..}]}\\n'
    )


def s1_prompt(over: dict | None = None) -> str:
    s = resolve(over)
    return (
        f"Extract every {s['entity']} {s['author']} describes in {s['source']} below.\\n"
        "\\nFor each one return:\\n"
        + ask(over)
        + f"  sct_label  - up to three {s['vocabulary']} NAMES for the {s['entity_short']}, best\\n"
        "               first. Names, not id numbers — the id is looked up for you.\\n"
        "  confidence - 0.0 to 1.0\\n"
        + rules(over)
        + f"\\nIf no {s['vocabulary']} describes the {s['entity_short']}, answer CONCEPT_LESS.\\n\\n"
        'Return JSON: {"mentions":[{"span_text":..,"context":..,"sct_label":[..],'
        '"negated":..,"confidence":..}]}\\n'
    )


def find_prompt(over: dict | None = None) -> str:
    s = resolve(over)
    return (
        f"Extract every {s['entity']} {s['author']} describes in {s['source']} below.\\n"
        "\\nFor each one return:\\n"
        + ask(over)
        + "  confidence - 0.0 to 1.0\\n"
        + rules(over)
        + f"\\nQuote the {s['entity_short']} itself, not the sentence around it. "
        f"The {s['vocabulary_short']} name is\\nchosen in a second step, so do not give one here.\\n\\n"
        'Return JSON: {"mentions":[{"span_text":..,"context":..,"negated":..,'
        '"confidence":..}]}\\n'
    )


def pick_prompt(over: dict | None = None) -> str:
    s = resolve(over)
    extra = s.get("pick_extra")
    return (
        f"For each {s['entity_short']} below, choose the {s['vocabulary_short']} that means the same thing.\\n"
        "\\n"
        + s["pick_guidance"] + "\\n"
        f'\\nEach {s["entity_short"]} has a number after the word "{s["entity_short"]}". '
        f'Each {s["vocabulary_short"]} has a number\\n'
        f"in [square brackets]. Answer with the {s['entity_short']}'s number and the number in\\n"
        f"brackets of the {s['vocabulary_short']} you choose. Answer with numbers only, never with a\\n"
        f"{s['vocabulary_short']} name. Two other answers exist for choice:\\n"
        f"  null          - the {s['entity_short']} is real, but none of these "
        f"{s['vocabulary_short']}s describes it\\n"
        f'  "no_concept"  - this is not something any {s["vocabulary_short"]} could describe\\n'
        + (("\\n" + extra + "\\n") if extra else "")
        + "\\n{blocks}\\n"
        'Return JSON: {{"picks":[{{"reaction":..,"choice":..}}]}}\\n'
    )


_ASK = ask()
_RULES = rules()
S0_PROMPT = s0_prompt()
S1_PROMPT = s1_prompt()
FIND_PROMPT = find_prompt()
PICK_PROMPT = pick_prompt()
'''

# ---- splice: replace from _ASK through the end of PICK_PROMPT ------------
start = src.index("_ASK = ")
end = src.index('Return JSON: {{"picks":[{{"reaction":..,"choice":..}}]}}\n"""')
end = src.index('"""', end + 20) + 3

# Keep the FEWSHOT block and its comment, which live between _RULES and S0.
middle = src[start:end]
fs_start = middle.find("#: The few-shot ARM")
fs_end = middle.find("S0_PROMPT = ")
fewshot_block = middle[fs_start:fs_end] if fs_start != -1 and fs_end != -1 else ""

new_src = src[:start] + NEW + "\n\n" + fewshot_block + src[end:]
backup = src
R0.write_text(new_src)

# ---- the guard -----------------------------------------------------------
ok = True
try:
    importlib.reload(mod)
    for n in NAMES:
        got = getattr(mod, n)
        if got != ORIGINAL[n]:
            ok = False
            print(f"\n  ! {n} CHANGED")
            for line in list(difflib.unified_diff(
                    ORIGINAL[n].splitlines(), got.splitlines(),
                    "before", "after", lineterm=""))[:24]:
                print("      " + line)
        else:
            print(f"  = {n} byte-identical")
except Exception as exc:
    ok = False
    print(f"\n  ! import failed: {exc}")

if not ok:
    R0.write_text(backup)
    print("\nRESTORED. Nothing written. Fix the template and re-run.")
    sys.exit(1)

print("\nAll six render byte-identical for CADEC.")
print("\nNext:  wire run.py to pass corpus.prompts, then")
print("  PYTHONPATH=. python3 -m ladder.run --manifest manifest.finer.json \\")
print("      ladder --split test --limit 5 --tui")

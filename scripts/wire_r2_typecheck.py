#!/usr/bin/env python3
"""
wire_r2_typecheck.py — rung 2 learns a new reason, and stops naming SNOMED at
every corpus.

TWO CHANGES, AND ONLY THE SECOND CARRIES ANY RISK

1. A FACT for `type_mismatch`, and the reason added to `correctable`. Both are
   append-only. `FACTS` is a lookup — `build_fact` does `FACTS.get(reason)` and
   returns None for anything absent — so a new key is unreachable on a corpus
   whose rung 1 cannot emit that reason. SNOMED cannot. CADEC's behaviour is
   unchanged by construction, not by assertion.

2. `PROMPT` becomes slotted. This is the only edit to a string that is already
   in use, and it is the one that needs proving.

WHY THE PROMPT HAS TO CHANGE AT ALL

It opens "One of your answers was checked against SNOMED CT and the source
post", and closes "If no SNOMED CT code is right for this reaction". On FiNER
that is wrong in three places at once — the vocabulary is US-GAAP tags, the
source is an SEC filing, and a filing does not have reactions.

It has never mattered because **rung 2 has never fired on FiNER**: rung 1
rejected 1 record in 704 there, so `correct()` was never called and the prompt
was never sent. Giving FiNER a rejection class wakes it, and the first thing it
would do is send a prompt naming the wrong vocabulary to a model reading
financial statements.

THIS IS THE THIRD INSTANCE OF THE SAME DEFECT and it is worth naming as a class
rather than fixing three times in silence:

    rung 4's judge asked SEC filings whether a figure was "really an adverse
    reaction the writer says they experienced"      (found 2026-08-30)
    rung 0's six prompt constants needed slot templating for the port
                                                     (found 2026-08-29)
    rung 2's correction prompt names SNOMED CT       (found 2026-09-02, here)

Each was found the moment a rung that had been silent started doing something.
**A dead rung's prompt is never wrong, because it is never sent.** A port that
only touches the rungs that run will leave the others wrong and quiet.

THE GUARD

`prompt(None)` must return the existing `PROMPT` string byte for byte. The old
constant is KEPT in the file precisely so a test can compare against it — the
same method `scripts/port_prompt_constants.py` used to prove rung 0's six
constants had not moved during the FiNER port. If that test passes, CADEC's
correction prompt is provably unchanged and the slots are inert.

    python3 scripts/wire_r2_typecheck.py
    PYTHONPATH=. python3 -m pytest tests/test_r2_prompt_slots.py -q
"""
import pathlib
import sys

R2 = pathlib.Path("ladder/rungs/r2.py")


def main() -> int:
    s = R2.read_text()
    if "R2_PROMPT_SLOTS" in s:
        print("already applied"); return 0

    # ── 1 · the fact, appended to a lookup ──────────────────────────────
    old_facts_tail = """    R_SPAN_OUT_OF_RANGE: (
        'The offsets {start}-{end} fall outside the post, which is {n_source} '
        'characters long.'
    ),
}"""
    new_facts_tail = """    R_SPAN_OUT_OF_RANGE: (
        'The offsets {start}-{end} fall outside the post, which is {n_source} '
        'characters long.'
    ),
    # Rung 7's reason (2026-09-02). Present tense, specific, no hedging — the
    # same shape as the five above. The two types are named rather than the
    # rule that derived them: "your answer is a percentage tag" is a fact the
    # model can act on, and "the type check disagreed" is not.
    R_TYPE_MISMATCH: (
        'The text "{text}" names a {span_type}, but {sct} names a {code_type}. '
        'A {span_type} cannot be coded to a {code_type}.'
    ),
}"""
    if old_facts_tail not in s:
        print("  ! FACTS tail not found — has r2 changed?", file=sys.stderr); return 1
    s = s.replace(old_facts_tail, new_facts_tail, 1)
    print("  + FACTS: type_mismatch")

    # ── 2 · the reason, appended to correctable ─────────────────────────
    old_corr = ('    "correctable": (R_CODE_UNKNOWN, R_CODE_INACTIVE, R_WRONG_SEMANTIC_TYPE,\n'
                '                    R_SPAN_UNGROUNDED, R_SPAN_OUT_OF_RANGE),')
    new_corr = ('    "correctable": (R_CODE_UNKNOWN, R_CODE_INACTIVE, R_WRONG_SEMANTIC_TYPE,\n'
                '                    R_SPAN_UNGROUNDED, R_SPAN_OUT_OF_RANGE,\n'
                '                    # Emitted only by rung 7, which is only in rung_order on\n'
                '                    # the arm that enables it, over a vocabulary that\n'
                '                    # implements code_type(). Unreachable on CADEC.\n'
                '                    R_TYPE_MISMATCH),')
    if old_corr not in s:
        print("  ! correctable tuple not found", file=sys.stderr); return 1
    s = s.replace(old_corr, new_corr, 1)
    print("  + correctable: type_mismatch")

    # ── 3 · the import ──────────────────────────────────────────────────
    if "R_TYPE_MISMATCH," not in s.split("PROMPT")[0]:
        s = s.replace("    R_SPAN_OUT_OF_RANGE,\n",
                      "    R_SPAN_OUT_OF_RANGE,\n    R_TYPE_MISMATCH,\n", 1)
        print("  + import R_TYPE_MISMATCH")

    # ── 4 · the prompt, slotted, with the original kept as the reference ─
    marker = 'PROMPT = """One of your answers was checked against SNOMED CT'
    if marker not in s:
        print("  ! PROMPT not found", file=sys.stderr); return 1

    slots_block = '''#: CADEC's wording, as slot values. `prompt(None)` renders EXACTLY the PROMPT
#: constant below, and tests/test_r2_prompt_slots.py asserts that byte for byte
#: — the constant is kept solely as that test's reference. Same method
#: scripts/port_prompt_constants.py used to prove rung 0's six constants had not
#: moved during the FiNER port.
R2_PROMPT_SLOTS = {
    "vocabulary": "SNOMED CT",
    "source_ref": "the source post",
    "source_head": "The post",
    "id_name": "code",
    "entity_short": "reaction",
}


def prompt(slots: dict | None = None) -> str:
    """The correction prompt for one corpus. None keeps CADEC's wording.

    Rung 2 had never needed this because it had never fired outside CADEC: on
    FiNER rung 1 rejected 1 record in 704, so `correct()` was never called and
    a prompt naming SNOMED CT at a model reading SEC filings was never sent.
    Rung 7 gives FiNER a rejection class, which wakes rung 2, which is when the
    wording starts to matter.
    """
    s = {**R2_PROMPT_SLOTS, **{k: v for k, v in (slots or {}).items() if v is not None}}
    return (
        f"""One of your answers was checked against {s['vocabulary']} and {s['source_ref']}, and is wrong.

FACT: {{fact}}

{s['source_head']}:
{{source}}

Your answer was:
  span_text: {{text}}
  start,end: {{start}},{{end}}
  {s['id_name']}:      {{sct}}

Correct it. If no {s['vocabulary']} {s['id_name']} is right for this {s['entity_short']}, set {s['id_name']} to null —
do not substitute a {s['id_name']} you are unsure of.

Return JSON only: {{{{"span_text":..,"start":..,"end":..,"{s['id_name']}":..,"confidence":..}}}}
"""
    )


'''
    s = s.replace(marker, slots_block + marker, 1)
    print("  + prompt() added, PROMPT kept as the reference")

    # ── 5 · the call site ───────────────────────────────────────────────
    old_call = "    prompt = PROMPT.format(fact=fact, source=source, text=rec.text,"
    new_call = ("    # PROMPT is now the CADEC reference the byte-identity test compares\n"
                "    # against; the call site renders from slots so a second corpus does\n"
                "    # not receive a prompt naming SNOMED CT.\n"
                "    tpl = prompt((cfg.get(\"manifest\") or {}).get(\"corpus\", {}).get(\"r2_prompts\"))\n"
                "    prompt_text = tpl.format(fact=fact, source=source, text=rec.text,")
    if old_call not in s:
        print("  ! call site not found", file=sys.stderr); return 1
    s = s.replace(old_call, new_call, 1)
    s = s.replace("                           start=s, end=e, sct=rec.sct)\n",
                  "                                  start=s, end=e, sct=rec.sct)\n", 1)
    s = s.replace('    raw, usage = llm(prompt, "", "correct")',
                  '    raw, usage = llm(prompt_text, "", "correct")', 1)
    print("  + call site renders from slots")

    R2.write_text(s)
    print("\nNow watch the guard fail, then pass:")
    print("    PYTHONPATH=. python3 -m pytest tests/test_r2_prompt_slots.py -q")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

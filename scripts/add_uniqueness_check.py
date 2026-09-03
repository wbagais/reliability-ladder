#!/usr/bin/env python3
"""
add_uniqueness_check.py — the preflight learns the thing the geo arm taught it.

WHAT WENT WRONG

`preflight_rungs.py` asks whether rung 1's ACCEPT lane can FIRE — can the span
and the code be compared as strings at all. It answered correctly three times:

    CADEC        42.4%  build   → the lane worked, 80-89% correct
    FiNER-139     0.0%  don't   → shipped 0%, exactly as predicted
    GeoWebNews   39.8%  build   → the lane fired, and was WORSE than BAND

The third is the problem. The tool said BUILD and the lane turned out to be
harmful: measured 2026-09-02, ACCEPT scored 0.206 / 0.134 / 0.214 against BAND's
0.250 / 0.330 / 0.370 on three models. The check endorses most confidently where
it knows least.

WHY, AND WHY IT IS PREDICTABLE

ACCEPT means *the vocabulary uses these very words*. That is evidence only if
the words IDENTIFY something. On SNOMED they do — little other than
|Chronic pain| is called "chronic pain". On a gazetteer they do not: "London"
matching an entry named "London" says nothing about WHICH London, and 1,117 of
2,399 GeoWebNews gold mentions carry a name more than one entry holds.

That is a property of the VOCABULARY, computable with no model, no corpus and no
run — exactly the shape everything else in this tool has. The preflight had the
data and did not look.

WHAT THIS ADDS

    ambiguity   what share of the vocabulary's names are held by more than one
                concept, and how many concepts the average shared name covers

and it changes rung 1's verdict from BUILD to CAUTION when a lane that fires
would be endorsing a name that does not identify. The two preconditions are now
separate and both are reported:

    can the check FIRE?      lexical comparability   (had this)
    is firing WORTH anything? name uniqueness         (this)

Run from the repo root. Idempotent.
"""
import pathlib
import sys

P = pathlib.Path("scripts/preflight_rungs.py")


def main() -> int:
    s = P.read_text()
    if "check_name_uniqueness" in s:
        print("already applied"); return 0

    # ── the new check ───────────────────────────────────────────────────
    anchor = "def check_reject_lane(man, gold, vocab):"
    if anchor not in s:
        print("  ! check_reject_lane not found", file=sys.stderr); return 1

    new_check = '''def check_name_uniqueness(man, gold, vocab):
    """rung 1 · does a name IDENTIFY, or merely match?

    The check this tool was missing, and the geo arm is why it exists.

    ACCEPT means the vocabulary uses the extracted words. That is evidence only
    where the words pick out one concept. Measured 2026-09-02: on GeoWebNews the
    ACCEPT lane FIRED at 39.8% and was WORSE than BAND on all three models —
    0.206/0.134/0.214 against 0.250/0.330/0.370 — because 1,117 of 2,399 gold
    mentions name a place more than one gazetteer entry holds. Matching "London"
    to "London" is not evidence about which London.

    Computed over the ANSWER KEY's own names rather than the whole vocabulary:
    a gazetteer's 13.4M entries contain vast numbers of names nothing will ever
    extract, and their ambiguity is not this task's problem. What matters is
    whether the names this corpus actually uses identify anything.
    """
    c = Check(1, "name uniqueness", "does a matching name IDENTIFY one concept?")
    shared = tried = 0
    worst = []
    for m in gold:
        name = None
        try:
            name = vocab.preferred(m.sct[0]) if m.sct else None
        except Exception:
            name = None
        if not name:
            continue
        try:
            holders = vocab.codes_for_term(name) or []
        except Exception:
            continue
        tried += 1
        if len(holders) > 1:
            shared += 1
            if len(worst) < 5:
                worst.append((name, len(holders)))
    if not tried:
        return c.failed(RuntimeError("no gold name could be looked up"))

    rate = shared / tried
    ev = (f"{shared} of {tried} gold names are held by more than one concept "
          f"({rate:.1%})")
    if worst:
        ev += "  e.g. " + ", ".join(f"{n!r}x{k}" for n, k in worst[:3])

    if rate > 0.30:
        return c.report(DONT, ev,
                        "A name that several concepts share is not evidence about which one. "
                        "A lane built on it will ENDORSE most confidently where it knows least "
                        "— measured on GeoWebNews, where the ACCEPT lane fired at 39.8% and "
                        "scored WORSE than BAND on every model tested. If the lane must exist "
                        "here, route on it as a warning rather than an endorsement.")
    if rate > 0.10:
        return c.report(UNKNOWN, ev,
                        "Enough shared names to weaken the lane without killing it. Measure the "
                        "ACCEPT lane's correctness AGAINST the BAND lane's before trusting it; "
                        "if ACCEPT is not clearly better, the check is matching rather than "
                        "identifying.")
    return c.report(BUILD, ev,
                    "Names in this vocabulary mostly identify one concept, so a lexical match is "
                    "evidence rather than a coincidence. This is the condition CADEC meets and a "
                    "gazetteer does not.")


'''
    s = s.replace(anchor, new_check + anchor, 1)
    print("  + check_name_uniqueness")

    # ── run it, right after the lane check it qualifies ─────────────────
    old_calls = """    checks.append(check_accept_lane(man, gold, vocab))
    checks.append(check_reject_lane(man, gold, vocab))"""
    new_calls = """    checks.append(check_accept_lane(man, gold, vocab))
    # Immediately after the lane check, because it QUALIFIES that verdict: a
    # lane that fires on names nothing identifies is worse than one that does
    # not fire at all, and only the pair says which case you are in.
    checks.append(check_name_uniqueness(man, gold, vocab))
    checks.append(check_reject_lane(man, gold, vocab))"""
    if old_calls not in s:
        print("  ! call site not found", file=sys.stderr); return 1
    s = s.replace(old_calls, new_calls, 1)
    print("  + wired after the ACCEPT lane check")

    # ── the closing note, which was a binary and is now not ─────────────
    s = s.replace(
        'print(DIM("  A rung marked DON\'T is not broken. Its bet does not hold on this data,"))',
        'print(DIM("  A rung marked DON\'T is not broken. Its bet does not hold on this data,"))\n'
        '    print(DIM("  and a rung marked BUILD is not finished: a check can FIRE and still be"))\n'
        '    print(DIM("  worthless, which is what the name-uniqueness row is for."))',
        1)

    P.write_text(s)
    print("\nRun it on all three corpora — the geo row is the one to read:")
    print("    PYTHONPATH=. python3 scripts/preflight_rungs.py --static")
    print("    PYTHONPATH=. python3 scripts/preflight_rungs.py --manifest manifest.finer.json --static")
    print("    PYTHONPATH=. python3 scripts/preflight_rungs.py --manifest manifest.geo.json --static")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

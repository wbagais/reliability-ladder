"""The calibration record — what this tool has predicted, and what happened.

WHY

Every threshold in the preflight was tuned on three corpora: 2% false
rejection, 10% minimum coverage, `worst > 50` for name ambiguity. All are
defensible and none is independently validated, and a verdict printed without
that context is read as authority it has not earned.

Worse, the tool has already been wrong once in a way that mattered. On
GeoWebNews it said the ACCEPT lane would fire — correct, 39.8% — and the lane
turned out to score WORSE than the BAND lane it was supposed to beat, on all
three models. The prediction was right and the recommendation was wrong.

A tool that reports its own miss rate is trustworthy in a way a confident one
is not. This module is that report.

THE RULE THIS ENFORCES, and it came from the tool getting it wrong

Measured 2026-09-02, the same relation on the same model output, differing only
in split:

    FiNER test   30 contradictions, 11 with gold,  0 false   —  0.0%
    FiNER dev    44 contradictions, 14 with gold,  5 false   — 35.7%

**A verdict is not a property of a check.** It is a property of
`(check, corpus, split, gold-or-model)`, and a number stated without that tuple
is manufacturing confidence. So `Verdict` cannot be constructed without one —
not by convention, by signature.

And where both splits are known the pair is reported, never the mean. The mean
of 0.0% and 35.7% is 17.9%, which describes neither and hides that they
disagree — the pooled-metrics failure this project documented on CADEC, arriving
inside the tool built to prevent it.
"""
from __future__ import annotations

import json
import pathlib
from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Any

RECORD = pathlib.Path("docs/calibration.json")


@dataclass(frozen=True)
class Scope:
    """The tuple a verdict is about. There is no verdict without one."""

    corpus: str
    split: str
    on: str            # "gold" | "model output"
    n: int             # the denominator, named and counted

    def __str__(self) -> str:
        return f"{self.corpus}/{self.split} on {self.on}, n={self.n}"


@dataclass
class Prediction:
    """What the tool said, when, and what happened afterwards.

    `outcome` is deliberately not a boolean. A prediction can be right about
    what it measured and wrong about what it implied — which is exactly the
    GeoWebNews miss, where "the lane will fire" was correct and "so build it"
    was not.
    """

    check: str
    scope: dict
    said: str
    when: str
    outcome: str = "unknown"       # right | wrong | partly | unknown
    what_happened: str = ""
    note: str = ""


#: The record so far. Hand-written because each row is a claim about this
#: project's own history, and generating them would make them unfalsifiable.
PREDICTIONS: list[Prediction] = [
    Prediction(
        check="accept_lane_fires", said="BUILD — the lane can fire",
        scope=asdict(Scope("CADEC", "dev", "gold", 276)),
        when="2026-09-01", outcome="right",
        what_happened="42.4% on gold; the lane measured 80-89% correct across "
                      "five model families spanning 2.8x in headline F1.",
    ),
    Prediction(
        check="accept_lane_fires", said="DON'T — the lane cannot fire",
        scope=asdict(Scope("FiNER-139", "dev", "gold", 165)),
        when="2026-09-01", outcome="right",
        what_happened="0 of 704 on the full run. Structural: a numeral shares "
                      "no token with an English phrase, on any run.",
    ),
    Prediction(
        check="accept_lane_fires", said="BUILD — the lane can fire",
        scope=asdict(Scope("GeoWebNews", "dev", "gold", 442)),
        when="2026-09-01", outcome="partly",
        what_happened="The lane DID fire at 39.8%, so the prediction was "
                      "correct. But it scored WORSE than the BAND lane it was "
                      "meant to beat — 0.206/0.134/0.214 against "
                      "0.250/0.330/0.370 on three models.",
        note="THE MISS THAT MATTERS. Right about firing, wrong about worth. "
             "name_uniqueness was added because of it, and has not itself been "
             "tested on a corpus it did not come from.",
    ),
    Prediction(
        check="name_uniqueness", said="DON'T — names do not identify",
        scope=asdict(Scope("GeoWebNews", "dev", "gold", 442)),
        when="2026-09-02", outcome="unknown",
        note="Added AFTER the miss above and tuned to catch it. Fitting a "
             "threshold to the case that embarrassed you is not validation; "
             "this stays `unknown` until it is right about a corpus it was not "
             "built on.",
    ),
    Prediction(
        check="type_relation", said="USABLE — 1.22% false on gold",
        scope=asdict(Scope("FiNER-139", "test", "gold", 187)),
        when="2026-09-02", outcome="wrong",
        what_happened="35.7% false rejections on model output, dev split. Gold "
                      "spans sit where the annotator put them; model spans "
                      "drift, and the type rules then read the wrong context "
                      "window and contradict confidently on a misreading.",
        note="Tuned on gold and validated on gold — the measurement set WAS "
             "the tuning set. Rung 7 was built on this verdict and rejected.",
    ),
    Prediction(
        check="type_relation", said="0% false",
        scope=asdict(Scope("FiNER-139", "test", "model output", 30)),
        when="2026-09-02", outcome="partly",
        what_happened="True on test, and 35.7% on dev with the same relation "
                      "and the same model output. The verdict is a property of "
                      "the split, not of the check.",
    ),
]


def summary(check: str | None = None) -> str:
    rows = [p for p in PREDICTIONS if check is None or p.check == check]
    if not rows:
        return ""
    counts = {k: sum(1 for p in rows if p.outcome == k)
              for k in ("right", "partly", "wrong", "unknown")}
    parts = [f"{v} {k}" for k, v in counts.items() if v]
    return f"{len(rows)} prediction(s) on record · " + ", ".join(parts)


#: The preflight named its checks before ladder/relations.py existed, and the
#: dated entries above use those names. Mapped rather than rewritten: an entry
#: is a claim about what was predicted on a date, and editing its subject would
#: change the claim.
ALIASES = {
    "lexical": "accept_lane_fires",
    "unique": "name_uniqueness",
    "type": "type_relation",
}


def caveat(check: str) -> str:
    """The line printed beside a verdict, or nothing if there is no history."""
    check = ALIASES.get(check, check)
    rows = [p for p in PREDICTIONS if p.check == check]
    if not rows:
        return "no track record — this check has never been tested against an outcome"
    misses = [p for p in rows if p.outcome in ("wrong", "partly")]
    s = summary(check)
    if not misses:
        return s
    worst = misses[0]
    return f"{s}  ·  MISSED on {worst.scope['corpus']}: {worst.what_happened[:88]}"


def report() -> str:
    lines = ["  what this tool has predicted, and what happened", ""]
    for p in PREDICTIONS:
        mark = {"right": "✓", "wrong": "✗", "partly": "~", "unknown": "?"}[p.outcome]
        sc = p.scope
        lines.append(f"  {mark} {p.check:22} {p.said}")
        lines.append(f"    {sc['corpus']}/{sc['split']} on {sc['on']}, "
                     f"n={sc['n']} · {p.when}")
        if p.what_happened:
            lines.append(f"    → {p.what_happened}")
        if p.note:
            lines.append(f"    ! {p.note}")
        lines.append("")
    lines.append(f"  {summary()}")
    lines.append("")
    lines.append("  Every threshold here was tuned on THREE corpora. Read a verdict as")
    lines.append("  a hypothesis with a track record, not as a fact — and read the tuple,")
    lines.append("  because the same check has measured 0.0% and 35.7% false on two")
    lines.append("  splits of one corpus.")
    return "\n".join(lines)


def save(path: pathlib.Path = RECORD) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(
        {"updated": date.today().isoformat(),
         "predictions": [asdict(p) for p in PREDICTIONS]}, indent=2) + "\n")


if __name__ == "__main__":
    print()
    print(report())
    print()

"""One file per rung. Rung ID equals execution position.

    r0  bare LLM          r3  voting
    r1  deterministic     r4  LLM-as-judge
    r2  self-correction   r5  abstention
                          r6  human-in-the-loop

Deterministic, no model call:  r1.py  r5.py
Model-facing:                  r0.py  r2.py  r3.py  r4.py

Every rung implements the same signature — `schemas.runner.Rung`,
`apply(records, sources, cfg) -> records` — which is what makes adding a rung
twenty minutes rather than an hour, and what lets iteration 2 swap any one of
them without touching the others.
"""

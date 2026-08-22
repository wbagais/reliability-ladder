"""One file per rung, one owner per file.

A (the spine, deterministic):  r1.py  r2.py
B (the model surface):         r0.py  r3.py  r4.py  r5.py
Joint:                         r6.py

Every rung implements the same signature — see `base.apply` — which is what
makes adding a rung twenty minutes rather than an hour, and what lets iteration
2 swap any one of them without touching the others.
"""

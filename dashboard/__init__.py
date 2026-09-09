"""Ladder Workbench — a read-only lens over the reliability-ladder pipeline.

M1 (spec.md §Milestones): tabs R1/R3/R4/R5 over existing artifacts, visuals
V1-V6 and V10. No launcher, no writes of any kind. The app never computes a
score its own way (`ladder.score.score_run` / `bootstrap_ci` only) and never
invents a file format — it reads what the pipeline already writes.

Start it with `python -m dashboard` (binds 127.0.0.1 only — C1).
"""

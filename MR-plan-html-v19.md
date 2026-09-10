# plan.html v19: the plan page rewritten around the consolidated re-run

Branch `claude/plan-html-redesign-12e3ae` → `main`. Written 2026-09-10; the durable record of each step is in `docs/decisions.md`'s dated entries and the commit messages on the branch.

## What was built

`docs/plan.html` v19 — the GitLab Pages page rewritten around the current outputs, plus the tooling that keeps it honest.

- **Plan tab**: a record of the result — the consolidated re-run's three draws, the shipping rules, cost, the noise floor, the matrix, PsyTAR's full ladder, the held-out run, the three checks, a resolved risk register. The four InfoQ figures embedded; the `pages` job now copies `docs/figures`.
- **One data block** (`<script id="plan-data">`) feeds every table and figure; `tests/test_plan_html.py` compares it cell by cell to `runs/archive/`, `matrix.csv` and the PsyTAR cell, forbids the superseded numbers and hosts, and requires the current ones.
- **Ladder demo**: real records, one example for every path a record can take, per dataset, drawn the way the Workbench's Live tab draws a document — rung 0 against gold, the grid of records by rungs 1–4, the person column with the six rules. `scripts/plan_demo.py` calls `dashboard.document_view` over the archived raw run and reduces the payload: no post, no calls, no prose, spans within the seven-word precedent. CADEC posts appear as a redacted paragraph (blank blocks, quoted spans in place); FiNER's excerpt is shown (CC-BY-SA); PsyTAR from the published stripped records.
- **Ladder flow**: four still figures, each one finding — a dataflow diagram per dataset, right answers against tokens per rung, the shipping rules as accuracy vs yield, the cross-corpus lane chart. Every count from tracked files, recomputed by the test.
- **Removed**: the Triage desk (a simulated review session never timed), the header knobs, the falling-dots animation.
- `scripts/plan_local.py` builds a local-only copy with the full posts under `out/` (gitignored), refusing any other path — for the licensee's screen, never for git.

## Checks

- 1,295 tests pass in the CI venv (`python:3.12-slim` + requirements + pytest), preflight clean on every commit.
- New tests: `test_plan_html.py` (14), `test_plan_demo.py` (10), `test_plan_local.py` (2).
- `origin/main` merged in (`bab01af`).


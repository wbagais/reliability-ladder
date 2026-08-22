# AI Reliability Ladder

Measure what each reliability layer around an LLM actually buys you — and what it
costs — so you can stop at the rung your economics justify instead of stacking
layers by intuition.

**Task.** Pharmacovigilance triage: read an archived patient report, identify the
adverse reactions the writer describes, and normalise each to a SNOMED CT code.
The system reports *what a document says*. It never asserts that a drug caused an
effect.

📄 **[Plan, architecture and interactive demo](https://pushpdeep.gitlab.io/ai-reliability-ladder/)** — published by CI on every push to `main`.

---

## The ladder

| Rung | Layer | Mechanism | Extra cost |
|---|---|---|---|
| 0 | bare LLM | one call; emits a code (with or without a lookup tool — see `rung0_mode`) | 1 call/item |
| 1 | deterministic | schema · **span grounding** · **negation** · code exists · semantic type | **none** |
| 2 | abstention | decline anything still unresolved below threshold | none |
| 3 | self-correction | one bounded retry, fired **only by a rung 1 failure**, reason stated as fact | +1 call |
| 4 | LLM-as-judge | second model, **different family**, scores the record | +1 call |
| 5 | voting | k samples, majority on the **normalised code**, never the string | k calls |
| 6 | human-in-the-loop | a person settles it — simulated, or timed in the review queue | human minutes |

Runtime order is `[0, 1, 3, 5, 4, 2, 6]`, not numeric — abstaining before you have
tried correction and voting throws away recoverable records. Order lives in
`manifest.json`, so it is a testable ablation rather than an assertion.

## Cost, in three measures that are never fused

**Tokens per record** · **latency p95** · **records routed to a person**.

No dollar figure: a single `$/100` needs a price table that shifts under you, and
it silently merges three costs that are not interchangeable. Keeping them apart
forces the honest question — *would you rather spend tokens or human attention?*

## Quick start

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt

# 0 · the critical-path dependency: does the vocabulary lookup work?
.venv/bin/python -c "import bench.vocab as v; print(v.exists('60862001'), v.is_finding('60862001'))"

# 1 · rung 0 + rung 1, both tool modes, side by side
.venv/bin/python -m bench.ladder_ab --compare

# 2 · before every push
python scripts/preflight.py --history
```

## Data — read before you clone

The corpus is **not in this repository and cannot be**.

| Source | Terms | Where it lives |
|---|---|---|
| **CADEC v3** | CSIRO Data Licence — non-commercial, **non-transferable**, no redistribution | [csiro:10948](https://data.csiro.au/collection/csiro:10948). Each team member accepts it individually. `data/cadec/` is gitignored. |
| **SNOMED CT** | affiliate licence for full releases | queried at run time via [EBI OLS4](https://www.ebi.ac.uk/ols4) — free, no API key |
| **MedDRA** | subscription (MSSO) | only `data/meddra_codes.example.csv` (10 rows, for tests) is committed |

`scripts/preflight.py` scans the working tree *and* git history for corpus text,
API keys and forbidden paths. It runs in CI on every merge request and blocks the
pipeline on a breach — deleting a file later does not remove it from history.

## Layout

```
bench/      vocab.py (SNOMED + MedDRA) · ladder_ab.py · rungs/ · metrics · cli
app/        dashboard (local: run + review queue; published: results viewer)
schemas/    runner · results.schema.json · adapter
data/       example files only — real corpora are gitignored
docs/       plan.html (published) · decisions.md (the article's raw material)
scripts/    preflight.py
tests/      against a fake LLM — no network, no keys, no corpus
```

## Hosting

**GitLab Pages** serves `docs/plan.html` as a static page — no Python, no corpus,
no key. It is *structurally* incapable of leaking anything, rather than merely
configured not to.

Streamlit Community Cloud is **GitHub-only**, so the interactive dashboard runs
locally. If you want it hosted later, the options are a push-mirror to GitHub or
Hugging Face Spaces.

## Licence

Code: MIT. Third-party data keeps its own terms — see `LICENSE`.

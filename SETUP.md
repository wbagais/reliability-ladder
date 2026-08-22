# Pushing to GitLab

```bash
git clone https://gitlab.com/pushpdeep/ai-reliability-ladder.git
cd ai-reliability-ladder
# copy this bundle in, preserving paths
python scripts/preflight.py --history     # must exit 0
git add . && git commit -m "scaffolding: CI, licence boundary, vocab resource"
git push
```

## Files in this bundle

| Path | Why |
|---|---|
| `.gitlab-ci.yml` | **preflight + licence-scan run on every MR and block the pipeline.** Plus tests, a vocab smoke test, and the Pages job. |
| `.gitignore` | The licence boundary as code. Note `*.ipynb` — output cells are the classic leak — and `public/`, built by CI. |
| `README.md` | Repo front page. Update the Pages URL if your namespace differs. |
| `LICENSE` | MIT for the code, with an explicit carve-out naming CADEC, MedDRA and SNOMED. |
| `requirements.txt` | Pinned. |
| `scripts/preflight.py` | Scans tree **and history** for corpus text, keys, forbidden paths, unpinned deps. |
| `bench/vocab.py` | SNOMED via EBI OLS4 (free, no key) + MedDRA local. A **global resource**, not a per-item trusted_record. |
| `bench/ladder_ab.py` | Rung 0 modes A/B + rung 1. One file, one flag — two implementations would confound tool access with prompting. |
| `bench/__init__.py` | Makes `bench` importable for CI. |
| `data/meddra_codes.example.csv` | 10 rows for tests. Full list stays gitignored. |
| `docs/plan.html` | v17 — plan, architecture, demo, glossary. **Published by CI to Pages.** |

## Turn Pages on

Settings → Pages. After the first `main` pipeline the site is at
`https://pushpdeep.gitlab.io/ai-reliability-ladder/`.

Pages serves `public/`, built by the `pages` job from `docs/plan.html`. Static
only — no Python runs there, so the published page cannot touch the corpus.

## Still to create

- **`app/results.reference.json`** — one real run. Without it the dashboard
  shows stub numbers as if real. `preflight.py` warns until it exists.
- **`ladder/rungs/r0.py` · `r3.py` · `r4.py` · `r5.py` · `ladder/score.py`** —
  owner B. `run.py` reports a missing rung rather than faking it.

Done since this file was written: `tests/` (129 tests, fake LLM, no network),
`docs/decisions.md`, and `manifest.json` — which replaced the template, so
copy that rather than filling a blank.

## Protect main

Settings → Repository → Protected branches → `main`, and require a passing
pipeline before merge. That makes the preflight gate binding rather than advisory
— which is the whole point of putting it in CI.

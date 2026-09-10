# Changelog

What changed, when, and **which published numbers it moved**. A study's
changelog is not a feature list: the entries that matter are the ones that
changed a figure someone may have already quoted.

Every entry here has a longer, dated counterpart in
[`docs/decisions.md`](docs/decisions.md), which is the durable record. This file
is the index into it.

---

## 2026-09-10

**The plan page rewritten (v19).** The page GitLab Pages serves had been
quoting a superseded run since 2026-08-28 — a shipped share, an error rate
and a routing count that the consolidated re-run replaced — from a
hand-typed array nothing checked. Every number on it now comes from one data
block that `tests/test_plan_html.py` compares to `runs/archive/`,
`matrix.csv` and the PsyTAR cell. The demo shows real records of the first
draw the way the Workbench's Live tab draws a document (the post redacted to
its quoted spans for CADEC, the excerpt shown for FiNER); the flow is four
still figures generated from the run; the simulated triage desk is gone.
`scripts/plan_local.py` builds a copy with the full posts under `out/` only.
Write-up: [`MR-plan-html-v19.md`](MR-plan-html-v19.md).

## v1.0 — 2026-09-08

**The state the InfoQ article cites.** Every number it prints was produced
by this tag and can be re-derived from the run archive without a GPU or a
corpus licence. Full notes, including the known limitations, in
[`docs/RELEASE-v1.0.md`](docs/RELEASE-v1.0.md).


**Published the matrix.** ~50 scoreable cells across 7 corpora and 5 model
families, development and held-out splits, in
[`runs/archive/matrix-2026-09-07/`](runs/archive/matrix-2026-09-07/). Stripped
of quoted text and **verified to score identically** — `score_matrix.py --dir`
reproduces every published figure from the repository alone.

**Retracted a claim.** The separation figure for TR-News — the endorsed lane
scoring *below* the records the check declined, 0.6–0.9× — was measured on the
development split and does **not** survive the held-out one, which gives
1.1–4.2×. It moved for the wrong reason: the lane's own accuracy fell while the
comparison band collapsed from 19.4% to 3.2%. The two-family result stands; the
"worse than not checking" reading does not.

**A fifth model family.** `qwen3:8b` across six corpora. The 8b and not the 4b,
which has no entry in `models.yaml`, falls back to a 2,000-token budget it
spends thinking, and returns empty content.

**LINNAEUS, third fix.** Capping the few-shot passage at 600 characters took
`granite4:micro-h` from 0 to 5 endorsed records and `mistral:7b` from 0 to 3.
`llama3.1:8b` still produces nothing at all, after three separate attempts.
Denominators of 3, 4 and 8 — real, and too thin to carry a claim.

## 2026-09-07

**`gatecheck` and `crosscheck`**, with 52 tests between them, in
`ladder/checks/`. Each test makes its check fail on the specific defect that
reached a rented GPU first, then confirms the fix passes.

**Four prompt blocks**, each derived from its corpus's own measured gold rather
than written from an impression of it.

**Corrected twelve cells.** LGL, TR-News, LINNAEUS and BC5CDR had run with
CADEC's task description — asking for adverse drug reactions in documents about
places, species and diseases. Their earlier numbers are void; the re-run
numbers are what the matrix now carries.

**The paid layers, on a second corpus.** Full ladder on PsyTAR, three draws:
self-correction, sampled voting and the second-model judge each routed **zero**
records. Coverage identical to the free layers alone. That was a one-corpus
claim before this run.

## 2026-09-06

**The matrix.** Six corpora × four model families, one variable per cell.

**Five cells found running the wrong model** — two runners sharing one scratch
filename overwrote each other's configuration. Caught only because every run
saves the configuration it actually received beside its results. All five were
deleted and re-run; the headline PsyTAR figure reproduced exactly.

## 2026-09-05

**PsyTAR**, the matched comparison: same forum, same vocabulary, different
drugs. The free check's precision transfers; its reach does not.

**The semantic check encodes CADEC's annotation guide**, not SNOMED's structure
— it contradicts 37 correct gold records on PsyTAR.

## 2026-09-04

**CADEC's endorsable ceiling corrected: 43% → 32% on development, 38%
corpus-wide.** The gold replay was re-run on the base run's own configuration
and denominator. Every figure quoting 43% was regenerated.

## 2026-09-03

**Consolidated re-run** of CADEC and FiNER at rungs 0–6, three draws each, in
`runs/archive/consolidated-2026-09-03/`. Every dev-side number in the article
has its source in git from this point.

## 2026-08-29 and earlier

FiNER-139 and GeoWebNews ported. `stagecheck` extracted to its own repository.
The judge shown the menu rather than a bare code, which took its separation
from 1.7× to 3.4–4.2×. Threshold-based confidence retired: the extractor
reports 1.0 on two-thirds of its answers, right or wrong.

See [`docs/decisions.md`](docs/decisions.md) for the full record, including
entries that predate this file.

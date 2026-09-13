# v1.1 — the Workbench, and a claim the harness had been making for us

*Tagged 2026-09-10. **No measured result changes in this release.** The matrix,
the two-family split and the paid-layer finding are exactly as v1.0 published
them. What changes is that you can now watch a run instead of reading a table —
and that two published claims turned out to be about our own code rather than
the model's behaviour.*

---

## The retraction first

**The article's "slot-0 attractor" was our fallback, not the model.**

Both `docs/article-v3.md` and `docs/article.md` led with a finding that the
extractor has a position prior — that it reaches for the first item on a menu.
Three draws with the menu permuted per mention were run to break it.

**There was no prior to break.** 74 of the base run's 77 attractor predictions
are `_fill_from_menu` writing menu position 0 — the harness's own fallback for a
pick the model never made. The model chose the first tag **3 times**, a 1.3%
rate against 0.72% by chance.

The shuffle arm itself collapsed — coding accuracy 0.425 → 0.058 — and that
collapse is an artefact it created: picks are batched seven per call, every
mention normally sees the same menu, so a per-mention permutation aliases the
indices. 26.0% of mis-codes read the right concept off a sibling's ordering,
against a 3.7% null, *p* = 0.0005. **The arm is rejected because the question
was malformed, not because randomisation fails.**

Both articles now carry the refutation. `CLAUDE.md` and the plan notes were
updated so the superseded numbers cannot be requoted as a claim about the model.

Priced while there: switching the fallback off costs F1 exact −0.0084
[−0.0279, +0.0000] and answers 239 records instead of 313. It converts 2 of 74
writes. New arms `manifest.finer.nofallback.json` and
`manifest.finer.shufflemenu.json` carry both configurations.

Incidentally, this was **the first FiNER measurement with no run-to-run
variation at all** — three base draws and three arm draws, byte-identical, no
document refused on any of the six.

## The published page had the same defect on its front

`docs/plan.html` — the page GitLab Pages serves — had been quoting a
**superseded run since 2026-08-28**: a shipped share, an error rate and a
routing count that the consolidated re-run had replaced, from a hand-typed chart
array nothing checked.

That is this project's signature failure, on its own front page: **a number
recorded in one place, never read back.**

Rewritten as v19. Every figure now comes from one data block, and
`tests/test_plan_html.py` compares it cell by cell against
`runs/archive/consolidated-2026-09-03/`, `matrix.csv` and the PsyTAR full-ladder
cell — forbidding the superseded strings and requiring the current ones.

The demo shows **real records** now, followed through the archived run by
`scripts/plan_demo.py`, rather than invented posts with measured numbers pasted
beside them. Licence handling is explicit: FiNER's excerpt is shown (CC-BY-SA),
PsyTAR is drawn from the published stripped records, and a CADEC document gets a
**synthetic stand-in** — the annotators' spans at their real positions, every
other slot filled from a bank of first-person phrases containing no symptom or
body words, so filler can never read as a missed annotation. A leak check
refuses any 24-character window of the real post outside an allowed span.
`scripts/plan_local.py` builds the full-text copy under `out/` only.

## The Workbench

A read-only local interface over runs that already exist — `dashboard/`, three
tabs, **113 dashboard tests**.

| tab | what it shows |
|---|---|
| **Data** | the corpus: a document with its annotations, or the table filtered by split and drug, with each document's pairing against gold so sorting by *missed* finds the interesting ones |
| **Results** | a batch run: the verdict flow from the ledger, rungs 0–4 lane by lane, and the six shipping rules over the batch with a proportion bar each |
| **Live** | one document through the **real** rungs, in-process, into a scratch directory that is deleted |

**Live calls `ladder.run.run_ladder` itself** — the pipeline's own driver, every
rung's own `apply`, the model resolved from the manifest. Nothing is
re-implemented, which is the governing rule, and nothing becomes a run: no
`out/` write, no `results.csv`, no entry in the runs list. The held-out split is
refused with a 403 carrying the word *spent*.

**What it will not do:** show prompts and raw replies on the page (they stay in
the run's call files), mix a live run with batch results, or state a number it
cannot source. What only a record knows — whether voting *changed* a code — is
reported as **unknown**, never as zero.

Three defects the work surfaced, each fixed test-first: one sqlite connection
shared across FastAPI worker threads, raising `InterfaceError` as a 500 the
moment two requests overlapped; a rescued record reading its rung-1 verdict from
the final record rather than the rung-1 row; and a CSS class shared with the
header logo squeezing the demo's legend into 19-pixel circles. The last was
caught only in a browser — **the frontend has no tests, and the repository's own
rule about untested code applies to `app.js` too.**

## What has not changed

**Every measured result from v1.0 stands.** Seven corpora in the matrix plus
CADEC as a reference, five model families, ~50 scored cells, the two-family
split, the paid layers routing zero on PsyTAR. Nothing in this release re-ran
them and nothing in it moves a figure in the InfoQ article.

The known limitations in [`docs/RELEASE-v1.0.md`](docs/RELEASE-v1.0.md) still
apply in full — retrieval not uniform across the table, CADEC as a reference
rather than a row, LINNAEUS thin at 3–8 scored records, the paid layers measured
on two corpora rather than seven.

## Verifying

```bash
git checkout v1.1
PYTHONPATH=. python3 scripts/score_matrix.py --dir runs/archive/matrix-2026-09-07/matrix
PYTHONPATH=. python3 scripts/crosscheck.py --quiet --manifest 'manifest*.json'
PYTHONPATH=.:tests python3 -m pytest tests -q
python3 -m dashboard            # then open the address it prints
```

The matrix command must print the same table as under v1.0. If it does not,
please open an issue — see [CONTRIBUTING](CONTRIBUTING.md).

---

### Tagging

```bash
git tag -a v1.1 -m "the Workbench, the plan page rebuilt from tracked data, and the slot-0 claim retracted"
git push origin v1.1
```

On GitLab: **Deploy → Releases → New release**, tag `v1.1`, paste everything
above this line.

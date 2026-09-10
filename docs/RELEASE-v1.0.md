# v1.0 — the measured study

*Tagged 2026-09-08. This is the state the InfoQ article cites: every number it
prints was produced by this commit, and every one of them can be re-derived from
this repository without a GPU, a licence, or asking us.*

---

## What was measured

| | |
|---|---|
| **corpora** | 8 — CADEC v2, FiNER-139, PsyTAR, BC5CDR, GeoWebNews, LGL, TR-News, LINNAEUS |
| **model families** | 5 — `gpt-oss:20b`, `llama3.1:8b`, `mistral:7b-instruct`, `ibm/granite4:micro-h`, `qwen3:8b`; 4B to 20B parameters |
| **cells** | ~50 scored, across development and held-out splits, one variable per cell |
| **layers** | 7, measured one at a time; the full ladder run on two corpora |
| **published** | every cell, scoreable, in [`runs/archive/matrix-2026-09-07/`](runs/archive/matrix-2026-09-07/) |

Three draws were byte-identical on three corpora at temperature 0, so a single
draw is a measurement rather than a sample.

## The three findings

**A zero-token check sorts answers, and does it well on some vocabularies and
badly on others.** Comparing an extracted span against the names its code
carries costs nothing and no latency. On clinical vocabularies the endorsed lane
is right **76–100%** of the time; on gazetteers the same lane is right
**7–26%**. Neither band overlaps the other, across five model families and two
splits.

**Reach runs opposite to accuracy.** The check that finds most to endorse is the
one to trust least — clinical lanes fire on 7–32% of records, gazetteer lanes on
20–76%. Occupancy predicts nothing about correctness in either direction, which
is why the two are never reported fused.

**Three paid layers changed almost no answer.** Self-correction, sampled voting
and a second-model judge cost roughly half a million tokens on CADEC and altered
one answer in 53. On PsyTAR, across three draws, they routed **zero** records
and coverage was identical to the free layers alone — including on the one
corpus where self-correction had real work to do, because the check that would
trigger it never rejects what the model actually writes.

## What is in the repository

**The ladder** — seven layers, one manifest per arm, one variable per cell, with
provenance recorded on every run.

**Three checks**, each answering a different question at a different moment:

| | | |
|---|---|---|
| [`gatecheck`](scripts/gatecheck.py) | should this corpus be run at all? | predicts the check's ceiling from the answer key alone, before any GPU time |
| [`crosscheck`](scripts/crosscheck.py) | is it wired as declared? | reads nine declared facts back from independent sources |
| [`stagecheck`](https://github.com/pushpdeep/stagecheck) | did the run mean anything? | a separate installable package, 43 tests, no dependencies |

126 tests across the three. Every test in `gatecheck` and `crosscheck` was
written from a defect that reached a rented GPU first, and each is made to fail
on that defect before being confirmed to pass on the fix.

**The decision log** — [`docs/decisions.md`](docs/decisions.md), dated, where a
correction sits *beside* the claim it corrects rather than replacing it.

**The run archive** — ~50 cells, stripped of quoted text, verified to score
identically:

```bash
PYTHONPATH=. python3 scripts/score_matrix.py --dir runs/archive/matrix-2026-09-07/matrix
```

## Known limitations, stated rather than buried

**Retrieval is not uniform across the table.** CADEC and PsyTAR retrieve densely
over an embedding index built from SNOMED; the other five retrieve lexically,
because no such index exists for a gazetteer, a taxonomy, a tag set or MeSH. On
CADEC that substitution was measured to cost ~21 points of recall@20 — larger
than most differences in the results. **A lexical row and a dense row are not
comparable.**

**CADEC is a reference, not a row of the same table.** It was produced on
different hardware, and floating-point arithmetic differs between a model split
across CPU and GPU and one held entirely in VRAM: identical manifest, corpus and
seed gave 23 records on one machine and 22 on the other.

**LINNAEUS is thin and one model fails on it entirely.** Denominators of 3, 4
and 8 scored records; `llama3.1:8b` produces no records at all after three
separate attempts — a prompt rewrite, a vocabulary filter, and a cap on the
few-shot passage. `gatecheck` predicted a 4.8% ceiling there before any of it
ran.

**The paid layers were measured on two corpora, not seven.** Rungs 2–6 ran on
CADEC and PsyTAR. The other five are first-two-layers only.

**One claim was retracted after its own held-out test.** TR-News's endorsed lane
scored *below* the records the check declined on the development split — 0.6 to
0.9× — and the held-out split gives 1.1 to 4.2×. It moved because the comparison
band collapsed, not because the lane improved. The two-family result stands; the
"worse than not checking" reading does not.

**`gatecheck` and `crosscheck` are not packaged separately.** They depend on the
ladder's corpus loaders and live in `ladder/checks/`. Extracting them needs one
dependency inverted, and is worth doing when someone outside this study wants to
run them on their own corpus.

## What is not here

**CADEC's text, and any run output containing it.** The CSIRO licence is
non-transferable: each person accepts the terms and downloads their own copy.
Six of the eight corpora are freely redistributable and their run outputs are
published in full.

**A product.** The first two layers are research artefacts with deliberate
failure rates. There is no free-text entry point in the package — the runner
takes a corpus split identifier, never a string.

## Verifying this release

```bash
git clone https://gitlab.com/pushpdeep/ai-reliability-ladder && cd ai-reliability-ladder
git checkout v1.0
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt pytest

# every published number, from the archive, no GPU and no corpus download
PYTHONPATH=. python3 scripts/score_matrix.py --dir runs/archive/matrix-2026-09-07/matrix

# the checks, on every arm
PYTHONPATH=. python3 scripts/crosscheck.py --quiet --manifest 'manifest*.json'
PYTHONPATH=.:tests python3 -m pytest tests -q
```

If any of that disagrees with the tables in the README or the article, please
open an issue — see [CONTRIBUTING](CONTRIBUTING.md). **A figure that does not
reproduce is the most useful thing anyone can send us.**

## Credits

Wejdan Bagais and Pushpdeep Mishra. Licence: see [LICENSE](LICENSE); corpus and
vocabulary terms in [`docs/licences.md`](docs/licences.md), which are separate
and binding.

---

### Tagging this release

```bash
git tag -a v1.0 -m "the measured study: 8 corpora, 5 model families, ~50 cells, every number reproducible from the archive"
git push origin v1.0
```

On GitLab: **Deploy → Releases → New release**, choose tag `v1.0`, and paste
everything above the *Tagging this release* line as the description.

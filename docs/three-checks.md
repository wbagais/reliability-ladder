# Three checks, three moments

| tool | question | when | knows about corpora | where |
|---|---|---|---|---|
| `gatecheck` | should I run this? | before booking a card | yes | [`ladder/checks/gate.py`](../ladder/checks/gate.py), CLI [`scripts/gatecheck.py`](../scripts/gatecheck.py) |
| `crosscheck` | is it what I declared? | first line of every run | yes | [`ladder/checks/cross.py`](../ladder/checks/cross.py), CLI [`scripts/crosscheck.py`](../scripts/crosscheck.py) |
| `stagecheck` | did the run mean anything? | after | **no, deliberately** | its own repository, [github.com/pushpdeep/stagecheck](https://github.com/pushpdeep/stagecheck) |

**The principle underneath all three:** a load-bearing fact recorded once
cannot be checked, and will eventually be wrong silently. Every defect caught
early in this study was caught by comparing two independent records of one
fact — the vocabulary gate, `manifest_diff`, a directory name against the
manifest saved inside it. Every defect that reached a rented card was a fact
written down once and never read back: on 2026-09-06/07, twelve matrix cells
ran with CADEC's prompt, the few-shot ids came from `train` rather than the
pool the guard reads, and five cells ran a model their directory name did not
claim. `gatecheck` and `crosscheck` were written from those failures the
following day and moved into `ladder/checks/` as a shared package; the history
is in [decisions.md](decisions.md) under 2026-09-07 and 2026-09-08.

## The shared core — `ladder/checks/`

`Arm` is the one place a manifest becomes a loaded corpus, a gold set and a
vocabulary. `Result` is what a single check returns: `pass`, `FAIL` or `skip`,
with what was declared, what was found, and why it matters. Every check is a
function from one to the other, so each is testable alone against a fixture
arm and adding one means writing a function rather than editing a paragraph of
control flow. The package decides nothing: it loads, predicts and compares, and
leaves "finding or bug?" to a person.

## gatecheck — should this corpus be run at all?

Rung 1's free check compares a span against the names its code carries. That
needs no model, so **the lane's ceiling on a corpus is knowable for nothing**
from gold and the vocabulary alone — and a ceiling of zero means the arm
cannot produce a lane however good the extractor is.

```bash
PYTHONPATH=. python3 scripts/gatecheck.py --manifest manifest.psytar.json
PYTHONPATH=. python3 scripts/gatecheck.py --manifest manifest.foo.json --write
```

Measured against arms that were later run on a rented card:

| corpus | predicted ceiling | measured lane |
|---|---|---|
| FiNER-139 | **0.0%** | 0.0% on four models |
| LINNAEUS | 4.8%, flagged thin | 12.5% on one model, 0 on three |
| PsyTAR | 24.3% | 18.6–31.0% |
| BC5CDR | 35.8% | 7.0–21.8% |
| GeoWebNews | 40.9% | 20.3–63.6% |

Every measured value sits at or below its prediction, which is what a ceiling
must do, and two of the five would have stopped a card being booked. It also
drafts the corpus's prompt rules, because every rule written by hand for four
corpora turned out to be a threshold applied to a measurement; the thresholds
are declared at the top of `gate.py` where a reader can disagree with them.

What it will **not** decide: whether a thin ceiling is a finding or a bug.
FiNER's zero is structural — a numeral shares no token with an English phrase,
on any run, forever. LINNAEUS's 4.8% was a vocabulary build choice, and an
all-names index moves the same gold to 35.4%. From gold alone those look
identical, and a tool that guessed would be inventing the more interesting of
two answers. Nor what the entity *is*: no span statistic says whether a corpus
is about organisms or diseases.

`scripts/prep_corpus.py` is the neighbouring tool that drafts a whole arm — a
manifest, the adapter registration, the nine things a new corpus has to
declare — and it calls the same profile.

## crosscheck — is this arm wired as it is declared?

Every load-bearing fact read back from an independent source and compared.
No GPU, no model call, about a second — cheap enough to be the first line of
every run and never skipped. The exit code is the number of failures, so
`crosscheck ... || exit` gates a run.

```bash
PYTHONPATH=. python3 scripts/crosscheck.py --manifest manifest.psytar.json
PYTHONPATH=. python3 scripts/crosscheck.py --manifest 'manifest.*.json' --quiet
```

Twelve check functions, listed at the bottom of `cross.py`, each a defect that
reached a rented card first:

| check | the defect it was written from |
|---|---|
| corpus loads | an adapter that returned no documents; a run over nothing succeeds |
| entity type is offered | BC5CDR annotates two types and the arm scores one; scoring the wrong one is silent |
| split ids are in this corpus | TR-News's splits were frozen while the adapter defaulted to LGL, so they held LGL's ids; rung 0 returned in 0.06 s with no error and no records |
| splits leave a pool | LINNAEUS has 95 documents; 40 dev + 60 test left nothing, the few-shot block came back empty and rung 0 fell back to CADEC's synthetic examples |
| few-shot ids are in the pool | BC5CDR's were picked from its own `train` split, not the pool `init` wrote, so the guard refused every cell at the first document |
| vocabulary gate | a real code resolves and a fake one does not, on the vocabulary this arm names; a vocabulary that answers True to everything produces a rung 1 that looks like it is working |
| gold codes resolve | the answer key and the vocabulary must be talking about the same thing; an OLS4-backed `exists()` once called 23.9% of CADEC gold nonexistent |
| prompt names this entity | twelve matrix cells asked for adverse drug reactions in papers about species |
| prompt names no other entity | the same defect from the other side, keyed by owner so `place` does not match "place the article refers to" |
| no doubled slot | a task description that rendered as *"the abstract describes the abstract describes"*, an hour after the identical bug had been diagnosed elsewhere |
| prompt fits a small model | two full-paper few-shot examples put a 4–8B model past what it holds; three of four returned nothing on LINNAEUS |
| models are installed | `granite4:micro-h` and `ibm/granite4:micro-h` share a digest and only one resolves; three ports refused at their first cell. A model merely absent from this machine is a `skip` with the pull command, not a failure |

## stagecheck — did the run mean anything?

Its own repository, and it stays that way: 43 tests, no dependencies, MIT, and
it knows nothing about corpora, vocabularies or language models. It records
the two things a pipeline usually does not — **the bet a stage makes**, and
**the records it could not judge**. A stage that judged 40 of 100 records and
reports 95% accuracy has reported a rate over an unnamed set; stagecheck
refuses to let that go unrecorded. The boundary with the other two is
deliberate: everything corpus-shaped lives here, everything stage-shaped lives
there, so it is usable outside this study.

Three gaps found while running the matrix are recorded in
[TODO-provenance.md](TODO-provenance.md), none built: a stage should record
what it *was* as well as what it did, hardware is part of the configuration,
and a stage should assert things about its own configuration before it runs.

## Tests

`tests/test_gatecheck.py` (21) and `tests/test_crosscheck.py` (31): 52 between
them, each written from a real defect and made to fail on that defect before
being confirmed to pass on the fix.

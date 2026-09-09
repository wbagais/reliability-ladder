# Contributing

**Come and break something.**

This is a measurement study, and the best thing that can happen to a measurement
is that someone else takes it apart. Every number here is published with the run
that produced it, so you can check any of them without asking us — and if one
does not hold up, we would genuinely rather know.

There is plenty worth poking at: seven corpora, five model families, a free
check that works beautifully on clinical vocabularies and badly on place names,
and three small tools that exist because we got things wrong repeatedly. Pick
whichever interests you.

---

## Reproduce a number

The quickest way in. Every cell is in
[`runs/archive/matrix-2026-09-07/`](runs/archive/matrix-2026-09-07/) and scores
from this repository alone — no corpus download, no GPU:

```bash
PYTHONPATH=. python3 scripts/score_matrix.py --dir runs/archive/matrix-2026-09-07/matrix
```

If that disagrees with the README or the article, please open an issue with the
command and what you saw. **A figure that does not reproduce is the most useful
thing anyone can send us.** It has already happened once from the inside: a
scorer bug reported the previous run's numbers for a day, caught only because
they were suspiciously identical to the day before.

## Bring a corpus

The central result is that clinical vocabularies give a small lane that is right
and gazetteers a large one that is wrong. Seven corpora agree. **A vocabulary
that fits neither pattern would be the most interesting thing to arrive here** —
legal citations, product catalogues, chemical nomenclature, anything where the
words people write and the names in the vocabulary relate differently.

Two commands before you spend anything on it:

```bash
PYTHONPATH=. python3 scripts/gatecheck.py  --manifest manifest.yours.json
PYTHONPATH=. python3 scripts/crosscheck.py --manifest manifest.yours.json
```

`gatecheck` reads your answer key and predicts what the free check *could*
endorse — before any GPU time. It reports 0.0% for FiNER-139 and says the arm
cannot produce a lane however good the model is, which is a whole GPU arm's
finding for nothing. `crosscheck` reads every declared fact back from an
independent source, in about a second.

### The nine things a new corpus declares

There was no list of these until each port cost a day, so here is one:

| | |
|---|---|
| adapter | registered in `ladder/run.py` |
| vocabulary index | plus gate codes **from your own gold**, not inherited |
| splits | frozen, sized so a pool remains |
| few-shot ids | from the pool split the guard actually reads |
| loader options | passed through, not defaulted |
| corpus version | which release, of the corpus and the vocabulary |
| entity type | if your corpus annotates several and you score one |
| prompt slots | derived from measured gold, not from an impression |
| model names | exactly as your runtime resolves them |

`crosscheck` verifies eight of the nine automatically. The ninth — what your
entity actually *is* — no statistic can answer, so `gatecheck` asks you to
declare it rather than guessing.

## Improve the tools

[`gatecheck`](scripts/gatecheck.py) and [`crosscheck`](scripts/crosscheck.py)
live in `ladder/checks/`, one function per check, listed at the bottom of
`cross.py`. **Adding a tenth check means writing a function** — the registry is
readable and each check is tested on its own.

[`stagecheck`](https://github.com/pushpdeep/stagecheck) is its own repository
with its own issues. It has no dependencies and knows nothing about corpora,
which is what makes it usable outside this study; keeping it that way is the
main design constraint.

## Two conventions, and the reasoning behind each

**Tests reproduce the defect before they confirm the fix.** Every test in
`tests/test_crosscheck.py` and `tests/test_gatecheck.py` was written from
something that actually went wrong, and each is made to fail on that defect
first. A test that has only ever passed has not shown the check works.

**A changed number gets an entry.** [`docs/decisions.md`](docs/decisions.md) is
the durable record, and its convention is that a correction sits *beside* the
claim it corrects rather than replacing it. Several entries retract others
written the day before — that is the file working as designed, and it is the
part of this project we are most attached to.

Before opening a merge request:

```bash
PYTHONPATH=. python3 scripts/crosscheck.py --quiet --manifest 'manifest*.json'
PYTHONPATH=.:tests python3 -m pytest tests/test_crosscheck.py tests/test_gatecheck.py -q
```

## Two things that will not work, and why

**A corpus we cannot license.** CADEC is non-transferable — each person accepts
the CSIRO terms and downloads their own copy — so no run output containing its
text can be published here. Corpora with open licences are very welcome, and six
of the seven here have them.

**A layer without a measurement.** The finding of this study is that three paid
layers changed almost no answer. An eighth layer becomes interesting the moment
it has a number, on a split, with its denominator stated.

## Where to raise things

Issues on [GitLab](https://gitlab.com/pushpdeep/ai-reliability-ladder) — the
GitHub copy is a mirror. Questions are as welcome as patches, and *"I could not
follow this"* about any part of the README is a real bug report.

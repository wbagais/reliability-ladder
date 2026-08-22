# Authorship

Who wrote what, measured from git rather than taken from the plan. Regenerate any figure here with the commands at the bottom.

## The two owners

| Role | Person | Commits |
|---|---|---|
| **owner A** | Wejdan Bagais | 37 |
| **owner B** | Pushpdeep Mishra | 15 |

- Wejdan's commits span three addresses (`wejdan.bagais@usp.org`, `w.bagais@Gmail.com`, `w.bagais@gmail.com`). Same person.

## Measured ownership

Lines surviving in `HEAD`, by author. Files with a single author are listed compactly.

| File | Lines | Wejdan | Pushpdeep |
|---|---|---|---|
| `ladder/run.py` | 567 | 567 | — |
| `ladder/registry.py` | 523 | 523 | — |
| `ladder/rungs/r1.py` | 353 | 262 | **91** |
| `ladder/vocab.py` | 352 | 216 | **136** |
| `ladder/rung0_ab.py` | 288 | 230 | **58** |
| `ladder/corpus.py` | 277 | 277 | — |
| `ladder/fixture.py` | 260 | 260 | — |
| `ladder/probe.py` | 237 | 237 | — |
| `ladder/schema.py` | 211 | 211 | — |
| `ladder/ledger.py` | 197 | 197 | — |
| `ladder/rungs/r2.py` | 193 | 193 | — |
| `ladder/vocab_crosscheck.py` | 189 | 189 | — |
| `ladder/calibrate.py` | 183 | 183 | — |
| `scripts/preflight.py` | 155 | 8 | **147** |
| `ladder/negation.py` | 147 | 147 | — |
| `ladder/llm.py` | 130 | 130 | — |
| `ladder/stub_llm.py` | 123 | — | **123** |
| `.gitlab-ci.yml` | 112 | 15 | **97** |
| `schemas/vocabulary.py` | 107 | 107 | — |
| `manifest.json` | 115 | 109 | 6 |
| `ladder/manifest.py`, `schemas/runner.py`, `ladder/__init__.py` | 115 | 115 | — |
| `tests/**` | 1,000 | 987 | 13 |

## Where the plan and the repo disagree

The plan assigns owner B rungs 0, 3, 4, 5 and `ladder/score.py`. **None of those files exist**, so measured against the repo the split is different from the one the plan describes — in both directions.

- **Pushpdeep did not write a rung.** The contribution is the **licence and CI boundary** plus the model client: `scripts/preflight.py` (147 of 155 lines), `.gitlab-ci.yml` (97 of 112), `ladder/stub_llm.py` (all 123), and substantial edits into two of Wejdan's files — `ladder/vocab.py` (136 lines) and `ladder/rungs/r1.py` (91).
- **Wejdan wrote `ladder/rung0_ab.py`**, 230 of its 288 lines, and created the file. The plan lists rung 0 as owner B's.
- Wejdan created every file in `ladder/` and `schemas/` except `stub_llm.py`.

Read plainly: **owner A built the ladder; owner B built the guard rails around it and the client that will drive rung 0.** The plan's division of the *rungs* has not yet been exercised, because rungs 3–5 are unwritten.

This is a description of the repo as it stands, not a criticism of either share. The plan's labels are forward-looking; the blame data is backward-looking.

## Pushpdeep's edits into rung 1

Both changed rung 1's behaviour and are documented in [[r1]]:

- **A missing vocabulary raises, it does not BAND.** BAND made "unverifiable" and "never checked" the same value, and nothing above rung 1 could tell them apart. `allow_no_vocab` opts out.
- **`all_reasons()`**, the audit pass that runs every check unconditionally. `zone()` short-circuits, which is right for a verdict and wrong for a reason table — measured, 6/6 records rejected as `span_ungrounded` while all three codes emitted were absent from SNOMED, and not one appeared in the reason table.

## AI assistance

- **22 of 52 commits** carry a `Co-Authored-By: Claude` trailer. All are authored under Wejdan's git identity, so blame attributes those lines to Wejdan.
- Treat the Wejdan column as *"authored or reviewed under Wejdan's identity"*, not as hand-typed lines.
- Pushpdeep's commits carry no such trailer.

## Reproduce these numbers

```bash
git shortlog -sne --all
```

```bash
git log --diff-filter=A --format='%an' -- <path> | tail -1
```

```bash
git blame --line-porcelain HEAD -- <path> | grep '^author ' | sort | uniq -c | sort -rn
```

```bash
git log --all --oneline --grep='Co-Authored-By: Claude' | wc -l
```

## Related

- [[contributing]] · [[architecture]] · [[index]]

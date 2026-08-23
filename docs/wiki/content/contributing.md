# Contributing

## Hard rules

- **Never commit corpus text.** CADEC is non-commercial and NON-TRANSFERABLE. `data/` is gitignored. Notebook output cells are the classic leak. See [[data-licences]].
- **Run preflight before any commit.** `python scripts/preflight.py --history`. Exits 1 on a breach.
- **Never put a real API key in a tracked file.** Preflight scans for key-shaped strings.
- **Never regenerate the frozen splits.** `--force` on `run init` is not a normal operation.

## File conventions

Who owns what changes too often to be worth writing down. These do not:

- **One file per rung.** A rung is registered by adding `ladder/rungs/rN.py` — never by editing `run.py`.
- `manifest.json` is **append-only** and edited jointly. It is the likeliest conflict in the repo.
- `ladder/score.py` is a **single** shared scorer. Nothing may import a second one.
- Schemas append, never reorder.

To find who wrote something, ask git rather than a doc:

```bash
git log --diff-filter=A --format='%an %ad' -- <path> | tail -1
```

```bash
git blame --line-porcelain HEAD -- <path> | grep '^author ' | sort | uniq -c | sort -rn
```

## Branching

- Branch off `main`. Never commit directly to it.
- Naming in use: `claude/<topic>-<hash>`, `<topic>-<hash>`.
- `main` is protected. A passing pipeline is required before merge.
- Merge requests target `main`. Source branch is deleted on merge.

## Merge request rules

- Preflight and the test suite must pass locally before pushing. CI runs both and blocks the pipeline.
- Describe the measurement, not just the change. A number without the setting that produced it is not a result.
- If the change moves a published number, say which number and by how much.
- Log the decision in `docs/decisions.md` in the same MR.

## Coding standards

- `from __future__ import annotations`, type hints on public functions.
- Docstrings explain **why**, not what. The repo's existing docstrings are the reference for tone and density.
- Match surrounding comment density and naming. Do not add a house style the file does not already use.
- Standard library first. A new pinned dependency needs a reason in the MR.
- Schemas append, never reorder — `schema.py` enums are the contract every rung reads.

## Adding a rung

- Create `ladder/rungs/rN.py` exposing `apply(records, sources, cfg) -> list[Record]`.
- Mutate only `zone`, `reason`, `provenance`, `checks`, via `Record.mark()`.
- Write one [[ledger]] row per record touched, with real token and latency figures.
- Add the rung's settings to `manifest.rungs.N`.
- Add a page to this wiki. See [[architecture]] for the contract.

## Adding a check to rung 1

- **Replay it over the gold standard first.** Every rejection there is false by construction. That process took the gate's error floor from 9.3 % to 0.13 %.
- `python -m ladder.calibrate --sweep` prices the setting.
- `python -m ladder.probe` measures what it catches.
- A new reject reason must be appended to `schema.REJECT_REASONS`, never inserted.

## Decision log

- `docs/decisions.md` — one entry per decision, as you go. It is the article's raw material and cannot be reconstructed afterwards.
- Record what you measured, not only what you chose.

## Wiki

- Source: `docs/wiki/content/*.md`. Build: `python docs/wiki/build.py`.
- Navigation comes from `PAGES` in `build.py` — one line per page, single source of truth.
- Cross-link with double-bracket wiki links naming a page slug. `python docs/wiki/build.py --check` fails on broken links and orphan pages.
- Synthetic examples only. Never paste corpus text into a wiki page.

## Related

- [[index]] · [[glossary]]

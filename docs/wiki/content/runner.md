# Runner & CLI

`ladder/run.py` · owner A. **Owner B never edits this file** — B registers a rung by adding `ladder/rungs/rN.py` and telling A the number.

> There is no free-text entry point. `--split` takes a split identifier; the runner reads documents out of the licensed corpus by ID and nothing else.

## Subcommands

| Command | Purpose |
|---|---|
| `init` | verify corpus + vocabulary, write the frozen splits |
| `gate` | the 13-record fixture gate |
| `ladder` | run the ladder over a split |
| `ablate` | each rung **alone** on identical input |

## init

```bash
python -m ladder.run init
```

- Parses the corpus, checks the index, asserts a real code resolves and a fake one does not.
- Prints `(frozen)` when reading existing splits. `--force` regenerates them — do not.

## ladder

```bash
python -m ladder.run ladder --split test --source gold --run-id demo
```

| Flag | Meaning |
|---|---|
| `--split` | `dev` · `test` · `pool` |
| `--source` | `model` (default) or `gold` |
| `--predictions` | JSONL of rung-0 records |
| `--rungs` | e.g. `1,2` or `0-6` |
| `--scorer` | `module:function`, defaults to `ladder.score` if present |
| `--run-id` | names the output files |

### Three ways records enter

- `--source gold` — the answer key dressed as rung-0 output. A **control**, not an accuracy test.
- `--predictions out/r0.jsonl` — owner B's output. Enforces **split discipline**: a file carrying a document outside the split is refused, exit 1. Blank `record_id`s are backfilled.
- neither — [[r0]] generates records from `sources`. Currently exits with a message, because `r0.py` does not exist.

### Output

| File | Contents |
|---|---|
| `<run_id>.results.csv` | summary, one row per rung |
| `<run_id>.ledger.jsonl` | one row per (rung, record) — see [[ledger]] |
| `<run_id>.records.jsonl` | final state per record, full `checks` |
| `<run_id>.manifest.json` | the exact config that produced it |

- A missing rung is **reported, never faked**: `NOT IN THIS RUN: rungs [3, 5, 4, 6]`.
- Without a scorer the accuracy columns are written **empty**, not guessed.

## ablate

```bash
python -m ladder.run ablate --split test --source gold
```

- `ladder` measures a **stack**: rung 4's row is rung 4 applied to what rungs 1, 3 and 5 already did.
- `ablate` holds the input fixed and varies **one rung**, so a row is attributable to that rung alone.
- Each rung gets a fresh record copy. Rung 0 is not ablatable — it *makes* the records — so it becomes the `input` row.
- Marginal-cost columns stay empty: "marginal" is only meaningful cumulatively.
- Both commands build rows through one `snapshot_row()`, so there is still exactly one accounting path.

## Related

- [[getting-started]] · [[ledger]] · [[manifest]] · [[measurement]]

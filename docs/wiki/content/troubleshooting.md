# Troubleshooting

## Setup

**`CADEC text/ not found under .../data/cadec/data/cadec`**

- `corpus.cadec_root` expects `data/cadec/data/cadec`.
- If your download unpacks under its DAP name, symlink rather than rename — `data/cadec` is gitignored:
- `ln -sfn 2016-04-15_Karimi_Sarvnaz_10948v3 data/cadec`

**`vocabulary index missing`**

- `python -m ladder.registry --build --release data/SnomedCT_Release_<yours>`
- ~9 s, ~365 MB, one time only.

**`No module named 'ladder'`**

- Run from the repo root, or set `PYTHONPATH=.`.

**Working in a git worktree and `data/` is empty**

- `data/` and `ladder/cache/` are gitignored, so they do not exist in a new worktree. Symlink them from the main checkout.

## Runtime

**`rung 0 is not implemented yet (owner B)`**

- Expected. Use `--source gold` for the control, or `--predictions out/r0.jsonl`. See [[runner]].

**`NO SCORER: accuracy columns are empty`**

- Expected. `ladder/score.py` is Pushpdeep's and unwritten. Zone and cost numbers are still valid.

**`NOT IN THIS RUN: rungs [3, 5, 4, 6]`**

- Expected. A missing rung is reported, never faked.

**`RuntimeError: rung 1 has no vocabulary backend`**

- Deliberate. BAND would make "unverifiable" and "never checked" the same value. Pass a registry, or set `allow_no_vocab=True` to measure without one.

**`<file> has records for N documents outside the split`**

- Split discipline. Predictions for the test split may only cover the test split. See [[corpus]].

**`GATE FAILED`**

- Stop. Nothing above it is trustworthy. The failing line names the expected verdict and reason. See [[testing]].

## Results that look wrong

**Rung 1 rejected 0 records**

- Expected on `--source gold` for dev and test. The false-rejection floor is 0 on those splits; all 12 corpus-wide fall in `pool`.

**Coverage is only 0.435 and everything was correct**

- Correct behaviour. All 393 gold codes are right; rung 1 vouches for 171 and [[r2]] withdraws 222. **That gap is what rungs 3–6 exist to close.**

**Rung 2 alone abstains nothing**

- Correct. It reads `checks["r1_verdict"]`; with no rung 1 upstream there is nothing to withdraw on. Visible only via `ablate`.

**A rung-1 rejection rate that disagrees with a colleague's**

- Check the backend. `local-rf2` and `ols4` disagree on **23.9 %** of gold. Rates are not comparable across backends. See [[vocabulary]].

**The reason table shows only `span_ungrounded`**

- `zone()` short-circuits on the first failure, so the table is a distribution over *first* failures weighted by check order. Use `all_reasons()` for the complete set. See [[r1]].

**`ablate` and `ladder` disagree**

- They should. `ladder` measures a stack, `ablate` measures each rung alone on identical input. See [[runner]].

## Licence

**preflight exits 1**

- Read the blocked path. If it is in **history**, deleting the file is not enough — use `git-filter-repo`. See [[data-licences]].

**preflight warns `one corpus-like phrase`**

- Check it by hand. The detector is four narrow regexes and real corpus text can pass it.

## Related

- [[getting-started]] · [[testing]] · [[runner]]

# Six declarations nothing read, one model name that does not exist, and a guard that could not fail

`manifest.json` declared `model.temperature: 0` and **nothing read it**.
`ladder/llm.py:Caller.__call__` carried `temperature: float = 0.0` as a
hardcoded default and no rung passed a value except rung 3, which reads its own
`rungs.3.temperature`. So "which temperature produced this number" had a
declared answer and a real answer, and **they agreed only by accident** — the
exact failure the note inside `manifest.model` was written for, one layer down,
and the same class as the 5.9-point manifest/arms gap of 2026-08-28.

Asking that same question of every other setting found five more. This branch
answers all six, deletes a module that had been shipped and never imported, and
fixes a guard of my own that could pass while reading nothing.

**No shipped number moves.** Every item here was inert at its declared value —
which is precisely how the temperature key looked before it was examined.

## What this is worth, in one measurement that already exists

`origin/main`'s BioMistral rung-0 arm (2026-08-31) needed the ladder to run at
temperature 1.0 to establish that BioMistral's failure is greedy decoding and
not our harness. It got there by **wrapping `Caller.__call__` in a scratch
script** (`out/harness/bmtemp.py`) "so production is untouched" — because there
was no way to set the temperature from configuration. That is the cost of an
unread declaration, paid in the same week, by the arm that sits two commits
ahead of this branch on main. After this MR the same arm is a manifest key.

That arm also makes the key newly load-bearing **in fact**: greedy decoding is
now a measured cause of a model failure in this project, not a background
convention.

## The six

| # | Declared | Was | Now |
|---|---|---|---|
| 1 | `manifest.model.temperature: 0` | never read; `Caller.__call__` hardcoded `0.0` | `llm.temperature_for` → bound by `for_rung` beside the model |
| 2 | `r4.DEFAULTS["temperature"]: 0` | never read | **removed** — a rung DEFAULT would override the manifest |
| 3 | `ladder_run.py` / `full_run.py` provenance `sampling={...}` | two literals; one reported **rung 3's** sampler temperature as the run's | `provenance.sampling_for(man)`, and `gather` defaults to it |
| 4 | `vocabulary.snomed_backend: "local-rf2"` | `run.py` hardwired to `Registry`; `ols4` would change nothing while the results file claimed it | `check_snomed_backend`, read at both construction sites |
| 5 | `vocabulary.meddra_mode: "reference"` | never read | `check_meddra_mode`; `answer_space` refused |
| 6 | `rungs.1.outdated_check: "flag"` | absent from `r1.DEFAULTS`; `_record_history` flagged unconditionally | declared and honoured |

Three more of the same shape in rung DEFAULTS — `r2.max_attempts`,
`r2.allow_withdrawal`, `r4.show_vocabulary_term` — are **removed rather than
wired**. The reasoning differs from #1: there is no manifest declaration to
defer to, only the question of whether the knob exists, and each one's own
comment already answered no. `max_attempts: 1` says *"more is a different
experiment"* while `_attempt` runs exactly once, so setting `3` changed nothing.

### Why #4 refuses instead of honouring

`vocab.Ols4Vocabulary` is real and serves rung 1's surface, but has no
`replacements` and none of rung 0's `shortlist` / `resolve` /
`search_labelled`. Running the ladder on it is **a measurement nobody has
taken**, not a fix. Refusing still closes the defect — a results file can no
longer claim a backend the run did not use — and the message carries the
23.9% / 7.5% retired / 16.4% AU-extension figures and points at
`python -m ladder.vocab_crosscheck`.

Same posture for `answer_space` in #5: it meant showing the model the MedDRA
list, which was rung 0's S3, dropped 2026-08-24. Accepting it would let a
manifest declare an experiment no code path implements.

## The no-shipped-number-changes guarantee, and a finding inside it

**`out/cadec-manifest-1` no longer exists on this machine.** Its worktree was
pruned, nothing under `out/archive/` carries the name, and the sha
`f76de5186eb1ad9e1ec5` survives only in `docs/decisions.md`. **The sha
comparison this work was specified against could not be made**, and that is
reported rather than worked around.

Proven at the cache-key layer instead, which is deductive rather than sampled:
the effective temperature is `0.0` before and after for **every** tracked
manifest, so every payload dict is byte-identical, so every call returns the
identical text, so every record is identical. Asserted three ways, including a
seeded pre-wiring cache entry that must still be a **hit** with the network
stubbed to raise.

**The float cast is the whole guarantee.** `temperature` is in the LLM cache key
and the key is a `json.dumps`: the manifest's int `0` and the code's `0.0` hash
differently. An uncast wiring would have missed all 7,247 cached calls and
re-generated every published number from a cold cache **while reading as a
no-op**.

## `ladder/otel.py` is deleted

Wired first, then deleted — and the wiring is what made the decision possible.

One commit ever (`44882a3`, 2026-08-23) touching exactly two files: the module
and `runs/otel-smoke.jsonl`. So *"phoenix transport verified"* meant verified
against a **hand-made row** (`{"run_id": "smoke", "doc_id": "D1"}`), never a
ladder run, and the `LADDER_OTEL=1 … scripts/ladder_run.py` in its own docstring
emitted nothing. Five phases, two corpora, zero `docs/decisions.md` entries
depending on it. Its spans were a strict copy of the ledger row — `denominator`
and `evaluable` included — and the ledger is already JSONL on disk and already
what `ladder_top.py`, `provenance` and every harness script read.

Gone with it: `run.ledger_for` (an indirection choosing between two ledgers —
with one left it is a branch that cannot branch), the README block, the
`docs/plan.html` row, and `provenance.gather`'s `env.ladder_otel`, a stamp
naming an env var that switched on nothing.

Also deleted, same shape, no caller anywhere: `vocab.lexical_overlap` and
`r0.report_run` — the second **worse than unused**, since it reads
`agg["documents"]` and `agg["tool_calls"]`, absent from the modern `apply()`
aggregate, so calling it today would `KeyError`.

## Three tracked manifests named a model that does not exist

`manifest.finer.llama.json`, `manifest.finer.mistral.json` and
`manifest.spine.finer.json` all said `ollama/granite4:micro-h`. Ollama
namespaces it under `ibm/` — confirmed against the live `provider_models`
list. That exact name spent **133 minutes** in rungs 0 and 3 of the first full
FiNER run before dying at rung 4 (2026-08-29); `manifest.finer.json` carries a
`_judge_name_note` about it and the other three never got the fix.

## Two things I got wrong, both caught here

**A guard that could not fail.** A scan for the shape *"build a collection by
globbing, assert it is empty"* found exactly two instances in the whole suite
and **both were mine, written in this branch** — and one had already fired: it
filtered on absolute `path.parts`, and this repo is worked in worktrees under
`.claude/`, so every path was excluded and it read nothing while `README.md`
still advertised the exporter. Both now count what they opened (`looked > 50`,
`seen >= 5`) and were confirmed discriminating by pointing each walk at an
extension that does not exist. **A guard that cannot fail is a declaration
nothing reads, and writing the rule down does not exempt you from it.**

**A skip that was a pass.** `tests/test_scripts_import.py`'s `ENVIRONMENT`
listed `SystemExit` wholesale, so four scripts that do their whole job at import
and **exit 0** were filed as *"environment, not code"*. Exit 0 is success.
`skip_reason()` now returns `None` for code 0/None; script-import skips fall
11 → 7 and the remaining 7 are genuinely environmental. The first version of
that fix had its own bug, caught by the suite: replacing `except ENVIRONMENT`
with `except Exception` let `SystemExit` escape, because **`SystemExit` is a
`BaseException`**. The old code worked only because `ENVIRONMENT` named it.

## Verification

- **756 passed, 24 skipped.** 42 new tests — 39 in three new files plus 3 in
  `test_scripts_import.py` — every one TDD'd fail-first.
- `scripts/preflight.py --history` → 3 warnings, all pre-existing, "Safe to push".
- `docs/wiki/build.py --check` → 23 pages, exit 0.
- CI's vocab smoke calls `exists` / `is_finding` / `negated` — checked
  explicitly, because this branch deletes a function from `ladder/vocab.py`.
- `docs/plan.html` table structure unchanged apart from the removed row
  (169/187 `<tr>` on main → 168/186 here).
- Merged `origin/main` (the BioMistral rung-0 arm); the one conflict was a pure
  append in `docs/decisions.md`, resolved in landing order.
- `git add -A` was used with a dirty tree, so the commits were audited
  afterwards: every hunk is this branch's own work.

## The pin worth knowing about

`test_every_tracked_manifest_resolves_to_the_published_temperature` fails if any
`manifest*.json` moves off `0.0`. That is the wiring's own risk stated as a
test: **editing that key no longer relabels a run, it changes one.** Confirmed
discriminating by setting `manifest.json` to `0.7` and watching it fail.

## Not in scope, registered

Six scripts build a `Registry` at import time, so their import smoke test skips
wherever `ladder/cache/snomed.sqlite` is absent — which is CI. The test
CLAUDE.md credits with catching two live bugs in `ladder_run.py` therefore
covers roughly half the scripts where it matters most. The fix is deferring
construction into a `main()` in each; it touches six scripts' structure and
deserves its own session.

Running the ladder on the `ols4` backend also remains an unrun experiment — now
with an error message that says so, instead of a manifest key that lied.

# Working notes for Claude Code

## Read these first
- `docs/plan.html` — plan, architecture, and the reasoning behind every design choice
- `README.md` — the ladder, the three cost measures, the data licences

## Hard rules
- **Never commit corpus text.** CADEC is non-commercial and NON-TRANSFERABLE.
  `data/cadec/` is gitignored. This includes notebook output cells — the classic leak.
- **Run `python3 scripts/preflight.py` before any commit.** Exits 1 on a breach.
  CI runs it too and blocks the pipeline, but catching it locally is cheaper.
- **Never put a real API key in a tracked file.** preflight scans for key-shaped strings.
- `bench/vocab.py` is a **global resource**, not a per-item `trusted_record`.
  SNOMED comes from EBI OLS4 (free, no key). MedDRA defaults to `reference` mode;
  `answer_space` mode is a declared choice that must go in the manifest.

## Design decisions — do not silently reverse these
- Rung IDs are fixed to the brief. Execution order lives in `manifest.json` as
  `rung_order` (`[0,1,3,5,4,2,6]`), so ordering is a testable ablation, not an assertion.
- Rung 1 is a **validation gate**, not a router. It cannot confirm a code is right —
  only that it is wrong. Two outcomes: REJECT with a reason, or PASS.
- Rung 3 fires **only on a rung 1 failure**, with the reason stated as a fact
  ("code 999999 does not exist"), never as a question ("are you sure?").
  It cannot fix records that passed validation — there is no fact to feed back.
- Rung 6 stays a rung. "Tell the model to escalate when unsure" is rung 2, not rung 6.
- Cost is three separate measures — tokens, latency p95, records routed to a person.
  Never fuse them into a currency figure.

## Current state
- Scaffolding pushed, CI green. **No measured results yet.**
- Every number in `docs/plan.html` is an illustrative placeholder except the
  twelve-string probe in §2.

## Next, in order
1. Wire `bench/vocab.py` in as a global `resources` hook in the runner
2. CADEC adapter → build 10 items by hand → **check whether variable-length mention
   arrays break the scorer.** This is the gate; hit it early.
3. `bench/ladder_ab.py --compare` with a real client, rung 0 modes A and B

## Conventions
- One file per rung, one owner per file. Append to schemas, never reorder.
- `manifest.json` is append-only and edited jointly.
- Log every decision in `docs/decisions.md` — one line, as you go. It is the
  article's raw material and cannot be reconstructed afterwards.

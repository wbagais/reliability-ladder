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
- `ladder/vocab.py` is a **global resource**, not a per-item `trusted_record` —
  now formalised as `schemas/vocabulary.py`, contract 2.
- **Two SNOMED backends, and they are NOT interchangeable.** `local-rf2` (an RF2
  release indexed to SQLite) is the default; `ols4` is the no-download fallback
  and is `lossy=True`. Measured: an OLS4-backed `exists()` calls 23.9% of CADEC
  gold nonexistent — 7.5% retired, 16.4% AU-extension, which is 100% of drug
  mentions. **Never report a rung 1 rejection rate without saying which backend
  produced it.** `python -m ladder.vocab_crosscheck`.
- MedDRA defaults to `reference` mode; `answer_space` is a declared choice that
  must go in the manifest. The available list is 666 codes, every one of which is
  in the gold annotations and none of which are not — the answer key's inventory,
  not a vocabulary. `meddra_check` is therefore `"flag"`, not `"reject"`.

## Design decisions — do not silently reverse these
- Rung IDs are fixed to the brief. Execution order lives in `manifest.json` as
  `rung_order` (`[0,1,3,5,4,2,6]`), so ordering is a testable ablation, not an assertion.
- Rung 1 cannot confirm a code is right — only that it is wrong. **THREE**
  outcomes, not two: REJECT (provably wrong), ACCEPT (the vocabulary uses these
  very words) and BAND (plausible, unverifiable). Two outcomes cannot express
  BAND, and BAND is where **57% of even a perfect answer set** lands — that
  fraction is the bill the paid rungs have to work through.
- **REVISED 2026-08-22 — rung 1 JUDGES, it does not ROUTE.** `rungs.1.mode`
  defaults to `"observe"`: the verdict is recorded, counted and reported, and the
  record's zone is untouched, so rungs 3-6 see the full unfiltered set. A
  filtering rung 1 confounds every rung above it — rung 4's judge graded on a set
  rung 1 pre-cleaned is no longer attributable to rung 4. Rung 2 runs last and is
  where a verdict is finally allowed to cost coverage, so this defers rung 1's
  cost rather than cancelling it. `"gate"` restores the old flow.
- **REVISED 2026-08-22 — negation FLAGS, it does not REJECT.** Measured: as a
  rejection it costs 427 gold-correct mentions (4.7%). CADEC annotates a mention
  regardless of polarity — the plan's own worked example, "so far no gastric
  problems", is coded 162076009 in ARTHROTEC.1 — and NegEx scope misfires on
  forum prose. The cue still fires and is still logged.
- **REVISED 2026-08-22 — "code exists" means present, active OR retired**, and
  the semantic-type check may reject only on a positive `not_finding`. 11% of
  CADEC's codes are retired, and SNOMED retires a concept's is-a rows with the
  concept, so an active-only hierarchy walk cannot place them. Treating "cannot
  place" as "wrong slot" cost another 413 gold mentions.
- Every one of those was found by replaying rung 1 over the gold standard, where
  every rejection is false by construction. It took the gate's own error floor
  from **9.3% to 0.13%**. Do that before trusting any new check.
- Rung 3 fires **only on a rung 1 failure**, with the reason stated as a fact
  ("code 999999 does not exist"), never as a question ("are you sure?").
  It cannot fix records that passed validation — there is no fact to feed back.
- Rung 6 stays a rung. "Tell the model to escalate when unsure" is rung 2, not rung 6.
- Cost is three separate measures — tokens, latency p95, records routed to a person.
  Never fuse them into a currency figure.

## Current state
- Owner A's half is built and measured: corpus + frozen splits, SNOMED index,
  ledger, rung 1, rung 2, harness, fixture gate, and two model-free
  characterisations of rung 1. 93 tests, CI green.
- Rungs 0/3/4/5 and the shared scorer are owner B's and outstanding. `run.py`
  reports a missing rung rather than faking it.
- **An earlier data-agnostic track was retired on 2026-08-22**, along with its
  results. The CADEC track imported none of it. Do not reintroduce its numbers:
  nothing in this repo is runnable that would reproduce them. Git history at
  `e938f8d` if you ever need them.
- Numbers in `docs/plan.html` are still illustrative placeholders EXCEPT where a
  "measured" note says otherwise. Everything measured so far is in
  `docs/decisions.md` and `docs/article-iterations.md`.

## Next, in order
1. ~~Wire `ladder/vocab.py` in as a global resource~~ — done, `schemas/vocabulary.py`.
2. ~~Check whether variable-length mention arrays break the scorer~~ — **they do,
   and it is measured.** Under index-based array comparison a *perfect*
   extraction listed in another order scores 0.216, and dropping one mention
   scores 0.081. Fix: key gold mentions by span rather than position, which
   scores 1.000 reordered with no change to any scorer. Owner B needs this before
   writing `ladder/score.py`.
3. Owner B: `ladder/rungs/r0.py` (rung 0 is handed an EMPTY record list and builds
   records from `sources`), then `r3` / `r4` / `r5`, then `ladder/score.py`.
   Rung 3's trigger is `record.checks["r1_verdict"] == "REJECT"`, with the fact to
   state in `checks["r1_reason"]`.
4. `python -m ladder.rung0_ab --compare` with a real client — needs
   `ladder/stub_llm.py` or an equivalent, which is not in the repo yet.

## Conventions
- One file per rung, one owner per file. Append to schemas, never reorder.
- `manifest.json` is append-only and edited jointly.
- Log every decision in `docs/decisions.md` — one line, as you go. It is the
  article's raw material and cannot be reconstructed afterwards.

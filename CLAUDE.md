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
  **Rung 0 does not read it at all** (since 2026-08-24) — it was reachable only
  through S3, and there is a test asserting the filename is absent from `r0.py`.
- **Preprocessing is FIVE steps now, in this order.** A fresh clone runs all of
  them; `data/` and `ladder/cache/` are gitignored.

      python -m ladder.registry --build     RF2 -> SQLite index
      python -m ladder.keywords --build     data/keywords.csv
      python -m ladder.clean    --build     data/exclusions.csv
      python -m ladder.embed    --build     ladder/cache/keywords.*  (dense S2)
      python -m ladder.run init             freeze the splits

  An index built before 2026-08-24 has no `association` table. Upgrade it in
  place with `python -m ladder.registry --associations --release <dir>` — a few
  seconds. Do NOT `build --force` where the index is reached through a symlink:
  the rebuild replaces the symlink with a private copy and forks the checkouts.

## How to work
- **TDD, always.** Write the failing test first, watch it fail, then write the
  code that makes it pass. No production code without a test that demanded it.
  This is not negotiable and applies to every change, including small ones.
  The reason is specific to this repo: every number here is evidence for an
  article, and a check that was never seen to fail is a check nobody has
  shown to work. `scripts/` having no coverage is how a `NameError` in
  `full_run.py` survived the renumber.

## Design decisions — do not silently reverse these
- Rung IDs are fixed to the brief. Execution order lives in `manifest.json` as
  `rung_order` (`[0,1,2,3,4,5,6]` since the 2026-08-23 renumber), so ordering is
  still read from configuration and stays testable.
- Rung 1 cannot confirm a code is right — only that it is wrong. **THREE**
  outcomes, not two: REJECT (provably wrong), ACCEPT (the vocabulary uses these
  very words) and BAND (plausible, unverifiable). Two outcomes cannot express
  BAND, and BAND is where **57% of even a perfect answer set** lands — that
  fraction is the bill the paid rungs have to work through.
- **REVISED 2026-08-22 — rung 1 JUDGES, it does not ROUTE.** `rungs.1.mode`
  defaults to `"observe"`: the verdict is recorded, counted and reported, and the
  record's zone is untouched, so rungs 3-6 see the full unfiltered set. A
  filtering rung 1 confounds every rung above it — rung 4's judge graded on a set
  rung 1 pre-cleaned is no longer attributable to rung 4. Rung 5 (abstention) runs last and is
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
- **Rung 0 does NOT retry.** When a proposed label resolves to no code, rung 0
  walks its next label and then stops. A retry loop inside rung 0 IS rung 2 —
  building one there would collapse rung 2's measured value into rung 0 and
  confound the ladder. Rung 0 proposes up to three labels in one call; rung 2
  is where a failure is stated back as a fact.
- Rung 2 (self-correct) fires **only on a rung 1 failure**, with the reason stated as a fact
  ("code 999999 does not exist"), never as a question ("are you sure?").
  It cannot fix records that passed validation — there is no fact to feed back.
  The trigger is `record.checks["r1_verdict"] == "REJECT"`, and the fact to
  state back is in `record.checks["r1_reason"]`. Rung 1 writes both in either
  mode, which is what lets rung 2 work while rung 1 only observes.
- Rung 6 stays a rung. "Tell the model to escalate when unsure" is rung 5, not rung 6.
- Cost is three separate measures — tokens, latency p95, records routed to a person.
  Never fuse them into a currency figure.

## Current state
- **All seven rung slots exist except rung 6.** The full ladder runs end to end,
  cold, in order `[0,1,2,3,4,5,6]`. 100 tests (96 + 4 integration), CI green.
- **Model selection is centralised.** `ladder/llm.py:for_rung` is the ONLY place
  a model is resolved. `run.py` injects `cfg["llm"]`; a rung never names a
  model. Bound by ROLE from `manifest.model` — `extractor` for rungs 0/2/3,
  `judge` for rung 4 — because rung 4 must be a different family. Rung 3 gets
  `Caller.sampler(temperature)` so its k votes are distinct samples rather than
  one cached answer k times.
- **Local by default, and remote is deliberate.** `ollama/gpt-oss:20b` unless
  overridden. Rung prompts carry CADEC text verbatim, so any provider with
  `local: false` in `models.yaml` is refused without `LADDER_ALLOW_REMOTE=1`.
- Cost accounting is complete: every rung logs tokens, api_calls, per-call
  latency **and `usd`** (fixed 2026-08-24 — all four paid rungs dropped the
  price the caller had already computed, which was invisible because zero is
  right for a local model). Rung 3 bills the k sampling calls as a DOCUMENT
  row, paid whether or not a record is re-found. Cost is still three separate
  measures; `usd` is carried alongside, never fused in.
- **`ladder/score.py` exists** (2026-08-23). Gold is keyed by SPAN, never by
  position; `span_match` is `exact` (headline) or `overlap`. It accepts the
  `{record_id: GoldMention}` collection `run.py` passes and re-keys it itself —
  record_id is a POSITION and the two numberings agree only by luck.
- **Rung 0 has THREE steps, S0-S2** — the prompt-engineering study. Scope is
  identical in all three; only where the CODE comes from changes. Select with
  `--rung0-step`, which writes the choice into the manifest copy saved beside
  the results. `rung0_step: null` keeps the original A/B mode path.
  **S3 was dropped 2026-08-24.** It was a pick from one fixed PRINTED list and
  no printable list survives measurement: its MedDRA list is the answer key's
  own inventory, the best ontology-native alternative (SNOMED's Clinical
  manifestation refset, 743 codes) caps at 48.7% of gold, the real keyword
  table is 227,554 rows, and a list retrieved per mention is S2. Do not
  reintroduce it.
- **S2 retrieves DENSELY by default** (2026-08-24). `rung0_retrieval` is
  `dense | lexical`. Measured over the same 6,595 gold mentions, same k, same
  answer key: lexical recall@20 61.8%, dense 86.1%. **The two also search
  different corpora** — lexical over 1.8M description rows of every semantic
  type, dense over 228k findings/disorders keywords — so the gain decomposes:
  running Jaccard over keywords.csv gives 65.1%, making it **+3.3 corpus,
  +21.0 scoring** at k=20. At k=1 it inverts (+29.1 corpus, +15.2 scoring):
  filtering before ranking is what clears the top slot. Lexical is kept, not
  deleted — a recall number under one retriever is only interpretable next to
  the other, and `checks.rung0_retrieval` is on every record. Dense is not
  magic: `"gas"` returns |gas gangrene|. **The 41.7% shortlist recall in the older notes
  could not be reproduced under any denominator or k** — see docs/decisions.md;
  do not requote it.
- **Rung 0 resolves NAMES through `data/keywords.csv`, not through the
  registry.** `KeywordTable.resolve` has the same return shape as
  `Registry.resolve` over a findings-and-disorders-only table. There is NO
  fallback to the registry — an unresolved name is unresolved, because falling
  back reinstates the search the table replaces and hides which one answered.
  The registry stays for rung 1 (`exists`/`is_active`/`finding_status`/`terms`
  over the WHOLE release) and for S2's shortlist.
- **Four outcomes, not two** (2026-08-24): `correct` / `outdated` / `abstained`
  / `incorrect`. `outdated` is a RETIRED code whose SNOMED-recorded successor
  is the gold answer, and it is **never** folded into `correct` — precision,
  recall and F1 count `correct` only. Successors come from the association
  refset via `Registry.replacements`, following SAME AS and REPLACED BY and
  nothing else. Rung 1's `outdated_check` is a **flag**, like `meddra_check`.
  With no vocabulary the outcome degrades to `incorrect`, never to `correct`.
- **An earlier data-agnostic track was retired on 2026-08-22**, along with its
  results. The CADEC track imported none of it. Do not reintroduce its numbers:
  nothing in this repo is runnable that would reproduce them. Git history at
  `e938f8d` if you ever need them.
- Numbers in `docs/plan.html` are still illustrative placeholders EXCEPT where a
  "measured" note says otherwise. Everything measured so far is in
  `docs/decisions.md` and `docs/article-iterations.md`.

## Done — do not redo these
- `ladder/vocab.py` wired in as a global resource, formalised as
  `schemas/vocabulary.py` (contract 2).
- Variable-length mention arrays checked against the scorer: **they break it**,
  and the fix is span-keying — now implemented in `ladder/score.py`.
- `Record.sct_label` appended, and rung 1's `label_check` (default `"flag"`).
  The model names the concept it thinks it coded; the vocabulary checks it for
  free. Catches what `exists()` cannot — 82249009 is real, active, and means
  |California chicken (organism)|.
- `ladder/rungs/r0.py`, then `r2` / `r3` / `r4` — all written and running.
- Rung IDs renumbered to match execution order (2026-08-23). Old→new is
  3→2, 5→3, 2→5. Anything in `docs/decisions.md` dated earlier uses the OLD ids.

## Next, in order
1. **The three dev runs — S0, S1, S2.** Everything measured so far is ONE
   document (ARTHROTEC.107) plus corpus-wide vocabulary statistics. Pick the
   winning step, freeze it in the manifest, and run the ladder from there —
   otherwise rungs 1-6 are measured against three different rung 0s and nothing
   above is comparable. `python -m ladder.run ladder --split dev --rung0-step S1`
2. **A full dev-split run.** Everything measured so far is ONE document
   (ARTHROTEC.107). The rung 4 confabulation and rung 3's `not_resampled` are
   single observations, not rates. Dev is 40 documents at roughly 30s each.
   `python -m ladder.run ladder --split dev` — drop `--limit`.
3. **Rung 6** — the last unbuilt slot. "Tell the model to escalate when unsure"
   is rung 5, not rung 6: rung 6 is a person actually resolving the record.
4. **Rung 3 cannot currently vote, and it is not a rung 3 bug.** It matches
   mentions by `(doc_id, spans)`, and samples at temperature 0.7 pick different
   phrases, so keys never align — every record comes back `not_resampled`.
   Matching on overlap rather than exact span would let voting run at all.
5. **`scripts/` has no test coverage.** That is how a `NameError` in
   `full_run.py` survived the renumber. One import smoke test per script closes
   it. `ladder/run.py:snapshot_row` was in the same state until 2026-08-24 and
   now has `tests/test_run_rows.py`.
6. **The lookup-vs-RAG 2x2 needs a model that names concepts.** Top row
   measured: a perfect clinical term scores 99.3% by exact lookup AND 99.3% by
   dense retrieval — they coincide by construction, so retrieval can only pay
   on an IMPERFECT label. Bottom row unmeasurable at 2B: granite4:micro-h
   proposed `AFTERPROMPT` for "rectal bleed", so there was no concept to
   retrieve on. Needs claude-sonnet-5, which is a licence call
   (`LADDER_ALLOW_REMOTE=1`, CADEC is non-transferable) as well as a cost one.
   `checks["labels_proposed"]` now records what the model offered, which is
   what makes the comparison possible at all.
7. **Dense retrieval's 13.9% miss is mostly NOT fixable by a better
   retriever, and a hybrid loses.** Measured at equal budget: dense@40 89.5%
   beats dense@20+lexical@20 88.0% and dense@20+char-trigram@20 89.3%. The fix
   for recall is `rung0_shortlist_k`, not a second index — but raising k costs
   at the PICK step, where a long menu bought position bias (measured at the
   retired S3). That trade-off is its own experiment. Miss profile: 8.6% are
   SENTENCES retrieved against 4-word terms (the same defect query rewriting
   would fix), 1.6% post-coordinated gold, 0.3% absent from the table, and the
   rest are ranked-too-low — a large part of which is gold naming one concept
   where the span literally names another ("little blurred vision" -> gold
   |Hazy vision|, retrieved "blurred vision").
8. **Schema enforcement is an A/B, not a switch.** It does not delete the
   parse-failure metric — it MOVES the failure (truncation, empty mention
   lists, plausible wrong values) and costs output quality, because
   probability mass goes to satisfying the grammar. Run both arms and report
   what it removed and what it cost. Not built.
9. **S0 records a LIST of codes as a string, and it will bias S0 downward.**
   `_step_s0` does `str(code)`, so a model answering `sct_code: ["21456007",
   ...]` gets `sct = "['21456007', ...]"` — never a valid code, so those
   mentions score 0 by construction. A RECORDING defect, not a model one: it
   makes "the model named two codes" indistinguishable from "the model emitted
   garbage". Decide what S0 should measure (first code / parse failure / its
   own outcome) BEFORE the dev runs, or S0's number is not the model's.
10. **The 111 retired gold mentions `clean.py` excludes but `outdated` can
   answer.** All 407 wholly-retired gold mentions leave the denominator, on the
   grounds that the keyword table is active-only. 111 of them (27.3%) have a
   SNOMED-recorded successor, so a model naming that successor is right against
   a stale answer key. Changing the answer key's inventory needs a measurement
   and a decision, not a quiet edit — see docs/decisions.md 2026-08-24.
11. `python -m ladder.rungs.r0 --compare` — the tool ablation. NOTE: mode B has
   no tool-call loop; `vocab.search()` runs AFTER the model replies, so today it
   measures "would a search have found the code it invented?", not "does search
   help?".

## Conventions
- One file per rung, one owner per file. Append to schemas, never reorder.
- `manifest.json` is append-only and edited jointly.
- Log every decision in `docs/decisions.md` — one line, as you go. It is the
  article's raw material and cannot be reconstructed afterwards.

## Rung numbering — renumbered 2026-08-23
Rung ID now equals execution position: `rung_order` is `[0,1,2,3,4,5,6]`.
Old → new is **3→2, 5→3, 2→5**; 0, 1, 4 and 6 did not move.

| id | rung |
|----|------|
| 0 | bare LLM |
| 1 | deterministic |
| 2 | self-correction |
| 3 | voting |
| 4 | LLM judge |
| 5 | abstention |
| 6 | human loop |

**Every measurement in `docs/decisions.md` dated before 2026-08-23 uses the OLD
ids.** The mapping table lives there too. This also means results are no longer
directly comparable to the brief's numbering without applying it.

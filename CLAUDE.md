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
- **`manifest.model` is the ONE place a model is named.** `ladder/llm.py`
  carries no default and `resolve()` RAISES on a missing entry — it used to
  fall back to `ollama/gpt-oss:20b` while the manifest said
  `granite4:micro-h`, so "which model produced this number" had two answers
  depending on whether a manifest reached the call. Order is `--extractor` >
  `LADDER_MODEL_SPEC` > manifest, and nothing after.
- **Extractor is `ollama/gpt-oss:20b`** (2026-08-24, on measurement).
  granite4:micro-h answered `AFTERPROMPT`; gpt-oss names real concepts.
  **It is a REASONING model** — its chain of thought goes to a separate
  `reasoning` field and `content` stays EMPTY until it finishes, so
  `max_tokens` and `reasoning_effort` are per-model registry data in
  `models.yaml`. **`reasoning_effort` is deliberately UNSET** with a 32000
  cap: `low` answers S0 in 104 tokens but finds **1 of 17** gold mentions
  across 3 documents against 11 at default effort. It stops truncating and
  starts missing — the same failure in a cheaper coat. The effort also cannot
  differ per step, since scope is identical across S0/S1/S2 by design. The
  cost is reported, not avoided: **a dev-split run takes hours, not minutes.**
- **The judge is now the WEAKER model** (granite4:micro-h, 2B, judging a 20B
  extractor). It is the only locally installed family that differs from the
  extractor, and rung 4 refuses to self-judge. Read rung 4's numbers with that
  stated, or install a third family.
- **The LLM cache key covers max_tokens and reasoning_effort.** It did not,
  and rerunning S0 with a new effort served the old truncated entry. A cache
  that survives a parameter change is a stale result. A TIMEOUT is never
  cached — it is a property of the run, not of the question.
- **Every call has a wall-clock budget** (`timeout_s`, registry data,
  300s for gpt-oss). Measured: a dev-split run stopped dead when one call
  generated for 25 minutes on a 761-character post. 90% of calls finish under
  3,244 completion tokens; the tail is what makes a run unbounded. The timeout
  does NOT raise — it returns an empty response flagged `timed_out`, so one
  runaway document costs ONE RECORD, not the run.
- **Three failure labels, most specific first: `timed_out` > `truncated` >
  `json_decode`.** They overlap on purpose. A cut-off reply must never be
  counted as a model that cannot produce JSON, and a hung machine must never
  be counted as either. **Timeouts belong in the cost column, not the accuracy
  one** — they measure this machine's throughput on a 20B model.
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

- `scripts/` import smoke test (2026-08-24), which immediately found two live
  bugs in `ladder_run.py`: `say()` called above its own definition, and the
  pre-renumber module pairing in the signature banner.
- **Truncation and timeout are recorded separately from a JSON parse
  failure** (2026-08-24). `timed_out` > `truncated` > `json_decode`.
- **S0's list-of-codes defect** (2026-08-24). `str(code)` on a list made
  "the model named three codes" identical to "the model emitted garbage";
  the first is taken and the violation is counted.

## Rung 0 measured — dev split, 40 docs, 226 gold mentions (2026-08-24)
`ollama/gpt-oss:20b`, `reasoning_effort: low`, rung 1 observe.

| | F1 exact | F1 overlap | calls | tokens | parse fails |
|---|---|---|---|---|---|
| S0 | **0.018** | 0.018 | 40 | 43,998 | 5 of 40 |
| S1 | **0.171** | 0.305 | 57 | 36,079 | 0 |
| S2 | **0.209** | 0.310 | 75 | 68,906 | 0 |

- **S0 is broken, not weak.** Ten times worse than S1 for MORE tokens. The one
  thing rung 0 cannot do — recall a nine-digit id — is also the most expensive.
  It is the only step that fails to parse, and the failure is its schema.
- **S1 and S2 are close and S2 costs 1.9x.** Half a point apart on overlap,
  3.8 points on exact. **S2 IS FROZEN in `manifest.rungs.0.rung0_step`
  (2026-08-24).** The 1.9x token cost is a declared trade, not a free win, and
  the three cost measures carry it. Frozen because rungs 1-6 must all be
  measured against ONE rung 0; `--rung0-step` still overrides for a single run.
- **The exact/overlap gap is span boundaries, not coding.** The model quotes
  "extreme rectal bleed" where gold says "rectal bleed" — same concept, scored
  as both a false positive and a false negative. Report both numbers.
- **An abstention hatch reduces fabrication but does not remove it.** S0 may
  answer `null` for an id it does not know and does so 12.4% of the time — and
  still emitted `2714004`, a nonexistent code, beside a correct label.

## Next, in order — the phase plan (2026-08-25, approved)
Phase A is DONE (two-layer scorer, bootstrap CIs, excluded-overlap fix,
S0/S1/S2 confirmed under the enhanced config — see docs/decisions.md).
Run each remaining phase in its own session; this section is the handoff.

1. **Phase B — rung 0 accuracy. DONE 2026-08-25** (see docs/decisions.md,
   four entries same date). (a) Negation SHIPPED: all three schemas ask for
   `negated`, denied mentions are extracted, flagged on
   `checks.negated`/`checks.r0_negated` (the copy rung 1's cue overwrite
   cannot clobber), marked `[denied]` in the pick menu — without that
   marker the pick declined every denied mention it was given. (b) Query
   rewriting REJECTED on the offline measurement: raw reproduced the 87.0%
   deduped recall@20 baseline, both rewrite variants lost (rescued 26,
   broke 62–71). Not wired. (d) SPAN TRIMMER shipped (`ladder/trim.py`,
   `rung0_trim: true`): pool-learned edge trims + interior clause cut;
   exact +0.4pt, overlap untouched. (c) Result on dev, 40 docs:
   **F1 exact 0.296 → 0.362, overlap 0.451 → 0.479** (detection
   0.501/0.783, coding 0.704/0.611), 137,828 tokens / 77 calls (+5.8%).
   Runs: `out/phaseB-1.*` (confounded by one `{"picks":[]}` reply — the
   diagnosis is the decisions entry), `out/phaseB-2.*` (the result).
   (e) One menu arm run: alphabetising the pick menu costs 10-12pt
   of coding accuracy at identical detection - the pick anchors on
   early slots, so retrieval's best-first order is load-bearing.
2. **Phase C — models.** Import BioMistral-7B (GGUF → ollama Modelfile),
   register in models.yaml, swap in as rung-4 JUDGE (fixes the 2B-judging-
   20B inversion; different family; local so no licence issue). Re-judge
   the full-ladder run's 240 records, compare against granite's 33%-vs-17%
   signal, then re-run the rung 5 gate analysis + tau sweep on the new
   judge's risk-coverage curve. Optional: one S2 extractor arm.
3. **Phase D — rung 3 repair.** FIRST disable rung 3 in ladder runs (it
   overwrote 9 of 32 verified-ACCEPT codes with memory-recalled
   hallucinations — see decisions 2026-08-25). Then: (a) match votes by
   record identity, not (doc_id, spans) key; (b) sampler must go through
   the FULL S2 retrieve-and-pick path per sample so votes come from the
   distribution being verified. Re-enable only with both fixed and measured.
4. **Phase E — rung 6.** Human-loop desk over `checks.withheld` of
   abstained records; resolution format feeds the scorer. Build AFTER C/D
   so the inbox is the real residue.
5. **Phase F — test split, ONCE.** Freeze manifest+prompts+models, run the
   60 held-out test docs, report as-is. Nothing is re-run after it.

Parked with the user: remote claude-sonnet-5 extractor (licence call,
LADDER_ALLOW_REMOTE=1); the 111 retired-gold successors denominator
decision.

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

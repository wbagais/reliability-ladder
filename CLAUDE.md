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
- **All seven rungs exist** (rung 6 landed 2026-08-26, Phase E). The full
  ladder runs end to end, cold, in order `[0,1,2,3,4,5,6]`. 581 tests, CI green.
- **Rung 6 is a rung with two modes and no model.** The queue is rung 5's
  abstained residue (`checks.withheld` preserved). `simulated` prices the queue
  at `minutes_per_record` into the ledger's `human_minutes` — no answer
  invented, coverage cannot move. `desk` applies a resolutions file from
  `scripts/r6_desk.py` (decisions `code|concept_less|uphold|skip`, matched BY
  SPAN KEY one-to-one, minutes measured; rows carry no corpus text). The desk
  shows vocabulary labels, never bare SCTIDs, and searches through rung 0's own
  retriever. `--oracle` writes gold-derived resolutions — an ORACLE CEILING,
  labeled `resolved_oracle` on every row and refused on the test split.
- **`manifest.model.temperature` IS READ NOW** (wired 2026-08-31). It was
  declared and unread: `Caller.__call__` had `0.0` hardcoded, so the declared
  and real answers agreed by accident. `llm.temperature_for` resolves it,
  `for_rung` binds it to the Caller, and an explicit call argument still wins
  so rung 3's `sampler(0.7)` is untouched. **The float cast is the whole
  no-change guarantee** — temperature is in the cache key, and int `0` and
  float `0.0` hash differently. `test_every_tracked_manifest_resolves_to_the_published_temperature`
  fails if any manifest moves off 0.0: editing that key now CHANGES a run
  rather than relabelling one. Provenance stamps `temperature_declared`, since
  a declared 0 and a defaulted 0.0 are the same number and not the same fact.
- **The same audit found FOUR more declared-and-never-read settings, now all
  read** (2026-08-31, `tests/test_declarations_are_read.py`). None changed a
  number; all four were inert at their declared value, which is how the
  temperature key looked too. (a) `vocabulary.snomed_backend` — `run.py` was
  hardwired to Registry, so `ols4` would have changed nothing while the
  results file claimed it. `run.check_snomed_backend` now REFUSES `ols4`
  rather than honouring it: `Ols4Vocabulary` serves rung 1 but has no
  `replacements` and none of rung 0's `shortlist`/`resolve`, so running on it
  is an unmeasured experiment, not a fix. (b) `vocabulary.meddra_mode` —
  `answer_space` is refused, because it meant S3, dropped 2026-08-24. (c)
  `rungs.1.outdated_check` — the `off` its own note documents did not exist;
  `r1.DEFAULTS` now carries it and `_record_history` honours it. (d)
  **`ladder/otel.py` is DELETED** (2026-08-31, the day after it was wired).
  It was UNIMPORTED, so the `LADDER_OTEL=1` in its own docstring emitted
  nothing; wiring it made that honest, and then the feature turned out not to
  be wanted. One commit ever (2026-08-23), touching only the module and a
  hand-made smoke row — "phoenix transport verified" meant verified against
  `{"run_id": "smoke", "doc_id": "D1"}`, never a ladder run. Five phases and
  two corpora later nothing had used it, no `docs/decisions.md` entry depended
  on it, and its spans were a strict copy of the ledger row that is already
  JSONL on disk and already what `ladder_top.py`, `provenance` and the harness
  scripts read. The README block and the `docs/plan.html` row went with it.
  **Do not reintroduce it without a consumer**: two tests keep it gone, one of
  which greps the docs, because a feature the README advertises and no code
  implements is this same defect pointed the other way.
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
  extractor), and as of Phase C that is a MEASURED choice, not a shortage: the
  third family that was installed to fix it (BioMistral-7B, domain-adapted)
  was rejected on the 240-record re-judge — it cannot reliably return the
  judge JSON and its verdicts carry no signal. Read rung 4's numbers with the
  2B caveat stated; it is the lesser evil until a better third family exists.
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
2. **Phase C — models. DONE 2026-08-25, negative result** (three decisions
   entries same date). BioMistral-7B imported, registered, swapped in,
   measured on the 240-record re-judge — and REJECTED: 167/240 unjudged
   even after two harness repairs (instant-EOS above ~430 prompt tokens),
   all 73 parsed verdicts "fail" (fail rows 23.3% correct vs 24.6%
   unjudged — no separation), confidence flat 0.0 so the tau sweep had
   nothing to sweep (skipped, contingency not met; S2 extractor arm
   declined on the same evidence). Judge REVERTED to granite4:micro-h —
   the 2B-judging-20B caveat stands as the measured lesser evil. Kept from
   the phase: the re-judge harness (`scripts/rejudge_r4.py`), the
   post-sent-TWICE fix in rung 4 (r2 has the same defect, flagged for its
   own session), and `Caller._reclose` (counted single-brace repair, like
   fence stripping). Also found: granite re-judged through the fixed path
   loses its pass/fail separation (28.0/15.6 → 25.4/23.6) — rung 4's
   signal was partly the prompt duplication, i.e. prompt form is
   load-bearing for small judges, same lesson as B(e)'s menu order.
3. **Phase D — rung 3 repair. DONE 2026-08-26** (four decisions entries
   same date). Disabled first — `enabled: false` is now a RECORDED run
   state (ledger row + aggregate), never a silent skip. Four fixes, all
   TDD'd (`tests/test_r3_repair.py`): (a) votes matched by span overlap,
   one-to-one per record identity; (b) every sample drawn through rung 0's
   configured path — `r0.prepare` + `r0.extract_document`, shared with
   `r0.apply` so the two cannot drift; (c) a change requires seen >= 2 —
   one counted vote is not a vote (found by measurement 1: |Analgesia|
   overwrote verified |Pain| on a 1-0 "majority"); (d) documents sampled
   in sorted order so the draw sequence reproduces from the run id.
   Re-enabled on `out/phaseD-r3-2` (dev): not_resampled 206/240 -> 38/245,
   hallucinated overwrites GONE, 0 correct codes destroyed, stack F1
   exact 0.335 -> 0.347, cost 383k tokens (2.6x rung 0). Rung 3 numbers
   are SAMPLES — always cite the run id.
4. **Phase E — rung 6. DONE 2026-08-26** (three decisions entries same
   date). `ladder/rungs/r6.py` + rewritten `scripts/r6_desk.py`, 23 new
   tests, all TDD'd. Measured on the phaseD-r3-2 residue (208 of 245
   abstained): **simulated** = 416.0 human minutes at the declared 2.0
   min/record, accuracy untouched (`out/phaseE-r6-sim.*`); **oracle
   ceiling** = shipped F1 0.131 → 0.444 [0.335–0.548] exact, coding
   accuracy on matched spans 0.291 → 0.990 with detection unchanged — the
   whole remaining gap is span boundaries, which a code-picking desk
   cannot fix (`out/phaseE-r6-oracle.*`). 9 schema-invalid records with
   unlocated `(-1,-1)` spans are unreviewable by a span-keyed desk and
   stay ESCALATE. The queue's withheld answers were already correct
   46×/74× (exact/overlap) — the oracle recovers 102 exact because a
   reviewer also FIXES wrong codes. Every oracle number is a labeled
   ceiling. DECIDED 2026-08-26: the headline rung-6 cost is the COUNT
   routed to a person (208/245, reviews_per_100 84.9) — minutes are not
   measurable here; the timed session is descoped, minutes_per_record
   stays a declared illustration only.
5. **Phase F — test split, ONCE. DONE 2026-08-26 — THE LADDER IS COMPLETE**
   (one decisions entry same date; run `phaseF-test-1`, artifacts in the
   phase-f worktree's `out/`). Frozen config, 60 test docs, cold cache,
   ~78 min, one run id, zero edits. Shipped: **F1 exact 0.204
   [0.150–0.260] / overlap 0.215**, detection 0.521/0.808, coding accuracy
   0.392/0.266; outcomes exact 60/0/91/2/0 — `modernised` did not fire.
   Above the re-derived dev baseline (0.131) on all three layers. Rung 1
   (local-rf2): 5.1% reject, all `schema_invalid`, so rung 2 attempted 0.
   Rung 3 (samples, this run id): re-found 8, all wrong — the dev gain did
   not transfer. Rung 6: **242/314 routed to a person, reviews_per_100
   77.1**; 484.0 min at the declared rate only. 844,657 tokens / 758
   calls; p95 57.2 s (r0) / 126.1 s (r3) / 1.5 s (r4); usd 0.00; zero
   timeouts/truncations/parse-fails at the transport level. Oracle desk
   refused on test, as designed. **These numbers are final as reported;
   nothing is re-run after Phase F, and there are no further phases.**

Both parked questions were DECIDED 2026-08-26 (two decisions entries):
the remote claude-sonnet-5 extractor is an OPTION, never the default —
`--extractor anthropic/claude-sonnet-5` + `LADDER_ALLOW_REMOTE=1` per run,
manifest stays local, budget registered in models.yaml (rung 3 caveat: no
temperature dial, votes degenerate). The 111 retired-gold successors get
the fifth outcome `modernised` (mirror of `outdated`, own `sct_modernised`
column, never folded into correct — headline denominators unchanged;
0 fired on dev, 6 possible there).

## Session 2026-08-30/31 — four tasks plus the article (14 commits, 725 tests)
1. **The three-draw debt is PAID and both arms survive** — nothing removed, no
   CADEC number re-run. `rung0_split` exact +0.0389/+0.0345/+0.0579, pooled
   **+0.0438 [+0.0012, +0.0937]** (separated); `rung0_cut_rate` exact
   +0.0139/+0.0183/+0.0098, pooled +0.0140 [−0.0163, +0.0500] (consistent, and
   SMALLER than the base's own 1.3pt spread). **The split buys EXACT ONLY** —
   its overlap sign reverses. Both manifest notes amended. Runs
   `out/arm-debt{base,nocut,nosplit}-d{0,1,2}-dev.*`.
   **`ladder.score.paired_bootstrap` is now production code**, because
   `out/harness/paired.py` resampled with `set(random.choices(...))` — a ~63%
   subsample, not a bootstrap. `bootstrap_ci` refactored onto the shared
   helpers, output byte-identical.
2. **Rung 4 is WIRED and it stays OFF** (owner's call: wire-and-measure).
   `rungs.5.abstain_on_judge_fail` (default false, declared in the manifest),
   `R_JUDGE_FAIL`, `manifest.judgearm.json` = a test-pinned one-key diff.
   Three draws: coverage 0.210/0.202/0.215 → 0.153/0.149/0.156; **yield
   0.169/0.161/0.177 → 0.125/0.121/0.131**; to a person 196/198/186 →
   210/211/200. Withdraws 14/13/14 to remove 3 errors — **3.7 correct destroyed
   per error caught**, lift 1.11–1.21x against the free check's 3.03–3.15x.
   Precision rose because abstaining always raises precision; yield is the
   number that cannot be fooled. Runs `out/judgearm/`.
3. **FiNER recall — the old premise was wrong.** 0.303 = detection **0.685** x
   coding **0.446**; the model reaches two thirds of gold and mis-codes it, and
   proposes 292 spans against 165 gold. **Recall work here is CODING work.**
   - **A REFUSAL IS NOT A JSON FAILURE.** One document held 21 of 165 dev gold
     (12.7%, 40% of the detection gap) and the extractor answered *"I'm sorry,
     but I can't provide that."* New label ladder `timed_out > truncated >
     refused > json_decode` (`r0.failure_reason`). The detector MUST read
     U+2019 — an ASCII-apostrophe detector never fires on real output.
   - **The refusal is the DRAW, not the document or the model**: same request,
     d0 refused / d1 33 mentions / d2 33 mentions; all three other families
     answered. So the 1.3pt spread understates the risk — variance concentrates
     into whole-document, all-or-nothing outcomes.
   - **REJECTED: `rung0_menu_order: "context"`** (`ladder/menuorder.py`, off in
     both manifests, `manifest.finer.ctxmenu.json` a test-pinned one-key diff).
     Detection byte-identical; coding 0.393 → 0.304. Mechanism confirmed on the
     artifacts (`out/harness/finerctxdiag.py`): slot-0 picks 20.4% → 50.2%,
     slot-0 accuracy 0.087 → 0.373, but the model's own unranked judgement
     scores **0.457**. A ranking can carry real signal, move the model, and
     still lose to what it displaced. **ONE DRAW** — three needs FOUR runs
     (both sides at d1 and d2) at ~78 min each. FiNER's own run-to-run spread
     has never been measured.
   - **THE SLOT-0 ATTRACTOR, and it is the session's sharpest result.**
     `AccrualForEnvironmentalLossContingencies` is **menu slot 0** (the menu is
     `sorted(set(tags))`) and is predicted **57 of 292** times against **2 in
     gold** — **19.5% of all predictions are the list's first line.** The
     context arm is the free position-vs-semantics discriminator: it moves the
     tag to median slot 92 and the prediction count falls **57 → 3**, and in
     BOTH arms every single one of those predictions was taken while the tag
     sat at slot 0. The model takes it **iff** it is first. So the context arm
     is TWO effects, not one failure: it killed the attractor (a real fix) and
     amplified the positional prior (20.4% → 50.2% slot-0 picks), net negative.
     **NEXT EXPERIMENT, and it is not a better ranker: break the position prior
     — a slot 0 that is never a valid answer, or a per-mention permutation with
     a fixed seed.** Composes with CADEC rather than contradicting it: there the
     menu is retrieval-score-ordered, so the same prior lands on the BEST
     candidate, which is why alphabetising it cost 10-12pt.
     `out/harness/finermiscode.py`. Also: of 113 matched spans 68 are miscoded
     and **0 are abstentions**, 79.4% of wrong tags share no leading word with
     gold, and 13 predictions are CONCEPT_LESS against 0 in gold.
4. **The published artifact is the ARTICLE now**, not the build log.
   `docs/article.html` serves the existing URL; `docs/article-build-log.html`
   is archived as `docs/versions/article-build-log-v2-2026-08-28.html`.
   **`docs/article.md` is the article, and it is canonical** — the 2026-08-30
   revision (the four results above) was promoted into it and the version it
   replaced is `docs/versions/article-v2-2026-08-28.md`. There is no
   `article_vN.md` beside it: one file, one answer to "which article is this".
   New material is marked in the typeset page so a reader who saw revision 2
   can find what changed.

**Where this session's artifacts live — THEY DO NOT, ANY MORE (deleted
2026-08-31).** `out/` is gitignored, and the worktrees that held it were removed
in the branch cleanup: `phase-e-rung-6-human-loop-64ce8e` (the debt arms,
`out/judgearm/`, `out/finer/`, ~80 harness scripts), `agitated-lewin-346b03`
(the five-model sweep and the FiNER data everything else symlinked to),
`reliability-ladder-owner-a-8786e6` (phaseB), `plan-e2e-test-b5f28f` (the gold
replays), `fervent-hellman-813240`, `phase-d-rung-3-repair-fafe4c` (phaseD-r3-2)
and `phase-f-test-split-cd5c99` (**`phaseF-test-1`, the one held-out run**).
This was the standing convention executed, not a mistake —
`out/harness/README.md` calls the scripts scratch and `docs/decisions.md` is the
durable record — and every number cited in this file stands as reported there.
The consequence to know before quoting one: **no number here can be re-derived
from disk any more, only re-run**, and Phase F cannot be re-run at all. Full
inventory of what went, per worktree, in the three `2026-08-31` entries at the
end of `docs/decisions.md`.

### Also this session — the article layer, and the FiNER draws
5. **The FiNER three-draw debt is PAID and the context arm is REJECTED.**
   base exact 0.193/0.205/0.205 vs ctx 0.149/0.128/0.128; coding
   0.393/0.421/0.421 vs 0.304/0.263/0.263. **d1 and d2 are BYTE-IDENTICAL**
   (same sha256, both arms) — so FiNER's whole run-to-run spread is ONE
   REFUSED DOCUMENT, not a distribution. Say "one refused document", never
   "±1.2 points". Runs `out/finer/arm-finer{base,ctx}-d{0,1,2}.*`.
6. **`docs/article-v3.md` is the live article draft** — based on
   `docs/article-v2.md` (the 3,579-word submission), NOT on `docs/article.md`
   (the longform build report). It carries **four `[PENDING]` markers**, and
   two of them can CHANGE a claim rather than add to it: the CONORM
   comparison (our "exact F1 0.70 is unreachable by any system" may hold only
   for ZERO-SHOT systems) and the retriever (our "retrieval is a ceiling" may
   be our general-purpose 30M embedder). **Do not quote either claim
   unqualified until those are closed.**
7. **`docs/PLAN-next-sessions.md` is the work queue**, four sessions with a
   paste-ready prompt for Session 1. Start there.
8. **Figure 2 is the article's spine diagram** (`docs/figures/fig6-spine.dot`)
   and every claim now carries a REAL example from the artifacts
   (`out/harness/examples.py`, `out/harness/rungexamples.py`). **Licence rule
   for examples: CADEC gives ANNOTATED SPANS and vocabulary labels only, never
   a sentence of post prose.** FiNER is CC-BY-SA-4.0 and is quoted directly.
9. **Naming, fixed:** `docs/article.md` = longform build report,
   `docs/article-v2.md` = the previous submission, `docs/article-v3.md` = the
   current draft, `docs/versions/article-longform-2026-08-28.md` = the
   archived longform. There is no `article_vN.md`.

## TODO — registered, not started

- **~~BioMistral-7B AS THE RUNG 0 EXTRACTOR~~ — DONE 2026-08-31, NEGATIVE, and the
  claim now holds in TWO roles** (three decisions entries same date). Protocol run
  exactly as registered: dev, 40 docs, frozen manifest, rungs 0-1,
  `--extractor ollama/biomistral:7b-q5_k_m`, three cold-cache draws. **3 predictions
  against 226 gold, F1 exact 0.0087, 36/40 documents `json_decode`, 621 completion
  tokens for the whole split** — and all three draws BYTE-IDENTICAL (BioMistral is
  bit-reproducible, like the four dense models). The reply is `" {"` then EOS, the
  same string as the 2026-08-25 judge failure.
  - **The prompt-token distribution was registered BEFORE the run** and that is what
    makes the null readable: find 828-1134 (median 918), pick 520-2339 (median
    1404), `over_430` = 100% on both. `out/biomistral-prompt-tokens.json`.
  - **The mechanism is NOT what was registered.** All 40 prompts replayed through
    raw httpx with no ladder code: same 4/40, `finish_reason: "stop"` on every one
    (not truncation, not our transport). The cliff is real but sits at **~856**
    tokens here, not ~430 — 0/31 above it answer, 4/9 at or below do — so a
    threshold that doubles with the role is not a token count. Stripping the
    few-shot block (520 tokens) does not rescue it; a 77-token bare ask answers.
  - **It is GREEDY DECODING.** Same failing prompt: temp 0.0 EOSes, 0.7 answers 2/3,
    1.0 answers 3/3. So an off-protocol temperature-1.0 arm was run (three draws,
    scratch-injected, production untouched): documents answered 4 -> 6/8/15, F1
    exact 0.0169/0.0504/0.0492 — **a factor of four below un-adapted
    `mistral:7b-instruct` (0.206) on the same split at temperature 0.** The escape
    is real and does not rescue the model.
  - **The ACCEPT lane is NOT measurable on any of the six runs** (n = 1, 2, 2, 6).
    The arm contributes NO row to the five-model table and must not be given one.
  - Discharges the article's standing limitation "we tested a domain-adapted model
    in one role only" (`docs/article-v3.md`). `models.yaml` resized 512/120 ->
    2000/180 (TDD'd) so a truncation and an instant EOS are distinguishable.
  - **INCIDENTAL, and it wants its own session: `manifest.model.temperature` is read
    by NOTHING.** `Caller.__call__` defaults to 0.0 and only rung 3 passes one, from
    `manifest.rungs.3.temperature`. Same shape as the `manifest.model` fallback
    defect and the 5.9-point arms gap, one layer down.

- **SapBERT (or any domain-adapted encoder) as the S2 retriever** (added
  2026-08-30, from the literature review). Dense retrieval currently runs
  `granite-embedding:30m`, a GENERAL-PURPOSE 30M embedder, where the field
  standard for biomedical entity linking is a domain-adapted encoder. Part of
  the retrieval ceiling this project attributes to the TASK may be attributable
  to that choice, and "retrieval is a ceiling" is a load-bearing claim. State it
  as a limitation in the article regardless; measure it if there is time.

- **Break the slot-0 position prior on FiNER** (added 2026-08-30, the highest
  value untried FiNER experiment — see the slot-0 attractor entry in
  `docs/decisions.md`). NOT a better ranker: a slot 0 that is never a valid
  answer, or a per-mention permutation under a fixed seed. The model takes menu
  line one iff it is line one, 19.5% of all predictions.

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

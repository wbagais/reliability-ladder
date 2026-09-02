# Plan — next sessions

**Updated 2026-09-01. Session 1 is DONE, B2 is DONE, and `docs/article-v3.md`
has NO `[PENDING]` markers left.** Read this header before working from anything
below it.

| item | state |
|---|---|
| **A1** · CONORM comparison | **DONE 2026-08-31.** The 0.70 ceiling claim is *corroborated*, not refuted — their span-exact 0.704 is **detection only**, and their 0.7245 end-to-end is the lenient figure. Our own comparison was the defective part and is rewritten. |
| **Session 1 §2** · FiNER three draws | **DONE 2026-08-31**, already written into §2: the run-to-run spread is one refused document, d1 and d2 byte-identical. |
| **Session 1 §4** · `preflight_rungs` | **DONE 2026-08-31.** Validated against the four dead rungs, 11 tests, mutation-checked. Scope and caveats in `docs/decisions.md`. |
| **Session 1 §5** · file-role headers | **DONE 2026-08-31.** |
| **B3** · BioMistral as extractor | **DONE 2026-08-31, negative.** Session 3 §1 below is spent; the article bullet is closed. |
| **B1** · discontinuous spans | **DEFERRED, deliberately.** Discharged in the article as a stated cap rather than a fix — no conclusion rests on the recall number, and the best supervised system appears to share the cap. Still worth building; not a blocker. |
| **B2** · domain-adapted retriever | **DONE 2026-09-01, negative.** SapBERT is the better retriever corpus-wide (menu recall@20 87.0% → 88.4%, separated) and made the system **worse** end to end (F1 exact −0.027 pooled, coding −0.048, 3/3, byte-identical detection). Arm ships OFF. **The probe that authorised it was run over 1,144 documents while the arm runs on 38, and on those 38 the sign flips — a go/no-go probe must use the arm's own denominator.** |
| **B4 · B6 · B7** | future work, documented in the article as such. |

**The structural reason not to run Sessions 2–4 in full:** Phase F spent the test
split. B1, B2 and B4 can only produce development-side deltas, and no
development-side delta can move a shipped number.

Run each session in its own worktree. Log every decision to `docs/decisions.md`
as you go. TDD, test first. Three draws plus the paired bootstrap, never one.

---

## Session 1 — Article, no code (~4 h) — **DONE 2026-08-31**

**Goal: article-v3 becomes submittable except for what Sessions 2–4 add.**

1. **A1 · Verify the CONORM comparison. Do this first.**
   Read *CONORM: Context-Aware Entity Normalization for Adverse Drug Event
   Detection* (medRxiv 10.1101/2023.09.26.23296150; medRxiv returns 403 to
   automated fetch — get the PDF another way). Answer exactly two questions:
   - Is their evaluation **end-to-end** (detect + normalise) or given gold spans?
   - Is their "exact F1" **span-exact** the way ours is?

   **Then decide, and it is a real decision:** if they are end-to-end and
   span-exact at ~0.72, our claim that *"exact F1 above 0.70 is unreachable by
   any system"* is **wrong as written** and becomes *"unreachable by a zero-shot
   system"*. Rewrite it; do not soften it. Log the outcome either way.

2. **Read the three finished FiNER draws** (`out/harness/finerdraws.log`, plus
   `out/finer/arm-finer{base,ctx}-d{0,1,2}.json`) and write up:
   - the paired three-draw result for the context-menu arm;
   - **FiNER's first run-to-run spread** — it has never had one, and every FiNER
     number in the article is currently a single draw;
   - the refusal's draw-dependence (d0 refused, d1 and d2 did not).

3. Apply the results to `docs/article-v3.md`, clear those `[PENDING]` markers,
   and drop the DRAFT header if nothing else blocks.

4. **`scripts/preflight_rungs.py` landed on main on 2026-08-31** — it is the
   rung-precondition check the article calls "the obvious next experiment, and
   we have not run it". Run it on both manifests and compare its predictions
   against what each rung actually paid (the spine ablation and the judge arm
   are the answer key). Then rewrite that bullet in
   *What we could not settle* — the tool existing is not the same as its
   predictions being validated, and the article must not claim either one
   wrongly.

5. Housekeeping: one-line header on `docs/article.md` (longform build report)
   and `docs/article-v2.md` (previous submission) saying which is which.

**Done when:** A1 is logged with a decision, the FiNER draws are written up, and
article-v3 has three fewer `[PENDING]`s.

---

## Session 2 — Our own bugs before the model's limits (~1 day)

**Goal: stop blaming the task for a cap we built.**

1. **B1 · Emit discontinuous spans.** 17.3% of CADEC gold is discontinuous and
   `r0` emits `spans=[(start, end)]` — a single segment, always. The scorer
   already keys by span and handles multi-segment; the coordination splitter
   already produces segment groups. So this is r0-side.
   - TDD first: a test asserting a discontinuous gold mention can be matched by
     a multi-segment prediction end to end.
   - Three draws, paired bootstrap, report **detection and coding separately**.
   - Expect recall movement. If it does not move, that is a finding too — say so.

2. **~~B2 · A domain-adapted retriever.~~ DONE 2026-09-01, negative.** Full
   result in `docs/decisions.md`; `manifest.sapbertarm.json` is the arm and it
   ships off. Two things to carry forward:
   - **A go/no-go probe must be run on the denominator the arm will be scored
     on.** Ours separated over 1,144 documents and the arm ran on 38, where the
     sign is negative. That is the reusable lesson.
   - **`ladder/menurecall.py` is the probe, and it is production code with
     tests** — the granite control reproduces the recorded baseline to every
     decimal, which is what makes any second row readable.

3. **B5 · The FiNER pick call cannot see the sentence, and the sentence is the
   whole answer.** FOUND 2026-09-01 while writing §1; not yet measured. This is
   a defect in our harness, not a limit of the task, and it is the same class as
   the unported judge prompt §6 already reports.
   - **The evidence, all from the code as it stands.** `r0._blocks` renders one
     pick block as `reaction {idx}: "{rec.text}"` plus the numbered menu, and
     **nothing else**. `context` is collected by the find call and used only by
     `locate()` and by the rejected `menu_order: "context"` arm — it never
     reaches the pick prompt. So the FiNER pick call sees:

         reaction 0: "47.6"
              [0] AccrualForEnvironmentalLossContingencies
              ... 139 lines ...

     while its own `pick_guidance` says *"The number itself carries no
     information. The sentence around it decides."* **The prompt states that the
     sentence decides, and the sentence is not in the prompt.** The manifest's
     own `_shape_differences_from_cadec` says the same thing: *"Tagged tokens
     are numeric and meaningless in isolation."*
   - **Why CADEC hid it.** There the span carries its own meaning — `"bit
     drowsy"` is most of what you need to pick |Drowsy| — so a context-free
     pick works well enough that nobody looked. FiNER is the corpus where the
     defect is visible, which is the second corpus doing its job.
   - **It predicts the slot-0 attractor rather than competing with it.** A pick
     with no information to act on takes line one; measured, line one is 19.5%
     of all predictions. It also explains why the context menu-order arm lifted
     slot-0 accuracy 0.087 → 0.373 — that arm was smuggling context in through
     the ranking, the only channel it had — while still losing overall.
   - **Second defect, same root, found the same way: `_blocks` hardcodes the
     word `reaction`.** It is not slotted. The FiNER pick prompt says *"Each
     fact has a number after the word 'fact'"* and the data says `reaction 0:`.
     CADEC is unaffected because its `entity_short` IS "reaction". Fix this
     first — it is a one-line slot and needs no arm.
   - **The arm.** Add the span's sentence (or the `context` window already
     collected) to each pick block, behind a declared manifest key, off by
     default, one-key diff pinned by a test. TDD first. Three draws on FiNER,
     detection and coding reported separately — detection should not move at
     all, and if it does, the arm is doing something it should not.
   - **State the confound rather than dodging it.** `r0.py` freezes the prompt
     SHAPE on purpose: *"a corpus needing those changed would be a different
     experiment rather than a second data point."* Giving FiNER context that
     CADEC does not have breaks that comparability. So run the arm on BOTH
     corpora, or report FiNER's improved number as a separate result and keep
     the ported-shape number as the comparable one. Do not quietly replace it.
   - **What it does to the article if it works.** §6's "the corpus where none of
     it works" survives — the ACCEPT lane is zero for a reason no prompt fixes,
     because a number shares no token with a tag name. But §6's coding numbers
     and the slot-0 attractor would need re-reporting against a pick that can
     actually see the evidence, and §9's "menu order is load-bearing" reads
     differently once the alternative signal is present.

**Done when:** both arms are measured at three draws, the article's recall
numbers are re-derived, and §9's claim is either confirmed or rewritten.
**B2 is done; B1 and B5 are what remain of this session.**

---

## Session 3 — The two model questions (~half day) — **§1 (B3) DONE, negative**

1. **B3 · BioMistral-7B as the rung 0 extractor.** Full brief already in
   `CLAUDE.md` under *TODO — registered, not started*. Read it before starting;
   the failure mode is pre-registered there so a null is interpretable.
   `--extractor ollama/biomistral:7b-q5_k_m`, CADEC dev, three draws, everything
   else frozen. Report detection and coding separately, and report the ACCEPT
   lane.

2. **B4 · Break the slot-0 position prior on FiNER.** Not a better ranker. Either
   a slot 0 that is never a valid answer, or a per-mention permutation under a
   fixed seed — the literature's own mitigation is option-order randomisation.
   Off-by-default arm. Three draws.

**Done when:** the "domain adaptation cost instruction-following" claim is either
strengthened to two roles or retracted to one, and the slot-0 finding has a
mitigation measured rather than proposed.

---

## Session 4 — The expensive reference point (~1–2 days, optional)

1. **B6 · A supervised baseline.** Even a small fine-tuned NER + linker on
   CADEC's training split. Off-thesis — we are testing zero-shot reliability —
   but it is the number that would embarrass us if a reviewer ran it first, and
   it settles A1's ceiling question empirically rather than by reading.

2. **B5 · Learn the boundary convention from pool gold.** Only worth doing if A1
   showed the ceiling is learnable. The oracle desk already showed the entire
   residual is span boundaries.

3. **B7 · Conformal / information-lift calibration for abstention.** Moves **no
   F1**. It is the most *on-thesis* item in this file: rung 5's `tau` is a dead
   dial because rung 0's confidence is a constant `{1.0: 204, 0.99: 44}`, so the
   abstention decision currently has no calibrated input at all.

---

## Required before the article ships

Everything here either blocks a claim the draft makes or removes a caveat it
carries. Items 1, 3, 5 and 6 need runs; 2, 4, 7, 8 and 9 do not. Item 3 is the only one
that goes beyond unblocking — it makes the model findings two-corpus instead of
one, and the article is shippable without it, with its CADEC-only caveats
intact.

0. **THE CONSOLIDATED RE-RUN — one config, one metric, one cache state, one
   record. Do this FIRST; it subsumes items 1 and 3 and makes 4 unnecessary.**
   Every number in the article was produced across roughly two weeks, in
   worktrees most of which no longer exist, under at least three different F1
   denominators. Nothing published is known to be wrong — but the figures cannot
   all be reproduced from one place, and reviewing §2 alone turned up a mean
   sitting in a per-draw column, a clustering bug, a "warm cache" that was not
   one, and a between-batch drift that was a metric mismatch. That rate of defect
   per section is the argument for the re-run.
   - **Scope: DEVELOPMENT SPLIT ONLY.** Three cold draws of the full ladder and
     of rung 0 alone, on CADEC dev and FiNER dev, from the tracked manifests with
     no override.
   - **THE HELD-OUT SPLIT IS NOT IN SCOPE AND MUST NOT BE TOUCHED.** Phase F was
     run once, on 2026-08-26, and `CLAUDE.md` is explicit: *nothing is re-run
     after Phase F.* The test numbers (F1 0.204 [0.150-0.260], 242 of 314 to a
     person) stay exactly as published. Re-running test would not refresh the
     headline, it would destroy the only honest held-out measurement this project
     has. If a dev number moves, report dev moving and leave the test box alone.
   - **Fix the metric first, then run.** Decide which F1 the article reports
     (currently `score_run` span-exact with exclusions), and make `results.csv`
     agree with it or label its column differently. Running before that fix
     produces a fourth set of numbers rather than a canonical one.
   - **Record per draw, in `docs/decisions.md` and not only in run files**: spans
     proposed, detection exact/overlap, coding exact/overlap, F1 exact/overlap,
     sha256, the three-way consensus categories, and the post-exclusion gold
     count for each split. Those are the fields this review needed and could not
     find.
   - **Then re-derive every figure in the article from that one run set**, and
     mark anything that cannot be — the article should not carry a number whose
     provenance is a deleted worktree.
   - **Also produces the FiNER stage-by-stage tree**, which article §2 carries a
     PENDING for. CADEC's version traces all 226 gold mentions through find →
     retrieve → pick and shows detection losing 100, retrieval 12 and the pick
     21; FiNER's cannot be drawn because `data/finer` is in no checkout, so its
     records cannot be re-scored against gold. Record the same three splits, and
     expect the shape to INVERT — FiNER's whole vocabulary is in the prompt, so
     retrieval loses nothing by construction and the loss should move into the
     pick. That inversion is the article's sharpest argument for reporting
     detection and coding separately, and it is currently asserted rather than
     shown.
   - Optional and separable: the five-model sweep (item 3b) on the same footing.

1. **B6 · Three draws of rung 0 on CADEC dev, recording detection AND coding
   per draw.** REQUIRES A RUN, and it is a cheap one — rung 0 only, 40 dev
   documents, `sample_index` 0/1/2, the tracked manifest with no override.
   - **Why it blocks a claim.** §2 argues that detection and coding move
     independently run to run. The evidence for it is two data points:
     `docs/decisions.md` (2026-08-28) recorded detection per draw (235 / 235 /
     225 spans, det 0.516 / 0.516 / 0.537) but F1 only as a RANGE and coding
     not at all. So the section's central claim is an inference on the corpus
     we ran properly, while the corpus with a complete per-draw record is
     FiNER, which we ran once. The draft says so; it should not have to.
   - **Also fixes a sourcing defect already corrected in the prose.** The §2
     table used to print `0.395 | 0.408 | 0.401` per draw. The record contains
     only the range and the mean, and 0.401 IS the mean — it was sitting in
     draw 2's column as though it were a measurement. Now stated as a range;
     the run is what makes a per-draw table honest again.
   - **Record all four levels per draw**: spans proposed, detection (exact and
     overlap), coding on matched spans, end-to-end F1. Level 2 (retrieval) is
     deterministic and needs no column — note that rather than measuring it.
   - `out/` is gitignored and the previous artifacts were deleted, so write the
     per-draw figures into `docs/decisions.md` this time, not just the run
     files. That is the whole lesson of the deleted worktrees.

2. **The five-model per-level table — NO RUN NEEDED, the data already exists.**
   `docs/decisions.md` (2026-08-30, the five-model table) already carries
   detection-overlap and coding-overlap per model, and four of the five are
   bit-reproducible at `±0.000`, so their three draws ARE one measurement. The
   article has never printed the decomposition, and it carries the sharpest
   model finding in the project: **`qwen3:8b` is second-best at coding (0.556,
   ahead of llama and mistral) and last overall, because it proposes 57 spans
   against gpt-oss's 232.** A single F1 ranks it below two models it beats at
   the half everyone assumes is hard. Placeholder is in §2 of
   `docs/article-v3.md`. Only gpt-oss's row needs B6 to complete.

3. **FiNER, five models, three cold draws each — the second-corpus twin of the
   CADEC model table.** REQUIRES RUNS, and this is the largest item here. It
   covers two things at once, which is why they are one entry: they need the
   same 15 runs.
   - **(a) FiNER's agreement figures on the run set the article reports.** §2 now
     gives FiNER consensus (306/306, 100%) from `arm-finerbase-d{0,1,2}`, which
     the 2026-09-01 correction confirmed are three genuine cold runs, not cache
     replays — the ledger shows 40 real calls per draw at ~56 s median. But that
     is a DIFFERENT configuration from the one behind the article's 0.193 /
     0.205 / 0.205, whose artifacts were deleted. So the article currently
     reports two FiNER run sets that disagree about whether this model is
     reproducible, and cannot put consensus figures on the second. Three cold
     draws of the reported configuration closes it.
   - **(b) The five-model table, on FiNER.** Every cross-model claim in the
     article is CADEC-only and says so. Three of them are worth testing on a
     second corpus: **is bit-reproducibility a property of the model or of the
     model-plus-corpus?** (four of five were bit-identical on CADEC; nothing
     establishes that it transfers); **does the detection-versus-coding
     decomposition reorder the models the same way?**; and **is the slot-0
     attractor model-specific?** — currently measured on `gpt-oss` alone, and if
     all five families take menu line one it is a general position prior rather
     than one model's quirk, which changes what section 6 is entitled to claim.
   - **What the table will NOT show, and do not build it expecting to.** The
     ACCEPT lane is **0 for every model on FiNER** by construction — a number
     shares no token with a tag name — so this is not a second ACCEPT/BAND table.
     The columns are spans proposed, detection, coding, agreement, and slot-0
     share.
   - **COLD CACHE, and verify it.** Check the ledger, not the records file:
     nothing in the output announces a replay. A run whose completions were all
     served from cache is one measurement wearing three hats.
   - **COST WARNING, and it may force a documented exclusion.** `qwen3:8b` costs
     ~2 h per draw on CADEC and was already excluded from the FiNER refusal probe
     after holding the GPU 45 minutes **on a single document** without returning.
     Three FiNER draws of it may be infeasible. If so, exclude it and say so in
     the table, the way the refusal probe did — an exclusion stated is a result;
     an exclusion hidden is a hole.
   - **Record per model per draw**: spans proposed, detection (exact and
     overlap), coding on matched spans, F1, sha256, wall clock, pairwise span
     Jaccard, and the same-code rate on shared spans. Write them into
     `docs/decisions.md`, not only the run files.

4. **NAME THE METRIC BESIDE EVERY F1 — there are at least three in this repo and
   they disagree by 2-3 points.** NO RUN NEEDED; this is a labelling fix, and it
   dissolves an apparent contradiction rather than explaining one. Measured on
   `arm-sapbase-d{0,1,2}` (CADEC, one configuration, three draws):

   | | draw 0 | draw 1 | draw 2 |
   |---|---|---|---|
   | `score_run`, exclusions applied | 0.413 | 0.434 | 0.422 |
   | `score_run`, no exclusions | 0.387 | 0.407 | 0.396 |
   | `results.csv` `f1_sct_strict` | 0.397 | 0.412 | 0.407 |

   The spread between metrics on the SAME run (2.6 points) is larger than the
   spread between runs (2.1 points). This was nearly written up as a
   between-batch drift finding: the 2026-08-28 baseline reads 0.399 / 0.395 /
   0.408 and the 2026-09-01 baseline reads 0.413 / 0.434 / 0.422, which looks
   like two barely-overlapping ranges from an identical configuration — until you
   notice the first is a `results.csv`-style figure and the second is
   `score_run` with exclusions. **On a common metric the two batches agree.**
   Same likely applies to FiNER, where the article reports 0.193 / 0.205 / 0.205
   and the surviving run's `results.csv` says 0.163; unconfirmed, because
   `data/finer` is in no checkout and the set cannot be re-scored.
   - **The fix:** state which metric every F1 in the article is, once, and check
     that no table mixes two. §2's figures are `score_run` with exclusions.
   - **The rule:** an F1 quoted without its denominator is not reproducible, and
     two of ours differ by more than any arm this project ever shipped.

5. **TWO CLAIMS IN §2 REST ON WORK THAT WAS NEVER FINISHED. Both need runs; do
   not close either by quoting the old figures into the article.** Each was
   measured once, in a different session under a different harness, and this
   review has already shown what happens when figures from two run sets are set
   beside each other — the apparent between-batch drift in item 4 was a metric
   mismatch, not a result. Re-run them on the consolidated footing from item 0.
   - **(a) The LLM reranker, at three draws.** §2 says nothing that tried to help
     the model choose better from the menu ever cleared the bar. True as written,
     and **misleading by omission**: the most promising candidate — a rerank pass
     driven by the model itself rather than by a free feature — was measured on
     ONE draw and dropped on cost, not on evidence. It is untested, not rejected,
     and the article now says so. Three draws settle it. Note the cost before
     starting: it is roughly 1.7× the calls and 2.2× the tokens of a baseline
     run, so three paired draws is six expensive runs.
   - **(b) FiNER's over-extraction, decomposed.** §6 presents FiNER as a recall
     problem. The record says the model proposes far MORE spans than gold holds,
     so the miss is *which* numbers rather than how many — a different diagnosis
     pointing at a different fix. That was measured on a single earlier run whose
     configuration does not match the one §6 reports. Recompute it on the run
     §6 actually cites, then either rewrite §6's framing or record that the
     earlier finding did not reproduce.

6. **RUNG 1 DOES NOT WORK ON FiNER AND THE ARTICLE NOW SAYS SO — build the
   version that can.** Not a measurement gap: a defect. Four of rung 1's five
   checks are vacuous on FiNER by construction (`exists` is always true because
   the menu IS the vocabulary, `is_active` is documented as "vacuously true",
   `finding_status` returns FINDING for anything that exists, and
   `lexical_match` compares a bare number to a tag name so it is always false).
   Only span-grounding has any power, and rung 0's drop filter already handles
   that. **`ACCEPT 0` therefore reports our implementation, not the corpus** —
   the same class of error as an `err_per_100` of 0.0 over an empty output,
   which §6 catches one layer up. `ladder/vocab_finer.py` says this itself in
   `terms()`: *"here it is close to a tautology, and the article should say so."*
   - **The evidence exists; we looked in the wrong place.** The tag's own words
     sit in the sentence, not in the span: *"the effective income tax rate was
     47.6 percent"* against `EffectiveIncomeTaxRateContinuingOperations`. The
     2026-08-30 context probe already showed the signal is real semantically —
     de-camel-cased tag names against 120 characters either side reach recall@20
     0.685, median rank 7. The open question is whether a DETERMINISTIC string
     test finds it too.
   - **Two candidate checks, both free, both deterministic.** (a) *Context
     lexical match*: do the tag's de-camel-cased tokens appear in the window
     around the span? Same comparison rung 1 already does, wider window. (b)
     *Type consistency*: a tag ending `Percentage` or `Rate` should carry a span
     in 0-100; one ending `Amount` or `Value` should sit near a currency symbol
     or a scale word. Both are checkable from the tag name and the text alone.
   - **Measure them the way `lexical_mode` was measured** — plant near-miss tags
     into FiNER gold and report, for each candidate, the ACCEPT-lane coverage
     AND the share of planted near-misses wrongly accepted. That protocol is the
     one thing in this project that produced a setting nobody had to argue
     about; reuse it rather than inventing a new one.
   - **Do not let this become a coverage-chasing exercise.** A check that lifts
     ACCEPT on FiNER while vouching for near-misses is worse than the vacuous
     one it replaces, because at least the vacuous one abstains honestly.

7. **§7's stamina example is framed as a coding fix and cannot be one.**
   Retrieval is deterministic and was replayed 2026-09-01: from the span
   `"stamina"`, `248277009` |Lack of stamina| is ABSENT from the menu at k=50,
   while from `"no stamina"` it sits at rank 0. So rung 3 cannot have changed
   only the code — it must have re-extracted a different span. Either recover
   the span (needs a re-run; the artifacts are gone) or reframe the example as
   what it actually demonstrates: **the span decides the menu, and the menu
   decides which answers are reachable at all.**

8. **WHY `contained` COSTS 22 POINTS OF LANE ACCURACY — measured, never
   explained.** NO RUN NEEDED; the records are on disk. Replaying
   `arm-sapbase-d0` through `r1.zone` under each setting gives ACCEPT 48 at
   85.4% correct (`exact`) against 88 at 63.6% (`contained`). The 40 records the
   looser setting admits are **15 correct and 25 not**, and nobody has looked at
   what separates them. §4 now states that this is unexplained and out of scope
   for the article.
   - **Why it is worth doing.** If the 25 share a structure — a class of
     qualifier, a length ratio, a shape of concept name — then a rule admitting
     the 15 without them is worth eleven points of free coverage, on the only
     rung in this project that costs nothing to run.
   - **Start with the 25.** Print them with their spans, their chosen codes, the
     matched term and which direction the subset ran (span ⊆ term, or term ⊆
     span). The second is the suspicious one: a term whose words are a subset of
     the span means the model quoted MORE than the concept names, which is
     exactly the boundary problem §1 describes.
   - **Then price any candidate rule the way `lexical_mode` was priced** — over
     planted near-misses, reporting coverage AND the share wrongly accepted. A
     rule that recovers coverage while re-admitting near-misses is the setting we
     already rejected, wearing a narrower name.

9. **The FiNER pipeline figure carries one unverified index.**
   `docs/figures/fig7-pipelines.dot` shows `choice 41 →
   EffectiveIncomeTaxRateContinuingOperations`. Slot 0 is verified; index 41 is
   not, because `data/finer` is in no checkout. Recompute it, and replace the
   illustrative excerpt with a real one — FiNER is CC-BY-SA-4.0, so unlike
   CADEC there is no reason for that cell to be illustrative. Both are flagged
   in the `.dot` header.

---

## Standing rules

- **Phase F spent the test split.** Everything here is dev-side and not
  validatable. Phase F's shipped numbers are final as reported.
- **An ablation must hold its base fixed.** The spine manifests nearly shipped a
  5.9-point rung 0 difference charged to the rungs being dropped.
- **Cost is three separate measures** — tokens, latency p95, records routed to a
  person. Never fuse them.
- **New behaviour is an off-by-default arm**, declared in the manifest, with a
  test pinning the one-key diff.
- **A go/no-go probe must use the ARM'S OWN DENOMINATOR.** B2's probe separated
  over 1,144 documents while the arm ran on 38, and on those 38 the sign
  flipped. A probe measured on a population the arm will not see is not a
  stop condition, it is a different experiment.
- **A held-fixed layer and a dead arm both print Δ = 0.000.** Record the
  ABSOLUTE values of anything an ablation pins, and verify the arm is not a
  no-op (menus differ, codes differ).
- **A green local suite is not a green pipeline.** CI is `python:3.12-slim`
  with `requirements.txt` + pytest — no numpy, httpx, torch or `git` binary.
  Two red pipelines in two days came from this. Reproduction command is in
  `CLAUDE.md`.
- **No ten-document arms.**

## Do not redo (measured and rejected)

Prompt rewording · merging overlapping predictions · lexical/hybrid reranking ·
deep=200 reranking · a system message · ten-document arms · BioMistral **as
judge** · BioMistral **as extractor** · the no-digit filter on FiNER · the
context-ordered FiNER menu · **a domain-adapted retriever (SapBERT) for S2** —
it is genuinely the better retriever corpus-wide and lost end to end, three
draws for three; `manifest.sapbertarm.json` is kept, off, if you need to see it
again.

---

## Prompt to start the next session — B4

Session 1 and B2 are spent; this is what the file's own queue points at next.
B1 is the alternative and is deliberately deferred (see the status table).

```
Continue the reliability-ladder project. Scope is B4 ONLY — break the slot-0
position prior on FiNER (docs/PLAN-next-sessions.md, Session 3 §2).

READ FIRST
- docs/PLAN-next-sessions.md   (status header is current; B2 closed 2026-09-01)
- docs/decisions.md            the slot-0 attractor entry (2026-08-30), the
                               context-menu rejection (2026-08-30), and the
                               2026-09-01 B2 entries
- CLAUDE.md                    "TODO — registered, not started", and the
                               session-2026-08-30 FiNER notes
- ladder/menuorder.py          the existing arm mechanism, off everywhere

THE FINDING UNDER ATTACK
FiNER's menu is `sorted(set(tags))`. `AccrualForEnvironmentalLossContingencies`
is alphabetically first, sits at slot 0 in every record, and is predicted 57
times in 292 against 2 in gold — 19.5% of all predictions are the list's first
line. The context arm proved it is POSITION, not meaning: move the tag to
median slot 92 and it is predicted 3 times, all 3 while it happened to be
first. The model takes line one iff it is line one.

This is now the third sighting. CADEC: alphabetising a score-ordered menu cost
10–12pt. FiNER: imposing a mediocre order cost 8.9pt. B2: a better encoder
pushed slot-0 selection 76.6%→79.0% while slot-0 accuracy fell.

DO THIS, IN ORDER
1. NOT A BETTER RANKER. Two candidate mechanisms, both off-by-default arms:
   (a) a slot 0 that is never a valid answer — a sentinel line;
   (b) a per-mention permutation under a fixed seed (the literature's own
       mitigation is option-order randomisation).
   Pick ONE to ship first and say why. Menu recall on FiNER is 1.000 by
   construction, so there is no recall probe to run and no stop condition —
   the arm is purely about position.
2. PRE-REGISTER THE PREDICTION BEFORE RUNNING, in docs/decisions.md: slot-0
   selection rate should FALL, and the attractor tag's prediction count should
   fall from 57 toward gold's 2. Say what result would REFUTE the mechanism.
   A null is only readable if the prediction was written down first.
3. Three draws, paired bootstrap over documents, detection and coding reported
   SEPARATELY. Base first at each draw with a shared cache so the arm's find
   calls are cache hits and detection is held fixed — then VERIFY the arm is
   not a no-op (menus differ, codes differ), because a held-fixed layer and a
   dead arm both print Δ = 0.000.

RULES THAT BIND
- TDD, test first, watch it fail. Mutate your own thresholds and confirm the
  tests catch it — B2's first pass left two mutations alive.
- One-key manifest diff with a test pinning the diff, same pattern as
  manifest.sapbertarm.json and manifest.finer.ctxmenu.json.
- An ablation holds its base fixed.
- A GO/NO-GO PROBE MUST USE THE ARM'S OWN DENOMINATOR. B2's probe separated
  over 1,144 documents while the arm ran on 38, and the sign flipped.
- Cost is three separate measures — tokens, latency p95, records routed to a
  person. Never fuse them. An arm that ran second has cached find calls, so
  its p95 is NOT comparable to the base's.
- Run the CI-shaped suite before pushing (command in CLAUDE.md). Two red
  pipelines in two days came from skipping it.
- Log every decision to docs/decisions.md as you go.
- Phase F spent the test split. Everything here is dev-side and not
  validatable; Phase F's shipped numbers are final and are not re-opened.
- Do not redo: see the list above. The context-ordered FiNER menu and a better
  ranker of any kind are both on it.

SETUP
Fresh worktree needs symlinks from the main checkout at
/Users/wejdanbagais/Documents/repo/reliability-ladder: data/cadec,
data/keywords.csv, data/exclusions.csv, data/SnomedCT_Release_*, ladder/cache.
The venv is that checkout's .venv. Run scripts/preflight.py before any commit.

COST WARNING: out/finer/* was deleted in the 2026-08-31 cleanup, so the base
draws must be re-run. Six runs; the FiNER base is ~78 min each and the arm is
much shorter on a shared cache. Estimate before you start and ASK before
running anything over an hour.

My voice for anything written: direct, short, to the point, no bluff, lead with
the takeaway, actionable, well structured and easy to follow.

Do not start B1, B5, B6 or B7 — they are documented as future work.
```

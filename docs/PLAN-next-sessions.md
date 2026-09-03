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
   the unported judge prompt §5 already reports.
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
   - **What it does to the article if it works.** §5's "the corpus where none of
     it works" survives — the ACCEPT lane is zero for a reason no prompt fixes,
     because a number shares no token with a tag name. But §5's coding numbers
     and the slot-0 attractor would need re-reporting against a pick that can
     actually see the evidence, and §8's "menu order is load-bearing" reads
     differently once the alternative signal is present.

**Done when:** both arms are measured at three draws, the article's recall
numbers are re-derived, and §8's claim is either confirmed or rewritten.
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

## The article was restructured on 2026-09-02 — read this before citing a section number

`docs/article-v3.md` went from ten numbered sections to nine, in a
section-by-section review with the owner. Every number in sections 1-4 was
re-derived from surviving run artifacts rather than requoted, which is what
produced items 4, 8 and 9 below.

| was | is now |
|---|---|
| §1 The two datasets | §1, rewritten: explains each corpus and the pipeline **before** limiting them; adds the exclusion criteria and names CADEC v2 |
| §2 The ground moves… | §2 **Rung 0: what it is, what we tried, what it achieves** — three shapes (S0/S1/S2), seventeen arms, then the funnel |
| §3 The significance test… | §3 **How much of this is real?** — the bootstrap, the `set()` bug, then the stability investigation as the payoff rather than the prerequisite |
| §4 The free check | §4 **Rung 1**, restructured lane by lane: each of REJECT / ACCEPT / BAND answers *what does it claim, how well does it deliver, how much lands here* |
| **§5 The one thing that worked** | **MERGED into §4** as its closing subsection. It had shrunk to 296 words, half of them duplicated by §4, and it contained a line ("you cannot make the model repeatable") that §3 now disproves |
| §6 → §9 | renumbered **§5 → §8** |

Four figures were added and are committed with their `.dot` sources:
`fig7-pipelines` (both corpora side by side), `fig9-funnel` (every gold mention
and prediction through rung 0's stages), `fig10-rung1` (what rung 1 receives and
how it sorts it), `fig11-lexmode` (the same records under both `lexical_mode`
settings).

**Sections 5 to 9 have not been reviewed yet.** The walkthrough stopped after
§4. Anything below §4 is still as it was written on 2026-08-30, including the
stamina example in §6 that item 7 says is stale.

---

## REVIEW STATUS — the line, as of 2026-09-03

The section-by-section review of `docs/article-v3.md` reached §7 and stopped.
Everything above the line was read against the code and the artifacts, corrected,
and committed; everything below has NOT been reviewed at all and its numbers are
unverified.

| | section | words | status |
|---|---|---|---|
| ✅ | Five key takeaways | 213 | reviewed 2026-09-03; **two claims stay provisional until item 14** |
| | What an AI reliability ladder is for | 179 | **NOT REVIEWED** |
| | The task, and the result | 443 | **NOT REVIEWED** |
| ✅ | 1. The two datasets | 1,523 | reviewed |
| ✅ | 2. Rung 0 | 2,663 | reviewed |
| ✅ | 3. How much of this is real? | 2,150 | reviewed |
| ✅ | 4. Rung 1 on CADEC | 2,590 | reviewed |
| ✅ | 5. Rung 1 on FiNER | 1,776 | reviewed |
| ✅ | 6. The five resolvers | 2,393 | reviewed |
| ✅ | 7. What each layer was for | 945 | reviewed |
| | **8. What no single-layer test could see** | 199 | **← THE LINE. Resume here.** |
| | 9. Did we try making the model better first? | 539 | **NOT REVIEWED** (swept for cuts only) |
| | 10. The division of labour | 222 | **NOT REVIEWED** (swept for cuts only) |
| | How we found these | 111 | **NOT REVIEWED** |
| | Where this sits in the literature | 481 | **NOT REVIEWED** — carries the CONORM comparison, the highest-risk unverified claim |
| | What we would tell you | 235 | **NOT REVIEWED** |
| | What we could not settle | 770 | **NOT REVIEWED** (swept for cuts only) |
| | Limitations | 185 | **NOT REVIEWED** |

"Swept for cuts only" means dead or duplicated material was removed on
2026-09-03, but no claim in those sections was checked against the code.

**THE TAKEAWAYS WERE REWRITTEN 2026-09-03** and the three stale claims below are
fixed. Two of them remain PROVISIONAL in the article's own words until item 14
lands, and must be re-read after the judge is re-measured:

- **Takeaway 2** — "Recalling an identifier, building the candidate list,
  ordering it, **checking, judging**, and deciding to abstain each measured
  better when taken away from the model." Checking and judging did NOT measure
  better. Self-correction never fired, so it was never tested, and the judge's
  separation was measured before we found it had never been shown what a code
  means. §10's table now says `unproven` and `not yet known` for those two rows;
  the takeaway still claims both.
- **Takeaway 3** — "A free string comparison beat the LLM judge by 3×." The free
  check's side is well measured across five model families. **The judge's side
  was measured blind.** So this compares a good measurement against a withdrawn
  one, and must say so until item 14 lands.
- **Takeaway 5** — "Deleting the three paid layers changed one answer out of 43
  and saved 518,590 tokens." Both halves are true, but the article no longer
  describes that ablation, and "saved 518,590 tokens" double-counts against §7's
  own cost column.

---

## THE ORDER OF WORK — read this before picking an item

The goal is one article whose every number comes from a run that exists. That
forces a strict order, because a fix that changes a number invalidates any run
taken before it.

**PHASE 1 — settle the code and the config. DONE 2026-09-03 (commit
`7457a79`; decisions entry same date).** Each one changed what a run records
or means, so they landed before the first draw.

| item | what | state |
|---|---|---|
| **12** | per-record per-rung trace **+ the error budget** | **DONE** — `ladder/trace.py`: `<run>.state.jsonl`, `<run>.r<N>.records.jsonl`, `<run>.r<N>.calls.jsonl` (full prompt + raw reply), `<run>.aggregates.json`; budget in `ladder/analysis.py` |
| **14** | the judge sees the menu and the pick | **DONE, OFF by default** — `rungs.4.menu off\|ranked\|shuffled`, four pinned arm manifests; the judge also gets the pick guidance (smoke run found it failing correct picks on a rule it never saw) |
| **16** | decide `lexical_mode` on yield, three draws | **ARM BUILT** (`manifest.lexarm.json`); the decision is Phase 2's, on yield |
| **17(d)** | retire or defend `tau` | **RETIRED** — refused by rung 5, gone from every manifest, sweep deleted, `tests/test_tau_retired.py` |
| 17(c) | unreviewable records | **DONE** — `R_UNREVIEWABLE`, counted in both modes |

**PHASE 2 — the consolidated re-run (item 0). ONE base run produces every
descriptive dev-side number in the article.** STARTED 2026-09-03 02:47 from
`7457a79`: `scripts/consolidated_rerun.sh` — three cold draws per corpus
(`LADDER_LLM_CACHE=.llm_cache.rerun-<corpus>-d<N>`), full ladder, dev only,
base first then the arms (`judgemenu`, `judgeshuffle`, CADEC `lexarm`) on the
same cache, plus a zero-model `spine` replay (rungs 5-6 over the rung 1
snapshot). Run ids `rerun-{cadec,finer}-d{0,1,2}[-<arm>]`; report by
`scripts/rerun_analysis.py`. Results in `docs/decisions.md` when the draws
finish.

**PHASE 3 — rewrite the article's numbers against that run**, clear the
`[PENDING]` markers, and only then review the takeaways. **CADEC DONE
2026-09-03** (decisions entry "THE CONSOLIDATED RE-RUN, CADEC"; article
commits `d430c63`, `fb4e597`): every CADEC dev-side number is now
`rerun-cadec-d0/d1/d2`, sections 2-4, 6, 7, 11, 12 and the takeaways
rewritten, figs 1 and 4 refreshed, figs 6/8/11/12/13 keep their runs named in
the caption. FiNER pending its three draws.

**ANY TIME — no run needed, no ordering constraint:** items 2, 4, 7, 8, 11, 13,
15, 17(c). (Item 18 is DONE — 2026-09-03.) **Also DONE 2026-09-03: 8
(answered on the re-run: 26-27 of the 38-39 admitted records wrap a term in a
qualifier; the 12 fragments are mostly wrong), 11 (rung 3's changes: 22/27/26
of 25/28/27 land in BAND, mostly on invented spans), 13 (index 47, real
excerpt), 15 (stated), 17(c). Items 12, 14, 16, 17(d) were Phase 1.**

**AFTER THE ARTICLE SHIPS:** items 1, 3, 5, 6, 9, 10, 17(a), 17(b). These extend
the study rather than unblock it.

---

## NUMBERS IN THE ARTICLE → WHERE THEY COME FROM

Checked 2026-09-03. **The article's numbers come from at least seven runs, four
of which no longer exist on disk.** This table is the checklist Phase 2 must
satisfy; a number with no row here is a number nobody can reproduce.

| run | what the article uses it for | on disk? | covered by item 0? |
|---|---|---|---|
| `phaseF-test-1` | the headline test result, §2, §3 | **no** | **NO — test is spent and cannot be re-run** |
| `audit-full-dev-1` (248 rec) | §7's role table, all token costs, 196 routed | **no** | yes |
| `arm-sapbase-d0/d1/d2` (222/232) | §3 draws, §4 lanes, Fig 6, Fig 8, Fig 14 | **yes** | yes |
| `phaseD-r3-2` (245) | §6's rung 3 figure | **no** | yes |
| the five-model sweep | §4's ACCEPT-lane invariance table | **no** | item 2 (data exists) / item 9 |
| FiNER `finer-full-2`, `arm-finer*` | §5 throughout, Fig 9, Fig 10, Fig 13 | partial | item 3 |
| the judge-arm draws | §6's policy table, bottom row | **no** | item 14 supersedes |

**The consequence to state plainly: `phaseF-test-1` is the one run that cannot be
regenerated.** The held-out split was spent once by design. So the article's
headline numbers stay as reported, and Phase 2 can only make the DEVELOPMENT-side
numbers consistent around them. Any Phase 1 fix that would change the test result
must be described as untested on held-out data.

---

## Required before the article ships

Everything here either blocks a claim the draft makes or removes a caveat it
carries. Items 1, 3, 5, 6, 9, 10, 14, 16 and 17(a,b) need runs; 2, 4, 7, 8, 11, 15 and 17(c,d) do not. Item 3 is the only one
that goes beyond unblocking — it makes the model findings two-corpus instead of
one, and the article is shippable without it, with its CADEC-only caveats
intact.

0. **NOTE (2026-09-03): the article's front-matter `[PENDING]` box for this item
   was folded into "The task, and the result" as prose and into §12's Limitations
   list. The requirement is unchanged; only its two duplicate statements in the
   article were merged into one.**

0b. **THE CONSOLIDATED RE-RUN — one config, one metric, one cache state, one
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
   - **ONE BASE RUN MUST PRODUCE EVERY DESCRIPTIVE DEV-SIDE NUMBER.** This is the
     requirement, not a preference. Today the CADEC dev story is told from at
     least four runs with four different record counts — `audit-full-dev-1` (248
     records: the per-layer table, 0.371 -> 0.367, every token cost),
     `phaseD-r3-2` (245: rung 3's tree and its +5), `arm-sapbase-d0` (222: rung
     1's lanes, the funnel, the agreement figures) and the five-model sweep (232:
     the model table). All four are "40 development documents"; they differ
     because the model is nondeterministic, which is the finding of section 3.
     **The result is that adjacent numbers in one section come from different
     draws and quietly disagree** — rung 3 is +5 on one and -0.004 on another,
     and the article had both, unlabelled, a paragraph apart.
   - **What cannot come from the base run, and must be named as an arm:** the
     five-model table (five models), the noise floor (three draws of one config),
     the ablation (two stacks), the judge arm (paired on/off). Each keeps its own
     run id in the caption. The Phase F test box is frozen and is never re-run.
   - **Every figure and table caption carries its run id.** A number whose
     provenance is not on the page is a number the next reader cannot check, and
     this review found four that disagreed because nobody could see they came
     from different places.
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
   - **(b) FiNER's over-extraction, decomposed.** §5 presents FiNER as a recall
     problem. The record says the model proposes far MORE spans than gold holds,
     so the miss is *which* numbers rather than how many — a different diagnosis
     pointing at a different fix. That was measured on a single earlier run whose
     configuration does not match the one §5 reports. Recompute it on the run
     §5 actually cites, then either rewrite §5's framing or record that the
     earlier finding did not reproduce.

6. **~~A rung 1 that works on FiNER.~~ ATTEMPTED 2026-09-02 AND REJECTED — the
   type check is built, measured, and off.** `ladder/rungs/r7.py`, 224 tests, arm
   not enabled. Kept here because the *method* failure is the reusable part and
   the article now carries it.
   - **On gold it looked excellent**: speaks to 87.7% of mentions where the
     lexical check speaks to 0%, false-rejection rate 1.22%. **On model output it
     rejects a correct answer once in three — 35.71%, twenty-nine times worse.**
     Pooled over three draws, 42 rejections with gold to check against: 27 right,
     15 wrong.
   - **Why gold lied, and this is the transferable part.** The rules read the
     characters either side of the span. On gold the span is where the annotator
     put it, so that window is always the right one. The model's spans drift, the
     rules read the wrong window, and reject confidently on a misreading. **Tuned
     on gold, validated on gold: the measurement set was the tuning set.**
   - **What is still open.** FiNER has no working rung 1 and the obvious route is
     closed. The remaining candidate is the context lexical match — the tag's own
     de-camel-cased words against the sentence rather than the span. **It must be
     validated on model output from the first measurement**, which no check in
     this project has been, and which is the whole lesson above.
   - Second-order, and it belongs in section 6: giving rung 2 a real trigger set
     for the first time — 44 rejections per run against CADEC's one in 248 —
     showed it **rescued nothing over 918 firings** (789 unchanged, 129 declined,
     0 rescued). The CADEC null used to be dismissable as too small a trigger set.
     It is not any more.

7. **~~§6's stamina example is framed as a coding fix and cannot be one.~~ CLOSED
   2026-09-02 — the example was removed.** It claimed rung 3 voted `"stamina"`
   from |Stamina| to |Lack of stamina|. Retrieval is deterministic and was
   replayed: from the span `"stamina"`, `248277009` is absent from the menu at
   k=50, so the vote could not have happened that way. The record came from the
   pre-`rung0_split` configuration, which could only quote the contiguous
   fragment of a discontinuous gold span; the shipped extractor now emits
   `"loss of stamina"` and codes it correctly. **Replaced with a real rung 3
   overwrite from `phaseD-r3-1`** — |Pain| overwritten to |Analgesia|, the
   absence of pain, on a 1-0 "majority" from the only sample that re-found the
   mention — which carries both defects the article needs: one vote counted as a
   majority, and a rung 1 verdict travelling with a code rung 3 had replaced.

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

9. **THE FIVE-MODEL TABLE (now §4's closing subsection) CANNOT BE REPRODUCED FROM ANYTHING THAT SURVIVES, AND
   MY BEST ATTEMPT BRACKETS IT WITHOUT MATCHING.** REQUIRES A RUN. This is the
   article's headline positive claim — the ACCEPT lane at ~85% across five model
   families — and it is the least checkable number in the piece.
   - **What was checked (2026-09-02).** The article's table matches
     `docs/decisions.md` (2026-08-30, five-model table) figure for figure. But
     the five-model runs were in worktrees deleted 2026-08-31, and only
     `gpt-oss` has a surviving same-config run (`arm-sapbase-d{0,1,2}`, records
     verified clean: zone NEW, no nulls, no r3/r4/r5 keys, rung 1 config
     identical key-for-key).
   - **Recomputing gpt-oss's lanes on those records, using the scorer's own
     `_pair`:** ACCEPT **89.1%**, BAND **51.1%** pooled over three draws, against
     the recorded **84.6 / 35.9**. Restricting instead to every record in the
     lane rather than the overlap-matched ones gives ACCEPT **78.0**, BAND
     **35.2** — so BAND matches the record under one denominator and ACCEPT
     under neither. Two recorded run sets agree with each other (the five-model
     table, and the 2026-08-28 three-draw re-measure at 83.7-87.2 / 35.9-36.8),
     so the outlier is the run I can reach, not the record.
   - **The qualitative claim is not in doubt.** ACCEPT sits far above BAND under
     every denominator tried — 89 vs 51, 78 vs 35, 85 vs 29 (the exact-span
     count in §4). What cannot currently be defended to the decimal is the
     specific pair of numbers the article prints, and the ~85% figure it is
     named after.
   - **What to do.** Re-run the five-model sweep on the consolidated footing from
     item 0, and **record the lane denominator explicitly** — overlap-matched or
     all-records — because the two differ by 16 points on BAND and the article
     currently states neither.
   - Until then, that subsection should carry the denominator the record names ("coding
     accuracy on overlap-matched spans") rather than leaving it implicit.

10. **THE SHORT-CIRCUIT WE NEVER BUILT: resolve the span by lookup and skip the
    pick call, where the vocabulary answers uniquely.** REQUIRES RUNS. Probed on
    one draw 2026-09-02 while reviewing §4; the article reports it under *What
    we could not settle* and nowhere else, because one draw is below this
    project's own bar.
    - **The probe.** Over `arm-sapbase-d0` (dev, 232 records): for **54 (23%)**
      the span text normalises to exactly one concept in `data/keywords.csv`.
      Taking that concept with no model call is correct **44/54 = 81.5%**;
      the model's pick on the same records is **41/54 = 75.9%**. Whether a span
      resolves uniquely is knowable **before** any model call, so this is a
      routable short-circuit, not a post-hoc filter.
    - **The counterpart, and it cuts the other way.** A dictionary DETECTOR —
      longest-match scan for text that is a concept name — gets **16.8% exact
      recall at 27.1% precision** against the model's 55.8% / 54.3%. Overlap
      45.1% / 72.9%, i.e. it lands on the right mentions with the wrong
      boundaries. **Detection is where the model earns its place**, and this is
      the first non-model baseline for §8's claim that it does.
    - **What to measure.** Three draws, both corpora. Report (a) the share of
      records the short-circuit claims, (b) accuracy on them against the pick,
      (c) tokens and calls saved, (d) **what it does to the rung 1 lanes** — a
      record resolved by lookup will land in ACCEPT by construction, so the
      ACCEPT lane's accuracy is no longer independent evidence for those
      records, and §4's headline would need restating.
    - **The caveat that decides how far this generalises.** `keywords.csv`
      excludes retired concepts, which is why `"knee pain"` resolves uniquely
      there while SNOMED holds two concepts with that name. Uniqueness is a
      property of our index, not of the vocabulary. Measure it against the full
      release too, and report both.

11. **RUNG 3'S CHANGES WERE NEVER CROSS-TABBED AGAINST RUNG 1'S LANES.** REQUIRES
    A RUN — no surviving artifact carries rung 3 output, checked 2026-09-02.
    Rung 3 re-extracts every document and never reads rung 1's verdict, so the
    obvious question has never been asked: **do its changes land in BAND, where
    the free check had no opinion and a vote might add something — or in ACCEPT,
    where it overwrites an answer already backed by evidence?**
    - What is recorded (`phaseD-r3-2`): 245 records, 38 never re-found, 188 with
      >=2 votes, unanimity 56.4%, 31 changes, +5 net correct, 0 correct
      destroyed. One verified-ACCEPT record was changed, on a genuine 2-1
      majority. None of it is broken down by lane.
    - **Why it matters beyond curiosity.** If the changes cluster in BAND, rung 3
      is under-targeted rather than useless and could be run on the BAND residue
      alone at a fraction of 425,355 tokens. If they cluster in ACCEPT, it is
      spending its budget overwriting the one lane that was already 85% correct.
      The article can currently say neither.
    - **What is already derivable, and it narrows the question:** a record with
      no code lands in BAND by construction (`r1.zone`), so all four
      "abstained →" transitions were BAND records — three to correct, one to
      incorrect. The changes we can place are in the right lane. The other 27
      are the ones that decide it.
    - **THE SPECIFICATION, and it is wider than "per lane": break every node of
      the rung 3 tree down by what rung 0 had already said about those records.**
      For the 38 it never re-found, were they records rung 0 had right, or wrong,
      or had never coded? Same for the 188 it voted on, the 106 unanimous, the 49
      split. Today only the 31 changes carry that, and only 25 of those. Without
      it the figure cannot answer the question it exists for — **is voting fixing
      what was broken, or churning what was already fine?**
    - Record per change: the record's rung 1 verdict, the vote spread, and the
      outcome transition. Same run should also fill the section 6 per-layer
      table's rung 3 row with its run id attached.
    - **DO THE SAME ON FiNER, where even less was recorded.** No vote spread, no
      transitions, no change count — only that answered accuracy moved 0.1396 ->
      0.1567, **net positive, the opposite sign to CADEC's 0.371 -> 0.367**, at
      the same 2.7x cost. One draw each on a sampling rung, so the flip is a
      difference to note and not to claim — and with no per-vote detail on either
      side there is currently no way to explain it. The article says so and
      carries no FiNER counterpart to the CADEC figure.

12. **THE ROOT CAUSE OF ITEMS 9, 11 AND HALF OF 3: NOTHING RECORDS A RECORD'S
    STATE AT EACH RUNG.** This is the infrastructure item, and doing it first
    makes several others cheap instead of impossible.
    - **What exists.** `out/*.ledger.jsonl` has one row per record per rung with
      `verdict`, `zone`, `outcome`, `reason` and the cost fields. That is real
      and it is why rung 1's lanes can be recovered at all.
    - **What it cannot answer, and why.** Rung 0 and rung 3 log **one row per
      DOCUMENT**, not per record — rung 3's samples are summed into a document
      cost row by design, so a record's before-and-after code is nowhere.
      And **correctness is not in the ledger at all**: it is computed afterwards
      by `score_run` against gold, and never joined back. So no row anywhere says
      *this record, at this rung, held this code, and it was right.*
    - **The consequence, hit four times in this review.** Rung 3's changes cannot
      be cross-tabbed against rung 1's lanes. The 38 records rung 3 never
      re-found cannot be checked against whether rung 0 had them right. The
      ACCEPT-lane figures cannot be reproduced under a stated denominator. FiNER
      has no agreement figures. Every one of those needs a re-run, and every one
      would have been a join.
    - **What to build:** a per-record, per-rung state table written at run time —
      `record_id x rung -> (code, span, verdict, changed_this_rung, outcome
      against gold)`. One row per record per rung, correctness included, written
      beside the records file. It is a few columns and it retires four open
      items.
    - **The standing rule it should carry:** a rung that cannot say what it did
      to an individual record cannot be credited or blamed for the aggregate. The
      article already argues this about dead fields in section 7; this is the
      same defect one level up, in the measurement rather than the code.

13. **The FiNER pipeline figure carries one unverified index.**
   `docs/figures/fig7-pipelines.dot` shows `choice 41 →
   EffectiveIncomeTaxRateContinuingOperations`. Slot 0 is verified; index 41 is
   not, because `data/finer` is in no checkout. Recompute it, and replace the
   illustrative excerpt with a real one — FiNER is CC-BY-SA-4.0, so unlike
   CADEC there is no reason for that cell to be illustrative. Both are flagged
   in the `.dot` header.

14. **THE JUDGE WAS NEVER SHOWN WHAT IT WAS JUDGING. Rung 4 asks an
    unanswerable question, and every rung 4 number in the article measures a
    blindfolded judge.** Found 2026-09-02 while reviewing §6. REQUIRES RUNS.
    - **The defect.** `r4.judge` formats the prompt with
      `source, text, start, end, sct` and nothing else
      ([r4.py:160](ladder/rungs/r4.py:160)); `sct_label` appears **zero times**
      in the file. So the judge is handed `code: 1003722009` — a bare
      nine-digit number with no name — and asked "is this the right SNOMED CT
      concept?". It cannot answer that, and the pass/fail split it returns is
      a measurement of a question that could not be answered.
    - **THIS OVERTURNS THE ARTICLE'S EXPLANATION.** §5 and §6 both attribute
      the CADEC/FiNER judge difference to context size — 139 tags fit, 129,675
      SNOMED concepts do not. The real cause is **identifier readability**: on
      FiNER `rec.sct` *is* the tag name (`DebtInstrumentFaceAmount`), on CADEC
      it is a number. The judge engages with codes on FiNER because that
      corpus's identifiers happen to be words. Nothing about context windows.
      Correct both sections.
    - **The redesign, and it is the standard LLM-as-judge setup we never
      built.** Give the judge what the extractor was given and what it
      answered, for both of the extractor's two decisions:
      post → span (call 1), menu → pick (call 2). The data is already on
      disk: `rec.checks["candidates"]` carries `{i, code, fsn/label,
      from_rank}` ([r0.py:1260](ladder/rungs/r0.py:1260)) and `_menu` renders
      it. This turns the code question from **recall** ("is 1003722009 right?")
      into **comparison** ("was line 7 the best of these 20?"), which is
      readable, and which is the same task the extractor faced.
    - **It buys a verdict the system cannot currently express:** *the right
      answer was not in the menu*. A code failure today is ambiguous between a
      bad pick and a bad menu, and those need opposite fixes — re-asking helps
      the first, only retrieval helps the second. Same detection/coding
      decomposition §3 uses, one level down.
    - **FIX FiNER TOO. It needs it more.** Its judge fails **299 of 351**
      records; a judge that fails 85% of everything carries about as little
      information as one that passes everything. Its identifier is readable but
      its menu is just as absent. And the slot-0 attractor is a FiNER finding
      (19.5% of predictions were menu line 0), so a judge shown the menu either
      catches it or inherits it — both results are worth having.
    - **CARRY THE `[denied]` MARKER, AND NOTE IT IS A LIVE BUG TODAY.** Rung 0's
      pick prompt says a denied reaction *"is still coded"*
      ([r0.py:479](ladder/rungs/r0.py:479)), added in Phase B because without it
      the pick declined every denied mention it was given. The judge has no such
      instruction, so it is currently failing spans like "no gastric problems"
      that CADEC marks correct. Same trap, one rung up. CADEC only — FiNER has
      no negation.
    - **PERMUTE THE MENU UNDER A FIXED SEED.** The slot-0 attractor has been
      found three times (FiNER context menu, SapBERT, the reranker). A judge
      shown a ranked list may simply ratify line 0. This is the same mechanism
      the registered "break the position prior" experiment wants, so run them
      together.
    - **RISKS, both real.** (a) It couples rung 4 to S2 — S0 and S1 have no
      menu. S2 is the frozen shipped config so this is tolerable, but rung 4
      stops being step-agnostic and the article must say so. (b) **It may make
      the judge worse.** Phase C's lesson was *prompt form is load-bearing for
      small judges* — granite lost its pass/fail separation when a duplicated
      post was removed. A 2B model given a longer, richer prompt is not
      reliably a better judge, and the honest outcome may be "this judge is too
      small," which is the parked remote-model question. Treat as an
      experiment, not a fix. Three draws, both corpora, paired against the
      current prompt.
    - **INVALIDATES ON LANDING:** every rung 4 figure in the draft — the 1.65x
      and 1.23x separations, 21.0%/12.7%, the pass/fail counts (146/95/7 CADEC,
      48/299/4 FiNER), Figure 13, and §7's dead-verdict finding. All are
      measurements of the blindfolded judge. They are not wrong as reported;
      they answer a different question than the article says they do.
    - Cost: roughly +160 tokens of menu per record on top of 92,687.
    - **AND EXTEND ITEM 12 WITH THE ERROR BUDGET.** The join must produce the
      exact detection / retrieval / picking split. The article states the shape
      (picking is the largest, retrieval the smallest) but the numbers
      55 / ~13 / ~58 mix denominators — 87.0% menu recall is over all 6,595 gold
      mentions, 0.291 coding accuracy over one run's matched spans — so they are
      an ESTIMATE and must never be printed as measured. Registered 2026-09-02
      after the owner corrected a recommendation built on them.

15. **NO RUNG IN THIS LADDER CAN ADD A MENTION — state it as a limitation.**
    NO RUN NEEDED; the proof is already in the artifacts. Raised 2026-09-02.
    Every rung above 0 operates only on records rung 0 already proposed: rung 1
    rejects, rung 2 fixes codes, rung 3 re-scores existing spans, rung 4 judges
    per record, rung 5 withholds, rung 6's desk is **span-keyed** and picks
    codes. The demonstration is Phase E's oracle: a perfect reviewer moved
    coding accuracy 0.291 -> 0.990 **with detection unchanged**. Flawless human
    review left recall exactly where rung 0 put it.
    - So the ladder's ceiling is rung 0's recall, structurally, and every
      technique in it is a precision instrument. The draft does not say this
      outright and it is one of the sharper findings available.
    - **Do NOT solve it by having rung 4 look for missed mentions.** Wrong unit
      (rung 4 is per-record, "what was missed" is per-document) and wrong act
      (a judge that names an unproposed mention is extracting, not judging —
      the same collapse the rung 0/rung 2 retry rule already forbids). Register
      "a rung that can propose a missed mention" as an open question instead,
      and bound it with an oracle ceiling first, exactly as rung 6 was bounded
      before it was built.

16. **`lexical_mode: exact` MAY BE THE WRONG SHIPPED DEFAULT, and the article's
    own numbers say so on the article's own rule.** REQUIRES RUNS. Raised
    2026-09-02 while reframing rung 5 as a policy dial.
    - On `arm-sapbase-d0` (222 scored): `exact` ships 48 records at 85.4%
      (41 correct, **yield 0.185**); `contained` ships 88 at 63.6% (56 correct,
      **yield 0.252**). The looser setting was rejected in §4 for costing 22
      points of LANE ACCURACY — a precision measure — and on yield it is 36%
      better.
    - This is the third instance of one pattern: the article states "abstaining
      always raises precision; yield cannot be fooled", applies it correctly to
      the judge arm, and not to rung 5's headline (**now fixed**) or to this
      config choice (**open**).
    - **ONE DRAW.** Changing a shipped default on one draw is exactly the error
      the SapBERT probe made — its go/no-go probe separated over 1,144 documents
      and the arm ran on 38. Three paired draws before anything moves, and the
      probe must run on the denominator the arm is scored on.
    - Composes with item 8, which asks *why* `contained` loses lane accuracy.
      Item 8 is the mechanism; this is the decision.

17. **RUNGS 5 AND 6 AS BUILT: four code changes the §6 review exposed.** Raised
    2026-09-02. (a) and (b) need runs; (c) and (d) do not.
    - **(a) THE DESK CANNOT CORRECT A SPAN, AND THAT IS THE CEILING.** `r6` takes
      `code | concept_less | uphold | skip` — every decision picks a code for a
      span the system already found. So the oracle stops at 0.444 (`detection
      0.449 x coding 0.990`) and the residual gap is entirely annotation. Add a
      span-correction decision and the desk can reach the other half. This is a
      capability gap, not a bug: the number we publish as a ceiling is a fact
      about our tool, and the article now says so.
    - **(b) MEASURE THE OTHER DIVISION OF LABOUR.** Run rung 0's pick step over
      GOLD SPANS and score the codes alone. That isolates coding, turns the
      estimated ~0.291 into a measurement, and settles the owner's question —
      *should the human fix the annotation and let the model code?* — with
      evidence instead of arithmetic. Cheap: no detection in the loop, no desk.
      Completes the 2x2 (0.131 measured / 0.444 measured / ~0.291 estimated /
      1.0 trivial).
    - **(c) NINE RECORDS ARE UNREVIEWABLE BY CONSTRUCTION.** The schema-invalid
      residue carries unlocated `(-1,-1)` spans; nine records collapse onto two
      span keys and a span-keyed desk refuses to guess which resolution belongs
      to which record, so they stay ESCALATE at zero minutes. Sixteen on test.
      Needs a disambiguating key, or an explicit "unreviewable" disposition that
      is counted rather than silently escalated.
    - **(d) `tau` IS A DIAL THAT CANNOT TURN — retire it or defend it in
      writing.** It is READ, unlike the five settings the 2026-08-31 audit
      found, but it can never usefully fire: rung 0 reports >= 0.95 confidence on
      every record (1.0 on 77%) while being right ~40% of the time, so no
      threshold separates anything. Leaving a live key that is structurally
      inert is the same defect one layer along from "declared and never read".
      Either delete it with a test that keeps it gone (the `otel.py` precedent),
      or keep it and put the distribution in the manifest note as the reason.

18. **~~RE-VERIFY THE CONORM COMPARISON AGAINST THE PAPER ITSELF.~~ DONE 2026-09-03 — three claims confirmed, one FABRICATED, one argument weakened. See docs/decisions.md. Original text below. It is the
    article's only external benchmark, its ceiling argument rests on it, and it
    could not be re-checked from public sources on 2026-09-03.** NO RUN NEEDED,
    but it needs the PDF.
    - **The DOI is correct** — `10.1101/2023.09.26.23296150` resolves to Yazdani,
      Rouhizadeh, Bornet and Teodoro, *CONORM: Context-Aware Entity Normalization
      for Adverse Drug Event Detection*, medRxiv 2023. Citation in §9 is now a
      proper link with title and authors.
    - **What could NOT be confirmed.** §9's table splits CONORM's CADEC results
      into `detection only` (0.704 exact / 0.891 lenient) and `end-to-end`
      (<= 0.704 / 0.7245). Public summaries report **70.40% exact and 89.10%
      lenient on CADEC** without clearly saying whether those are NER-only or
      end-to-end. medRxiv's full text returns 403 to automated fetch and the
      `ds4dh/CONORM` repository publishes no results.
    - **Why it matters.** §9 argues "the ceiling claim survives the check that was
      meant to break it": that a fully supervised tagger reaching **0.704
      span-exact ON DETECTION ALONE** is the number CADEC's ~67% boundary
      determinism predicts. **If 0.704 is instead their end-to-end figure, that
      argument breaks** — detection-only would be higher, and the coincidence
      with the predicted ceiling weakens or disappears.
    - The article states the comparison was "verified line by line against their
      evaluation code", so this was checked once. The requirement is to record
      WHERE — table number, row and column of the paper — so the next reader does
      not have to re-derive it from search summaries.
    - Do this before the article ships. It is cheap (read one PDF) and it is the
      claim most exposed to an outside reviewer.

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

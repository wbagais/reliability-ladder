# Plan — next sessions

**Updated 2026-08-31. Session 1 is DONE and `docs/article-v3.md` now has ONE
`[PENDING]` left — B2.** Read this header before working from anything below it.

| item | state |
|---|---|
| **A1** · CONORM comparison | **DONE 2026-08-31.** The 0.70 ceiling claim is *corroborated*, not refuted — their span-exact 0.704 is **detection only**, and their 0.7245 end-to-end is the lenient figure. Our own comparison was the defective part and is rewritten. |
| **Session 1 §2** · FiNER three draws | **DONE 2026-08-31**, already written into §2: the run-to-run spread is one refused document, d1 and d2 byte-identical. |
| **Session 1 §4** · `preflight_rungs` | **DONE 2026-08-31.** Validated against the four dead rungs, 11 tests, mutation-checked. Scope and caveats in `docs/decisions.md`. |
| **Session 1 §5** · file-role headers | **DONE 2026-08-31.** |
| **B3** · BioMistral as extractor | **DONE 2026-08-31, negative.** Session 3 §1 below is spent; the article bullet is closed. |
| **B1** · discontinuous spans | **DEFERRED, deliberately.** Discharged in the article as a stated cap rather than a fix — no conclusion rests on the recall number, and the best supervised system appears to share the cap. Still worth building; not a blocker. |
| **B2** · domain-adapted retriever | **OPEN — the only blocker.** Do the offline menu-recall@20 probe first and stop on a null. |
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

2. **B2 · A domain-adapted retriever.** Swap `granite-embedding:30m` for a
   SapBERT-class encoder in the S2 shortlist. Off-by-default arm, one-key diff
   manifest, test pinning the diff — same pattern as `manifest.judgearm.json`.
   - Measure **menu recall@20 first, offline.** If gold does not reach the menu
     more often, stop: there is nothing for the pick to convert and no run is
     needed.
   - This directly tests *"retrieval is a ceiling"*, which §9 leans on.

**Done when:** both arms are measured at three draws, the article's recall
numbers are re-derived, and §9's claim is either confirmed or rewritten.

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

## Standing rules

- **Phase F spent the test split.** Everything here is dev-side and not
  validatable. Phase F's shipped numbers are final as reported.
- **An ablation must hold its base fixed.** The spine manifests nearly shipped a
  5.9-point rung 0 difference charged to the rungs being dropped.
- **Cost is three separate measures** — tokens, latency p95, records routed to a
  person. Never fuse them.
- **New behaviour is an off-by-default arm**, declared in the manifest, with a
  test pinning the one-key diff.
- **No ten-document arms.**

## Do not redo (measured and rejected)

Prompt rewording · merging overlapping predictions · lexical/hybrid reranking ·
deep=200 reranking · a system message · ten-document arms · BioMistral **as
judge** · the no-digit filter on FiNER · the context-ordered FiNER menu.

---

## Prompt to start Session 1

Paste this once the current run has finished.

```
Continue the reliability-ladder project, Session 1 of docs/PLAN-next-sessions.md.

READ FIRST
- docs/PLAN-next-sessions.md  (this session's scope is Session 1 only)
- docs/article-v3.md          (the draft; six [PENDING] markers are the work)
- docs/decisions.md, entries dated 2026-08-30
- CLAUDE.md "Current state" and "TODO — registered, not started"

The four FiNER draws launched on 2026-08-30 should be finished. They are in
out/harness/finerdraws.log and out/finer/arm-finer{base,ctx}-d{0,1,2}.json,
in the phase-e-rung-6-human-loop-64ce8e worktree.

Do Session 1 and nothing else:
1. A1 first — verify the CONORM comparison and DECIDE on our 0.70 ceiling
   claim. This can invalidate a published claim, so do it before any writing.
2. Write up the three FiNER draws: the paired context-arm result, FiNER's
   first run-to-run spread, and the refusal's draw-dependence.
3. Apply both to docs/article-v3.md and clear the [PENDING] markers they close.
4. Add the one-line file-role headers to docs/article.md and docs/article-v2.md.

Rules that bind: TDD if any code changes. Log every decision to
docs/decisions.md as you go. Three draws plus the paired bootstrap, never one.
Phase F spent the test split — everything is dev-side and not validatable.

My voice for anything written: direct, short, to the point, no bluff, lead with
the takeaway, actionable, well structured and easy to follow.

Do not start Sessions 2-4. Ask before running anything that takes over an hour.
```

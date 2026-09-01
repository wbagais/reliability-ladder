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

**Done when:** both arms are measured at three draws, the article's recall
numbers are re-derived, and §9's claim is either confirmed or rewritten.
**B2 is done; B1 is what remains of this session.**

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

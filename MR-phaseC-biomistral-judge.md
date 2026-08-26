# Phase C — models: BioMistral judge measured, rejected; two rung-4 call-path fixes kept

**Negative result, deliberately merged.** BioMistral-7B was imported,
registered, swapped in as the rung-4 judge, and measured on a 240-record
re-judge of `full-ladder-dev-1` — and it fails as a judge on three
independent grounds, so `manifest.model.judge` reverts to granite4:micro-h.
The 2B-judging-20B inversion stands, now as a measured lesser evil rather
than a shortage. Three decisions entries dated 2026-08-25 in
`docs/decisions.md` carry the full story; runs are
`out/rejudge-biomistral-3.*` (final), `out/rejudge-granite-dedup.*`
(same-prompt baseline), plus two diagnostic passes — all in the
`biomistral-judge-reeval-6eb47e` worktree's `out/`.

## What changed

- **Registration** (`ladder/models.yaml`): `biomistral:7b-q5_k_m`,
  max_tokens 512 / timeout_s 120, no reasoning channel. Stays registered so
  the arm is reproducible; it is just not the judge.
- **The re-judge harness** (`scripts/rejudge_r4.py`, TDD'd in
  `tests/test_rejudge_r4.py`): replays rung 4 over a finished run with the
  current manifest judge. Restores pre-abstention codes from
  `checks.withheld` (rung 5 ran after rung 4 — the saved `sct` is null on
  all 208 abstained records), and stashes the incumbent's verdicts once
  under `checks.r4_prior` (first stash wins).
- **Fix 1 — the post was sent TWICE on every rung-4 call.** r4's template
  embeds `{source}` and also passed it as `Caller`'s text, which appends a
  second copy as a `POST:` section. Invisible with granite (only cost),
  fatal for BioMistral (it stops answering above ~430 prompt tokens).
  `Caller` now sends the bare prompt when `text=""`; a contract test
  asserts the post reaches the judge exactly once. **r2 has the identical
  defect** — flagged for its own session; no measured number invalidated
  (r2 fired zero times on this config).
- **Fix 2 — `Caller._reclose`.** 91 of BioMistral's 240 replies were a
  complete, correct-schema judgement that hit EOS one character before the
  closing `}` (finish_reason stop, not truncated). Same class as a markdown
  fence: repaired centrally, counted in `caller.unclosed`, guarded so a
  bare `{` cannot become a fabricated `{}`.

## The measurement

- **Delivery:** 208/240 unparseable through the original path; still
  167/240 unjudged after both fixes — instant-EOS is prompt-length-driven
  (answers at median 324 prompt tokens, 100% EOS above 500), so the longest
  third of posts cannot be judged at all.
- **Discrimination:** all 73 parsed verdicts are "fail" (code_ok 1/73 — it
  calls 386661006 wrong for the literal span "Lower Back Pain"). Fail rows
  23.3% correct vs 24.6% among unjudged: zero separation.
- **Confidence: flat 0.0 on all 73.** The planned rung-5 tau sweep was
  contingent on the field varying; contingency not met, sweep skipped. The
  optional S2 extractor arm declined on the same evidence.
- **The bonus finding:** granite re-judged through the fixed single-post
  path loses its own separation — pass/fail correctness 28.0%/15.6%
  (stored, doubled post) → 25.4%/23.6%. Rung 4's 2:1 signal was partly the
  prompt duplication: presentation is load-bearing for small judges, same
  lesson as Phase B(e)'s menu order. The duplication stays fixed anyway — a
  signal living in an accident is not one the article can stand on.

## Notes for review

- `manifest.json` judge is granite again; the model note records the full
  round trip (append-only kept). The prior "33% vs 17%" could not be
  reproduced exactly under any denominator tried (28.0/15.6 over all 240;
  direction always reproduces) — the prior session's denominator went
  unrecorded, noted in decisions as its own lesson.
- 550 tests pass (20 new, all TDD-first); preflight clean.

# Phase B — rung 0 accuracy: negation, span trimmer, pick fixes

**Dev split, 40 docs, 226 gold: F1 exact 0.296 → 0.362, overlap 0.451 → 0.479**
(detection 0.501/0.783, coding 0.704/0.611), 137,828 tokens / 77 calls
(+5.8% over baseline). Five decision entries dated 2026-08-25 in
`docs/decisions.md` carry the full measurement story; runs are
`out/phaseB-1.*` (diagnostic), `out/phaseB-2.*` (result),
`out/phaseB-arm-alpha.*` (menu arm).

## What changed

- **(a) Negation.** All three step schemas extract denied reactions with
  `"negated": true` — the old "do not report what they did NOT have" rule
  fought the answer key (427 denied gold mentions, 4.7%). The model's claim
  lands on `checks.negated` and `checks.r0_negated`; the duplicate exists
  because rung 1's cue check (untouched, the deterministic cross-check)
  overwrites `negated` via `rec.checks.update()` in full-ladder runs.
- **(a′) The discovered interaction.** The first run found 4 denied gold
  mentions and the pick step then declined every one ("they did not have
  it, so no concept applies"). The menu now marks denials `[denied]`, the
  pick prompt states denial is never a reason to decline, the string
  `"null"` is normalised to the null decline, and blanket wellness
  statements ("no side effects") are out of extraction scope. After the
  fix the denied gold mentions score CORRECT.
- **(b) Query rewriting: measured offline and REJECTED, not wired.** The
  harness reproduced the 87.0% deduped recall@20 baseline exactly; both
  strip-the-qualifiers variants lost (rescued 26 mentions, broke 62–71).
  The finding is in `docs/decisions.md`; no production code carries it.
- **(d) Span trimmer** (`ladder/trim.py`, `rung0_trim: true` in the
  manifest). Rules learned at runtime from POOL gold only (dev/test
  refused): edge tokens gold leaves outside boundaries ≥95% of ≥20
  sightings, plus an interior clause cut at tokens with inside_rate ≤2%
  over ≥50 occurrences. Exact +0.4pt, overlap byte-identical; originals
  kept on-record as `span_untrimmed`. Looser thresholds bought exact F1 by
  cutting spans out of their overlap matches and were rejected.
- **(e) Menu-order arm.** Alphabetising the same candidates costs 10–12
  points of coding accuracy at byte-identical detection — the pick anchors
  on early slots, so the dense retriever's best-first order is
  load-bearing. `rung0_menu_order` stays a declared arm, `"score"` default.

## Notes for review

- `manifest.json` gains `rung0_trim` / `rung0_trim_note` (append-only kept).
  This changes the frozen rung 0 that Phases C–F measure against — flagged
  here because the manifest is edited jointly.
- Seventh dev-tuned prompt iteration, declared; the test split remains
  untouched.
- 530 tests pass (33 new, all TDD-first); preflight clean.

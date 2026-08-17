# InfoQ article — outline (6 beats, practitioner)

Lead with the finding, not the taxonomy. The numbers are the whole contribution.

## Findings from the full run (60 items, K=10, granite4:micro-h on SROIE)

Detail in decisions.md. These are one model on one task — say so in the piece;
the contribution is the *method plus the shape of the result*, not a leaderboard.

1. **The metric trap (the strongest finding).** Accuracy is a ratio over
   *answered* fields, so any layer that withholds answers raises it for free.
   The judge rung lifted accuracy 0.938 → 0.960 while **yield** (share of ALL
   fields correct) fell 0.938 → 0.772. A team watching accuracy ships a layer
   that produces ~17% fewer correct fields and calls it an improvement.
   Yield by rung: 0.938 / 0.938 / 0.932 / 0.934 / 0.772 / 0.772 / 0.988.
2. **Only the human rung beat the bare model on yield.** Everything in between
   was neutral or negative on this model + task.
3. **Self-referential layers were inert against a confidently-wrong model** —
   format checks, self-confidence abstention, and self-correction changed
   nothing that mattered; the first real signal was the first *independent* one.
4. **Confidence is real but miscalibrated**: 0.995 mean when correct vs 0.879
   when wrong, yet 140/150 errors sat above the default 0.7 gate. The mechanism
   works; the threshold has to be fitted per model.
5. **The stack is worse than its best layer.** Voting *alone* yields 0.946 —
   above the bare model and above every cumulative rung except the human one —
   but voting *inside* the stack yields 0.772, because cumulative stacking drags
   the judge along. Judge alone yields 0.905, below baseline. Cumulative
   stacking is the wrong default; this is the case for the composer.
6. **Errors concentrate**: address 100 wrong, total 40, date 10, company 0.
   Two thirds of the reliability problem is one field — worth saying out loud,
   because fixing that field beats every layer in the ladder here.
7. **The gate has to be calibrated, and calibration buys precision, not yield**:
   at 0.90 the error rate among shipped answers falls 0.060 → 0.043 for 1.7pt
   of coverage; yield is unchanged. Useful when a wrong answer costs more than
   a missing one — which is exactly the economics beat.
8. **Correction worth reporting honestly**: on the 10-item smoke run,
   cross-prompt dispersion looked like a better error signal than self-reported
   confidence. At n=60 it is not — thresholding on vote agreement costs yield
   fast while confidence at 0.90 costs none. Nine errors was too small a base.
   (Good material for a "how we nearly published a wrong finding" aside.)
9. **Determinism was 1.000 everywhere** — local greedy decoding at temp 0 is
   exactly reproducible, so that axis is free locally and only becomes
   interesting on hosted APIs (batching nondeterminism). [needs the Gemini run]

## Beats

1. **Every agent is 90% harness, built by intuition** — the hook. Teams stack
   reliability layers by vibes and never measure which pay.
2. **The 7 layers people actually use** — one concrete paragraph each.
3. **How to measure a layer honestly** — determinism, yield (not accuracy!),
   coverage, cost. THE CONTRIBUTION, and beat 4 is why it matters. [A]
4. **The layer that improves your metric and degrades your product** — the
   judge case: accuracy up, yield down. Replaces the old "knee" beat: on this
   run reliability was not front-loaded, it was mostly absent until a human
   appeared. Report that honestly rather than forcing a knee. [B]
5. **The flip** — whether withholding answers is worth it depends entirely on
   your cost of a wrong answer vs a missing one; the optimal rung moves with
   your economics (rung 1 below ~$2 per error, rung 2 at ~$5, rung 6 from ~$10).
   Headline. [B]
6. **Decision rule + the tool** — takeaway table + configurator link. Two
   practical rules fall out of the findings: compose layers deliberately rather
   than stacking cumulatively, and calibrate the abstention gate per model
   before concluding the layer doesn't work.

Discipline: write each figure's caption the day you make the figure. A caption
you can't write = a result that isn't clear yet.

Figures so far: (1) the four-line curve with yield emphasised — caption written,
see the app's Figure 1; (2) cost frontier; (3) net-utility bars showing the flip.

Future-work para (one line each): RAG over the same ladder · prompt optimization
(raw-vs-optimized comparison) · multi-domain generalization · threshold
calibration as its own rung (fit the abstention gate per model).

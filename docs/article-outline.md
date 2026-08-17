# InfoQ article — outline (6 beats, practitioner)

Lead with the finding, not the taxonomy. The numbers are the whole contribution.

Early findings feeding the beats (smoke run, granite4:micro-h on SROIE — see
decisions.md for detail; confirm on the full 60-item run before writing):
- Local greedy decoding at temp 0 is perfectly deterministic — the determinism
  axis is free locally; it should move on hosted APIs (batching noise).
- Self-referential layers (format checks, self-confidence abstention,
  self-correction) were inert against a confidently-wrong model; the first
  accuracy gain came from the first independent signal (the judge).
- The model's self-reported confidence was uncalibrated (≈1.0 correct vs ≈0.93
  wrong) — the abstention threshold must be calibrated per model.
- Disagreement across prompt variants pointed exactly at the wrong fields even
  when the majority vote picked the wrong value — dispersion beats confidence.
- The judge ran at precision 0.25 / recall 0.67: it generated 75% of the
  human's rung-6 workload from false alarms.

1. **Every agent is 90% harness, built by intuition** — the hook. Teams stack
   reliability layers by vibes and never measure which pay.
2. **The 7 layers people actually use** — one concrete paragraph each.
3. **We measured determinism + accuracy + cost per layer** — method + the curve.
   THE CONTRIBUTION. Everything rides on this being clean. [A: method/numbers]
4. **The knee** — reliability is front-loaded; first 2–3 rungs do the work, top
   rungs rarely pay. [B]
5. **The flip** — cheap-error tasks stop low, expensive-error tasks climb high;
   optimal rung moves with your economics. Headline. [B]
6. **Decision rule + the tool** — takeaway table + configurator link.

Discipline: write each figure's caption the day you make the figure. A caption
you can't write = a result that isn't clear yet.

Future-work para (one line each): RAG over the same ladder · prompt optimization
(raw-vs-optimized comparison) · multi-domain generalization.

# spec.md — The Reliability Ladder

## The one-sentence thesis

Every LLM agent is ~10% model, ~90% harness — and that harness is built by
vibes. We measure which harness layers actually earn their cost, so you can stop
guessing and pick a rung.

## What we're measuring (the entire contribution)

The 7 rungs are known techniques. The novelty is **the measured tradeoff curve**:
determinism + accuracy + cost per rung, and where the knee is. Everything rides
on this curve being clean. No clean curve → no paper. Guard this ruthlessly.

## Scope — narrowed for a one-day MVP

ONE task. All 7 rungs. Three scores each. One clean curve with a visible knee.
**Explicitly cut today:** RAG, prompt-optimization loops, multi-domain.
Parked as one-line "future work" each — not built.

---

## Input contract (what the user gives us)

- **prompt** — their task, as a prompt (the ladder is task-agnostic; it wraps
  reliability layers around whatever their prompt does)
- **data** — their inputs (~50–100 items)
- **gold** — the correct answer per item

The ladder runs their prompt through each rung and returns scores. Task can be
anything with a structured, checkable output.

## The 7 rungs (each implements the Runner contract)

| Rung | Layer | Mechanism |
|------|-------|-----------|
| 0 | bare LLM | one call, take output as-is |
| 1 | deterministic | format/type checks, normalized compare |
| 2 | abstention | low confidence → decline instead of guess |
| 3 | self-correction | model reviews + revises its own output |
| 4 | LLM-as-judge | second model grades/filters (see judge note) |
| 5 | voting | K samples, majority — the determinism workhorse |
| 6 | human-in-loop | flagged items → human (simulate: gold + fixed minutes) |

Run cumulative (main story) + single-rung ablations (which layer is individually
strongest). Gap = redundancy across layers.

---

## Three scores per rung

**1. Determinism** — run each input K times (K=10). Primary metric =
**field-level exact-match agreement**: for each field, fraction of the K runs
that match the modal value; average across fields, then items. Purely mechanical
string comparison, no model needed. Range 0–1.

**2. Accuracy** — vs gold. Exact-match where possible; **LLM-as-judge as scorer**
only for fields where "correct" is semantic (paraphrase, free text). A rung that
is stable but wrong is a trap — you want stable AND correct.

**3. Cost** — tokens, $, latency, human-minutes. Identical cost model across
rungs or the comparison is meaningless.

## The judge wears two hats — keep them separate

- **Judge as RUNG 4** — a reliability layer we are *measuring*.
- **Judge as SCORER** — how we measure accuracy on semantic fields.

Different prompts. If the same judge does both, you can't tell whether a rung
improved output or gamed the scorer. Also: the judge is itself stochastic —
run the scorer K times and report its own consistency, so the instrument's noise
is measured, not hidden.

## The headline results

- **The knee** — most reliability comes from the first 2–3 rungs; top rungs
  rarely pay. Find where the curve flattens.
- **The flip** — under user economics, the optimal rung changes:
  cheap-error tasks stop low, expensive-error tasks climb to voting/human.
  net utility = value_correct·correct − cost_wrong·wrong − cost_abstain·abstained
  − $compute − $human.

---

## Output: results.json

Per rung: determinism, accuracy, cost (+ deltas + CIs). See
schemas/results.schema.json. App reads it → frontier + net-utility + recommended
rung + composer.

## Today's order of operations

1. Both (30 min): lock task + dataset + model/temp=0 + K=10. Confirm contracts. Push.
2. A: adapter → harness with K-runs loop → determinism + accuracy + cost → rungs 0–2 → real results.json.
3. B: app on results.stub.json → rungs 3–6 → analysis → swap real data.
4. Integrate: full ladder + ablations → the one curve.
5. Article: fill numbers, write captions as figures land.

## Definition of done (MVP)

- results.json: all 7 rungs, three scores each, on one task
- app: frontier + net-utility + recommended rung + composer
- article: draft with the knee figure and the cheap-vs-expensive flip

## Article outline (6 beats — practitioner)

1. Every agent is 90% harness, built by intuition.
2. The 7 layers people actually use.
3. We measured determinism + accuracy + cost per layer. ← the contribution
4. The knee: reliability is front-loaded; top rungs rarely pay.
5. The flip: cheap-error stops low, expensive-error climbs high.
6. Decision rule + the tool.

Discipline: write each figure's caption the day you make the figure. Can't write
the caption → the result isn't clear yet.

## Not today (one line each, future work)

RAG pipeline (retrieval is a different axis) · prompt optimization (build-time
preprocessor OR raw-vs-optimized comparison study) · multi-domain generalization.

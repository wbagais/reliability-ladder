# plan.html v17 — audit against measured results

Audited 2026-08-23 against the 40-doc runs, the gold controls, the end-to-end
run, and `docs/decisions.md`. Seven tabs: Plan, Ladder demo, Ladder flow,
Triage desk, Architecture, Iterations, Glossary.


> **Numbering.** This audit's rung IDs were remapped to the 2026-08-23 scheme
> (`[0,1,2,3,4,5,6]`). **`plan.html` itself has not been renumbered** and still
> uses the old IDs throughout, so a reference here to "rung 3" points at a
> section the document labels rung 5. Renumbering plan.html is itself an open
> item. Mapping: self-correction 3→2, voting 5→3, abstention 2→5.

Severity: **BLOCKING** = states something now known false · **STALE** = was true,
no longer · **GAP** = missing a finding that changes the argument.

---

## 0. Read this before editing anything

**A branch `claude/renumber-rungs` is open and unmerged.** The Plan tab §5
contains a section arguing against exactly that, on grounds that survive today's
results: rung ID is identity, execution order is configuration, and collapsing
them costs you the ordering ablation. That ablation is now one of the article's
findings. **Settle the numbering before editing any tab**, or every rung
reference gets rewritten twice.

---

## Tab 1 — Plan

### BLOCKING — the status banner is now false

> *"Everything numeric in this document is an illustrative placeholder except
> the twelve-string probe in §2 — including the rung 1 rejection rate, which is
> a prediction to be read out at hour 3. The brief says 'our contribution = the
> numbers', and there are currently no numbers."*

There are now numbers, for every rung, plus two gold controls and an end-to-end
run. This banner is the first thing a reader sees and it tells them to disbelieve
the document. Replace with a status block pointing at measured results.

### BLOCKING — §1 record shape contradicts the built system

§1 shows one object pairing `drug_text` with `reaction_text`. `decisions.md`
2026-08-22 records this as contradicting the plan's own safety constraint 3
(never emits "drug X causes Y") and resolves it: **one record = one mention**,
with an `entity_type`. The plan still shows the rejected shape.

### BLOCKING — §5 rung 3 says k=5; the implementation is k=3 per document

Two errors in one row. The manifest sets k=3, and the implementation samples
each **document** k times, not each record — 35 documents × 3 = 105 calls for
169 records. The row's "~5× cost" is wrong twice over. Measured: 55,704 tokens,
*cheaper* than self-correction's 72,539.

### BLOCKING — §5 rung 2 says a rescued record re-enters unverified

> *"a rescued record re-enters the pipeline unverified"*

Changed deliberately during build. Rung 2 re-validates through `r1.zone()`,
because without it `rescued` is an assertion rather than a measurement. A
spec-conformant rung 2 would have reported 158 corrections, none checked, all
empty. This is in the article as a finding; the plan still specifies the version
that would have produced the false number.

### BLOCKING — §6 gold count

> *"~6,754 gold mentions supports a 200-record dev split and a 600–800 frozen
> test split"*

`decisions.md`: the real count is **9,111**; 6,754 is the published paper's
figure for a subset. And the actual splits are **dev=40 documents, test=60
documents**, not 200/600–800 records. Every power argument in §6.2 rests on the
wrong denominator.

### BLOCKING — §9 claim 3 depends on a retired track

> *"Same ladder on CADEC and ADE Corpus V2."*

The second-corpus track was retired 2026-08-22 with its results. This claim
cannot be made and the difficulty-contrast finding it promised is gone. Either
cut it or restate it as an open question — the article does the latter.

### STALE — §5 counter-metrics, all six

Each rung's counter-metric column now has a measured answer, and in four cases
the interesting number is not the one predicted:

| rung | plan's counter-metric | measured |
|---|---|---|
| 0 | JSON parse failure rate | 0 failures; the interesting number is 0/105 correct codes |
| 1 | rejection rate + breakdown by reason | 98% rejected — but the breakdown is **check-order dependent**, 172 of 176 failures masked |
| 2 | over-abstention | 66% of correct gold codes withheld (150/226) |
| 3 | **"regression rate — the most interesting number on the ladder"** | 0 regressions, because 0 rescues. The interesting outcome is `declined` 158/158, which is not in the plan's outcome list at all |
| 4 | judge false-approval rate | 86–92% code approval on gold *and* fabricated codes alike — **both channels constant**, no discrimination |
| 5 | consensus-on-wrong | 3 unanimous on fabricated codes, but dominated by `not_resampled` 166/169 — an outcome the plan does not anticipate |

### STALE — §5 rung 5, τ

> *"τ tuned on dev only; sweep and report the curve."*

τ defaults to 0.0 — the confidence gate is off pending a real rung-0 confidence
distribution. The sweep has never been run. Either run it or say why not.

### STALE — §5 rung 4 prediction

> *"Uncertain. Often repeats what the vote already told you."*

Measured. It repeats nothing — voting had 3 records; the judge answered 96. Its
actual failure is different and more interesting: two constants, and an
agreement figure that moves 100% → 98% → 49% on set composition alone.

### STALE — §5 rung 6, "both review the same 25"

The triage desk has never taken a review. It cannot usefully take one: it would
receive 169 withheld records, all carrying a wrong answer or none. State that as
the finding rather than as pending work.

### STALE — §7 hour budget, three iterations, slippage rules

"Two people, three days" and a seven-hour budget. The project has run
considerably longer and the iteration structure no longer maps. Either rewrite
against actuals or move the whole section to the Iterations tab as history.

### STALE — §10 risk table, four rows resolved

| risk | outcome |
|---|---|
| No working vocabulary lookup | Resolved — local RF2 release, no network in the loop. Also produced a finding: 23.9% of gold mentions absent from OLS4 |
| Judge shares extractor's blind spots — *tell: approval near 100%* | **The tell fired.** Code approval 86–92%. The mitigation (different model family) was applied and did not help |
| Gold-matching rule argued mid-project | Resolved — one shared scorer |
| Check thresholds tuned on test | Not exercised; τ never swept |

Move resolved risks to an outcomes column rather than deleting — a risk register
that shows which risks materialised is more useful than one that shows only open
ones.

### GAP — findings with no home in the plan

None of these have a section, and three change the argument:

- Check order determines the reported diagnosis (§2 is where it belongs)
- Pooled drug/reaction ratios describe neither population — 43.1% pooled is
  35.0% on reactions
- Determinism is bounded by hardware — 176 CPU / 169 GPU, same seed
- Wall clock 2–4× longer end-to-end at identical token counts
- Eight instances of a check that could not run reporting as one that did
- The BAND zone demonstration — one code for two opposite conditions in one
  document
- The gold defect — a date where an SCTID belongs, `LIPITOR.511.ann`

### GAP — §13 first three commands

Almost certainly stale after A's restructure (`rung0_ab.py` → `rungs/r0.py`, new
`ladder/llm.py`). Needs re-testing against the current tree, not editing from
memory.

---

## Tab 5 — Architecture

### BLOCKING — corpus version wrong in the diagram

The SVG says **CADEC v3**. It is **v2**. `decisions.md`: v3 is the DAP
*collection* edition, and the collection contains only `CADEC.v1.zip` and
`CADEC.v2.zip`. The working copy is verified byte-identical to the v2 archive
with checksums committed. This appears in the data-plane box, which is the most
load-bearing part of the diagram.

### BLOCKING — presentation plane names the wrong hosts

> *"Streamlit Cloud · GitHub Pages"*

The project uses **GitLab**, with GitLab Pages and a GitLab CI pipeline. No
Streamlit. Three planes is still the right model; two of the three names are
wrong.

### GAP — the results plane understates what is now published

> *"`results.json` — scores, counts, costs. No document text."*

The repository now also publishes `runs/*.json` with backend, release and corpus
version stamped, an append-only JSONL ledger with per-record cost, an engineering
wiki, and `docs/decisions.md`. The plane is right; its contents list is a
subset of what exists.

### GAP — the preflight gate's known limitation

Preflight scans **tracked files only**. An `unzip -d data/` once put both corpus
zips in the tree untracked and unignored, and preflight would not have caught it.
That belongs in the architecture tab beside the licence constraint, because it
is the one gap in the control that constraint depends on.

---

## Tab 6 — Iterations

Not stale so much as **behind**. Its own note says six entries are corrections,
and that logging them costs a line. Today alone produced several that are not
there: the R4 gold control, the ledger's dead call sites, the caching bug that
produced free unanimity, zero rung interaction end-to-end, and R2 measured as an
inherited transfer function.

`docs/decisions.md` has A's 169 new lines. The Iterations tab and the decisions
log now overlap heavily and neither is a superset. Worth deciding which is
canonical before the article's process section is written from either.

---

## Tabs 2, 3, 4, 7 — not audited

**Ladder demo**, **Ladder flow**, **Triage desk**, **Glossary** are interactive:
embedded JS with what look like hardcoded illustrative numbers, a canvas
animation, and a paginated glossary index.

I have not audited these because editing them safely means reading the
JavaScript, and the header knobs (`tok/error 500`, `review % 11`, `n 800`)
suggest the demos are driven by placeholder parameters that should now be
driven by measured values — a rewrite rather than a correction.

The Triage desk in particular needs a decision, not an edit: it simulates a
review workflow that the real rung 6 cannot exercise. Either it becomes an
explicit "what this would look like if the bottom of the ladder produced
reviewable records", or it is misleading.

---

## Suggested order of work

1. Settle the renumbering with A. Everything else depends on it.
2. Plan tab: status banner, §1 record shape, §5 table, §6 denominators, §9
   claim 3. These five are the blocking set.
3. Architecture tab: v3→v2, GitHub/Streamlit→GitLab, preflight limitation.
4. Plan tab: counter-metrics column, risk outcomes, the seven missing findings.
5. Iterations: reconcile against `decisions.md`, pick a canonical source.
6. Interactive tabs: separate session, with the JS in front of us.

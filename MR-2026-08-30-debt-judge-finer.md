# The three-draw debt, rung 4's fate, and what FiNER's recall is actually made of

Four tasks. Two of them settle questions the audit left open, one corrects a
premise this project had been carrying, and one moves the published artifact
onto the article it is supposed to be serving.

**Nothing here re-opens Phase F.** The test split was spent on 2026-08-26 and
every number below is dev-side and labelled as such.

## 1. The three-draw debt is paid, and both arms survive

`manifest.json` declared `rung0_split` and `rung0_cut_rate` on **one draw
each** — the protocol that certified the reranker at `+0.0215 [+0.0000,
+0.0433]` before its sign reversed on the third run. The manifest said so, in
its own notes, for three days.

Nine dev runs, leave-one-out from the tracked manifest, `sample_index` 0/1/2,
paired bootstrap over documents at 2,000 replicates:

| removed | F1 exact, three draws | pooled |
|---|---|---|
| `rung0_split` | +0.0389 / +0.0345 / +0.0579 | **+0.0438 [+0.0012, +0.0937]** |
| `rung0_cut_rate` | +0.0139 / +0.0183 / +0.0098 | +0.0140 [−0.0163, +0.0500] |

Both survive the rule pre-registered before the third draw landed (sign
consistency on the layer the arm was sold on), so **neither is removed and no
CADEC number is re-run**. They survive on different strengths and the notes now
say which: the splitter is separated; the trimmer threshold is *consistent and
small* — six sign-consistent comparisons out of six, every interval containing
zero, and an effect smaller than the 1.3-point spread the same three draws show
in the baseline itself.

**The claim that died** is one the single draw implied but never stated: the
splitter buys **exact only**. On overlap its sign reverses (+0.0000 / −0.0047 /
+0.0229), which is exactly what the mechanism predicts — cutting a coordinated
quote into pieces turns one already-overlap-matched blob into several
exactly-matched spans, so overlap has nothing to gain.

### And the bootstrap helper was not a bootstrap

`out/harness/paired.py`, which every rung 0 arm in this project was measured
with, resampled documents as `set(random.choices(ids, k=len(ids)))`. The
`set()` collapses the duplicates a bootstrap draw is made of, leaving a ~63%
subsample — a different, wider estimator wearing a bootstrap's name. It went
unnoticed for a month because it produced plausible intervals.

`ladder.score.paired_bootstrap` is now production code, TDD-first, six tests,
including one that pins the defect directly. `bootstrap_ci` was refactored onto
the shared `_per_doc_stats` / `_layers` / `_pct` helpers and its output over a
real records file is **byte-identical before and after**, verified rather than
assumed.

## 2. Rung 4 has a reader now, and measured, it stays off

The audit found nothing in `ladder/` reads `checks["r4_verdict"]`, so ~93k
tokens per run could not move a shipped number by construction. Three options
went to the owner; the call was **wire it as an arm and measure whether it adds
anything**.

Shipped TDD-first: `R_JUDGE_FAIL`, `rungs.5.abstain_on_judge_fail` (default
**false**, declared explicitly in the manifest), and `manifest.judgearm.json` —
a one-key diff with a test asserting it is exactly one key. The arm may only
*subtract*: a record already heading for ABSTAIN keeps `unresolved`, and a
missing or unparsed verdict is never read as a failed one, or disabling the
judge would abstain the whole run.

Three rung 0 draws, `--rungs 1,4,5` over each:

| | judge off | judge on |
|---|---|---|
| coverage | 0.210 / 0.202 / 0.215 | 0.153 / 0.149 / 0.156 |
| precision on answered | 0.808 / 0.800 / 0.824 | 0.816 / 0.811 / 0.838 |
| **yield** (correct ÷ all) | 0.169 / 0.161 / 0.177 | **0.125 / 0.121 / 0.131** |
| records to a person | 196 / 198 / 186 | 210 / 211 / 200 |

It withdraws 14 / 13 / 14 shipped answers to remove **3 errors each time** —
about **3.7 correct answers destroyed per error caught** — and the records it
withdraws are only **1.11–1.21×** more likely to be wrong than the ones it
keeps. The same free lexical check, on the same records, separates
**3.03–3.15×**.

Precision rose, which is the trap: abstaining always raises precision. Yield is
the number that cannot be fooled by abstaining, and it fell 26%. **The arm
stays off, and the question is answered with a measurement instead of an
inference.**

## 3. FiNER recall — the premise was wrong, and two things fell out

The handoff said "the model never proposes 70% of gold". It does not.

> detection recall **0.685** × coding accuracy on matched spans **0.446** =
> recall 0.303

The model reaches more than two thirds of the gold spans and mis-codes most of
what it reaches, and it proposes 292 spans against 165 gold. On a corpus where
the whole 139-tag vocabulary is in the prompt and the right tag is therefore
always on the menu, **recall work here is coding work**. One recall number for a
pipeline that both finds and classifies sends the effort to the wrong half.

### A refusal is not a JSON failure — and it is not even a property of the model

52 gold mentions were never touched, and **21 of them — 12.7% of the entire dev
gold, 40% of the detection gap — sat in one document the extractor refused**:
2,153 reasoning tokens, then *"I'm sorry, but I can't provide that."* on a
public SEC filing. The ledger recorded it as `json_decode`, i.e. as a model that
cannot emit JSON.

`r0.failure_reason` is now the one place a document failure is named:
**`timed_out > truncated > refused > json_decode`**. The detector reads U+2019,
because that is the apostrophe the model actually types — an ASCII-only
detector passes every test you would think to write and never fires on real
output.

Then we put the same request back three times:

| | draw 0 | draw 1 | draw 2 |
|---|---|---|---|
| `gpt-oss:20b` | **refused** | 33 mentions | 33 mentions |

`llama3.1:8b` 38, `mistral:7b-instruct` 22, `granite4:micro-h` 9 — one draw
each, because those three are bit-reproducible and three identical draws of a
bit-reproducible model are three copies of one measurement. `qwen3:8b` is
excluded and the exclusion is stated: it held the GPU for 45 minutes on this one
document without returning.

**This reframes the nondeterminism result.** The 1.3-point run-to-run spread is
an average over records and it understates the risk: the variance concentrates
into whole-document, all-or-nothing outcomes, and one of them is 12.7% of the
answer key decided by which draw you got. A bit-reproducible model can be
wrong, but it cannot answer on Tuesday and refuse on Wednesday.

### REJECTED: the context-ordered menu, and the mechanism is the finding

FiNER's menu is all 139 tags in alphabetical order, on the sound argument that a
bare number carries no words to rank on. But the sentence does. An offline probe
put the correct tag at **median rank 7 of 139** when tag names are ranked
against the 120 characters around the number.

So `rung0_menu_order: "context"` (`ladder/menuorder.py`, off in both manifests,
`manifest.finer.ctxmenu.json` a test-pinned one-key diff) reorders and drops
**nothing** — menu recall stays 1.000 and detection is byte-identical by
construction. Coding accuracy went **0.393 → 0.304**.

The artifacts say why, and it is not that the ranking was bad:

| | alphabetical | context-ranked |
|---|---|---|
| pick lands on menu slot 0 | 20.4% | **50.2%** |
| median picked slot | 30 | **0** |
| accuracy when slot 0 is picked | 0.087 | 0.373 |
| accuracy when any other slot is picked | **0.457** | 0.245 |

The ranking is informative — its top slot is four times better than the
alphabetical one. The model plainly follows it. And it still loses, because what
it displaced was better: the model's own unaided reading of an unranked menu
scores **0.457** against the ranker's 0.373.

> A ranking can carry real signal, visibly move the model, and still make the
> system worse — because what it displaces was better than it.

That completes a pair with CADEC's menu-order arm: destroying a *good* order
cost 10–12 points there; imposing a *mediocre* one costs 8.9 here.

**Provenance stated, not smoothed: this is ONE DRAW** and does not meet this
project's three-draw standard. It is reported as a rejection on an effect
roughly seven times the CADEC run-to-run spread plus a mechanism read off the
artifacts, not as a separated measurement. Three draws needs **four** more runs
(both sides at d1 and d2, since a paired comparison needs both sides at the same
draw) at ~78 minutes each. FiNER's own run-to-run spread has never been
measured, which is the larger reason to run them.

## 4. The published artifact is the article now

The live artifact was still the ladder-framed build log while the deliverable
had moved to the visibility question on 2026-08-28 — so the only thing a reader
outside the terminal could see was the superseded framing.

- `docs/article.html` — the typeset article, ten sections, published **in
  place** so the link survives. It reuses the project's existing design system
  rather than replacing it, because the ACCEPT/BAND/REJECT colours carry
  meaning, and it carries across the build log's `Reproducing` command block —
  the only content on the live page not already in the article.
- `docs/article.md` — the 2026-08-30 revision, promoted to canonical. The
  version it replaced is `docs/versions/article-v2-2026-08-28.md`; the outgoing
  build log is `docs/versions/article-build-log-v2-2026-08-28.html`.

New material is marked in the typeset page so a reader who saw revision 2 can
find what changed.

## Notes

- **725 tests, preflight clean.** New: 6 for `paired_bootstrap`, 6 for the judge
  arm, 5 for the refusal label, 15 for the menu order and its manifests.
- `manifest.json` gained one declared key (`abstain_on_judge_fail: false`) and
  two amended notes. `manifest.finer.json` is unchanged. Both new arms are off.
- `out/` is gitignored, so the runs and the harness scripts cited throughout sit
  in the `phase-e-rung-6-human-loop-64ce8e` worktree. `docs/decisions.md` is the
  durable record, per the standing convention.

---

## Added after the first review pass

**5. The FiNER draws finished, and the context arm is rejected on three.**
base exact **0.193 / 0.205 / 0.205** against ctx **0.149 / 0.128 / 0.128**;
coding **0.393 / 0.421 / 0.421** against **0.304 / 0.263 / 0.263**. Detection is
byte-identical between arms at every draw, as designed.

The second finding is the better one. **Draws 1 and 2 are byte-identical** —
same sha256 on the records file, for both arms — and only draw 0 differs. So
FiNER's entire run-to-run spread is **one refused document**, worth 21 of 165
gold mentions. It is not a distribution and must not be reported as "±1.2
points".

**6. The article layer.** `docs/article-v3.md` (draft, four `[PENDING]`
markers), `docs/article-v3-outline.md` (word budget and cut list, decided before
writing), `docs/PLAN-next-sessions.md` (four sessions, paste-ready prompt for
Session 1). Figure 2 is a new spine diagram with Graphviz source.

**7. Every claim now carries a real example from the artifacts** — including one
per rung, from `cadec-verify-1`. The sharpest is rung 3 on `"stamina"`: rung 1
ACCEPTed |Stamina| on an exact word match, rung 3 voted it to |Lack of stamina|,
**which is the right answer**, and the record shipped carrying a verdict computed
against the code rung 3 replaced. It improved the answer and invalidated the
evidence for it in one step.

**Licence discipline on examples:** CADEC contributes annotated spans and
vocabulary labels only — never a sentence of post prose, which is what the
non-transferable licence covers and what preflight's corpus tells detect. FiNER
is CC-BY-SA-4.0 and is quoted directly.

**Two claims in the draft are still at risk and are declared as such in the
article's own header:** the 0.70 ceiling (task A1) and "retrieval is a ceiling"
(task B2).

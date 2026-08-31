# article-v3 — outline and word budget

Decided before writing, so the cuts are a plan rather than a panic at the end.

**Base:** `docs/article-v2.md` (3,579 words, the submitted cut). v3 EDITS it; it
does not restructure it. Three things v2 does that nothing else does are kept
untouched: *What an AI reliability ladder is for* (the premise, stated before it
is demolished), *What we could not settle*, and *How we found these* (the
measurement loop as the transferable artifact).

**Target:** ~4,000 words. v2 was 3,579 and the longform it came from was 4,569.
The additions below are ~1,900 words and the cuts ~1,150, so v3 lands near 4,300
with a marked optional-cut list to reach 3,600 if the editor wants it.

## The spine

Three questions, in order, each answered by one angle:

| | question | angle | sections |
|---|---|---|---|
| **Q1** | How unstable is it really? | models | 2 |
| **Q2** | What tells you an answer is trustworthy? | rungs | 4, 5, 7 |
| **Q3** | When does that stop working? | corpora | 6 |

Method and the ~20 negative arms are the EVIDENCE LAYER under all three, not a
peer section (§3 and §8).

## Sections

| § | section | words | status |
|---|---|---|---|
| — | Title, byline, hero figure | 60 | keep |
| — | **Five key takeaways** | 320 | **EDIT** — swap the bootstrap takeaway for the division of labour |
| — | What an AI reliability ladder is for | 330 | **EDIT** — narrow the novelty claim; cite the literature |
| — | The task, and the result | 300 | keep |
| **1** | **The two datasets, and what neither can tell you** | **380** | **NEW** — reader cannot follow §6 without it |
| 2 | The ground moves more than our improvements do | 430 | keep |
| 3 | The significance test that certified noise | **220** | **CUT to a third** + add the three-draw debt |
| 4 | What a free deterministic check can and cannot see | **380** | **CUT the error table to the two rows that matter** |
| 5 | The one thing that worked | 400 | keep — strongest section |
| **6** | The corpus where none of it works | **620** | **EDIT** — add the refusal and the slot-0 attractor |
| 7 | What the four paid resolvers bought | **700** | **EDIT** — add the spine ablation and the measured judge arm |
| **8** | **Did we try making the model better first?** | **300** | **NEW** — forecloses the reviewer's first objection |
| **9** | **The division of labour** | **260** | **NEW** — the most reusable output in the article |
| 10 | What no single-layer test could see | **300** | **FOLD** most of it into §7 |
| — | How we found these | **180** | **CUT to half**, keep the figure |
| — | **Where this sits in the literature** | **330** | **NEW** — what we agree with, what we contradict |
| — | What we would tell you | 300 | keep |
| — | What we could not settle | **380** | **EDIT** — add the supervised gap and the retriever gap |
| — | Limitations | 200 | keep |

## What pays for the additions

| cut | words | why it is safe |
|---|---|---|
| §3 compressed to a third | ~300 | it is method; the takeaway already carries the punch |
| §10 folded into §7 | ~350 | once the spine ablation lands, "wired to nothing" is a paragraph |
| §4's error table trimmed to two rows | ~200 | the 1.000 / 0.000 contrast IS the point; four more rows decorate it |
| *How we found these* halved, figure kept | ~250 | lovely, and the most cuttable under pressure |

## Optional further cuts, if 3,600 is a hard ceiling

In this order: §8 (serves the reviewer, not the reader) → the literature section
compressed to a paragraph inside *What we could not settle* → §2's per-model
determinism table reduced to its one-line conclusion.

**Do not cut, under any pressure:** §1 (the datasets) or §9 (the division of
labour). The first is what lets a reader follow the precondition argument; the
second is the only part of this article another team can act on directly.

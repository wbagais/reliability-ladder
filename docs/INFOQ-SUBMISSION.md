# The InfoQ article — rules every edit must keep

`docs/article-infoq-CADEC.md` is the submission to InfoQ; the Word file beside
it, `docs/Group 3 – <title>.docx`, is what gets uploaded. InfoQ's checklist has
ten items. Six are mechanical and **`tests/test_infoq_article.py` enforces
them in CI**; four are people's work and are listed below so nobody forgets
them at upload time.

## Enforced by the test

| rule | how it is checked | if it fails |
|---|---|---|
| **2,000–3,000 words**, excluding code snippets | every word outside fenced code blocks and HTML comments, up to `## About the authors` — tables, captions, takeaways and the reference list all count (the strict reading); the bios do not, they are author metadata InfoQ shows beside the article | cut prose or a table; never a number |
| **two author bios**, about 75 words each | each `**Name**` paragraph under `## About the authors` is 50–100 words (the test is `xfail` until the second bio lands) | write it in third person, present tense, current role first |
| **five key takeaways**, full sentences, **≤ 130 words together** | five `- ` bullets under `## Key takeaways`, each starting with a capital, ending with a period, at least eight words | rewrite; the takeaways are lessons a reader can apply, each opening with the action and closing with the number that earns it |
| **authors under the title** | the first non-comment line after the `# ` title is an italic byline containing " and " | keep `*Wejdan Bagais and Pushpdeep Mishra*` there |
| **captions with image source** | every `![…](…)` is followed by `*Figure N: … Image: the authors.*` and the file exists | add the caption; all figures are the authors' own |
| **links without tracking** | no `utm_`, `fbclid`, `gclid`, `ref=`, `mc_` in any URL | use the bare DOI or arXiv URL |
| **Word file named to convention and current** | exactly one `.docx` in `docs/`, named `Group <N> – <title>.docx`, whose text contains the title, all five takeaways and all captions verbatim | regenerate it (below) |

Run before committing an article edit:

```bash
/tmp/civenv/bin/python -m pytest tests/test_infoq_article.py -q
```

## Regenerating the Word file

Every edit to the markdown must be followed by this, or the sync test fails:

```bash
cd docs && pandoc article-infoq-CADEC.md -o "Group 3 – Testing Six LLM Reliability Layers: What Each Bought and What It Cost.docx" --from gfm --resource-path=.
```

If the title changes, the file name changes with it: delete the old `.docx`
(only one may exist) and keep the `Group 3 – ` prefix.

## Regenerating the figures

The two charts read the tracked report; the tables are `.dot` files. See
`docs/figures/README.md`. After a change to `runs/archive/consolidated-2026-09-03/rerun/cadec.json`:

```bash
.venv/bin/python docs/figures/make_infoq_figs.py
```

`tests/test_infoq_figs.py` pins the first draw's counts to the published figure.

## Not enforceable by a test — do these at upload

1. **Generative-AI disclosure.** InfoQ allows AI for drafting assistance and feedback, bans text written entirely by AI, and requires authors to say which tools they used and how. This article's drafts and revisions were produced with Claude Code, reviewed and corrected by the authors; say so in the submission form.
2. **Image copyright.** All three figures are the authors' own, generated from files in this repository; no third-party imagery. Keep it that way.
3. **Editor access.** Enable full editor access for the editorial team on the uploaded document.
4. **Proofreading pass.** Run a basic spell check before upload (`codespell docs/article-infoq-CADEC.md` found nothing on 2026-09-08). Spelling is British throughout; say so.
5. **Author bios.** Wejdan's is in (she/her, in the house pattern: role and employer, specialism tied to the article, years and background, degrees); Pushpdeep's is still a placeholder comment — ask for role, employer and one line of background.
6. **The medRxiv reference.** The DOI answers 403 to automated fetches; open it once in a browser before submitting.

## What the takeaways must keep claiming

The body and the takeaways were aligned on 2026-09-08. A change to either side
must keep them consistent; the five claims and where the body carries them:

| takeaway | body |
|---|---|
| layers sort answers by trustworthiness, they do not fix them; judge on correct over all inputs | "One dial, not a staircase" — the yield paragraph, the 128 / 49 / 177 sentence (`tests/test_infoq_figs.py` pins those to the first run's report) |
| the free check sorted answers; the three paid layers changed one answer, each having little to act on or going unread | the six bullets in "What each layer bought"; the replay without the paid layers (one record different, first run only); the held-out paragraph at the end of "One dial" (72 ACCEPT, 60 right; 242 others, 45 right) |
| the model reads, never remembers: 13–18 percent invented codes | the three-column table in "The system under test" and the paragraph after it |
| repeat runs as a validation step; 70 percent agreement | "The noise floor" — the agreement table (164 of 233) and the five-model determinism paragraph |
| study the data before adding layers; not medicine; no layer recovers what was not read | "Where the model loses" and the first Monday practice |

The reviewers' round of 2026-09-08 (27 comments on the Word file) set three
more rules for this file: **no dial table** — Figure 2 plus prose, and the
prose carries the first run's numbers; **figures at print size** — the two
Graphviz tables run at 12.5–15.5 pt with the darker grey `#3a464c`, the chart
at 10–13 pt; **the multi-corpus result is one section of this article**
("Does it hold beyond CADEC?"), not an appendix pasted from the README.

Do not write "better than the paid layers" for the free check: the menu-shown
judge separates right from wrong more sharply (3.4–4.2× against 2.7–2.8×); its
verdict is read by nothing, which is a different claim.

Two more rules from the owner's section-by-section review (2026-09-08, section 1):
**the opening states the theory under test** (each layer catches what the layers
below missed, so accuracy rises with every layer) and frames the layers as
evaluating and flagging output, not as ship / do-not-ship decisions; **the
CONORM comparison uses the bare model, everything it returned**, under CONORM's
own lenient matching (0.72 against our 0.47–0.50 on dev), never the
after-abstention held-out 0.204.

**No unproven claims about the field.** "Nobody has", "the common answer",
"most teams", "rarely stated" and similar were cut on 2026-09-08; a sentence
about what practitioners generally do needs a citation, otherwise it is
written as what we did or measured.

**Figure 1 is the flowchart** (`infoq-fig6-pipeline-flow.dot`), and it stands in
for the worked example: the payload on each arrow is the example. Do not
reintroduce the sample post and menu as code blocks beside it.

**Figure 2 is the three-variant chart** (`infoq-fig7-variants.png`, drawn by the
figure script from the S0/S1/S2 reports); the three-column table it replaced
must not come back. Figures are numbered 1 pipeline, 2 variants, 3 shipped set,
4 funnel. The matrix chart (`infoq-fig9-matrix.png`) is drawn but not in the
article; "Does it hold beyond CADEC?" carries no figure and no performance
numbers, only whether each lesson agrees (the matrix holds FOUR model
families, not five).

**Three-run figures are written as ranges in prose** ("76 to 82 percent",
"177 to 187 records"), never as three numbers and never as an average: two of
the three runs are byte-identical, so a mean is two thirds one run and hides
the spread the noise section is about. The individual runs stay only where a
specific run is the subject (the noise section, the deletion replay) and in
Figure 2's dots. Owner's decision, 2026-09-08.

**One repository link in the article**, github.com/wbagais/reliability-ladder,
at the end. The stagecheck link (gitlab.com/pushpdeep/stagecheck) is reached
from that repository's README, not from the article. At upload: push the final
commit to BOTH remotes (`origin` is GitLab, `github` is the mirror the article
cites) so the link shows the code the article describes.

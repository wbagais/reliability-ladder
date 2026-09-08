# The InfoQ article — rules every edit must keep

`docs/article-infoq-CADEC.md` is the submission to InfoQ; the Word file beside
it, `docs/Group 3 – <title>.docx`, is what gets uploaded. InfoQ's checklist has
ten items. Six are mechanical and **`tests/test_infoq_article.py` enforces
them in CI**; four are people's work and are listed below so nobody forgets
them at upload time.

## Enforced by the test

| rule | how it is checked | if it fails |
|---|---|---|
| **2,000–3,000 words**, excluding code snippets | every word outside fenced code blocks and HTML comments — tables, captions, takeaways and the reference list all count (the strict reading) | cut prose or a table; never a number |
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
cd docs && pandoc article-infoq-CADEC.md -o "Group 3 – Six Reliability Layers Around an LLM Sorted Its Answers and Fixed Almost None.docx" --from gfm --resource-path=.
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
5. **Author bios.** Two, about 75 words each, under "About the authors" — still a placeholder comment in the markdown.
6. **The medRxiv reference.** The DOI answers 403 to automated fetches; open it once in a browser before submitting.

## What the takeaways must keep claiming

The body and the takeaways were aligned on 2026-09-08. A change to either side
must keep them consistent; the five claims and where the body carries them:

| takeaway | body |
|---|---|
| layers sort answers by trustworthiness, they do not fix them; judge on correct over all inputs | "It is a dial, not a staircase" — the yield column, the 128 / 49 / 177 sentence |
| the free check sorted answers; the three paid layers together changed one answer | the tier table; "What each layer bought"; the deletion replay (one shipped answer of 53, first run only) |
| the model reads, never remembers: 13–18 percent invented codes | the three-column table in "The pipeline" and the paragraph after it |
| repeat runs as a validation step; 70 percent agreement at temperature 0 | "We nearly published a result that was not there" |
| study the data before adding layers; not medicine; no layer recovers what was not read | "Where the system actually loses" and the first Monday practice |

Do not write "better than the paid layers" for the free check: the menu-shown
judge separates right from wrong more sharply (3.4–4.2× against 2.7–2.8×); its
verdict is read by nothing, which is a different claim.

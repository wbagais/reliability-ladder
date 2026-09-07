# docs/figures — where every figure comes from

Two kinds of source live here, and every PNG has one or the other:

| kind | source | regenerate with |
|---|---|---|
| Graphviz tables and diagrams | `<name>.dot` beside the PNG | `dot -Tpng -Gdpi=200 <name>.dot -o <name>.png` |
| Matplotlib charts | a Python script in this directory | `.venv/bin/python docs/figures/<script>.py` |

Needs `dot` (Graphviz, `brew install graphviz` / `apt install graphviz`) and
`matplotlib` (`pip install matplotlib`; a local-only extra, not in
`requirements.txt` because nothing tracked is read through it).

## The InfoQ article (`docs/article-infoq-CADEC.md`)

One script draws all of them: `make_infoq_figs.py`. It renders the three
`.dot` tables and draws the two charts. **Every number in the two charts is
read from the tracked report** `runs/archive/consolidated-2026-09-03/rerun/cadec.json`
— the `shipping_rules` section of each draw and `shipping_rules_mean` — which
`scripts/rerun_analysis.py` writes from `ladder.analysis.shipping_rules`.
Nothing is typed in but labels, colours and label positions;
`tests/test_infoq_figs.py` keeps it that way and pins the first draw's counts
to the published figure.

| figure | article | source | data |
|---|---|---|---|
| `infoq-fig1-ladder` | — (earlier revision) | `.dot` | hand-written table |
| `infoq-fig2-dial` | — (earlier revision) | `make_infoq_figs.py` | `shipping_rules_mean`: share shipped, accuracy, extra tokens |
| `infoq-fig3-funnel` | Figure 3 | `.dot` | hand-written from the report's error budget |
| `infoq-fig4-flow` | — (earlier revision) | `.dot` | hand-written |
| `infoq-fig5-shipped` | Figure 2 | `make_infoq_figs.py` | `draws["rerun-cadec-d0"].shipping_rules`: the four-way split, to a person, F1 |
| `fig7-pipeline-cadec` | Figure 1 | `.dot` | hand-written |

To regenerate after the report changes:

```bash
.venv/bin/python scripts/rerun_analysis.py --runs out/rerun-cadec-d0 out/rerun-cadec-d1 out/rerun-cadec-d2 \
    --arms judgemenu judgeshuffle lexarm spine --out runs/archive/consolidated-2026-09-03/rerun/cadec
.venv/bin/python docs/figures/make_infoq_figs.py
```

The first command needs the raw run under `out/` and the corpus (see
`docs/REPRODUCE.md`); the second needs only the tracked JSON. Regenerating
`infoq-fig5-shipped.png` from the tracked report on 2026-09-07 produced a
byte-identical PNG to the one published on 2026-09-04.

## The long articles (`docs/article-v3-CADEC.md`, `docs/article-v3.md`)

Numbered `fig0`–`fig21`, plus `figA`–`figE` for the GeoWebNews arm. All the
`figN-*.png` diagrams are hand-written `.dot` files whose numbers were copied
from `docs/decisions.md` at the time; regenerate with `dot` as above. The
exceptions, drawn by script:

| figure | script | data |
|---|---|---|
| `fig0-hero`, `fig2-flat` | `fig0.py`, `fig2.py` | numbers inside the script, from `docs/decisions.md` |
| `figA`–`figE` | `build_geo_figures.py` | numbers inside the script, from the geo arm's decisions entries |

Those three scripts still carry their numbers as literals. They predate the
tracked report and are not read by the InfoQ article; when one of them is
next touched, the fix is the same as for `make_infoq_figs.py`: read the
number from a tracked file and pin it with a test.

## House palette

From `fig7-pipeline-cadec.dot`, reused by every script: teal `#0c6469` where a
language model runs, grey `#5a6b73` where nothing but deterministic code runs,
ink `#121a1e`, rule `#c8d1d5`.

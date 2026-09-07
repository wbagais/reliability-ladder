# Reproducing the article — re-score, re-derive, re-run

Every number in `docs/article-infoq-CADEC.md` (and the dev-side numbers in
`docs/article-v3-CADEC.md` / `docs/article-v3.md`) is produced by one chain:

```
corpus + vocabulary ──▶ ladder/run.py (rungs 0–6) ──▶ out/<run>.*  (raw run: records, state rows, call traces, ledger, aggregates)
                                                            │
                        scripts/rerun_analysis.py ◀─────────┘   ladder/analysis.py + ladder/score.py do the arithmetic
                                    │
                                    ▼
      runs/archive/consolidated-2026-09-03/rerun/cadec.{md,json}   (tracked)  ──▶  the article's tables
                                    │
                                    ▼
                    docs/figures/make_infoq_figs.py  ──▶  docs/figures/infoq-fig*.png
```

You can enter that chain at three depths. Each layer needs strictly more than
the one before it.

| layer | what you regenerate | needs | time |
|---|---|---|---|
| **1. Re-score** | the figures, and every table from the tracked report | a clone, Python, matplotlib, graphviz | seconds |
| **2. Re-derive** | the reports themselves from the raw run | + the corpus, the vocabulary index, the raw run under `out/` | ~2 s per report |
| **3. Re-run** | the rungs, on this data or yours | + ollama with the two models, ~14 GB VRAM | ~1 h per CADEC base draw, ~13 h for the whole re-run |

The gold-only findings (`scripts/reproduce.py`) and the six-corpus free-check
matrix (`scripts/score_matrix.py`) are separate short chains, covered at the
end.

---

## Layer 1 — re-score from what is tracked (any machine, no corpus)

The consolidated re-run of 2026-09-03 is the run behind every dev-side number.
Its corpus-free files are tracked at `runs/archive/consolidated-2026-09-03/`
(see the README there): per run, `.aggregates.json`, `.ledger.jsonl`,
`.results.csv`, `.manifest.json`; plus the derived reports under `rerun/`.
`tests/test_runs_archive.py` pins that set.

**Open a number's source.** `runs/archive/consolidated-2026-09-03/rerun/cadec.md`
is the report the CADEC article was audited against, section by section:

| report section | feeds |
|---|---|
| Rung 0 per draw | F1 0.393 / 0.393 / 0.434, the detection × coding decomposition |
| Error budget per draw | Figure 3 (the funnel): missed, invented, on menu, lost pick |
| Rung 1 lanes per draw | the ACCEPT / BAND tiers and their correctness |
| Rung 3 by rung 1 lane | every code voting changed, and whether it was right |
| Rung 4 (blind, shipped) vs the menu arms | the judge's separation, blind 1.7× against menu-shown 3.4–4.2× |
| The shipped result and the policy arms | ships 53 / 53 / 51, yield, 177 / 177 / 187 to a person |
| **Every rung's verdict as a shipping rule** | **Figure 2 (first draw) and the shipping-rules table (three-draw means)** |
| Cost per rung | tokens, calls, p95 latency, records routed |
| Gold lane occupancy | the free check's ceiling: 32% / 68% on dev |
| Provenance | cache directory, git sha, dirty flag, start and finish per draw |

`rerun/cadec.json` is the same report as data; `rerun/finer.{md,json}`,
`rerun/cadec-s{0,1}.{md,json}` and `rerun/cadec-probe-*.json` are the FiNER,
S0/S1 and corruption-probe reports.

**Redraw the figures.**

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt pytest matplotlib
brew install graphviz        # or: apt install graphviz
.venv/bin/python docs/figures/make_infoq_figs.py
```

The two charts read `rerun/cadec.json`; the tables are `.dot` files. See
`docs/figures/README.md` for which figure comes from where.

**Check the chain holds.** These run in CI on every push, with nothing but
`requirements.txt` and pytest:

```bash
.venv/bin/python -m pytest tests/test_runs_archive.py tests/test_infoq_figs.py tests/test_analysis.py -q
```

`test_infoq_figs.py` asserts the first draw's rows equal the published figure
(88 / 28 / 23 / 91 for "ship everything", 39 / 2 / 0 / 12 / 177 / 49 for
ACCEPT, …) and that the figure script carries no hand-typed counts.

---

## Layer 2 — re-derive the reports from the raw run

The raw run — `<run>.r<N>.records.jsonl`, `<run>.state.jsonl`,
`<run>.r<N>.calls.jsonl` — carries corpus text and is never in git. It is
archived with checksums on the owner's machine at
`out/archive/reliability-ladder-b2-menu-f77617/` (CADEC and FiNER, 1.3 GB, call
traces included). To re-derive a report you need that directory, or a run of
your own (layer 3), plus the corpus and vocabulary it was scored against.

### 2a. Corpus and vocabulary

Each manifest names its corpus root and split directory. Place the data there;
`data/` is gitignored except the frozen CADEC split ids.

| manifest | corpus | root the manifest expects | licence | vocabulary index |
|---|---|---|---|---|
| `manifest.json` | CADEC | `data/cadec/data/cadec` | CSIRO, non-commercial, **non-transferable** — the owner only | `ladder/cache/snomed.sqlite` |
| `manifest.finer.json` | FiNER-139 | `data/finer/extracted` | CC-BY-SA-4.0, open | none (the tag set is the vocabulary) |
| `manifest.psytar.json` | PsyTAR | `data/psytar` | on request from the authors | `ladder/cache/snomed.sqlite` |
| `manifest.bc5cdr.json` | BC5CDR | `data/bc5cdr/CDR.Corpus.v010516` | open | `ladder/cache/mesh.sqlite` |
| `manifest.geo.json` | GeoWebNews | `data/gwn/Geocoding` | open | `ladder/cache/geonames.sqlite` |
| `manifest.lgl.json`, `manifest.trnews.json` | LGL, TR-News | `data/gwn/Corpora` | open | `ladder/cache/geonames.sqlite` |
| `manifest.linnaeus.json` | LINNAEUS | `data/linnaeus/manual-corpus-species-1.0` | open | `ladder/cache/taxonomy-clean.sqlite` |

Sources and the licence detail are in `README.md` ("Data — read before you
clone", "Five more corpora") and `docs/licences.md`. The SNOMED release the
CADEC numbers were measured against is `SnomedCT_Release_AU1000036_20260731`
(the AU extension — 16% of CADEC's gold, all drug mentions, exists only
there); a different release changes rung 1's verdicts and is a different
experiment.

Build the vocabulary index the manifest names:

```bash
python -m ladder.registry --build --release data/SnomedCT_Release_AU1000036_20260731     # SNOMED RF2 -> ladder/cache/snomed.sqlite
PYTHONPATH=. python3 scripts/build_mesh_index.py --help                                  # MeSH   -> ladder/cache/mesh.sqlite
PYTHONPATH=. python3 scripts/build_geo_index.py --dump allCountries.txt --out ladder/cache/geonames.sqlite
PYTHONPATH=. python3 scripts/build_taxon_index.py --help                                 # NCBI Taxonomy -> ladder/cache/taxonomy-clean.sqlite
```

Then the CADEC-side preprocessing, five steps in this order (all outputs are
gitignored, licence-bound data):

```bash
python -m ladder.keywords --build      # data/keywords.csv — the name->code table rung 0 resolves through
python -m ladder.clean    --build      # data/exclusions.csv — gold mentions that cannot be answered, with the reason
python -m ladder.embed    --build      # ladder/cache/keywords.* — S2's dense retrieval index (needs numpy, httpx, ollama)
python -m ladder.run init              # verify corpus + vocabulary, write the frozen splits
```

`data/splits/{dev,test,pool}.json` for CADEC are tracked and frozen: `init`
reads them back when they exist and refuses to regenerate them without
`--force` (a regenerated split is a different experiment). For the other
corpora `init --manifest <m>` writes them under the manifest's `splits_dir`
from the manifest's seed.

### 2b. The commands that wrote the four tracked reports

Run from the repository root with the raw run under `out/` (or point `--runs`
at the archive). Each takes about two seconds.

```bash
.venv/bin/python scripts/rerun_analysis.py \
    --runs out/rerun-cadec-d0 out/rerun-cadec-d1 out/rerun-cadec-d2 \
    --arms judgemenu judgeshuffle lexarm spine \
    --out runs/archive/consolidated-2026-09-03/rerun/cadec
```

```bash
.venv/bin/python scripts/rerun_analysis.py --manifest manifest.finer.json --full-vocabulary \
    --runs out/finer/rerun-finer-d0 out/finer/rerun-finer-d1 out/finer/rerun-finer-d2 \
    --arms judgemenu judgeshuffle spine \
    --out runs/archive/consolidated-2026-09-03/rerun/finer
```

```bash
.venv/bin/python scripts/rerun_analysis.py --runs out/rerun-cadec-s0-d0 out/rerun-cadec-s0-d1 out/rerun-cadec-s0-d2 \
    --out runs/archive/consolidated-2026-09-03/rerun/cadec-s0
```

(and the same with `s1`.) The corruption probe, model-free over the whole
corpus, one file per lexical mode and split:

```bash
PYTHONPATH=. .venv/bin/python -m ladder.probe --split all --lexical-mode exact \
    --json runs/archive/consolidated-2026-09-03/rerun/cadec-probe-all-exact.json
```

**What to expect.** On 2026-09-07 the CADEC report regenerated from the archive
byte-identical to the tracked file, apart from the sections added since. If a
line differs, one of three things changed: the code in `ladder/analysis.py` or
`ladder/score.py` (both tested — read the diff), the exclusions file, or the
vocabulary release. The report's "Provenance" section names the git sha and
cache directory of each draw, so the comparison is always against a stated
commit.

`scripts/rerun_analysis.py` only loads and prints; every function that does
arithmetic is in `ladder/analysis.py` (each names its denominator in its
docstring) and `ladder/score.py` (gold keyed by span, `exact` and `overlap`
pairings, four outcomes — `correct` / `outdated` / `abstained` / `incorrect` —
and `outdated` is never folded into `correct`). To add a number to the article,
add a function there with a test, then a section in `rerun_analysis.fmt`; do
not write a scratch script.

---

## Layer 3 — re-run the rungs

### 3a. Models

Both models run locally through [ollama](https://ollama.com); a remote provider
is refused unless `LADDER_ALLOW_REMOTE=1`, because the prompts carry corpus text.

```bash
ollama pull gpt-oss:20b && ollama pull ibm/granite4:micro-h
```

`manifest.model` is the one place a model is named: `extractor`
(`ollama/gpt-oss:20b`, rungs 0/2/3) and `judge` (`ollama/ibm/granite4:micro-h`,
rung 4 — a different family on purpose). Per-model request settings —
`max_tokens`, `reasoning_effort`, `timeout_s`, price — are registry data in
`ladder/models.yaml`. `manifest.model.temperature` is read and is part of the
cache key; every tracked manifest declares `0`. A run stamps the models it used
into `<run>.aggregates.json`.

### 3b. What a run is, and what it writes

```bash
PYTHONPATH=. .venv/bin/python -m ladder.run --manifest manifest.json ladder \
    --split dev --rungs 0-6 --plain --run-id <run-id>
```

Rungs execute in `manifest.rung_order` (`[0,1,2,3,4,5,6]`). Beside the
ledger, every run writes (`ladder/trace.py`):

| file | what |
|---|---|
| `out/<run>.r<N>.records.jsonl` | the record set as rung N left it |
| `out/<run>.state.jsonl` | one row per record per rung: code, span, zone, verdicts, `changed_this_rung`, outcome under both pairings |
| `out/<run>.r<N>.calls.jsonl` | every model call: full prompt, raw and normalised reply, cost, cached flag, document |
| `out/<run>.ledger.jsonl` | one row per record per rung: tokens, latency, usd, human minutes, verdict, reason |
| `out/<run>.results.csv`, `out/<run>.aggregates.json`, `out/<run>.manifest.json` | the per-rung table, the aggregate (models, cache dir, git sha, dirty flag), the configuration as run |

Useful flags: `--rungs 5,6 --predictions <run>.r1.records.jsonl` replays later
rungs over a saved snapshot at zero model calls; `--rung0-step S0|S1|S2`
selects the rung 0 prompt step (S2 is frozen in the manifest); `--extractor
<provider/model>` overrides the extractor for one run and is written into the
saved manifest; `--limit N` is a smoke run and its result is not a result for
the split; `--source gold` runs the ladder over the answer key (the
false-rejection floor). `python -m ladder.run gate` runs the fixture gate
first.

### 3c. The protocol behind the article: draws and arms

A **draw** is a run against a **cold cache**: `LADDER_LLM_CACHE=<dir>` names a
directory that must not exist yet, and the run stamps it into the aggregates.
The arms of a draw run second on the *same* cache, so their rung 0 is
byte-identical to the base's and only the arm's own rung is paid for (their
p95 latencies include cache hits and are never compared with the base's).
The arm manifests are one-key diffs from the base, pinned by tests:

| arm | manifest | the one key |
|---|---|---|
| judgemenu | `manifest.judgemenu.json` | `rungs.4.menu: "ranked"` |
| judgeshuffle | `manifest.judgeshuffle.json` | `rungs.4.menu: "shuffled"` |
| lexarm | `manifest.lexarm.json` | `rungs.1.lexical_mode: "contained"` |
| spine | — | rungs 5–6 replayed over the base's rung 1 snapshot |

The scripts, in the order the re-run used them:

```bash
scripts/consolidated_rerun.sh cadec 0      # base draw d0 (rungs 0–6, ~1 h), then its three arms on the same cache
scripts/rerun_spine.sh        cadec 0      # rungs 5–6 over d0's r1 snapshot, zero model calls
scripts/rerun_all.sh                       # the driver: draws 0,1,2 for CADEC then FiNER (~13 h)
scripts/rerun_steps.sh                     # S0 and S1 on CADEC dev, rung 0 only, three cold draws each
scripts/rerun_typecheck.sh                 # FiNER's type-check arm (rung 7, then 2–6) over each base draw's r1 snapshot
```

Each script refuses an existing cache directory and the held-out split. The
held-out split was spent once (Phase F, 2026-08-26, one run id, never re-run);
`--split test` is not part of any protocol here.

**Determinism, so you know what a difference means.** CADEC draws d0 and d1
were byte-identical (sha `c96289db` on rung 0); d2 diverged on a handful of
records and its F1 is 0.434 against 0.393. FiNER's three draws were
byte-identical. A prompt that diverged, replayed eight times in isolation,
gave one reply; the divergence happens only inside a full run and is
unexplained (server state between requests is the suspect). So: one draw is
a measurement, three draws bound the spread, and a difference smaller than
d0-vs-d2 is not a result.

### 3d. On new data

To run the ladder on a corpus of your own:

1. **Before booking any GPU time**, two model-free checks, a second each:
   `scripts/gatecheck.py --manifest <m>` predicts the free check's ceiling
   from gold alone (FiNER: 0.0% — numerals share no token with English tags,
   so rung 1 cannot fire whatever the model does), and
   `scripts/crosscheck.py --manifest <m>` reads every declared fact back from
   an independent source. `docs/three-checks.md` explains both.
2. **An adapter** `ladder/corpus_<name>.py` exposing `load_corpus(root, …)`
   and `read_split(splits_dir, split)` in the shape of `ladder/corpus.py`
   (gold keyed by span, `GoldMention`). `scripts/prep_corpus.py` reads a
   corpus and drafts its arm, refusing to guess what it cannot measure.
3. **A manifest** copied from the nearest one, naming the corpus root, the
   split directory, the vocabulary index and the prompts block; a vocabulary
   index in SNOMED's schema (`scripts/build_*_index.py` are the three
   worked examples).
4. `python -m ladder.run --manifest <m> init`, then `ladder --split dev` as
   in 3b, then `scripts/rerun_analysis.py --manifest <m> --runs out/<run>`
   for the report, or `scripts/score_matrix.py` for the free-check row.

`docs/scaling-design.md` and `docs/three-checks.md` are the design notes for
this path; `docs/decisions.md` records what each of the six added corpora
taught.

---

## The two shorter chains

**Gold-only findings.** Five of the article's claims need no model: they are
re-derived from gold, the committed ledger and records on disk.

```bash
PYTHONPATH=. python3 scripts/reproduce.py            # or --claim accept_lane
```

**The six-corpus matrix** (`matrix.csv` at the root; the "two families"
finding). `scripts/run_matrix.sh` runs every model on every corpus, rungs 0–1,
into `out/matrix/<corpus>-<model>-d<N>/`; `scripts/score_matrix.py` scores
the newest run in each cell against its own manifest's gold and writes the
table. The raw cells live on the machine that ran them (not the CADEC
owner's); the tracked result is `matrix.csv`.

---

## Before you push anything

```bash
python3 scripts/preflight.py --history     # corpus text, key-shaped strings, forbidden paths — in the tree AND the history
```

and run the suite the way CI does — `python:3.12-slim`, `requirements.txt` +
pytest and nothing else, so a test that needs numpy, httpx, torch or the git
binary fails there whatever it does on your machine:

```bash
python -m venv /tmp/civenv && /tmp/civenv/bin/pip install -r requirements.txt pytest
/tmp/civenv/bin/python -m pytest tests/ -q -m "not integration"
```

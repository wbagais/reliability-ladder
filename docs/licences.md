# Data licences — read before you touch `data/` or push anything

Two of the three data sources in this project carry licences with teeth. Neither
can be redistributed, so neither is in the repo, and neither ever will be.

## CADEC v3 — CSIRO Data Licence

- **Where** — <https://data.csiro.au/collection/csiro:10948> · DOI
  `10.4225/08/570FB102BDAD2` · cite Karimi, Metke-Jimenez, Kemp & Wang (2016);
  corpus paper *J. Biomedical Informatics* 55 (2015).
- **Terms** — royalty-free, non-exclusive, **non-commercial**, and
  **non-transferable**. The corpus paper states the data is for research
  purposes only. CSIRO retired this licence for new collections in July 2021,
  so older collections like CADEC still carry it.

Three consequences that shape the repo:

1. **You cannot redistribute the corpus.** Not in the repo, not as a release
   asset, not in a committed notebook whose output cells contain post text.
   `.gitignore` covers `data/2016-04-15_Karimi_Sarvnaz_*` and `data/CADEC*` from
   day zero.
2. **Each person accepts the licence individually** — it is non-transferable, so
   "my teammate downloaded it" is not a licence.
3. **This work cannot become commercial** on this corpus. If it ever does, the
   corpus is out and the study needs a different dataset.

`data/splits/*.json` stores **document IDs only** — no post text, no
annotations, no codes. Anyone with their own licensed copy reproduces the exact
splits from them; nobody obtains the corpus from this repo. Quote sparingly in
the article: short illustrative snippets are normal academic practice, an
appendix of post text is redistribution.

## SNOMED CT — affiliate licence

- **Where** — this project uses a local RF2 release
  (`SnomedCT_Release_AU1000036_20260731`, the Australian edition, which contains
  the international core).
- **Terms** — SNOMED International affiliate licence. Free for use in member
  countries, but the release files themselves are not ours to hand on.

`.gitignore` covers `data/SnomedCT_Release_*`. The derived index
(`ladder/cache/snomed.sqlite`, ~365 MB) is also ignored: it contains the full
description table, so it is a redistribution of the release by another name.
Rebuild it in seconds from your own copy:

```bash
python -m ladder.registry --build --release data/SnomedCT_Release_<yours>
```

Record the release directory name in `manifest.json`. Two releases a year add
and inactivate codes, so a rung-1 result without a pinned release is not
reproducible — 11% of CADEC's codes are already inactive in this one.

### The `out/` trap

`out/` is gitignored, and not only because run output churns. The analysis JSON
files carry worked examples, and a worked example is a **quotation from the
corpus**: `out/rung1_floor.json` stores 45 characters of surrounding post text
for every rejection it reports, and `out/rung1_detection.json` stores the mention
strings it wrongly accepted. Both are exactly what makes them useful to read, and
both are corpus text. They stay local; the aggregate numbers derived from them
are what goes in the docs.

Rebuild either in minutes:

```bash
python -m ladder.calibrate --split all --sweep --json out/rung1_floor.json
python -m ladder.probe --split all --json out/rung1_detection.json
```

## MedDRA — not used, deliberately

MedDRA needs a subscription, and the only MedDRA artefact available here is
`meddra_codes.csv`, which ships *inside* CADEC and is derived *from* it (its
columns include `occurrences` and `posts`). Using it as rung 1's existence check
would be leakage: the check would accept exactly the codes the answer key uses
and reject everything else. MedDRA annotations are parsed and carried on each
record, and are neither checked nor scored. See `manifest.json` →
`vocabulary.meddra_note`.

## Nothing else is committed

There is no other dataset in this repository. An earlier track shipped a
redistributable demo dataset; it was retired on 2026-08-22 and removed. If you
add one, put it through the same three questions: may it be redistributed, does
it embed document text, and is the licence transferable to your co-authors.

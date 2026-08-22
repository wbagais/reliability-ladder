# Getting Started

## Prerequisites

- Python 3.11+ (developed on 3.14).
- A **licensed** CADEC v2 copy. Each person accepts the CSIRO Data Licence individually. See [[data-licences]].
- A SNOMED CT RF2 release. Affiliate licence. AU edition `AU1000036_20260731` is what the manifest pins.
- Optional: Ollama, for rung 0. Not needed for rungs 1–2.

Nothing licensed is in the repo, and none can be. `data/` is gitignored.

## 1 — Environment

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt pytest
```

- `requirements.txt` is pinned deliberately. An unpinned dep can move a measured number silently.
- Only `pyyaml` is required to run rungs 1–2.

## 2 — Place the data

Paths come from `manifest.json`, resolved relative to the manifest. See [[manifest]].

| Manifest key | Expected path |
|---|---|
| `corpus.cadec_root` | `data/cadec/data/cadec` |
| `vocabulary.snomed_release_dir` | `data/SnomedCT_Release_AU1000036_20260731` |
| `vocabulary.meddra_csv` | `data/meddra_codes.csv` |

- If your CADEC download unpacks under its DAP name, symlink rather than rename: `ln -sfn 2016-04-15_Karimi_Sarvnaz_10948v3 data/cadec`.
- Verify your copy against `docs/cadec-checksums.txt`.

## 3 — Build the vocabulary index

```bash
python -m ladder.registry --build --release data/SnomedCT_Release_AU1000036_20260731
```

- Writes `ladder/cache/snomed.sqlite`, about 365 MB, in roughly 9 seconds.
- One time only. Skip if the file exists.
- Reproducible: a rebuild produces identical stats and lookups.

## 4 — Verify the install

```bash
python -m ladder.run init
```

Expect:

- `1250 documents, 9111 gold mentions`
- a vocabulary line with `concepts: 721187`
- `gate : real code resolves, fake code does not`
- three split lines marked `(frozen)`

Never pass `--force`. It regenerates the frozen splits. See [[corpus]].

## 5 — Run the harness gate

```bash
python -m ladder.run gate
```

- 13 hand-made records, several deliberately broken, checked against expected verdicts.
- Must end `GATE PASSED`. If it does not, stop — nothing above it is trustworthy.
- Detail in [[testing]].

## 6 — First run

```bash
python -m ladder.run ladder --split test --source gold --run-id first
```

- `--source gold` feeds the answer key in as if a model produced it.
- This is a **control, not an accuracy test**. Every rejection is false by construction, which is what makes it measure rung 1's own error floor.
- Writes four files to `out/`. See [[runner]].

Expect `ACCEPT=171 BAND=222 REJECT=0`, coverage `0.435`.

## 7 — Model-free measurements

```bash
python -m ladder.calibrate --split all --sweep
```

```bash
python -m ladder.probe --split all
```

Both run against the answer key with zero model calls. See [[measurement]].

## Before every push

```bash
python scripts/preflight.py --history
```

- Scans the working tree **and git history** for corpus text, key-shaped strings and forbidden paths.
- Must exit 0. CI runs it too and blocks the pipeline.

## Next

- Understand the flow → [[architecture]]
- Understand a rung → [[rungs]]
- Something failed → [[troubleshooting]]

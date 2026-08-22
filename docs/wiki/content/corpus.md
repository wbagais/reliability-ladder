# Corpus & splits

`ladder/corpus.py`

## CADEC

- CSIRO Adverse Drug Event Corpus. Patient posts from AskaPatient, two drug groups: diclofenac (Arthrotec, Voltaren) and lipitor.
- **1,250 documents · 9,111 gold mentions · 8,666 carrying a SNOMED code.**
- Manifest records `CADEC v2 (corpus); DAP collection v3 (csiro:10948)`. Verify your copy against `docs/cadec-checksums.txt`.
- Licence: non-commercial, **NON-TRANSFERABLE**. See [[data-licences]].

## Four annotation layers

`load_corpus()` reads all four. `cadec_root` points at the directory containing them.

| Directory | Contributes | Human-authored? |
|---|---|---|
| `text/` | the post body — becomes `sources` | no — the raw post |
| `original/` | the CADEC label only (ADR/Symptom/Disease/Finding/Drug), joined `TTn` → `Tn` | **yes** |
| `sct/` | **drives the mention list** — one `GoldMention` per `TTn`, and supplies `text`, `spans`, `sct`, `gold_kind` | **yes** |
| `meddra/` | the gold MedDRA codes, joined on `TTn` | **yes** |

`original/` carries the same offsets but the parser does not read them. A span annotated in `original/` with no `sct/` entry never becomes a `GoldMention`.

- Three of the four are answer key. Only `text/` is available to [[r0]] at inference time.
- The annotator's label in `sct/` (`267036007 | Dyspnoea | ...`) is **discarded at parse time**. `GoldMention` keeps only the code, so nothing downstream can depend on an annotator's wording. Keeping it would let [[r1]] match against the label and ACCEPT everything.

## Why three splits

| Split | Docs | Mentions | Purpose |
|---|---|---|---|
| `dev` | 40 | 287 | where you are allowed to **look**. τ is swept here |
| `test` | 60 | 393 | held out, touched once, at the end |
| `pool` | 1,150 | 8,431 | the rest — model-free characterisation, future work |

- Any setting chosen by inspecting results is fitted to what you inspected. τ, `lexical_mode`, `finding_scope` were all picked that way. Doing it on `test` means the test number is no longer held out.
- `pool` is **not** a training set — nothing is trained. It is what makes `--split all` statistically meaningful: the 0.13 % floor comes from 9,111 mentions, not 393.

## Why document-level

- Mentions from one post share its wording and its annotator. A mention-level split leaks dev into test.
- One post is one unit.

## Why stratified

- Stratified by drug family, largest-remainder allocation to hit exactly n documents.
- Adverse-event profiles differ sharply between a statin and an NSAID. Unstratified sampling could hand you a test set that is 80 % one drug.

## Frozen

- `seed=42`, sorted then shuffled — deterministic.
- `data/splits/*.json` holds **document IDs only**. No text, no annotations. It is committed.
- Anyone with their own licensed copy reproduces the identical split. Nobody obtains the corpus from the repo.
- `run init` prints `(frozen)` when reading existing splits. **Never pass `--force`.**

## Gold as a control

`gold_as_records()` dresses the answer key as rung-0 output.

- Not a baseline and not a rung — a **control**. Every rejection is false by construction, so it measures the gate's own error floor.
- Reported as `--source gold`, never as a rung 0 number.
- Post-coordinated gold: 252 mentions are `A + B`, 3 are `A or B`. `gold_to_record` takes the first code — rung 1 asks whether *a* code is real and correctly typed, not whether the expression is complete.

## Related

- [[data-licences]] · [[record]] · [[measurement]] · [[manifest]]

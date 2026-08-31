# BioMistral as the rung-0 extractor — a null, and the mechanism is greedy decoding

**Negative result, deliberately merged.** BioMistral-7B was rejected as the
rung-4 *judge* on 2026-08-25, and the article has since carried the claim
"domain adaptation cost instruction-following" — resting on **one role**. The
model had never run as an extractor, so the strongest domain-knowledge question
in the project ("is a domain-adapted model better at the domain?") was being
answered from a role it never got to play. This MR runs it, in the role whose
prompts are 2–3x longer than the judge's. Three decisions entries dated
2026-08-31 in `docs/decisions.md` carry the full story; six runs plus the
diagnosis and prompt-token JSONs are archived to
`out/archive/biomistral-rung-0-af8e96/`.

## The result

Protocol exactly as registered in `CLAUDE.md`: CADEC dev, 40 documents, frozen
`manifest.json`, rungs 0–1, `--extractor ollama/biomistral:7b-q5_k_m` the only
override, three draws each against its own cold cache.

| | value |
|---|---|
| predictions / gold | **3 / 226** |
| F1 exact / overlap | **0.0087 / 0.0087** |
| detection recall | 0.0088 |
| documents `json_decode` | **36 of 40** |
| completion tokens, whole split | **621** (~15 per document) |
| draws | **byte-identical sha256** |

The reply is `" {"` and then end-of-sequence — the same string as the
2026-08-25 judge failure. BioMistral is bit-reproducible, which puts it with
the four dense models in the five-model table rather than with gpt-oss.

**The ACCEPT lane is NOT measurable here** (n = 1). The arm contributes no row
to the five-model table and has not been given one.

## The prompt-token distribution was registered BEFORE the run

That is what makes the null readable rather than mysterious — a distribution
measured after an empty run is a distribution fitted to its own answer. Exact
counts from BioMistral's own tokenizer, sent straight to ollama at
`max_tokens=1` so the probe could not seed the run's cache:

- **FIND**, 40 documents: min 828, median 918, p90 1050, max 1134
- **PICK**, 62 batched calls (sized on gold spans): min 520, median 1404, max 2339
- `over_430`: **100.0% on both**

## The diagnosis is the result, because the mechanism is not what was registered

The 2026-08-28 rule was applied — *a model comparison measures your harness
until you prove otherwise* — and all 40 FIND prompts were replayed through raw
`httpx` with no ladder code in the path.

1. **Not our harness, and not truncation.** The raw replay answers the same
   4 of 40, and `finish_reason` is `"stop"` on **all 40**, never `"length"`.
2. **There is a cliff, and it is at ~856 tokens, not ~430.** 0 of 31 prompts
   above it answer; 4 of 9 at or below do; it is content-dependent right at the
   boundary (ARTHROTEC.107 answers at 856, ARTHROTEC.139 EOSes at 856). The
   judge role put the same wall at ~500. **A threshold that doubles with the
   role is not a token count**, so "EOSes above N tokens" is the wrong shape of
   claim.
3. **Not the prompt shape.** Stripping the few-shot block takes the prompt to
   520 tokens and it still answers `" {"`; a 77-token bare ask answers fine.
4. **It is greedy decoding.** Same failing prompt: temperature 0.0 EOSes, 0.7
   answers 2 of 3 samples, 1.0 answers **3 of 3**, with well-formed `mentions`
   JSON each time. The EOS token is merely the argmax, and not by much.

## The off-protocol temperature arm, which is what turns the null into an answer

Since (4) means the protocol run measures an interaction between this model and
the project's temperature-0 policy, a temperature-1.0 arm was run — three draws,
temperature injected by wrapping `Caller.__call__` **in scratch, production
untouched**, and labelled off-protocol wherever it is quoted (every row of the
five-model table is temperature 0).

| | temp 0 | temp 1.0, d0 / d1 / d2 |
|---|---|---|
| documents answered | 4 / 40 | 6 / 8 / 15 |
| predictions | 3 | 10 / 12 / 18 |
| F1 exact | 0.0087 | 0.0169 / 0.0504 / 0.0492 |

The escape is real and roughly triples the output — and still lands a **factor
of four below the un-adapted `mistral:7b-instruct` (0.206)**, which produced 259
predictions at temperature 0 on this identical split and configuration.

**So "domain adaptation cost instruction-following" now holds in two roles.**
The failure is transport, not knowledge, and that is precisely why it is fatal:
a rung that cannot deliver a reply cannot be measured on the domain it knows.
What the model emits when it emits anything is not nonsense — the protocol run
produced |Muddled thinking| on an exact lexical match and rung 1 ACCEPTed it.

## What changed in tracked files

- **`ladder/models.yaml`** — `biomistral:7b-q5_k_m` resized from the
  judge-shaped 512/120 to **2000/180, matching `mistral:7b-instruct` exactly**.
  At 512 a truncation and an instant EOS are the same observation, and telling
  those two apart is the whole point of the arm; matching the control's budget
  is also what leaves one variable. TDD'd — failing test first
  (`test_biomistral_carries_the_instruct_extractor_budget`); the two superseded
  value assertions were rewritten rather than deleted.
- **`.gitignore`** — `.llm_cache.*`, the per-draw cache directories. A *draw* is
  a run against a cold cache, so a three-draw arm keeps three side by side.
- **`CLAUDE.md`** — the TODO is closed with its result, its caveats, and the
  explicit instruction that the arm gets no five-model-table row.
- **`docs/article-v3.md`** — the standing limitation *"we tested a domain-adapted
  model in one role only"* is **discharged**, with the numbers that discharge it.
- **`docs/decisions.md`** — three entries: the pre-run registration, the protocol
  null, the diagnosis and the temperature arm.

No production behaviour changes. `manifest.json` is byte-unchanged, no shipped
number moves, and nothing about the ladder's configured path was touched.

## Flagged, not fixed: `manifest.model.temperature` is read by nothing

Found while reading the temperature path. `Caller.__call__` defaults to
`temperature=0.0` and no rung passes one except rung 3, which takes its own from
`manifest.rungs.3.temperature`. So the key that looks like the answer to "what
temperature produced this number" is decoration, and the real answer is a
default in code — the same shape as the pre-2026-08-24 model fallback and the
5.9-point manifest/arms gap. Wiring it changes every rung 0 number in the
project and `manifest.json` is edited jointly, so it is recorded and left for
its own session.

## CI

Verified under CI's own conditions before pushing, not just locally:
`git archive HEAD` into a clean tree (tracked files only — no corpus, no
`data/exclusions.csv`, no `ladder/cache/`), fresh venv holding only
`requirements.txt` + pytest. **685 passed, 23 skipped, 10 deselected.**
`preflight.py --history` exits 0; the licence-scan script exits 0; the `wiki`
job does not trigger (no `docs/wiki/**` changes).

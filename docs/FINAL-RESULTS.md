# Final results

*50 measured cells · 7 corpora · 5 model families · dev and test · rungs 0–1*

Every cell derived from its corpus's own manifest by changing one key,
`model.extractor`, and verified after running against the manifest it saved
beside its results. One draw per cell: three draws were measured byte-identical
on three corpora at temperature 0, so a repeat is the same computation, not a
sample.

---

## The headline

| family | corpora | lane fires | of that, correct |
|---|---|---|---|
| **clinical** | CADEC, PsyTAR, BC5CDR | **7 – 32%** | **80 – 100%** |
| **gazetteer** | GeoWebNews, LGL, TR-News | **20 – 76%** | **6.7 – 26%** |
| taxonomy | LINNAEUS | 0 – 15% | 75 – 100% *(n = 3–8)* |
| tag set | FiNER-139 | **0.0%** | — |

**Clinical vocabularies give a small lane that is right. Gazetteers give a large
lane that is wrong.** Both columns invert together and neither band overlaps:
the worst clinical correctness is 80.0%, the best gazetteer correctness is
25.8%; the largest clinical lane is 32.0%, the smallest gazetteer lane is 20.3%.

**The occupancy inversion was not expected.** The check that reaches furthest is
the one you can trust least, so occupancy predicts nothing about correctness in
either direction — which is why the two are reported separately and never fused.

**And it is not about medicine.** Three ontologies behave alike — SNOMED CT
twice, MeSH once — and one gazetteer behaves the same way across three corpora
built on it. What the clinical vocabularies share is that the term and the
writing come from overlapping registers: `weight gain`, `seizures`,
`hypertension` are both what a person writes and what the ontology calls the
concept. `Britain` against *United Kingdom of Great Britain and Northern
Ireland* is not.

---

## Every cell

`occ` is ACCEPT ÷ records. `correct` is over `scored` — the ACCEPT records that
sit on a gold mention, which is smaller than ACCEPT because a model finds spans
the annotators did not mark. `BAND` is the accuracy of what the check declined
to endorse, and `sep` is `correct ÷ BAND`: **whether the lane sorted anything at
all**, which precision alone cannot show.

### Clinical

| corpus | split | model | recs | ACCEPT | occ | scored | correct | BAND | sep |
|---|---|---|---|---|---|---|---|---|---|
| BC5CDR | dev | gpt-oss:20b | 156 | 34 | 21.8% | 30 | **96.7%** | 45.7% | 2.1× |
| BC5CDR | dev | granite4:micro-h | 71 | 5 | 7.0% | 5 | **100.0%** | 36.8% | 2.7× |
| BC5CDR | dev | llama3.1:8b | 162 | 27 | 16.7% | 26 | **100.0%** | 29.7% | 3.4× |
| BC5CDR | dev | mistral:7b | 119 | 15 | 12.6% | 13 | **100.0%** | 40.5% | 2.5× |
| BC5CDR | dev | qwen3:8b | 98 | 19 | 19.4% | 19 | **100.0%** | 41.0% | 2.4× |
| BC5CDR | test | gpt-oss:20b | 223 | 58 | 26.0% | 57 | **98.2%** | 37.0% | 2.7× |
| BC5CDR | test | granite4:micro-h | 121 | 20 | 16.5% | 19 | **100.0%** | 28.1% | 3.6× |
| BC5CDR | test | llama3.1:8b | 208 | 42 | 20.2% | 37 | **94.6%** | 26.6% | 3.6× |
| BC5CDR | test | mistral:7b | 180 | 33 | 18.3% | 31 | **93.5%** | 24.5% | 3.8× |
| PsyTAR | dev | gpt-oss:20b | 248 | 77 | 31.0% | 47 | **80.9%** | 41.2% | 2.0× |
| PsyTAR | dev | granite4:micro-h | 274 | 51 | 18.6% | 31 | **90.3%** | 33.3% | 2.7× |
| PsyTAR | dev | llama3.1:8b | 232 | 72 | 31.0% | 42 | **81.0%** | 40.0% | 2.0× |
| PsyTAR | dev | mistral:7b | 307 | 60 | 19.5% | 39 | **84.6%** | 35.4% | 2.4× |
| PsyTAR | dev | qwen3:8b | 97 | 29 | 29.9% | 17 | **88.2%** | 42.3% | 2.1× |
| PsyTAR | test | gpt-oss:20b | 323 | 101 | 31.3% | 67 | **82.1%** | 43.8% | 1.9× |
| PsyTAR | test | granite4:micro-h | 381 | 83 | 21.8% | 53 | **81.1%** | 21.4% | 3.8× |
| PsyTAR | test | llama3.1:8b | 284 | 91 | 32.0% | 57 | **84.2%** | 34.3% | 2.5× |
| PsyTAR | test | mistral:7b | 366 | 69 | 18.9% | 55 | **80.0%** | 28.8% | 2.8× |
| **CADEC** | dev | *3 draws, other machine* | — | — | **32%** | — | **75.5 / 75.5 / 82.4%** | 26.9 / 26.9 / 30.4% | 2.7–2.8× |

### Gazetteer

| corpus | split | model | recs | ACCEPT | occ | scored | correct | BAND | sep |
|---|---|---|---|---|---|---|---|---|---|
| GeoWebNews | dev | gpt-oss:20b | 214 | 136 | 63.6% | 128 | **25.8%** | 13.0% | 2.0× |
| GeoWebNews | dev | granite4:micro-h | 153 | 31 | 20.3% | 26 | **15.4%** | 2.8% | 5.5× |
| GeoWebNews | dev | llama3.1:8b | 241 | 109 | 45.2% | 88 | **11.4%** | 8.5% | 1.3× |
| GeoWebNews | dev | mistral:7b | 178 | 104 | 58.4% | 97 | **17.5%** | 9.5% | 1.8× |
| GeoWebNews | dev | qwen3:8b | 95 | 63 | 66.3% | 56 | **25.0%** | 13.3% | 1.9× |
| LGL | dev | gpt-oss:20b | 275 | 174 | 63.3% | 150 | **19.3%** | 6.5% | 3.0× |
| LGL | dev | granite4:micro-h | 111 | 33 | 29.7% | 27 | **22.2%** | 0.0% | — |
| LGL | dev | llama3.1:8b | 128 | 85 | 66.4% | 68 | **10.3%** | 4.8% | 2.2× |
| LGL | dev | mistral:7b | 154 | 114 | 74.0% | 97 | **14.4%** | 0.0% | — |
| LGL | dev | qwen3:8b | 121 | 88 | 72.7% | 79 | **17.7%** | 0.0% | — |
| LGL | test | gpt-oss:20b | 440 | 271 | 61.6% | 230 | **17.8%** | 12.5% | 1.4× |
| LGL | test | granite4:micro-h | 201 | 47 | 23.4% | 40 | **12.5%** | 4.7% | 2.7× |
| LGL | test | llama3.1:8b | 145 | 87 | 60.0% | 76 | **23.7%** | 7.7% | 3.1× |
| LGL | test | mistral:7b | 252 | 165 | 65.5% | 143 | **16.8%** | 6.9% | 2.4× |
| TR-News | dev | gpt-oss:20b | 253 | 183 | 72.3% | 160 | **16.9%** | 19.4% | 0.9× |
| TR-News | dev | granite4:micro-h | 178 | 66 | 37.1% | 58 | **10.3%** | 6.7% | 1.6× |
| TR-News | dev | llama3.1:8b | 213 | 114 | 53.5% | 99 | **13.1%** | 15.6% | 0.8× |
| TR-News | dev | mistral:7b | 166 | 119 | 71.7% | 99 | **12.1%** | 18.8% | 0.6× |
| TR-News | dev | qwen3:8b | 105 | 80 | 76.2% | 71 | **15.5%** | 25.0% | 0.6× |
| TR-News | test | gpt-oss:20b | 414 | 295 | 71.3% | 253 | **13.4%** | 3.2% | 4.2× |
| TR-News | test | granite4:micro-h | 217 | 89 | 41.0% | 75 | **6.7%** | 2.4% | 2.8× |
| TR-News | test | llama3.1:8b | 328 | 208 | 63.4% | 161 | **9.9%** | 8.7% | 1.1× |
| TR-News | test | mistral:7b | 234 | 178 | 76.1% | 156 | **9.6%** | 0.0% | — |

### The two that sit outside both families

| corpus | split | model | recs | ACCEPT | occ | scored | correct | BAND |
|---|---|---|---|---|---|---|---|---|
| FiNER-139 | dev | gpt-oss:20b | 324 | 0 | **0.0%** | 0 | — | 39.4% |
| FiNER-139 | dev | granite4:micro-h | 188 | 0 | **0.0%** | 0 | — | 2.9% |
| FiNER-139 | dev | llama3.1:8b | 691 | 0 | **0.0%** | 0 | — | 5.2% |
| FiNER-139 | dev | mistral:7b | 238 | 0 | **0.0%** | 0 | — | 2.2% |
| FiNER-139 | dev | qwen3:8b | 96 | 0 | **0.0%** | 0 | — | 44.4% |
| LINNAEUS | dev | gpt-oss:20b | 59 | 9 | 15.3% | 8 | 100.0% | 10.8% |
| LINNAEUS | dev | granite4:micro-h | 103 | 5 | 4.9% | 4 | 75.0% | 0.0% |
| LINNAEUS | dev | mistral:7b | 122 | 3 | 2.5% | 3 | 100.0% | 0.0% |
| LINNAEUS | dev | llama3.1:8b | **0** | 0 | 0.0% | 0 | — | — |

**FiNER's zero is structural, not a low score.** The spans are numerals (`47.6`)
and the tags are English phrases (`EffectiveIncomeTaxRateContinuingOperations`),
so the two share no token by construction — on any run, with any model, forever.
Five model families and 1,537 records confirm it.

**LINNAEUS is consistent with the clinical band and confirms nothing.** Three,
four and eight scored records. `gatecheck` predicted a 4.8% ceiling from gold
before any of it ran, and `llama3.1:8b` produces no records at all after three
separate fixes — a prompt rewrite, a vocabulary filter, and a cap on the
few-shot passage.

---

## The paid layers

Rungs 0–6 on PsyTAR, `gpt-oss:20b`, three draws:

| rung | routed |
|---|---|
| 2 · self-correction | **0** |
| 3 · sampled voting | **0** |
| 4 · LLM judge | **0** |
| coverage | 31.048%, identical to rungs 0–1 alone |

Byte-identical in all three draws. On CADEC self-correction fired 2–3 times and
corrected nothing, voting changed almost nothing, and the judge's verdict is
read by nothing downstream. **That was a one-corpus claim until this run.**

**And PsyTAR is where rung 2 should have had work.** Rung 1's semantic check
encodes CADEC's annotation guide and wrongly rejects codes like |Suicide| there
— 37 correct gold records contradicted. Rung 2 fires only on REJECT. So the one
corpus where self-correction had something real to correct is the one where it
fired zero times, which means **rung 1 produces no REJECTs on model output at
all**, only on gold. The reject path is dead in production.

---

## What must travel with these numbers

**Retrieval is not uniform.** CADEC and PsyTAR retrieve densely over an
embedding index built from SNOMED; the other five retrieve lexically, because
no such index exists for a gazetteer, a taxonomy, a tag set or MeSH. On CADEC
that substitution was measured to cost ~21 points of recall@20 — larger than
most differences in this table. **A lexical row and a dense row are not
comparable.**

**CADEC is a reference, not a row.** It was produced on different hardware, and
floating point differs between a CPU-split model and a GPU-resident one:
identical manifest, corpus and seed gave 23 records on one and 22 on the other.
Two machines are two experiments.

**A separation ratio has a small denominator in it.** TR-News reads 0.6–0.9× on
dev and 1.1–4.2× on test, and the improvement came from BAND *collapsing* from
19.4% to 3.2% while ACCEPT's own accuracy fell. The earlier claim that the check
is actively harmful there did not survive held-out data and is retracted in
`docs/decisions.md`.

**Small scored sets are labelled and not hidden.** BC5CDR's dev 100%s are over
5 to 30 records; the test split took them to 19–57 and they came off to
93.5–100%, which is what a small-sample artefact does when the sample grows.
LINNAEUS's cells are 3, 4 and 8 records and are not used for any claim.

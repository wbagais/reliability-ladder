# Glossary

## Project terms

- **Rung** — one reliability layer wrapped around the model call. Seven of them, IDs fixed by the brief. See [[rungs]].
- **Zone** — where the ladder has routed a record so far. `NEW` `ACCEPT` `BAND` `REJECT` `ABSTAIN` `ESCALATE` `VERIFIED` `RESOLVED`. See [[record]].
- **BAND** — passed validation but unverifiable by string comparison. Not a rejection. **56.8 % of even a perfect answer set.**
- **Verdict** — what [[r1]] *concluded*. Distinct from zone, which is where the record *is*.
- **Observe vs gate** — rung 1 judges without routing (`observe`, default) or filters (`gate`).
- **Control** — the gold standard fed in as if it were model output. Measures the gate's own error floor. **Not a baseline and not an accuracy test.**
- **Coverage** — fraction of records still shipping an answer.
- **Yield** — fraction of all records that are both answered and correct.
- **Withheld** — the answer [[r5]] preserved when it abstained. Withdrawal, never deletion.
- **Error floor / false-rejection floor** — rejections made against gold, all of which are wrong by construction. **12 / 9,111 = 0.13 %.**
- **Ablation** — one variable changed, everything else held. `run ablate` runs each rung alone on identical input.
- **Marginal cost** — a rung's own spend divided by the errors it prevented. Two currencies, never fused.

## Corpus terms

- **CADEC** — CSIRO Adverse Drug Event Corpus. 1,250 patient posts, 9,111 annotated mentions.
- **Mention** — one annotated span in one post. **The unit of evaluation.**
- **Discontinuous mention** — a mention whose span is in several pieces ("hair … breakage"). 11.7 % of reaction mentions.
- **Post-coordinated gold** — gold that is two codes, `A + B`. 252 mentions. 3 more are disjunctions, `A or B`.
- **CONCEPT_LESS** — "no code in the vocabulary is correct". A positive, scoreable answer, not an abstention. 445 gold mentions.
- **ADR** — CADEC's adverse-drug-reaction label. **A causal attribution by the annotator**, deliberately not reproduced — it collapses into `reaction`.
- **dev / test / pool** — 40 / 60 / 1,150 documents. See [[corpus]].

## Vocabulary terms

- **SNOMED CT** — the clinical terminology. Codes are `concept_id`s.
- **RF2** — SNOMED's release format. `Snapshot/Terminology/*.txt`.
- **AMT** — Australian Medicines Terminology, an extension module. **100 % of CADEC's drug codes.**
- **Retired / inactive** — a concept SNOMED no longer asserts. Still real, still in the release. **11 % of CADEC's codes.**
- **FSN** — fully specified name, e.g. `Dyspnea (finding)`.
- **Preferred term vs synonym** — a concept has many terms. `lexical_match` runs over **all** of them.
- **OLS4** — EBI's Ontology Lookup Service. The no-download fallback backend. **Lossy**: active international only. See [[vocabulary]].
- **MedDRA** — the other terminology. Here, only an answer-key-derived 666-code list.
- **Clinical finding** — SNOMED `404684003`. The semantic-type gate's target.

## Method terms

- **Gold rule** — strict: the predicted code is **in the gold code set** for that mention.
- **Answer space vs reference** — whether a code list is the set to choose from (a much easier task) or only a cross-check. MedDRA is `reference`.
- **Leakage** — answer-key information reaching a component that should not see it.
- **τ (tau)** — [[r5]]'s confidence threshold. Swept on dev, written before the first test run.
- **Risk-coverage curve** — accuracy as a function of how much you decline to answer.

## Related

- [[index]] · [[architecture]] · [[rungs]]

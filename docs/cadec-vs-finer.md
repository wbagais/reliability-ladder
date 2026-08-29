# CADEC vs FiNER-139 — the two arms, side by side

**Read the caveat first.** These are not comparable as results. CADEC is a
frozen test split of 60 documents, run once, cold, under a configuration tuned
over five phases. FiNER is 10 documents on a machine that could not finish half
of them. The comparison below is about **what the ladder and the harness did**,
not about which corpus scores better — and the places where a number is missing
are as informative as the places where one exists.

---

## The corpora

| | CADEC | FiNER-139 |
|---|---|---|
| Domain | patient forum posts, adverse drug reactions | SEC filings, XBRL-tagged numeric facts |
| Gold from | human annotators, CSIRO | what the company **filed** — an audited fact |
| Vocabulary | SNOMED CT-AU, **129,675** clinical findings | **139** US-GAAP tags |
| Fits in a prompt | no | **yes** — this is the whole reason for the arm |
| Licence | CSIRO, non-transferable, not redistributable | CC-BY-SA-4.0, **a reader can reproduce it** |
| Span shape | phrases; **11.7% discontinuous** | bare numbers; **3 of 407 multi-token** |
| Span example | "extreme rectal bleed" | `47.6` |
| Repeats | tagged separately | tagged separately (38 of 407) |
| Ambiguity | one phrase, usually one concept | **39 numbers take different tags in different places** |
| Documents with no gold | none — every post has mentions | **36 of 100**, deliberately sampled |

The last two rows are the task difference. In CADEC the span carries meaning and
the vocabulary is enormous. In FiNER the span is `47.6` and means nothing; the
sentence decides, and there are only 139 answers.

---

## Prediction vs outcome

Written into `manifest.finer.json` **before the run**, dated, so the result is a
measurement rather than a story told afterwards.

| rung | predicted | observed |
|---|---|---|
| 1 validate | **weakens** — `exists()` near-trivial over 139 visible names | **confirmed, and worse than predicted.** Two of three checks are *vacuously true*: no retirement, no semantic hierarchy. `lexical_match` is always False — the span is a number, the tag is a name. Every record BAND. |
| 2 self-correct | **improves** — the model can pick from a list it can see | **not measured.** All records were BAND, and rung 2 only fires on REJECT. It attempted zero corrections, for the same structural reason it attempted zero on CADEC's test split. |
| 3 vote | uncertain; should at least *engage* | **not measured.** 15 sampled calls with a 139-item menu were unaffordable on this hardware. |
| 4 judge | **improves** — a small judge might check a number | **not measured**, and its prompt was never ported: it judged a financial filing by asking whether the text indicated *"a personal adverse reaction"*. A seventh prompt constant, in `r4.py`. |
| 5 abstain | **weakens** — less to withdraw | **not measured** on the full arm. On the 5-document run it withdrew everything, as on CADEC. |
| 6 triage | — | not run. |

**The prediction that mattered was right, and for a stronger reason than
predicted.** The deterministic spine's value on CADEC came from a vocabulary
large enough to be fabricated against. Remove the knowledge gap and two of its
three free checks stop being checks at all.

---

## What each arm measured

| | CADEC (test, 60 docs, frozen) | FiNER (10 docs, smoke) |
|---|---|---|
| Records | 314 | 32 |
| Gold mentions | 290 scorable | 407 in the 120-doc pool |
| Rung 0 → could not run | **0** json_decode failures | **5 of 10 documents** |
| Rung 1 | ACCEPT 72 / BAND 226 / REJECT 16 | **BAND 32 / 32** |
| Rung 1 rejection rate | 5.1% | 0% |
| Rung 2 corrections attempted | 0 — all rejects `schema_invalid` | 0 — nothing rejected |
| Rung 3 | re-found 8, **all 8 wrong**; dev gain did not transfer | not run |
| Rung 4 | pass 202 / fail 110, 2 parse failures | not run |
| Rung 5 | ships 72 at **0.833**, withdraws 242; err/100 **59.6 → 3.8** | not run |
| Rung 6 | 242 of 314 routed, **77.1 reviews/100** | not run |
| **F1 exact** | **0.204** [0.150–0.260] | — |
| Coding accuracy | **0.392** [0.305–0.476] | 0 of 3 matched spans |
| Tokens | 844,657 over 758 calls | 12,207 over 10 documents |
| Wall | 78 min | 20 min for 10 docs, half unusable |

---

## The failure modes differ, and that is the interesting part

| | CADEC | FiNER |
|---|---|---|
| What the model got wrong | **invented codes that exist nowhere** — 155 of 169 failed `exists()` | **real, related, plausible tags outside the label set** |
| Example | `41456009` — not in any release, affirmed by the judge at 0.95 confidence with a fabricated term | `1` → predicted `BusinessAcquisitionEquityInterestsIssuedOrIssuableNumberOfSharesIssued`, gold `StockIssuedDuringPeriodSharesNewIssues` — both share counts |
| | | `19.4` → predicted `CashAndCashEquivalentsFairValueDisclosure`, gold `ProceedsFromIssuanceOfCommonStock` — both cash amounts |
| Reading | fabrication: no knowledge to draw on | **right category, wrong tag.** FiNER-139 is the 139 *most frequent* tags of thousands; the model is not wrong about accounting, it is wrong about which subset was annotated |

A low score means different things in the two arms, and any comparison that
puts 0.392 next to a FiNER number without saying so is comparing nothing.

---

## What could not be held constant

Freezing the configuration is what makes two arms comparable, so each deviation
is declared rather than absorbed.

| setting | CADEC | FiNER | why it cannot be frozen |
|---|---|---|---|
| `rung0_retrieval` | `dense` — cosine over 127,515 embedded concepts, worth **+21.0 points** recall@20 there | `full` — all 139, no ranking | retrieval is a function of what is retrieved *from*, and the two differ by three orders of magnitude |
| few-shot documents | `ARTHROTEC.22`, `ARTHROTEC.110` | `FINER.test.0051`, `FINER.test.0049` | examples belong to the corpus — the same finding as the prompt, one layer down |
| prompts | six constants about adverse reactions | six constants about financial facts | see below |
| `timeout_s` | 300 | 900 | **hardware, not design** — and it is a shared value |

---

## What the port cost, which is the durable finding

**Sixteen one-line edits to the harness. Zero changes to rung logic.** The
runner contract, the vocabulary Protocol, the ledger, the injected scorer and
the manifest-driven config all held.

**Rung 0 did not port at all.** Seven prompt constants, every one written about
adverse drug reactions in patient posts. `_RULES` encodes CADEC annotation
conventions with measurements behind them — *1 of 7,311 gold mentions names a
procedure*. `PICK_PROMPT` carries a worked example about *"felt like my old self
was gone"*. Rung 0 is a CADEC extraction system; the ladder above it is what
generalises.

Six things the port had to touch, each found one crash at a time:

  * four corpus-loading sites hardcoding `cadec_root`, two of them **inside
    rungs**, reaching for the corpus rather than receiving it
  * an unbound loader — three call sites each built a *different* corpus from
    the same adapter
  * `manifest.py` resolving `cadec_root` and no other corpus root
  * an empty `rungs` block that meant "nothing configured" rather than "nothing
    overridden"
  * sampling config in the manifest that was never read
  * rung 3 enumerating which keys to pass rung 0, so two new ones never arrived

Every one is the same shape: **something enumerating what to pass, rather than
passing what it had.**

---

## Two things the second arm proved that one corpus could not

**Modularity is a claim about which axes vary, and one dataset cannot test it.**
Every axis *known* to vary was abstracted — models, rung order, thresholds,
retrieval, few-shot ids, vocabulary backend, scorer. The prompts were never
known to vary, because there was one corpus. `schemas/adapter.py` is listed in
the plan as a contract and was never written, for the same reason. You can only
parameterise what you can imagine changing.

**Config that depends on hardware, with no record of which hardware, is the same
failure as a rate with no denominator.** `rung0_retrieval: "full"` was chosen
from the vocabulary size by someone who did not know the card. `timeout_s: 300`
is right on one machine and wrong on another. `provenance.py` computes whether
the model *fits* in VRAM and nothing acts on it. Phase F records the vocabulary
backend and not the compute backend, so its 78 minutes belong to no machine.

---

## Where the FiNER arm stops

The port works. The prompts render. The pick step chooses real tags from the
full menu. What does not work is running it here: `gpt-oss:20b` is 14 GB against
4 GB of VRAM, and a 139-item menu pushed it to **81% CPU / 19% GPU**. Half of
rung 0's calls are cut off mid-generation with empty output. Tripling the
timeout — 300s to 900s — turned six failures into five.

That is a hardware statement and it is stated as one. The arm needs a card that
fits the model; the port findings above do not depend on the numbers it would
produce.

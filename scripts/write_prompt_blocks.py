#!/usr/bin/env python3
"""
write_prompt_blocks.py — the four missing `corpus.prompts`, from measured gold.

WHY THESE EXIST

`run.py` reads rung 0's task description from `corpus.prompts` and falls back to
CADEC's wording when the key is absent. That fallback is deliberate and correct
for an adverse-reaction corpus — PsyTAR has no block and needs none. It is wrong
for a corpus about places, species or diseases, and four arms inherited it: LGL,
TR-News, LINNAEUS and BC5CDR contributed twelve cells to the 2026-09-06 matrix
that measure a model answering the wrong question.

EVERY NUMBER BELOW WAS MEASURED BY `scripts/gold_span_stats.py`

Not one is an impression. GeoWebNews's block records its own provenance the same
way, and the discipline is the point: a prompt written from a feeling about a
corpus sounds specific and is anchored to nothing, which is the same defect as a
rate over an unnamed set.

WHAT IS DELIBERATELY NOT WRITTEN

CADEC's negation rule is **dropped, not translated**, in all four — as it was on
FiNER and GeoWebNews. CADEC gold marks denied reactions with `negated:true`;
none of these four has a denial convention, so the field is always false. A
silently dropped rule is indistinguishable from an overlooked one, so it is
recorded rather than omitted.

    python3 scripts/write_prompt_blocks.py --dry-run
    python3 scripts/write_prompt_blocks.py
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

BLOCKS: dict[str, dict] = {}

# ── LGL ───────────────────────────────────────────────────────────────
BLOCKS["manifest.lgl.json"] = {
    "_derivation":
        "Derived from LGL's own gold over 4,462 mentions in 588 documents, "
        "measured by scripts/gold_span_stats.py, not invented. 23.9% of surface "
        "forms are multi-token; 3.2% carry an initial and a dot (U.S., N.J.); "
        "100% begin with a capital, so case IS a usable cue here, unlike "
        "LINNAEUS where it is 34.3%. 3,916 of 4,462 mentions are a form used "
        "more than once, and every occurrence is tagged separately. 626 "
        "annotations carry no geonameid and are dropped before scoring.",
    "entity": "place the article refers to",
    "entity_short": "place",
    "entity_plural": "places",
    "author": "the article",
    "author_possessive": "the article's",
    "source": "the local news article",
    "vocabulary": "GeoNames place",
    "vocabulary_short": "place",
    "id_name": "GeoNames id",
    "vocabulary_qualifier": "GeoNames entry",
    "rules": """
Quote the place EXACTLY as the article writes it. If it says 'U.S.', quote
'U.S.'; if it says 'Ohio', quote 'Ohio'. Measured on gold: 3.2% of mentions
carry an initial and a dot, and 23.9% run to more than one word.

A WORD THAT REFERS TO A PLACE COUNTS EVEN WHEN IT IS NOT THE PLACE'S NAME.
'American', 'Russian' and 'Turkish' each refer to a country and are reported,
quoted as written. Both appear among this corpus's twelve commonest forms.

Report a place EVERY TIME it appears. Measured: 3,916 of 4,462 gold mentions
are a form that occurs more than once, and each occurrence is tagged where it
appears — never merge repeats.

SMALL PLACES COUNT AS MUCH AS LARGE ONES. This is local journalism: county
names, parishes, townships and small towns are most of the answer.
'Rapides Parish', 'Avoyelles Parish', 'Pointe Coupee', 'Gainesville' and
'Elbow Lake' are all gold. A place is not too obscure to report.

A person's name, a company, a product, or a nationality used as a language
is not a place.
""",
    "pick_guidance": """
Choose the entry for the place the article ACTUALLY MEANS, which for this
corpus is usually NOT the largest or best-known one with that name.

That is what LGL exists to test — its name is the Local-Global Lexicon, and it
was built from local newspapers precisely because a local report naming
'Georgia' more often means the county than the country, and 'Paris' more often
a town in Texas than the capital. The surrounding sentence decides.

For an abbreviation or a demonym, choose the entry for the place it stands
for: 'U.S.' is the United States, 'American' is the United States.
""",
    "span_question": "really a place this news article refers to",
    "claim_verb": "was referred to",
    "claim_object": "place",
    "_negation_note":
        "CADEC's negation rule is DROPPED, not translated. LGL has no "
        "denied-place convention and `negated` is always false here.",
    "_locality_note":
        "The pick_guidance leans on locality deliberately. Unlike GeoWebNews, "
        "whose gold carries a name and coordinates and forced a lookup that "
        "once resolved a Brooklyn to South Africa, LGL's gold carries the "
        "geonameid directly — so the resolution step cannot be got wrong here "
        "and the remaining difficulty is entirely the local/global ambiguity.",
}

# ── TR-News ───────────────────────────────────────────────────────────
BLOCKS["manifest.trnews.json"] = {
    "_derivation":
        "Derived from TR-News's own gold over 1,159 mentions in 118 documents, "
        "measured by scripts/gold_span_stats.py, not invented. 12.8% of surface "
        "forms are multi-token — the LOWEST of the three geo corpora, against "
        "GeoWebNews's 20.7% and LGL's 23.9% — so this corpus's mentions are "
        "mostly single words. 2.8% carry an initial and a dot; 100% begin with "
        "a capital. 965 of 1,159 are a form used more than once. 116 of 1,275 "
        "annotations have offsets that do not land and are dropped with a "
        "reason before scoring.",
    "entity": "place the article refers to",
    "entity_short": "place",
    "entity_plural": "places",
    "author": "the article",
    "author_possessive": "the article's",
    "source": "the news article",
    "vocabulary": "GeoNames place",
    "vocabulary_short": "place",
    "id_name": "GeoNames id",
    "vocabulary_qualifier": "GeoNames entry",
    "rules": """
Quote the place EXACTLY as the article writes it. If it says 'U.S.', quote
'U.S.'; if it says 'US', quote 'US'. Both forms appear in this corpus's twelve
commonest mentions and they are quoted as written, not normalised.

MOST MENTIONS ARE A SINGLE WORD. Measured on gold: only 12.8% run to more
than one word — 'Edmonton', 'London', 'Turkey', 'Russia', 'Canada' are the
shape of this corpus. Do not extend a span past the name itself.

A WORD THAT REFERS TO A PLACE COUNTS EVEN WHEN IT IS NOT THE PLACE'S NAME.
'Russian' and 'Turkish' are both among the commonest gold forms here and are
reported, quoted as written.

Report a place EVERY TIME it appears. Measured: 965 of 1,159 gold mentions
are a form that occurs more than once, tagged separately at each occurrence.

A person's name, a company, a product, or a nationality used as a language
is not a place.
""",
    "pick_guidance": """
Choose the entry for the place the article ACTUALLY MEANS. The surrounding
sentence decides: there are several Londons and several Parises on the menu.

For an abbreviation or a demonym, choose the entry for the place it stands
for: 'U.S.' and 'US' are both the United States, 'Turkish' is Turkey.
""",
    "span_question": "really a place this news article refers to",
    "claim_verb": "was referred to",
    "claim_object": "place",
    "_negation_note":
        "CADEC's negation rule is DROPPED, not translated. TR-News has no "
        "denied-place convention and `negated` is always false here.",
}

# ── LINNAEUS ──────────────────────────────────────────────────────────
BLOCKS["manifest.linnaeus.json"] = {
    "_derivation":
        "Derived from LINNAEUS's own gold over 4,259 mentions in 95 documents, "
        "measured by scripts/gold_span_stats.py, not invented. Two numbers make "
        "this corpus unlike the geo arms and both are in the rules below. "
        "**Only 34.3% of mentions begin with a capital** — against 100% on LGL "
        "and TR-News — because the commonest gold forms are 'patients', "
        "'human', 'mice', 'mouse', 'people', 'women', 'yeast': lowercase common "
        "nouns. And **18.0% carry an initial and a dot**, five times the geo "
        "rate, because an abbreviated binomial is written 'C. elegans' or "
        "'E. coli'. 27.1% are multi-token; 4,077 of 4,259 are a form used more "
        "than once.",
    "entity": "organism the paper mentions",
    "entity_short": "organism",
    "entity_plural": "organisms",
    "author": "the paper",
    "author_possessive": "the paper's",
    "source": "the research article",
    "vocabulary": "NCBI Taxonomy",
    "vocabulary_short": "taxon",
    "id_name": "NCBI taxonomy id",
    "vocabulary_qualifier": "NCBI Taxonomy entry",
    "rules": """
AN ORDINARY ENGLISH WORD FOR A LIVING THING IS AN ORGANISM MENTION.
This is the most important rule here and it is the opposite of what a
capitalised-name heuristic would do. 'patients', 'human', 'mice', 'mouse',
'people', 'women', 'men', 'participants' and 'yeast' are the nine commonest
gold mentions in this corpus, and every one is lowercase. Measured: only
34.3% of gold mentions begin with a capital, so CASE IS NOT A CUE HERE.

A word for a group of PEOPLE is an organism mention — it refers to Homo
sapiens. 'patients', 'participants', 'women', 'men' and 'people' are all
gold.

Scientific names are reported as written, in full or abbreviated.
'Saccharomyces cerevisiae', 'Escherichia coli', 'Caenorhabditis elegans',
'Xenopus laevis' and 'Drosophila melanogaster' appear in full; 'C. elegans'
and 'E. coli' appear abbreviated. Measured: 18.0% of gold mentions carry an
initial and a dot, so the abbreviated form is common and is quoted exactly as
the paper writes it — never expanded.

An ADJECTIVE referring to an organism counts. 'murine' is among the twelve
commonest gold mentions and refers to mice.

Report an organism EVERY TIME it appears. Measured: 4,077 of 4,259 gold
mentions are a form used more than once, tagged separately at each
occurrence.

A gene, a protein, a cell line, a disease or a chemical is not an organism,
even where its name contains one.
""",
    "pick_guidance": """
Choose the taxon the paper MEANS, which is very often not spelled anything
like the word on the page.

This is the corpus's central difficulty. 'mice' resolves to Mus musculus,
'yeast' to Saccharomyces cerevisiae, 'patients' to Homo sapiens — a common
name against a Latin binomial that shares no word with it. Measured on gold
against a scientific-names-only vocabulary, 76.8% of mentions share NO token
with the name they resolve to.

For an abbreviated binomial, choose the species it stands for: 'C. elegans'
is Caenorhabditis elegans, 'E. coli' is Escherichia coli.

Prefer the SPECIES over a genus, a family or a kingdom where the paper is
specific enough to support it.
""",
    "span_question": "really an organism this research paper mentions",
    "_span_question_note":
        "CADEC's phrasing asks whether the writer EXPERIENCED something, which "
        "encodes first-person patient narrative. A research paper mentions an "
        "organism; it does not experience one. The same constant was missed on "
        "the FiNER port and is declared here rather than defaulted.",
    "claim_verb": "was mentioned",
    "claim_object": "organism",
    "_negation_note":
        "CADEC's negation rule is DROPPED, not translated. LINNAEUS has no "
        "denied-organism convention and `negated` is always false here.",
    "_vocabulary_note":
        "The arm runs against a SCIENTIFIC-NAMES-ONLY taxonomy index. The "
        "all-names build, which admits 'mouse' and 'baker's yeast', moves the "
        "endorsable stratum from 5.4% to 35.4% on identical gold. The strict "
        "build is chosen to match the main-name-only GeoNames build so the "
        "lexical arms read alike, and the gap is a measured finding rather "
        "than an accident.",
}

# ── BC5CDR ────────────────────────────────────────────────────────────
BLOCKS["manifest.bc5cdr.json"] = {
    "_derivation":
        "Derived from BC5CDR's own gold over 4,130 DISEASE mentions in 500 dev "
        "documents, measured by scripts/gold_span_stats.py, not invented. "
        "**39.4% of surface forms are multi-token**, the highest of the six "
        "corpora in this study and nearly double LGL's 23.9%, so a disease "
        "mention here is usually a phrase. Only 15.6% begin with a capital and "
        "0% carry an initial and a dot. Median length 12 characters, p95 25. "
        "3,559 of 4,130 are a form used more than once. 100 annotations name "
        "two concepts and 59 are marked unresolvable by the annotators; both "
        "are dropped with a reason before scoring.",
    "entity": "disease or symptom the abstract describes",
    "entity_short": "disease",
    "entity_plural": "diseases",
    "author": "the abstract",
    "author_possessive": "the abstract's",
    "source": "the biomedical abstract",
    "vocabulary": "MeSH",
    "vocabulary_short": "disease",
    "id_name": "MeSH id",
    "vocabulary_qualifier": "MeSH descriptor",
    "rules": """
MOST MENTIONS ARE A PHRASE, NOT A WORD. Measured on gold: 39.4% run to more
than one word, the highest rate in this study. 'secondary hyperparathyroidism',
'low bone turnover', 'renal failure', 'suppression of bone turnover' and
'adynamic bone disease' are all single gold mentions. Quote the whole phrase.

REPORT DISEASES AND SYMPTOMS, NOT CHEMICALS OR DRUGS. This corpus annotates
both and this arm scores only diseases. 'seizures', 'hypotension', 'pain',
'catalepsy', 'nephrotoxicity' and 'breast cancer' are gold; the drug that
caused them is not.

Quote the disease EXACTLY as the abstract writes it, in the number it uses.
Both 'seizure' and 'seizures' are gold forms in this corpus and each is
quoted as written, never normalised to the other.

Case is not a cue. Measured: only 15.6% of gold mentions begin with a
capital — 'seizures', 'toxicity' and 'hypertension' are lowercase mid-
sentence and are gold.

Report a disease EVERY TIME it appears. Measured: 3,559 of 4,130 gold
mentions are a form used more than once, tagged separately at each
occurrence.

A drug, a chemical, a gene, a protein or a laboratory measurement is not a
disease, even where an abstract discusses it alongside one.
""",
    "pick_guidance": """
Choose the MeSH descriptor for the condition the abstract means.

Prefer the specific descriptor over a broad one where the abstract supports
it: 'breast cancer' is Breast Neoplasms, not Neoplasms.

An adjective form resolves to the noun the descriptor is named for:
'hypertensive' is Hypertension, 'hypotensive' is Hypotension. Measured on
gold, that morphological gap is this corpus's main reason for a mention
sharing no token with the name it resolves to.
""",
    "span_question": "really a disease or symptom this abstract describes",
    "_span_question_note":
        "CADEC's phrasing asks whether the writer EXPERIENCED something. A "
        "biomedical abstract describes a condition in a study population; it "
        "does not experience one.",
    "claim_verb": "was described",
    "claim_object": "disease",
    "_negation_note":
        "CADEC's negation rule is DROPPED, not translated. BC5CDR marks "
        "unresolvable mentions with -1 and those leave the denominator before "
        "scoring, but it has no denied-disease convention and `negated` is "
        "always false here.",
    "_entity_arm_note":
        "This arm scores DISEASE. Chemicals are the larger class — 15,935 of "
        "28,785 annotations corpus-wide — and are a separate arm. The rules "
        "say so explicitly because a corpus that annotates two types and "
        "scores one will otherwise be judged on mentions it never asked for.",
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    for path, block in BLOCKS.items():
        p = pathlib.Path(path)
        if not p.is_file():
            print(f"  {path:26} NOT FOUND")
            continue
        man = json.loads(p.read_text())
        had = "prompts" in (man.get("corpus") or {})
        n_rules = len([l for l in block["rules"].strip().split("\n\n")])
        print(f"  {path:26} {len(block):2} slots · {n_rules} rules"
              + ("  (replacing existing)" if had else ""))
        if a.dry_run:
            continue
        man["corpus"]["prompts"] = block
        p.write_text(json.dumps(man, indent=2) + "\n")

    if a.dry_run:
        print("\n  --dry-run: nothing written.\n")
        return 0
    print("\n  Written. Verify each arm is still one variable, then re-run the")
    print("  twelve affected cells:\n")
    for path in BLOCKS:
        print(f"    PYTHONPATH=. python3 scripts/manifest_diff.py manifest.json "
              f"{path} --declared corpus vocabulary rungs")
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

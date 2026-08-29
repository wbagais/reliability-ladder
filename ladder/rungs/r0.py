"""Rung 0 — the bare LLM. One call per document. Everything else is measured
against this.

Rung 0 is the one rung handed an EMPTY record list: it receives the split's
`sources` and returns the records every other rung then routes. Rungs 1-6 judge,
correct, vote on and abstain from what this rung produced; none of them can
create a mention.

    raw, usage = cfg["llm"](prompt, source, mode)

The model is never chosen here. `run.py` resolves it once from
`manifest.model.extractor` and injects `cfg["llm"]` — see `ladder.llm.for_rung`.

MODES. Rung 0 has an ablation built in, and the rule is one implementation, one
flag: modes A and B share every line except the tool block, because two
implementations would confound tool access with prompting.

    A  recall only — the model emits a SNOMED code from its own knowledge
    B  search tool — the model is given a vocabulary lookup first

`rung0_mode` in manifest.json decides which is the headline and which is the
ablation. `--compare` at the bottom of this file runs them side by side.

WHAT RUNG 0 IS ACTUALLY ASKED TO DO, and how the four parts fail differently:

    find     which spans are adverse reactions
    quote    the reporter's exact words          — reliable
    locate   character offsets of that quote     — fails at every model size
    code     the SNOMED concept id               — scales with the model

Measured on ARTHROTEC.1, mode A: claude-haiku-4-5 got 2 of 3 codes real and
0 of 3 offsets right; granite4:micro-h got 0 of 2 codes and 0 of 2 offsets, and
0 of 26 codes across ten dev documents. Quoting is near-perfect for both (77%
verbatim over the ten documents) while offset arithmetic fails regardless of
size — which is what `rung0_offsets: "search"` exists to bypass, since a span
the model quoted correctly can be located by string search instead of trusting
its character count.
"""

from __future__ import annotations

import argparse
import json
import time
from typing import Any

from ladder import vocab
from ladder.ledger import Ledger
from ladder.rungs import r1
from ladder.schema import (
    CONCEPT_LESS,
    REACTION,
    REJECT_REASONS,
    Record,
    ZONE_ACCEPT,
    ZONE_BAND,
    ZONE_REJECT,
)

RUNG = 0

DEFAULTS: dict[str, Any] = {
    #: "model" trusts the offsets the model emitted; "search" discards them and
    #: locates span_text in the source. See the module docstring.
    "rung0_offsets": "model",
    "rung0_mode": "recall",
    #: None keeps the original A/B mode path. "S0".."S2" select the
    #: prompt-engineering study below, where scope is fixed and only the way
    #: the CODE is obtained changes.
    "rung0_step": None,
    "rung0_shortlist_k": 20,
    #: The few-shot ARM. False keeps the frozen S2 prompt; True appends the
    #: synthetic worked example (FEWSHOT below) to every extraction prompt.
    #: An arm rather than a default so its effect is measured against the
    #: freeze, not folded into it.
    "rung0_fewshot": False,
    #: Which retriever builds S2's candidate menu. "lexical" is
    #: Registry.shortlist — Jaccard token overlap over every SNOMED
    #: description. "dense" is cosine over the embedded keyword table
    #: (ladder/embed.py). Measured 2026-08-24 over the same 6,595 scorable
    #: gold reaction mentions. THE TWO ALSO SEARCH DIFFERENT CORPORA —
    #: lexical over 1,822,645 description rows of every semantic type, dense
    #: over 227,554 findings/disorders keywords — so the corpus and the
    #: scoring are varied SEPARATELY here, one per row:
    #:
    #:                                 recall@1  @5     @10    @20    @50
    #:     lexical over descriptions   19.5%     52.4%  57.6%  61.8%  66.7%
    #:     lexical over keywords.csv   48.6%     57.2%  61.1%  65.1%  69.6%
    #:     dense   over keywords.csv   63.8%     76.7%  82.1%  86.1%  90.3%
    #:
    #: At k=20 that is +3.3 points of corpus and +21.0 of scoring. At k=1 it
    #: inverts — +29.1 corpus, +15.2 scoring — because filtering to findings
    #: BEFORE ranking is what clears the top slot, which is the same defect
    #: that once answered |California chicken (organism)| for a rectal bleed.
    #: The default moved on that and on nothing else; lexical stays reachable
    #: because a number produced under one retriever is only interpretable
    #: next to the other, which is why the choice is written onto every record.
    "rung0_retrieval": "dense",  # "dense" | "lexical"
    #: Trim rung 0's spans to the answer key's boundary convention, AFTER
    #: locate() — rules learned from POOL gold at runtime (ladder/trim.py).
    #: Note the order: S2's retrieval queries the model's FULL quote and the
    #: trim happens afterwards, so the menu is built on more context, not
    #: less. cfg["trimmer"] injects rules directly (tests; measurement runs).
    "rung0_trim": False,
    #: How S2's menu is ORDERED before numbering. "score" is retrieval order,
    #: best first — which means the gold code usually sits high, and a model
    #: that anchors on early items looks better than it reads. "alpha"
    #: re-sorts the same candidates alphabetically: if F1 holds, the pick
    #: reads content; if it drops, position was doing work. An arm.
    "rung0_menu_order": "score",  # "score" | "alpha"
    "embed_prefix": "ladder/cache/keywords",
    #: Where S1's names are turned into codes. `data/keywords.csv` — findings
    #: and disorders only, built from the SNOMED release by
    #: `python -m ladder.keywords --build`. NOT the registry: resolving
    #: against every description in the release is what returned
    #: |California chicken (organism)| for a rectal bleed.
    "keyword_table": "data/keywords.csv",
}

# ------------------------------------------------------------------ prompts
# The task belongs to the CORPUS; the structure belongs to the LADDER.
#
# Only these five slots vary between corpora. The field names, the offset
# convention, the JSON shape and the do-not-invent instruction are NOT slots —
# they are what makes two arms comparable, and a corpus that needed them changed
# would be a different experiment rather than a second data point.
#
# Defaults are CADEC's exact wording, so the rendered CADEC prompt is
# byte-identical to what phase F ran. There is an assertion below that says so.
PROMPT_SLOTS = {
    "entity": "adverse reaction",
    "entity_short": "reaction",
    "entity_plural": "reactions",
    "author": "the reporter",
    "source": "the post",
    "vocabulary": "SNOMED CT concept",
    "id_name": "concept id",
    "policy": (
        "Report only reactions the writer actually experienced. Do not report "
        "anything\nthey say they did NOT have."
    ),
    "sentinel_rationale": (
        "many reactions people\ndescribe have no SNOMED CT concept"
    ),
}

BASE_TEMPLATE = """Extract every {entity} {author} describes in {source} below.

For each one return:
  span_text  - {author}'s exact words, copied character for character
  start,end  - character offsets of span_text in {source}
  code       - the {vocabulary} id for that {entity_short}, or the literal
               string CONCEPT_LESS if no {vocabulary} correctly describes it
  confidence - 0.0 to 1.0

{policy}

Do not invent a {id_name}. If you cannot name one you are confident is a real
{vocabulary} for this {entity_short}, answer CONCEPT_LESS. That is a correct
answer in its own right, not a failure to answer — {sentinel_rationale}.

Return JSON: {{"mentions":[{{"span_text":..,"start":..,"end":..,"code":..,"confidence":..}}]}}
"""


def render_base(slots: dict | None = None) -> str:
    """The task prompt for one corpus. Missing slots fall back to CADEC's."""
    return BASE_TEMPLATE.format(**{**PROMPT_SLOTS, **(slots or {})})


BASE = render_base()

# The literal above has to be the sentinel rung 1 branches on and the scorer
# grades against, so a rename of the constant must not leave the prompt behind.
# Checked rather than interpolated because BASE also contains JSON braces.
if CONCEPT_LESS not in BASE:  # pragma: no cover
    raise RuntimeError(
        f"rung 0's prompt does not name {CONCEPT_LESS!r}. A model that is never "
        "told the sentinel exists cannot answer it, and every abstention it "
        "meant to make arrives as an invented code instead."
    )

TOOL_BLOCK = """
You have a vocabulary search tool. Call it before choosing any code:
    SEARCH("term") -> [{code, label}, ...]
Choose a code from the results. If nothing in the results fits, answer
CONCEPT_LESS — do not fall back to a code you did not look up.
"""


def build_prompt(mode: str, slots: dict | None = None) -> str:
    """`slots` comes from manifest.corpus.prompt. None keeps CADEC's wording."""
    s = {**PROMPT_SLOTS, **(slots or {})}
    return render_base(s) + (
        TOOL_BLOCK
        if mode == "B"
        else f"\nEmit the {s['vocabulary']} id from your own knowledge.\n"
    )


def recover_offsets(span_text: str, source: str, claimed: tuple[int, int]) -> tuple[int, int, str]:
    """Locate span_text in source. Returns (start, end, how).

    Disambiguates repeats by the model's own claim: its arithmetic was wrong but
    its sense of position was roughly right, so the nearest occurrence to the
    claimed start is a better guess than the first one.
    """
    if not span_text:
        return -1, -1, "empty"
    hits, i = [], source.find(span_text)
    while i != -1:
        hits.append(i)
        i = source.find(span_text, i + 1)
    if not hits:
        low = source.lower().find(span_text.lower())
        if low == -1:
            return -1, -1, "not_in_source"
        return low, low + len(span_text), "search_case_insensitive"
    if len(hits) == 1:
        s = hits[0]
        return s, s + len(span_text), "search_unique"
    anchor = claimed[0] if isinstance(claimed[0], int) and claimed[0] >= 0 else 0
    s = min(hits, key=lambda h: abs(h - anchor))
    return s, s + len(span_text), f"search_nearest_of_{len(hits)}"


def rung0(doc_id: str, text: str, mode: str, llm, cfg=None) -> tuple[list[Record], dict]:
    """One document, one model call. Identical for A and B except the tool block."""
    meta = {"tool_calls": 0, "tokens_in": 0, "tokens_out": 0, "usd": 0.0}
    raw, usage = llm(build_prompt(mode, cfg.get("prompt_slots")), text, mode)
    meta["tokens_in"] += usage["in"]
    meta["tokens_out"] += usage["out"]
    meta["usd"] = meta.get("usd", 0.0) + usage.get("usd", 0.0)
    meta["truncated"] = meta.get("truncated", False) or bool(usage.get("truncated"))
    meta["timed_out"] = meta.get("timed_out", False) or bool(usage.get("timed_out"))

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        # Never silently repaired: a parse failure is a real reliability cost
        # and rung 0's counter-metric.
        return [], {**meta, "parse_failed": True}

    offsets_mode = (cfg or {}).get("rung0_offsets", "model")
    out = []
    for i, m in enumerate(parsed.get("mentions", [])):
        start, end = m.get("start", -1), m.get("end", -1)
        how = "model"
        if offsets_mode == "search":
            start, end, how = recover_offsets(m.get("span_text", ""), text, (start, end))
            key = "offsets_" + how.split("_")[0]
            meta[key] = meta.get(key, 0) + 1
        rec = Record(
            doc_id=doc_id,
            entity_type=REACTION,
            text=m.get("span_text", ""),
            spans=[(start, end)] if isinstance(start, int) and isinstance(end, int) else [],
            sct=(str(m["code"]) if m.get("code") is not None else None),
            confidence=float(m.get("confidence", 0) or 0),
            record_id=f"{doc_id}#{i}",
        )
        rec.checks["rung0_mode"] = mode
        rec.checks["offsets"] = how
        if mode == "B" and rec.text:
            # POST-HOC. The model has already emitted rec.sct above; this search
            # happens after generation and its results never reach the model.
            # The cost is real (one search per mention) but the model had no
            # tool. See honoured_tool() below.
            rec.checks["tool_results"] = vocab.search(rec.text, 5)
            meta["tool_calls"] += 1
        out.append(rec)
    return out, meta


# ============================================================================
# THE PROMPT-ENGINEERING STUDY — steps S0, S1, S2
#
# SCOPE IS IDENTICAL IN ALL THREE. Every step finds the same mentions, writes
# the same record keys, and is scored the same way. The single thing that
# varies is where the CODE comes from:
#
#   S0  label and code recalled from the model's own weights
#   S1  label recalled, code resolved from the KEYWORD TABLE by that label
#   S2  label PICKED from a shortlist retrieved for the mention
#
# Two facts decide the shape. Measured over CADEC gold: exact-matching the
# patient's own words against SNOMED returns nothing 57.1% of the time, which
# is why S2 exists; and 76.8% of multi-candidate sets contain two concepts with
# an IDENTICAL label, which is why a pick is an INDEX and never a label string.
#
# Call counts differ — S0 and S1 are one call, S2 is two — so they are reported
# as cost rather than pretended away.
#
# S3 WAS DROPPED 2026-08-24. It was a pick from one fixed list printed in the
# prompt, and no printable list survives its own measurement: the MedDRA list
# it used is the answer key's own inventory (all 666 of its codes appear in the
# gold and none do not), the best ontology-native alternative — SNOMED's
# Clinical manifestation refset, 743 codes — caps at 48.7% of gold, the real
# keyword table is 227,554 rows and cannot be printed at all, and a list
# retrieved per mention is S2 by another name. See docs/decisions.md.
# ============================================================================

STEPS = ("S0", "S1", "S2")

# ---------------------------------------------------------------------------
# THE TASK BELONGS TO THE CORPUS.
#
# Seven prompt constants below were written about adverse drug reactions in
# patient posts. Pointed at a financial filing they ask the wrong question, and
# gpt-oss:20b correctly answers {"mentions":[]} — the extractor did not port.
#
# These slots are what varies. The STRUCTURE does not: field names, JSON
# shapes, the find-then-pick split and the pick menu's numbering are frozen,
# because they are what make two arms comparable. A corpus needing those
# changed would be a different experiment rather than a second data point.
#
# Defaults are CADEC's exact wording. There is an assertion in
# scripts/port_prompts.py that every CADEC prompt renders byte-identical.
PROMPTS = {
    "entity": "adverse reaction",
    "entity_short": "reaction",
    "entity_plural": "reactions",
    "author": "the reporter",
    "author_possessive": "the reporter's",
    "source": "the post",
    "vocabulary": "SNOMED CT concept",
    "vocabulary_short": "concept",
    "id_name": "concept id",
    "rules": None,          # filled from _RULES_CADEC below
    "pick_guidance": None,  # filled from _PICK_GUIDANCE_CADEC below
}


def prompt_text(key: str, over: dict | None = None) -> str:
    return {**PROMPTS, **(over or {})}[key]


def resolve(over: dict | None = None) -> dict:
    """Slots for one corpus. Missing keys fall back to CADEC's."""
    return {**PROMPTS, **{k: v for k, v in (over or {}).items() if v is not None}}


_ASK_TEMPLATE = """  span_text  - {author_possessive} exact words, copied character for character
  context    - the three or four words IMMEDIATELY BEFORE span_text, copied the
               same way, so the quote can be located when it appears twice
"""

#: CADEC's extraction conventions. Every paragraph is a rule about THIS corpus,
#: several with measurements behind them, so this is a whole-paragraph slot
#: rather than something substitution can produce. A second corpus supplies its
#: own under manifest corpus.prompts.rules.
_RULES_CADEC = """
Report a reaction the writer explicitly says they did NOT have as well, and
mark it "negated": true — a denied reaction is still recorded. Every other
mention is "negated": false. Only the writer's own reactions count either way.
A blanket statement of wellness — "no side effects", "I feel fine" — is not a
reaction and is not reported; report only a SPECIFIC denied reaction.

Report EVERY symptom, condition or health problem the writer says they
experienced — including the condition the drug was taken for, and conditions
they merely compare themselves to. Work through the WHOLE POST: posts often
list many reactions in one sentence, and every item in the list is reported
separately.

Report a reaction EVERY TIME it is described. If the writer mentions the same
reaction twice, report it twice, each one where it appears — never merge
repeat mentions into one.

Vague and general states count. Feeling sick, being unwell, exhaustion or
feeling terrible are reactions too — report them even when the writer names no
specific symptom.

Report the reaction, not the treatment for it. A transfusion, an operation, a
scan or a hospital admission is something done TO the writer, not something the
drug did to them. Measured: 1 of 7,311 gold mentions names a procedure.
"""

#: The pick step's guidance. Also a whole-paragraph slot: it encodes what
#: "the right concept" MEANS for this corpus, including a worked example.
_PICK_GUIDANCE_CADEC = """Choose the PLAIN concept that names the reaction itself. When the list has
both a plain concept and a more specific variant of it, the plain one is
correct — severity, timing and circumstances the writer added do not belong
in the concept."""

#: CADEC-only. Fires only when rung0_fewshot_docs is empty; a corpus that names
#: its own pool documents never reaches it. NOT ported to other corpora —
#: porting a fallback nobody exercises is invented work.
_PICK_EXTRA_CADEC = """Example of no_concept: for reaction "felt like my old self was gone" with a
list of mood and fatigue concepts, the writer is describing a personal state
no clinical concept names — the answer is "no_concept", not the nearest mood.

A reaction marked [denied] is one the writer says they did NOT have. It is
still coded: choose the concept for the reaction being denied, exactly as if
it were experienced — the denial is recorded separately. That the writer did
not have it is never a reason to answer null or "no_concept"."""

PROMPTS["rules"] = _RULES_CADEC
PROMPTS["pick_guidance"] = _PICK_GUIDANCE_CADEC
PROMPTS["pick_extra"] = _PICK_EXTRA_CADEC
#: "any clinical concept" — the adjective is corpus-specific and belongs in
#: the slot table, not baked into the template.
PROMPTS.setdefault("vocabulary_qualifier", "clinical concept")


def ask(over: dict | None = None) -> str:
    return _ASK_TEMPLATE.format(**resolve(over))


def rules(over: dict | None = None) -> str:
    return resolve(over)["rules"]


def s0_prompt(over: dict | None = None) -> str:
    s = resolve(over)
    return (
        f"Extract every {s['entity']} {s['author']} describes in {s['source']} below.\n"
        "\nFor each one return:\n"
        + ask(over)
        + f"  start,end  - character offsets of span_text in {s['source']}\n"
        + f"  sct_label  - up to three {s['vocabulary']} names for the {s['entity_short']}, best first\n"
        + f"  sct_code   - the {s['vocabulary']} id matching sct_label[0]\n"
        "  confidence - 0.0 to 1.0\n"
        + rules(over)
        + "\nTwo different answers, and they are not the same:\n\n"
        f"  If no {s['vocabulary']} describes the {s['entity_short']}, answer CONCEPT_LESS for both\n"
        "  sct_label and sct_code.\n\n"
        f"  If you know which {s['vocabulary_short']} it is but do not recall its id, give sct_label and\n"
        "  answer null for sct_code. That is a complete and acceptable answer.\n\n"
        f"Never invent a {s['vocabulary_short']} id, and do not spend effort trying to recall one — null\n"
        "is better than a guess.\n\n"
        'Return JSON: {"mentions":[{"span_text":..,"context":..,"start":..,"end":..,'
        '"sct_label":[..],"sct_code":..,"negated":..,"confidence":..}]}\n'
    )


def s1_prompt(over: dict | None = None) -> str:
    s = resolve(over)
    return (
        f"Extract every {s['entity']} {s['author']} describes in {s['source']} below.\n"
        "\nFor each one return:\n"
        + ask(over)
        + f"  sct_label  - up to three {s['vocabulary']} NAMES for the {s['entity_short']}, best\n"
        "               first. Names, not id numbers — the id is looked up for you.\n"
        "  confidence - 0.0 to 1.0\n"
        + rules(over)
        + f"\nIf no {s['vocabulary']} describes the {s['entity_short']}, answer CONCEPT_LESS.\n\n"
        'Return JSON: {"mentions":[{"span_text":..,"context":..,"sct_label":[..],'
        '"negated":..,"confidence":..}]}\n'
    )


def find_prompt(over: dict | None = None) -> str:
    s = resolve(over)
    return (
        f"Extract every {s['entity']} {s['author']} describes in {s['source']} below.\n"
        "\nFor each one return:\n"
        + ask(over)
        + "  confidence - 0.0 to 1.0\n"
        + rules(over)
        + f"\nQuote the {s['entity_short']} itself, not the sentence around it. "
        f"The {s['vocabulary_short']} name is\nchosen in a second step, so do not give one here.\n\n"
        'Return JSON: {"mentions":[{"span_text":..,"context":..,"negated":..,'
        '"confidence":..}]}\n'
    )


def pick_prompt(over: dict | None = None) -> str:
    s = resolve(over)
    extra = s.get("pick_extra")
    return (
        f"For each {s['entity_short']} below, choose the {s['vocabulary_short']} that means the same thing.\n"
        "\n"
        + s["pick_guidance"] + "\n"
        f'\nEach {s["entity_short"]} has a number after the word "{s["entity_short"]}". '
        f'Each {s["vocabulary_short"]} has a number\n'
        f"in [square brackets]. Answer with the {s['entity_short']}'s number and the number in\n"
        f"brackets of the {s['vocabulary_short']} you choose. Answer with numbers only, never with a\n"
        f"{s['vocabulary_short']} name. Two other answers exist for choice:\n"
        f"  null          - the {s['entity_short']} is real, but none of these "
        f"{s['vocabulary_short']}s describes it\n"
        f'  "no_concept"  - this is not something any {s["vocabulary_qualifier"]} could describe\n'
        + (("\n" + extra + "\n") if extra else "")
        + "\n{blocks}\n"
        'Return JSON: {{"picks":[{{"reaction":..,"choice":..}}]}}\n'
    )


_ASK = ask()
_RULES = rules()
S0_PROMPT = s0_prompt()
S1_PROMPT = s1_prompt()
FIND_PROMPT = find_prompt()
PICK_PROMPT = pick_prompt()


#: The few-shot ARM (rung0_fewshot, default False). CADEC's span conventions
#: are not all stateable as prose — measured 2026-08-25, gold KEEPS a leading
#: intensifier 3x more often than it drops one (6.8% vs 2.2%), so a "trim the
#: intensifier" rule was rejected and the example models the dominant
#: convention instead. The post is SYNTHETIC: CADEC is non-transferable and
#: this file is tracked, so the example must never quote the corpus — there is
#: a test asserting it does not.
FEWSHOT = """
Example. A post reading:
  "Got terrible cramps in both legs. The cramps came back the next night.
   Felt totally washed out all week. My doctor ordered an MRI."
has exactly these mentions:
  "terrible cramps in both legs"  - the writer's own words, intensifier included
  "cramps"                        - the same reaction, reported again where it reappears
  "washed out"                    - a vague general state is still a reaction
and nothing for the MRI - a test done to the writer, not a reaction.
"""


def _extraction_prompt(base: str, cfg: dict | None) -> str:
    """The step's extraction prompt, plus the worked example when the few-shot
    arm is on. Appended to ALL of S0/S1/FIND identically — scope is identical
    across steps by design, and an example only some steps saw would break
    that.

    Pool-derived examples (rung0_fewshot_block, rendered by apply() from
    rung0_fewshot_docs) replace the synthetic FEWSHOT when present: real
    CADEC examples carry the corpus's own conventions, which the synthetic
    one cannot. The synthetic block stays as the no-configuration fallback.
    """
    cfg = cfg or {}
    if not cfg.get("rung0_fewshot"):
        return base
    return base + (cfg.get("rung0_fewshot_block") or FEWSHOT)


def render_fewshot(examples: list[tuple[str, list[str]]]) -> str:
    """Worked examples as the prompt shows them: the post, then its mentions.

    `examples` is (post_text, [mention texts in document order]). A repeated
    mention text is annotated as a repeat — the convention it exists to
    teach. Pure so it is testable without the corpus; the corpus-reading
    wrapper is pool_fewshot_block below.
    """
    out = []
    for text, mentions in examples:
        seen: set[str] = set()
        lines = []
        for m in mentions:
            key = " ".join(m.lower().split())
            note = "  - the same reaction, reported again where it reappears" \
                if key in seen else ""
            seen.add(key)
            lines.append(f'  "{m}"{note}')
        body = "\n   ".join(text.strip().splitlines())
        out.append(
            f'Example. A post reading:\n  "{body}"\n'
            "has exactly these mentions, each one reported separately:\n"
            + "\n".join(lines)
        )
    return "\n\n" + "\n\n".join(out) + "\n"


def pool_fewshot_block(man: dict, doc_ids: list[str], loader=None) -> str:
    """Render rung0_fewshot_docs into a prompt block, from data/ at runtime.

    The corpus is non-transferable, so the examples can never live in a
    tracked file — only the doc IDs are configuration, and the text is read
    from the licensed local copy each run.

    POOL ONLY, refused otherwise: a dev or test example would put that
    document's own gold answers in the prompt while the document is being
    scored. Pool is disjoint from both by construction and is never scored.
    """
    from ladder import clean
    from ladder import corpus as corpus_mod

    pool = set(corpus_mod.read_split(man["corpus"]["splits_dir"], "pool"))
    outside = [d for d in doc_ids if d not in pool]
    if outside:
        raise ValueError(
            f"rung0_fewshot_docs {outside} are not in the pool split. An "
            "example from dev or test puts its own gold answers in the "
            "prompt of a scored run."
        )
    # `cadec_root` was hardcoded here — a rung reaching for the corpus
    # directly rather than receiving it. The FiNER port found it: this is
    # the second corpus-loading site in the codebase and the only one
    # inside a rung.
    _c = man.get("corpus") or {}
    docs = (loader or corpus_mod.load_corpus)(_c.get("root") or _c["cadec_root"])
    excluded = clean.load_exclusions()
    examples = []
    for d in doc_ids:
        doc = docs[d]
        # Document order, not annotation-file order — the example reads as a
        # walk through the post, which is the behaviour it teaches.
        kept = sorted(
            (m for m in doc.mentions
             if m.entity_type == REACTION and m.record_id not in excluded),
            key=lambda m: m.spans[0][0] if m.spans else 0,
        )
        examples.append((doc.text, [m.text for m in kept]))
    return render_fewshot(examples)




def locate(span_text: str, source: str, context: str = "", claimed=None):
    """Find span_text in source. Returns (start, end, how).

    Replaces the model's character arithmetic, which is wrong at every model
    size, with a search anchored on something models are good at: quoting. When
    the quote appears more than once — 14.5% of CADEC mentions — the preceding
    words decide which one, and first-occurrence is only right 33.9% of the
    time, so the anchor is doing real work rather than tidying.
    """
    if not span_text:
        return -1, -1, "empty"
    hits, i = [], source.find(span_text)
    while i != -1:
        hits.append(i)
        i = source.find(span_text, i + 1)
    if not hits:
        low = source.lower().find(span_text.lower())
        if low == -1:
            return -1, -1, "not_in_source"
        return low, low + len(span_text), "context_case_insensitive"
    if len(hits) == 1:
        return hits[0], hits[0] + len(span_text), "context_unique"

    ctx = " ".join((context or "").split()).lower()
    if ctx:
        for h in hits:
            before = " ".join(source[max(0, h - len(ctx) - 8):h].split()).lower()
            if before.endswith(ctx):
                return h, h + len(span_text), f"context_anchored_of_{len(hits)}"
    if isinstance(claimed, int) and claimed >= 0:
        h = min(hits, key=lambda x: abs(x - claimed))
        return h, h + len(span_text), f"context_claimed_of_{len(hits)}"
    return hits[0], hits[0] + len(span_text), f"context_first_of_{len(hits)}"


def _menu(cands) -> list[str]:
    if not cands:
        return ["     (no candidates)"]
    return [f'     [{c["i"]}] {c.get("fsn") or c.get("label")}' for c in cands]


def _blocks(pairs) -> str:
    """Render the numbered candidate menus the PICK call reads.

    One menu per mention, because S2's shortlists are retrieved per mention
    and genuinely differ. A `shared=` path printed one identical list once —
    S3's, and S3 alone; it went with S3 rather than staying as scaffolding a
    later reader would mistake for a code path in use. The measurement it
    encoded (a 666-item list rendered per mention put 1,998 candidate lines
    and ~13.7k tokens into one prompt) is in docs/decisions.md, which is where
    a finding survives its mechanism.
    """
    out = []
    for idx, (rec, cands) in enumerate(pairs):
        # The pick must know a mention is a denial, or it reasons "they did
        # not have it, no concept applies" and declines — measured on the
        # first negation run: every denied gold mention it found, it then
        # refused to code. Gold codes the concept being denied.
        denied = " [denied]" if rec.checks.get("r0_negated") else ""
        out.append("\n".join([f'reaction {idx}:{denied} "{rec.text}"', *_menu(cands)]))
    return "\n\n".join(out) + "\n"


def _mention_record(doc_id: str, i: int, m: dict, source: str, step: str) -> Record:
    """The one place a Record is built, so all four steps write the same keys."""
    start, end, how = locate(
        m.get("span_text", ""), source, m.get("context", ""), m.get("start")
    )
    rec = Record(
        doc_id=doc_id,
        entity_type=REACTION,
        text=m.get("span_text", ""),
        spans=[(start, end)],
        confidence=float(m.get("confidence", 0) or 0),
        record_id=f"{doc_id}#{i}",
    )
    # The model's OWN polarity claim (2026-08-25) — CADEC annotates denied
    # reactions, 427 gold mentions (4.7%), so they are extracted and flagged
    # rather than skipped. Written twice on purpose: rung 1's cue check does
    # rec.checks.update(...) with its own "negated", so in a full-ladder run
    # that key ends up holding the CUE verdict — r0_negated is the copy that
    # survives, keeping the model-vs-cue cross-check readable from disk.
    negated = bool(m.get("negated", False))
    rec.checks.update(
        rung0_step=step, offsets=how, negated=negated, r0_negated=negated
    )
    return rec


def _keywords(cfg: dict):
    """The keyword table, loaded once per run and cached on the cfg.

    NOT the registry. `Registry.resolve` searched every description in the
    release — organisms, products, substances and qualifiers included — which
    is the class that answered |California chicken (organism)| for a rectal
    bleed and let |Gaseous substance| outrank the right concept for "gas". The
    keyword table is findings and disorders only.

    The registry stays in cfg and is still S2's retrieval source; rung 1 needs
    it over the WHOLE release, because 82249009 is real, active, and absent
    from the keyword table on purpose.

    A missing table RAISES. Resolving nothing silently would report a build
    step nobody ran as a model that named no concepts.
    """
    table = cfg.get("keywords")
    if table is None:
        from ladder.keywords import DEFAULT_OUT, KeywordTable

        path = cfg.get("keyword_table") or DEFAULT_OUT
        try:
            table = KeywordTable(path)
        except FileNotFoundError as exc:
            raise RuntimeError(
                f"rung 0 resolves names through {path}, which is missing. "
                "Build it once with:\n    python -m ladder.keywords --build"
            ) from exc
        cfg["keywords"] = table
    return table


def _resolve_labels(rec: Record, labels, cfg: dict, source_name: str) -> None:
    """Turn the model's proposed NAMES into a code, and record how it went.

    There is no fallback to the registry when the table has no row. An
    unresolved name is UNRESOLVED — falling back would reinstate the search
    the table exists to replace and hide which of the two answered. Rung 0
    does not retry either: it walks its remaining names and stops, because a
    retry loop here IS rung 2.
    """
    if isinstance(labels, str):
        labels = [labels]
    proposed = [str(x) for x in (labels or []) if x is not None and str(x).strip()]
    got = _keywords(cfg).resolve(proposed)
    rec.sct = got["code"]
    rec.sct_label = got["label"]
    rec.checks.update(
        label_source=source_name,
        code_source="keyword_table",
        label_rank=got["rank"],
        label_unresolved=got["code"] is None,
        label_ambiguous=got["ambiguous"],
        # WHAT the model said, not just whether it worked. `sct_label` holds
        # only the name that WON, so a failed resolution used to record that
        # it failed and not what was proposed — and two very different
        # failures then looked identical on disk: the model naming nothing
        # usable, and the model naming a real concept this table happens not
        # to carry. The first is a model problem and the second is a
        # vocabulary problem.
        #
        # Measured on ARTHROTEC.107 with granite4:micro-h at S1: the model
        # answered sct_label: ["AFTERPROMPT"], a prompt artifact rather than a
        # clinical term. Emphatically the first kind, and invisible until this
        # was recorded. It is also what makes lookup-vs-retrieval measurable
        # at all — you cannot test whether dense retrieval rescues an
        # imperfect label if the imperfect label was discarded.
        labels_proposed=proposed,
    )
    if got.get("candidates"):
        rec.checks["candidates"] = got["candidates"]


def _step_s0(doc_id, source, llm, cfg, meta):
    raw, usage = llm(_extraction_prompt(s0_prompt(cfg.get("prompt_slots")), cfg), source, "S0")
    meta["tokens_in"] += usage["in"]
    meta["tokens_out"] += usage["out"]
    meta["usd"] = meta.get("usd", 0.0) + usage.get("usd", 0.0)
    meta["truncated"] = meta.get("truncated", False) or bool(usage.get("truncated"))
    meta["timed_out"] = meta.get("timed_out", False) or bool(usage.get("timed_out"))
    meta["api_calls"] += 1
    parsed = _parse(raw, meta)
    if parsed is None:
        return []
    out = []
    for i, m in enumerate(parsed.get("mentions", [])):
        rec = _mention_record(doc_id, i, m, source, "S0")
        labels = m.get("sct_label") or []
        if isinstance(labels, str):
            labels = [labels]
        # S0 asks for ONE code — "the id matching sct_label[0]". Models answer
        # with a list anyway. `str(code)` turned that into
        # "['21456007', '38485006']", a string no code can ever equal, so the
        # mention scored 0 by construction even when the first id was right.
        # It also made "the model named three codes" indistinguishable from
        # "the model emitted garbage", and those are different failures.
        #
        # The first is taken, because that is the one the prompt asks for, and
        # the schema violation is COUNTED rather than repaired away: how often
        # a model ignores "one code" is a reliability fact about the model,
        # which is exactly what S0 measures.
        # A NULL code with a label present is the model saying "I know the
        # concept, not its number" — an answer S0 had no way to express, so
        # the model deliberated instead. Measured on the dev split before this
        # existed: 10% of calls ran to the 8,000-token cap and returned
        # nothing, on two-line posts, at a healthy 52 tok/s. It was not
        # thinking hard; it had been given a question with no legal answer.
        #
        # Counted separately from CONCEPT_LESS, which is a claim about the
        # VOCABULARY rather than about the model's memory. Without the split, a
        # model with a bad memory looks like a gap in SNOMED.
        code = m.get("sct_code")
        if code is None and labels and str(labels[0]).strip().upper() != CONCEPT_LESS:
            rec.checks["code_unknown"] = True
            meta["code_unknown"] = meta.get("code_unknown", 0) + 1
        if isinstance(code, (list, tuple)):
            rec.checks["sct_code_multi"] = [str(c) for c in code]
            meta["multi_code"] = meta.get("multi_code", 0) + 1
            code = code[0] if code else None
        rec.sct = str(code) if code is not None else None
        rec.sct_label = str(labels[0]) if labels else None
        rec.checks.update(label_source="memory", code_source="memory")
        out.append(rec)
    return out


def _label_candidates(proposed, cfg) -> list[dict]:
    """Every concept EVERY proposed name maps to, deduped, in proposal order.

    This is what multi-label was always for and never did: raise the chance
    that something maps, then hand the alternatives to the decide step. The
    old path took the first name that mapped and threw the rest away.

    Ambiguous keywords contribute ALL their concepts, not just the first —
    |coma| is both 371632003 and 50061006, and choosing between them is the
    same judgement as choosing between two names, not a coin for a build
    script to flip.

    Displayed by the VOCABULARY's own words where it has them, not by the
    model's proposal: showing the model its own wording back invites it to
    prefer whichever it wrote first, which is the bias being removed.
    """
    table = _keywords(cfg)
    reg = cfg.get("registry")
    out, seen = [], set()
    for rank, label in enumerate(proposed):
        if str(label).strip().upper() == CONCEPT_LESS:
            continue
        for code in table.lookup(label):
            if code in seen:
                continue
            seen.add(code)
            shown = None
            if reg is not None:
                shown = (getattr(reg, "fsn", lambda c: None)(code)
                         or getattr(reg, "preferred", lambda c: None)(code))
            out.append({
                "i": len(out),
                "code": code,
                "label": shown or label,
                "fsn": shown or label,
                "via": "keyword_table",
                "from_rank": rank,
                "from_label": label,
            })
    return out


def _step_s1(doc_id, source, llm, cfg, meta):
    """Propose names, map ALL of them, then decide against the original text.

    Two calls when there is something to decide, ONE when there is not — a
    single candidate is not a choice, and paying for a pick over it is pure
    cost. So S1's call count is data about the corpus, not a constant.
    """
    raw, usage = llm(_extraction_prompt(s1_prompt(cfg.get("prompt_slots")), cfg), source, "S1")
    meta["tokens_in"] += usage["in"]
    meta["tokens_out"] += usage["out"]
    meta["usd"] = meta.get("usd", 0.0) + usage.get("usd", 0.0)
    meta["truncated"] = meta.get("truncated", False) or bool(usage.get("truncated"))
    meta["timed_out"] = meta.get("timed_out", False) or bool(usage.get("timed_out"))
    meta["api_calls"] += 1
    parsed = _parse(raw, meta)
    if parsed is None:
        return []

    out, undecided = [], []
    for i, m in enumerate(parsed.get("mentions", [])):
        rec = _mention_record(doc_id, i, m, source, "S1")
        labels = m.get("sct_label") or []
        if isinstance(labels, str):
            labels = [labels]
        proposed = [str(x) for x in labels if x is not None and str(x).strip()]
        cands = _label_candidates(proposed, cfg)
        rec.checks.update(
            label_source="memory",
            code_source="keyword_table",
            labels_proposed=proposed,
            label_ambiguous=len(cands) > 1,
            label_unresolved=not cands,
        )
        if cands:
            rec.checks["candidates"] = cands
        out.append(rec)

        if len(cands) > 1:
            undecided.append((rec, cands))
            continue
        if len(cands) == 1:
            rec.sct = cands[0]["code"]
            # The model's own name, not the vocabulary's — see _decide.
            rec.sct_label = cands[0]["from_label"]
            rec.checks["label_rank"] = cands[0]["from_rank"]
            continue
        # Nothing mapped. CONCEPT_LESS is an ASSERTION the model made, and a
        # dead end is not one — the two must not collapse into each other.
        if any(str(x).strip().upper() == CONCEPT_LESS for x in proposed):
            rec.sct = CONCEPT_LESS
            rec.sct_label = CONCEPT_LESS
            rec.checks["label_unresolved"] = False
            rec.checks["label_rank"] = next(
                i for i, x in enumerate(proposed)
                if str(x).strip().upper() == CONCEPT_LESS
            )
        else:
            rec.sct = None
            rec.sct_label = None
            rec.checks["label_rank"] = None

    # ONE decide call per document, over only the mentions that need one.
    # Menu position is the answer key, so a mention that was never shown must
    # not occupy a slot in it.
    if undecided:
        _decide(undecided, source, llm, cfg, meta, "S1")
    return out


RETRIEVERS = ("lexical", "dense", "full")


def _retriever(cfg: dict):
    """(search_fn, name) for S2's candidate menu.

    Both return the same hit shape — `i`, `code`, `label`, `fsn`, `via` — so
    S2's pick logic does not branch on which one ran. A retriever with a
    different shape would fail at the PICK rather than at the swap, which is
    a long way from the cause.
    """
    which = cfg.get("rung0_retrieval", DEFAULTS["rung0_retrieval"])
    if which not in RETRIEVERS:
        raise ValueError(
            f"rung0_retrieval={which!r} is not one of {RETRIEVERS}. A retriever "
            "nobody defined would report a run under a label the article "
            "cannot explain."
        )
    if which == "lexical":
        reg = cfg["registry"]
        return (lambda text, k: reg.shortlist(text, k=k)), which

    if which == "full":
        # No ranking, no query: the whole vocabulary IS the menu. Correct when
        # it fits in a prompt, which is the case that makes retrieval
        # unnecessary rather than the case that makes it easy. The `text`
        # argument is ignored, deliberately — a number carries no terms to rank
        # on, and pretending otherwise is what produced an empty menu and a
        # null code for every record.
        reg = cfg.get("registry")
        if reg is None or not hasattr(reg, "all_codes"):
            raise RuntimeError(
                "rung0_retrieval='full' needs a vocabulary that can enumerate "
                "itself (an `all_codes()` method). It is meant for a tag set "
                "small enough to put in a prompt; SNOMED is not."
            )
        menu = [{"code": c, "label": reg.preferred(c) or c, "fsn": c,
                 "via": "full"} for c in reg.all_codes()]
        return (lambda text, k: menu), which

    index = cfg.get("dense")
    if index is None:
        from ladder.embed import DEFAULT_PREFIX, EmbeddingIndex

        prefix = cfg.get("embed_prefix") or DEFAULT_PREFIX
        try:
            index = EmbeddingIndex(prefix)
        except FileNotFoundError as exc:
            raise RuntimeError(
                f"rung0_retrieval='dense' needs the embedding index at "
                f"{prefix}, which is missing. Build it once (minutes) with:\n"
                "    python -m ladder.embed --build"
            ) from exc
        cfg["dense"] = index
    return (lambda text, k: index.search(text, k=k)), which


def _merged_candidates(search, span: str, labels: list[str], k: int) -> list[dict]:
    """The menu: hits for the SPAN and for each proposed NAME, merged.

    Measured on arm 3 (2026-08-25): 35 of 226 gold mentions never had their
    code on a span-only menu, and the recurring case is a colloquial span
    whose embedding cannot reach the clinical concept — "extremely sick"
    never surfaces |Generally unwell|, but the model can PROPOSE that name.

    Deduped by concept, capped at k, renumbered. Ordered by score when every
    hit carries one (cosine scores are comparable across queries — same
    embedder); span-hits-first otherwise, so the lexical path keeps a
    deterministic order. Each hit records which query found it.
    """
    batches = [("span", search(span, k))]
    for lb in labels:
        batches.append(("label", search(lb, k)))
    hits = [{**h, "query": q} for q, batch in batches for h in batch]
    if hits and all(isinstance(h.get("score"), (int, float)) for h in hits):
        hits.sort(key=lambda h: -h["score"])
    seen, out = set(), []
    for h in hits:
        if h["code"] in seen:
            continue
        seen.add(h["code"])
        out.append({**h, "i": len(out)})
        if len(out) >= k:
            break
    return out


MENU_ORDERS = ("score", "alpha")


def _order_menu(cands: list[dict], which: str) -> list[dict]:
    """The menu in its declared order, renumbered. S2 only — S1's menus are
    the model's own names' codes, typically two or three lines."""
    if which not in MENU_ORDERS:
        raise ValueError(
            f"rung0_menu_order={which!r} is not one of {MENU_ORDERS}. An order "
            "nobody defined would report a run under a label the article "
            "cannot explain."
        )
    if which == "alpha":
        cands = sorted(
            cands, key=lambda c: str(c.get("fsn") or c.get("label") or "").lower()
        )
        cands = [{**c, "i": n} for n, c in enumerate(cands)]
    return cands


def _step_pick(doc_id, source, llm, cfg, meta, step):
    """S2: find the mentions, then choose from a shortlist retrieved for each."""
    raw, usage = llm(_extraction_prompt(find_prompt(cfg.get("prompt_slots")), cfg), source, step)
    meta["tokens_in"] += usage["in"]
    meta["tokens_out"] += usage["out"]
    meta["usd"] = meta.get("usd", 0.0) + usage.get("usd", 0.0)
    meta["truncated"] = meta.get("truncated", False) or bool(usage.get("truncated"))
    meta["timed_out"] = meta.get("timed_out", False) or bool(usage.get("timed_out"))
    meta["api_calls"] += 1
    parsed = _parse(raw, meta)
    if parsed is None:
        return []

    search, retrieval = _retriever(cfg)
    pairs = []
    for i, m in enumerate(parsed.get("mentions", [])):
        rec = _mention_record(doc_id, i, m, source, step)
        labels = m.get("sct_label") or []
        if isinstance(labels, str):
            labels = [labels]
        proposed = [str(x) for x in labels
                    if x is not None and str(x).strip()
                    and str(x).strip().upper() != CONCEPT_LESS]
        menu_order = cfg.get("rung0_menu_order", DEFAULTS["rung0_menu_order"])
        cands = _order_menu(
            _merged_candidates(
                search, rec.text, proposed, cfg.get("rung0_shortlist_k", 20)
            ),
            menu_order,
        )
        rec.checks["candidates"] = cands
        rec.checks["rung0_menu_order"] = menu_order
        # WHAT the model offered, same as S0/S1 — it is also what makes the
        # lookup-vs-retrieval 2x2 measurable on S2 runs.
        rec.checks["labels_proposed"] = proposed
        rec.checks["label_source"] = "shortlist"
        rec.checks["code_source"] = "shortlist"
        # Two runs that differ only in their retriever must not look identical
        # on disk. The manifest copy beside the results says it too.
        rec.checks["rung0_retrieval"] = retrieval
        pairs.append((rec, cands))

    if not pairs:
        return []
    _decide(pairs, source, llm, cfg, meta, step)
    return [rec for rec, _ in pairs]


def _decide(pairs, source, llm, cfg, meta, step) -> None:
    """THE DECIDE STEP. One call, one menu, the ORIGINAL text beside each menu.

    Shared by S1 and S2, and that is the point rather than an economy. Getting
    several candidate concepts is only half the job; the other half is saying
    which of them matches what the reporter actually wrote, and it is the same
    judgement whichever way the candidates were obtained.

    S2 always had this. S1 did not — `resolve()` walked the proposed names and
    returned the FIRST that mapped, so the span was never consulted. Measured
    on the real keyword table for "extreme rectal bleed":

        'rectal pain'       -> 77880009   WON, on list position alone
        'rectal bleeding'   -> 12063002   right, mapped fine, discarded
        'rectal hemorrhage' -> 12063002   right, mapped fine, discarded

    `pairs` is (record, candidates) for the mentions that HAVE something to
    decide. Callers must leave out mentions with none: menu position is the
    answer key here, and padding it with entries the model was not shown would
    assign one mention's pick to another.
    """
    raw, usage = llm(pick_prompt(cfg.get("prompt_slots")).format(blocks=_blocks(pairs)), source, step)
    meta["tokens_in"] += usage["in"]
    meta["tokens_out"] += usage["out"]
    meta["usd"] = meta.get("usd", 0.0) + usage.get("usd", 0.0)
    meta["truncated"] = meta.get("truncated", False) or bool(usage.get("truncated"))
    meta["timed_out"] = meta.get("timed_out", False) or bool(usage.get("timed_out"))
    meta["api_calls"] += 1
    # A pick reply that will not parse is NOT the model declining. Measured on
    # the retired S3: 666 candidates cost 16.9k prompt tokens and came back as
    # 14 tokens of truncated JSON. Counting that as "saw the menu, chose
    # nothing" would report a transport failure as an abstention.
    picked = _parse(raw, {})
    pick_failed = picked is None
    if pick_failed:
        meta["pick_parse_failed"] = True
    choices = {}
    if picked is not None:
        # A reply that parses to something other than an object is a parse
        # failure, not a crash. mistral:7b-instruct returned a bare value
        # here; the contract in _parse says a bad shape costs one document.
        if not isinstance(picked, dict):
            meta["pick_parse_failed"] = True
            picked = {}
        for p in picked.get("picks", []):
            # "reaction" is what the prompt asks for; "i" is accepted too,
            # because an earlier prompt used it and its cached replies are
            # still valid data.
            ref = p.get("reaction", p.get("i"))
            try:
                choices[int(ref)] = p.get("choice")
            except (TypeError, ValueError):
                continue

    for idx, (rec, cands) in enumerate(pairs):
        if pick_failed:
            rec.checks["pick_parse_failed"] = True
            continue
        if idx not in choices:
            rec.checks["no_pick"] = True
            meta["no_pick"] = meta.get("no_pick", 0) + 1
            continue
        choice = choices[idx]
        # The string "null" is the model SAYING null, not failing to use the
        # menu — measured 9 times in one dev run, always from a reply that
        # used real numbers elsewhere. Same posture as the fence stripping
        # and the old "i" key: a transport convention, normalised and gone.
        if isinstance(choice, str) and choice.strip().lower() in ("null", "none"):
            choice = None
        if isinstance(choice, str) and choice.strip().lower() == "no_concept":
            # The explicit assertion the decline is not: "this is not a
            # codable reaction". This is what CONCEPT_LESS means, and the one
            # way S2 can say it — 10 of 226 dev gold mentions (4%) are
            # concept-less, and after the decline revision below a null could
            # no longer reach them.
            rec.sct = CONCEPT_LESS
            rec.sct_label = CONCEPT_LESS
            continue
        if choice is None:
            # REVISED 2026-08-25: this used to write CONCEPT_LESS, on the
            # theory that declining the menu asserts no concept fits. But the
            # menu is k of 227,554 — it misses the gold code for 13.0% of
            # coded mentions even deduped — so the decline asserts "none of
            # THESE" and nothing wider. The scorer credits CONCEPT_LESS as
            # CORRECT against concept-less gold, so the old behaviour scored
            # a vocabulary-wide claim the model never made. Degrades to None
            # (abstained), never up to an assertion.
            rec.sct = None
            rec.sct_label = None
            rec.checks["declined_shortlist"] = True
            meta["declined_shortlist"] = meta.get("declined_shortlist", 0) + 1
            continue
        try:
            n = int(choice)
        except (TypeError, ValueError):
            rec.checks["bad_pick"] = choice
            meta["bad_pick"] = meta.get("bad_pick", 0) + 1
            continue
        if not 0 <= n < len(cands):
            # Never clamped: an out-of-range index is the model failing to use
            # the menu, and clamping it would report that as a code choice.
            rec.checks["bad_pick"] = n
            meta["bad_pick"] = meta.get("bad_pick", 0) + 1
            continue
        chosen = cands[n]
        # `sct_label` is "what the MODEL said that code means", and rung 1's
        # label_check compares it against the vocabulary's own words for the
        # code. Filling it FROM the vocabulary makes that check vacuous — it
        # could never fail. So when the candidate carries the model's own
        # proposing name (S1 does; S2's retrieved candidates do not), that is
        # what is recorded.
        label = (chosen.get("from_label")
                 or chosen.get("fsn") or chosen.get("label"))
        if chosen.get("code"):
            rec.sct = chosen["code"]
            rec.sct_label = label
            rec.checks["label_unresolved"] = False
            # Which of the model's OWN names reached the chosen concept. That
            # is the finding multi-label exists to produce, so it survives onto
            # the record; S2's candidates carry no proposing name and get 0.
            rec.checks["label_rank"] = chosen.get("from_rank", 0)
            rec.checks["label_ambiguous"] = len(cands) > 1
        else:
            _resolve_labels(rec, [label], cfg, rec.checks["label_source"])
            rec.checks["candidates"] = cands


def _trim_records(records: list[Record], trimmer, agg: dict) -> None:
    """Boundary-convention trim, in place, after locate().

    Only grounded spans are touched — (-1, -1) means the quote is not in the
    source, and moving those offsets would fabricate a grounding. The
    original quote survives on the record (`span_untrimmed`), so the trim is
    auditable and the untrimmed number recomputable from disk.
    """
    for rec in records:
        if not rec.text or not rec.spans:
            continue
        start, end = rec.spans[0]
        if not (isinstance(start, int) and start >= 0):
            continue
        text, span = trimmer.trim(rec.text, (start, end))
        if text == rec.text:
            continue
        rec.checks["span_untrimmed"] = rec.text
        rec.checks["span_trimmed"] = True
        rec.text = text
        rec.spans = [span]
        agg["trimmed"] += 1


def _parse(raw: str, meta: dict):
    """JSON or nothing. A parse failure is rung 0's counter-metric, not a bug
    to repair — repairing it here would delete the measurement."""
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        meta["parse_failed"] = True
        return None


def run_step(doc_id: str, source: str, step: str, llm, cfg: dict) -> tuple[list[Record], dict]:
    meta = {"tokens_in": 0, "tokens_out": 0, "api_calls": 0,
            "tool_calls": 0, "usd": 0.0}
    if step == "S0":
        return _step_s0(doc_id, source, llm, cfg, meta), meta
    if step == "S1":
        return _step_s1(doc_id, source, llm, cfg, meta), meta
    return _step_pick(doc_id, source, llm, cfg, meta, step), meta


def honoured_tool(rec: Record) -> bool | None:
    """Mode B only. NOT what the name says — read this before quoting it.

    The name claims tool fidelity: the model searched, got candidates, and
    either used one or overrode it. **That is not what happens.** `vocab.search`
    runs in the parse loop above, AFTER the model has returned its JSON and
    after `rec.sct` is set from it. The model never sees the results.

    What this actually measures is a COINCIDENCE RATE: does the code the model
    invented from memory happen to appear in the candidates a search returns for
    the same text? On the dev split it is never True, which is unsurprising
    given rung 0 produces 0/105 correct codes.

    Mode B is therefore **not a tool-access arm**. It is recall plus a post-hoc
    lookup, and the A/B against mode A measures prompt wording plus one extra
    search per mention. Reporting it as tool access would be a claim the
    experiment cannot support. A real tool loop — the model calling search
    mid-generation and seeing results — is untested and is the obvious next
    experiment, since the model's failure is missing knowledge and a tool is
    what would supply it.

    Returns None when no search was made for this record.
    """
    results = rec.checks.get("tool_results")
    if not results:
        return None
    return str(rec.sct) in {str(r["code"]) for r in results}


def prepare(cfg: dict[str, Any] | None) -> dict[str, Any]:
    """Merge DEFAULTS and build the run-scoped pieces of rung 0's path.

    Validates the step, requires a registry for the steps that resolve codes,
    and builds the few-shot block and the trimmer ONCE, cached on the returned
    cfg. Shared by apply() and by rung 3's sampler — rung 3 must draw its
    votes from the distribution rung 0 actually ran (measured 2026-08-25:
    sampling the legacy recall prompt against an S2 run overwrote 9 of 32
    verified-ACCEPT codes with hallucinations), and two callers stay on one
    path only if one function builds it.
    """
    cfg = {**DEFAULTS, **(cfg or {})}
    step = cfg.get("rung0_step")
    if step is not None and step not in STEPS:
        raise ValueError(
            f"rung0_step={step!r} is not one of {STEPS}. A step nobody defined "
            "would report a run under a label the article cannot explain."
        )
    if step is not None and cfg.get("registry") is None:
        raise RuntimeError(
            f"step {step} resolves codes through the vocabulary and has no "
            "registry. Pass one in cfg."
        )
    if (cfg.get("rung0_fewshot") and cfg.get("rung0_fewshot_docs")
            and not cfg.get("rung0_fewshot_block")):
        cfg["rung0_fewshot_block"] = pool_fewshot_block(
            cfg["manifest"], cfg["rung0_fewshot_docs"],
            loader=cfg.get("corpus_loader"),
        )
    if cfg.get("rung0_trim") and cfg.get("trimmer") is None:
        from ladder.trim import pool_trimmer

        cfg["trimmer"] = pool_trimmer(cfg["manifest"], loader=cfg.get("corpus_loader"))
    return cfg


def extract_document(doc_id: str, text: str, llm, cfg: dict[str, Any]) -> tuple[list[Record], dict]:
    """One document through rung 0's CONFIGURED path — step dispatch plus the
    span trim. The single per-document body: apply() loops over it and rung 3
    samples through it, so the two cannot drift onto different paths.
    `cfg` must have been through prepare()."""
    step = cfg.get("rung0_step")
    if step is None:
        mode = "B" if cfg.get("rung0_mode") == "search" else "A"
        got, meta = rung0(doc_id, text, mode, llm, cfg)
        meta.setdefault("api_calls", 1)
    else:
        got, meta = run_step(doc_id, text, step, llm, cfg)
    if cfg.get("rung0_trim") and cfg.get("trimmer") is not None:
        counts = {"trimmed": 0}
        _trim_records(got, cfg["trimmer"], counts)
        meta["trimmed"] = counts["trimmed"]
    return got, meta


def apply(
    records: list[Record], sources: dict[str, str], cfg: dict[str, Any]
) -> tuple[list[Record], dict]:
    """The rung entry point. `records` is EMPTY — rung 0 builds from `sources`.

    Refuses to run on a non-empty list rather than appending to it: rung 0 twice
    over the same split would double every mention and every number above it.
    """
    cfg = prepare(cfg)
    if records:
        raise RuntimeError(
            f"rung 0 was handed {len(records)} existing records. It is the rung "
            "that CREATES them, so running it over a populated set would double "
            "the mention count. Run it first, or not at all."
        )
    llm = cfg.get("llm")
    if llm is None:
        raise RuntimeError(
            "rung 0 has no model. Skipping silently would report an empty "
            "extraction as a result. Set manifest.model.extractor."
        )
    ledger = cfg.get("ledger")
    mode = "B" if cfg.get("rung0_mode") == "search" else "A"
    step = cfg.get("rung0_step")

    agg: dict[str, Any] = {
        "documents": 0, "records": 0, "tokens_in": 0, "tokens_out": 0,
        "tool_calls": 0, "api_calls": 0, "parse_failed": 0, "usd": 0.0,
        "pick_parse_failed": 0, "truncated": 0, "multi_code": 0, "timed_out": 0,
        "code_unknown": 0, "no_pick": 0, "bad_pick": 0, "declined_shortlist": 0,
        "trimmed": 0,
        "t0": time.time(),
    }
    out: list[Record] = []
    for doc_id, text in sources.items():
        t0 = time.time()
        got, meta = extract_document(doc_id, text, llm, cfg)
        elapsed_ms = (time.time() - t0) * 1000
        agg["documents"] += 1
        agg["parse_failed"] += int(meta.get("parse_failed", False))
        agg["pick_parse_failed"] += int(meta.get("pick_parse_failed", False))
        # Counted SEPARATELY, and it overlaps parse_failed on purpose: a
        # truncated reply IS unusable, but "the harness cut it off" and "the
        # model cannot emit JSON" are different findings and must not share a
        # label. Raising max_tokens moves this, it does not remove it.
        agg["truncated"] += int(meta.get("truncated", False))
        agg["timed_out"] += int(meta.get("timed_out", False))
        # S0 only: mentions where the model answered with several codes where
        # the prompt asked for one.
        agg["multi_code"] += meta.get("multi_code", 0)
        # S0 only: the model named a concept but did not recall its id.
        agg["code_unknown"] += meta.get("code_unknown", 0)
        # S1/S2 pick outcomes that are failures or declines, not choices.
        for k in ("no_pick", "bad_pick", "declined_shortlist"):
            agg[k] += meta.get(k, 0)
        for k in ("tokens_in", "tokens_out", "tool_calls", "api_calls", "usd"):
            agg[k] += meta.get(k, 0)
        agg["trimmed"] += meta.get("trimmed", 0)
        for rec in got:
            rec.checks["honoured_tool"] = honoured_tool(rec)
        # One ledger row per DOCUMENT, not per record: rung 0's unit of cost is
        # the call, and a document that produced no mentions still cost one.
        if ledger:
            ledger.log(
                rung=RUNG,
                doc_id=doc_id,
                record_id=doc_id,
                zone="NEW",
                outcome="parse_failed" if meta.get("parse_failed") else "extracted",
                reason=(
                    "timed_out" if meta.get("timed_out")
                    else "truncated" if meta.get("truncated")
                    else "json_decode" if meta.get("parse_failed")
                    else None
                ),
                tokens_in=meta["tokens_in"],
                tokens_out=meta["tokens_out"],
                api_calls=meta.get("api_calls", 1),
                latency_ms=elapsed_ms,
                # The caller already priced the call from models.yaml. Not
                # passing it logged 0.0 for every paid run, and the bug hid
                # because zero is RIGHT for a local model.
                usd=meta.get("usd", 0.0),
                denominator="r0_documents",
                evaluable="could_not_run" if meta.get("parse_failed") else "pass",
                mode=step or mode,
                mentions=len(got),
            )
        out += got

    agg["records"] = len(out)
    agg["seconds"] = round(time.time() - agg["t0"], 2)
    return out, agg


def report_run(agg: dict) -> None:
    n, docs = agg["records"], agg["documents"]
    print(f"\n{'=' * 58}\nRUNG 0 — bare LLM\n{'=' * 58}")
    print(f"  documents             {docs}")
    print(f"  mentions emitted      {n}  ({n / docs if docs else 0:.1f} per document)")
    print(f"  JSON parse failures   {agg['parse_failed']}")
    print(f"  tokens {agg['tokens_in'] + agg['tokens_out']:6d}   "
          f"tool calls {agg['tool_calls']:3d}   {agg['seconds']}s")


# ============================================================================
# THE ABLATION — does a vocabulary lookup tool help?
#
# Was ladder/rung0_ab.py. Folded in here so the rung and the experiment over it
# cannot drift apart: `run()` calls the same `rung0()` that `apply()` calls, and
# then the ONE measured rung 1, never a second copy of either.
#
#     python -m ladder.rungs.r0 --mode A       # recall only
#     python -m ladder.rungs.r0 --mode B       # search tool
#     python -m ladder.rungs.r0 --compare      # both, side by side
# ============================================================================

# ------------------------------------------------------------------ harness
def run(items, mode, llm, cfg=None):
    """Rung 0, then the measured rung 1 — no second validation implementation."""
    cfg = dict(cfg or {})
    recs: list[Record] = []
    agg = {"tokens_in": 0, "tokens_out": 0, "tool_calls": 0, "parse_failed": 0, "t0": time.time()}
    sources = {}
    ledger = cfg.get("ledger")
    for it in items:
        t0 = time.time()
        got, meta = rung0(it["doc_id"], it["text"], mode, llm, cfg)
        elapsed_ms = (time.time() - t0) * 1000
        for k in ("tokens_in", "tokens_out", "tool_calls"):
            agg[k] += meta.get(k, 0)
        agg["parse_failed"] += int(meta.get("parse_failed", False))
        sources[it["doc_id"]] = it["text"]
        recs += got
        # Same per-document row apply() writes. Rung 0's unit of cost is the
        # call: a document that produced no mentions still cost one. Without
        # this, every script that uses run() — which is all of them — reports
        # rung 0 as free.
        if ledger:
            ledger.log(
                rung=RUNG,
                doc_id=it["doc_id"],
                record_id=it["doc_id"],
                zone="NEW",
                outcome="parse_failed" if meta.get("parse_failed") else "extracted",
                reason=(
                    "timed_out" if meta.get("timed_out")
                    else "truncated" if meta.get("truncated")
                    else "json_decode" if meta.get("parse_failed")
                    else None
                ),
                tokens_in=meta.get("tokens_in", 0),
                tokens_out=meta.get("tokens_out", 0),
                api_calls=1,
                latency_ms=elapsed_ms,
                usd=meta.get("usd", 0.0),
                mentions=len(got),
                denominator="r0_documents",
                evaluable="could_not_run" if meta.get("parse_failed") else "pass",
            )
    r1.apply(recs, sources, cfg)
    for rec in recs:
        rec.checks["honoured_tool"] = honoured_tool(rec)
    agg["seconds"] = round(time.time() - agg["t0"], 2)
    return recs, agg


def report(mode, recs, agg):
    n = len(recs)
    verdicts = [r.checks.get("r1_verdict") for r in recs]
    rej = [r for r in recs if r.checks.get("r1_verdict") == ZONE_REJECT]
    overrode = sum(1 for r in recs if r.checks.get("honoured_tool") is False)
    print(f"\n{'=' * 58}\nMODE {mode} — {'search tool' if mode == 'B' else 'recall only'}\n{'=' * 58}")
    print(f"  mentions emitted by R0     {n}")
    print(f"  rejected by R1             {len(rej)}  ({(len(rej) / n * 100 if n else 0):.0f}%)")
    print(f"  accepted / band            {verdicts.count(ZONE_ACCEPT)} / {verdicts.count(ZONE_BAND)}")
    reasons = {w: sum(1 for r in rej if r.checks.get("r1_reason") == w) for w in REJECT_REASONS}
    audited = {
        w: sum(1 for r in recs
               if w in (r.checks.get("r1_audit", {}) or {}).get("reasons", []))
        for w in REJECT_REASONS
    }
    masked = sum(max(0, audited[w] - reasons[w]) for w in REJECT_REASONS)
    print("  rejection reasons — verdict (first failure) vs every failure:")
    print(f"     {'':22s} {'verdict':>8s} {'all':>6s}")
    for why in REJECT_REASONS:
        if reasons[why] or audited[why]:
            flag = "  <- hidden by check order" if audited[why] > reasons[why] else ""
            print(f"     {why:22s} {reasons[why]:8d} {audited[why]:6d}{flag}")
    if masked:
        print(f"  failures the verdict table did not show: {masked}")
    unevaluable = {}
    for r in recs:
        for k, v in ((r.checks.get("r1_audit", {}) or {}).get("unevaluable") or {}).items():
            unevaluable[f"{k}: {v}"] = unevaluable.get(f"{k}: {v}", 0) + 1
    for k, v in sorted(unevaluable.items()):
        print(f"  could not be checked: {k}  ({v})")
    if mode == "B":
        print(f"  overrode its own lookup    {overrode}")
    print(
        f"  tokens {agg['tokens_in'] + agg['tokens_out']:6d}"
        f"   tool calls {agg['tool_calls']:3d}"
        f"   JSON failures {agg['parse_failed']}"
        f"   {agg['seconds']}s"
    )
    return {
        "mode": mode,
        "n": n,
        "rejected": len(rej),
        "reasons": reasons,
        "reasons_all": audited,
        "masked": masked,
        "overrode_tool": overrode,
        "tokens": agg["tokens_in"] + agg["tokens_out"],
        "tool_calls": agg["tool_calls"],
    }


def compare(a, b):
    print(f"\n{'=' * 58}\nA vs B — the ablation\n{'=' * 58}")
    print(f"  {'':24s} {'A recall':>10s} {'B tool':>10s}")
    print(
        f"  {'rejection rate':24s} "
        f"{a['rejected'] / max(a['n'], 1) * 100:9.0f}% {b['rejected'] / max(b['n'], 1) * 100:9.0f}%"
    )
    for w in REJECT_REASONS:
        if a["reasons"].get(w) or b["reasons"].get(w):
            print(f"  {w:24s} {a['reasons'].get(w, 0):10d} {b['reasons'].get(w, 0):10d}")
    print(f"  {'overrode its own lookup':24s} {a['overrode_tool']:10d} {b['overrode_tool']:10d}")
    print(f"  {'tokens':24s} {a['tokens']:10d} {b['tokens']:10d}")
    print(f"  {'vocabulary calls':24s} {a['tool_calls']:10d} {b['tool_calls']:10d}")
    print("\n  Read it this way: if B's rejection rate falls but errors reappear as")
    print("  'overrode its own lookup' or as wrong-but-valid codes, the tool MOVED")
    print("  the errors rather than removing them. That is the finding either way.")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="rung 0 — the bare LLM, and the tool ablation over it")
    ap.add_argument("--mode", choices=["A", "B"])
    ap.add_argument("--compare", action="store_true")
    ap.add_argument("--manifest", default="manifest.json")
    ap.add_argument(
        "--model",
        help="provider/model from ladder/models.yaml. Defaults to "
        "manifest.model.extractor, then to a local ollama model — a hosted "
        "provider sends CADEC text off the machine and needs LADDER_ALLOW_REMOTE=1",
    )
    a = ap.parse_args(argv)

    from ladder.manifest import load_manifest
    from ladder.registry import Registry

    man = load_manifest(a.manifest)
    cfg = dict(man["rungs"].get("1", {}))
    cfg["registry"] = Registry(man["vocabulary"]["snomed_db"])
    cfg["ledger"] = Ledger(f"{man['output']['dir']}/r0_ab.ledger.jsonl", run_id="r0_ab")

    from ladder.llm import for_rung
    from ladder.stub_llm import load_items

    stub = for_rung(0, man, a.model)
    print(f"[rung0] model={stub.spec} ({stub.role})")

    items = load_items(man["corpus"]["splits_dir"])
    if a.compare:
        ra, ga = run(items, "A", stub, cfg)
        rb, gb = run(items, "B", stub, cfg)
        compare(report("A", ra, ga), report("B", rb, gb))
    else:
        mode = a.mode or ("B" if man.get("rung0_mode") == "search" else "A")
        report(mode, *run(items, mode, stub, cfg))
    cfg["ledger"].close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

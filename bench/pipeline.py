"""The ladder as composable layers.

One function runs an item through any subset of layers {1..6} on top of the
bare call (layer 0 = empty set). Cumulative rung r = layers {1..r}; the
single-rung ablation of r = layers {r}. Every layer is exactly the mechanism
from the spec; all calls go through the cached client at temperature 0.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Callable

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bench.flatten import flatten_json, index_free_path, schema_node_for_path
from bench.llm import LLMClient
from bench.normalize import format_ok, normalize_text, normalize_value, values_match
from bench.parse import parse_reply
from bench.prompts import N_VARIANTS, base_messages, judge_messages, revise_messages
from schemas.adapter import Dataset, Item
from schemas.runner import Cost, FieldResult, RunnerOutput

RUNG_NAMES = {
    0: "bare_llm",
    1: "deterministic",
    2: "abstention",
    3: "self_correction",
    4: "llm_judge",
    5: "voting",
    6: "human_in_loop",
}

CONF_THRESHOLD = 0.7
DEFAULT_CONF = 0.8          # when the model doesn't report one
HUMAN_MINUTES_PER_ITEM = 2.0

# live rung-6 hook: (item, path, draft_value, confidence) -> corrected value
HumanResolver = Callable[[Item, str, str | None, float], str | None]


def _lookup(mapping: dict, path: str, default=None):
    return mapping.get(path, mapping.get(index_free_path(path), default))


def run_item(
    client: LLMClient,
    dataset: Dataset,
    item: Item,
    layers: set[int],
    sample_index: int = 0,
    human_resolver: HumanResolver | None = None,
    conf_threshold: float = CONF_THRESHOLD,
) -> RunnerOutput:
    schema = dataset.output_schema
    prompt = dataset.prompt or (
        "Extract the fields described by the output schema from the document."
    )
    trusted_flat = flatten_json(item.trusted_record) if item.trusted_record else None
    gold_paths = list(flatten_json(item.gold).keys())
    calls = []

    def call(messages):
        resp = client.chat(messages, sample_index=sample_index)
        calls.append(resp)
        return resp

    # --- layer 0/5: base generation (5 prompt variants when voting) ----------
    n_variants = N_VARIANTS if 5 in layers else 1
    parses = []
    for v in range(n_variants):
        resp = call(base_messages(prompt, schema, item.doc, item.trusted_record, v))
        parses.append(parse_reply(resp.text))

    def canon(path, value):
        """Comparison key for voting: normalized when layer 1 is on, raw otherwise."""
        if value is None:
            return None
        node = schema_node_for_path(schema, path)
        return normalize_value(value, node) if 1 in layers else str(value)

    values: dict[str, object] = {}
    confs: dict[str, float] = {}
    verdicts: dict[str, str] = {}
    if n_variants == 1:
        ans, conf_map, verd_map = parses[0]
        flat = flatten_json(ans) if ans else {}
        for p in gold_paths:
            values[p] = flat.get(p)
            confs[p] = float(_lookup(conf_map, p, DEFAULT_CONF if p in flat else 0.0))
            verdicts[p] = str(_lookup(verd_map, p, "n_a"))
    else:
        flats = [flatten_json(a) if a else {} for a, _, _ in parses]
        for p in gold_paths:
            variants = [(canon(p, f.get(p)), f.get(p)) for f in flats]
            counts: dict = {}
            for key, _ in variants:
                counts[key] = counts.get(key, 0) + 1
            modal_key = max(counts, key=counts.get)
            share = counts[modal_key] / n_variants
            values[p] = next(raw for key, raw in variants if key == modal_key)
            confs[p] = share  # vote share IS the confidence under voting
            verd_votes = [str(_lookup(v, p, "n_a")) for _, _, v in parses]
            verdicts[p] = max(set(verd_votes), key=verd_votes.count)

    # --- layer 3: self-correction -------------------------------------------
    if 3 in layers:
        draft = {p: values[p] for p in gold_paths}
        resp = call(revise_messages(prompt, schema, item.doc, item.trusted_record, draft))
        ans, conf_map, verd_map = parse_reply(resp.text)
        if ans is not None:
            flat = flatten_json(ans)
            for p in gold_paths:
                values[p] = flat.get(p)
                confs[p] = float(_lookup(conf_map, p, confs[p]))
                verdicts[p] = str(_lookup(verd_map, p, verdicts[p]))

    # --- layer 1: deterministic normalization + mechanical verdicts ---------
    if 1 in layers:
        for p in gold_paths:
            node = schema_node_for_path(schema, p)
            raw = values[p]
            if raw is not None:
                values[p] = normalize_value(raw, node) or normalize_text(str(raw))
            if trusted_flat is not None:
                tv = trusted_flat.get(p)
                if raw is None:
                    verdicts[p] = "not_found"
                elif tv is None:
                    verdicts[p] = "n_a"
                else:
                    verdicts[p] = "matches" if values_match(raw, tv, node) else "conflicts"
            else:
                verdicts[p] = "n_a"

    # --- layer 2: abstention -------------------------------------------------
    # Under voting, confidence IS the vote share; a strict majority (>=0.5)
    # stands, since 3-of-5 agreement is the signal voting exists to use.
    abstained: set[str] = set()
    if 2 in layers:
        threshold = 0.5 if 5 in layers else conf_threshold
        for p in gold_paths:
            node = schema_node_for_path(schema, p)
            bad_format = values[p] is not None and not format_ok(values[p], node)
            if confs[p] < threshold or bad_format:
                values[p] = None
                abstained.add(p)

    # --- layer 4: LLM-as-judge (filter, never rewrite) -----------------------
    if 4 in layers:
        candidate = {p: values[p] for p in gold_paths}
        resp = call(judge_messages(prompt, schema, item.doc, item.trusted_record, candidate))
        graded, _, _ = parse_reply(resp.text)
        grades = (graded or {}).get("grades", graded or {})
        for p in gold_paths:
            if str(_lookup(grades, p, "pass")).lower().startswith("fail"):
                values[p] = None
                abstained.add(p)

    # --- layer 6: human-in-the-loop ------------------------------------------
    human_minutes = 0.0
    if 6 in layers:
        escalated = [
            p for p in gold_paths
            if values[p] is None or verdicts[p] == "conflicts" or confs[p] < conf_threshold
        ]
        if escalated:
            human_minutes = HUMAN_MINUTES_PER_ITEM
            gold_flat = flatten_json(item.gold)
            for p in escalated:
                node = schema_node_for_path(schema, p)
                if human_resolver is not None:  # live mode: the user answers
                    resolved = human_resolver(item, p, values[p], confs[p])
                else:                           # simulated: human == gold
                    resolved = gold_flat.get(p)
                values[p] = (
                    normalize_value(resolved, node) or normalize_text(str(resolved))
                ) if resolved is not None else None
                confs[p] = 1.0
                abstained.discard(p)
                if trusted_flat is not None:
                    tv = trusted_flat.get(p)
                    if resolved is None:
                        verdicts[p] = "not_found"
                    elif tv is None:
                        verdicts[p] = "n_a"
                    else:
                        verdicts[p] = "matches" if values_match(resolved, tv, node) else "conflicts"

    fields = [
        FieldResult(
            field=p,
            value=None if values[p] is None else str(values[p]),
            verdict=verdicts[p] if verdicts[p] in ("matches", "conflicts", "not_found", "n_a") else "n_a",
            confidence=round(float(confs[p]), 3),
        )
        for p in gold_paths
    ]
    cost = Cost(
        tokens=sum(c.prompt_tokens + c.completion_tokens for c in calls),
        dollars=round(
            client.info.dollars(
                sum(c.prompt_tokens for c in calls),
                sum(c.completion_tokens for c in calls),
            ),
            6,
        ),
        latency_s=round(sum(c.latency_s for c in calls), 3),
        human_minutes=human_minutes,
    )
    return RunnerOutput(
        fields=fields, cost=cost, abstained=all(f.value is None for f in fields)
    )

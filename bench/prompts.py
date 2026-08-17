"""Harness-owned prompt templates.

The user's task prompt is DATA inside these fixed templates — users never write
rung prompts. Rung 5's deterministic diversity comes from the 5 base variants
(different framings/orderings at temperature 0). The rung-4 judge template and
any scorer-judge must never be the same prompt (spec rule).
"""

from __future__ import annotations

import json

from bench.flatten import schema_field_names

SYSTEM = "You are a careful information extraction engine. Respond with a single JSON object and nothing else."

N_VARIANTS = 5


def _format_spec(schema: dict, verification: bool) -> str:
    fields = schema_field_names(schema)
    spec = (
        "Return a single JSON object with these keys:\n"
        '- "answer": an object matching this JSON Schema:\n'
        + json.dumps(schema, indent=1)
        + "\n"
        '- "confidence": an object mapping each field name ('
        + ", ".join(f'"{f}"' for f in fields)
        + ") to your confidence from 0.0 to 1.0.\n"
    )
    if verification:
        spec += (
            '- "verdicts": an object mapping each field name to one of '
            '"matches" (document agrees with the trusted record), '
            '"conflicts" (document disagrees with the trusted record), or '
            '"not_found" (value absent from the document).\n'
        )
    spec += 'If a value is absent from the document, use null for it in "answer".'
    return spec


def base_messages(
    task_prompt: str,
    schema: dict,
    doc: str,
    trusted_record: dict | None,
    variant: int = 0,
) -> list[dict]:
    """The rung-0 call. Variants 0-4 reorder/reframe the same content (rung 5)."""
    spec = _format_spec(schema, trusted_record is not None)
    task = f"TASK:\n{task_prompt}"
    document = f"DOCUMENT:\n{doc}"
    record = (
        f"TRUSTED RECORD (verify the document against this):\n{json.dumps(trusted_record, ensure_ascii=False)}"
        if trusted_record is not None
        else None
    )

    if variant == 0:
        parts = [task, document, record, spec]
    elif variant == 1:
        parts = [document, record, task, spec]
    elif variant == 2:
        parts = [
            "Work through the document carefully, then answer.",
            record, document, task, spec,
        ]
    elif variant == 3:
        parts = [
            spec, task,
            "Extract each field one at a time, exactly as evidenced in the document.",
            document, record,
        ]
    else:
        parts = [task, record, document, "Be precise and literal.", spec]

    user = "\n\n".join(p for p in parts if p)
    return [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}]


def revise_messages(
    task_prompt: str, schema: dict, doc: str, trusted_record: dict | None, draft: dict
) -> list[dict]:
    """Rung 3 — self-correction. The draft answer is reviewed against the document."""
    spec = _format_spec(schema, trusted_record is not None)
    record = (
        f"TRUSTED RECORD:\n{json.dumps(trusted_record, ensure_ascii=False)}\n\n"
        if trusted_record is not None
        else ""
    )
    user = (
        f"TASK:\n{task_prompt}\n\n"
        f"DOCUMENT:\n{doc}\n\n"
        f"{record}"
        f"DRAFT ANSWER (may contain mistakes):\n{json.dumps(draft, ensure_ascii=False)}\n\n"
        "Verify every field of the draft against the document. Fix any value that "
        "is wrong, incomplete, or not actually supported by the document. Then "
        "return the corrected result.\n\n" + spec
    )
    return [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}]


def judge_messages(
    task_prompt: str, schema: dict, doc: str, trusted_record: dict | None, candidate: dict
) -> list[dict]:
    """Rung 4 — LLM-as-judge. Grades, never rewrites. Distinct from any scorer prompt."""
    fields = schema_field_names(schema)
    record = (
        f"TRUSTED RECORD:\n{json.dumps(trusted_record, ensure_ascii=False)}\n\n"
        if trusted_record is not None
        else ""
    )
    user = (
        "You are grading another model's output. Do not produce your own answer.\n\n"
        f"TASK GIVEN TO THE MODEL:\n{task_prompt}\n\n"
        f"DOCUMENT:\n{doc}\n\n"
        f"{record}"
        f"CANDIDATE ANSWER:\n{json.dumps(candidate, ensure_ascii=False)}\n\n"
        "For each field, grade \"pass\" if the candidate value is correct and "
        "supported by the document (a null is a pass only when the value truly "
        "is absent), otherwise \"fail\".\n"
        'Return a single JSON object: {"grades": {'
        + ", ".join(f'"{f}": "pass|fail"' for f in fields)
        + "}}"
    )
    return [
        {"role": "system", "content": "You are a strict grader. Respond with a single JSON object and nothing else."},
        {"role": "user", "content": user},
    ]

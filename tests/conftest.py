import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from bench.llm import LLMResponse, ModelInfo
from schemas.adapter import Dataset, Item

SCHEMA = {
    "type": "object",
    "properties": {
        "company": {"type": "string"},
        "date": {"type": "string", "format": "date"},
        "total": {"type": "number", "format": "currency"},
    },
    "required": ["company", "date", "total"],
}


class FakeClient:
    """Deterministic scripted LLM. Routes on prompt content; logs every call."""

    def __init__(self, replies: dict[str, str] | None = None, default: str | None = None):
        self.info = ModelInfo("ollama/fake")
        self.replies = replies or {}
        self.default = default
        self.calls: list[list[dict]] = []

    def chat(self, messages, sample_index=0, temperature=0.0, max_tokens=2000):
        self.calls.append(messages)
        user = messages[-1]["content"]
        text = None
        for needle, reply in self.replies.items():
            if needle in user:
                text = reply
                break
        if text is None:
            text = self.default if self.default is not None else json.dumps(
                {
                    "answer": {"company": "ACME SDN BHD", "date": "01/02/2024", "total": "42.00"},
                    "confidence": {"company": 0.9, "date": 0.9, "total": 0.9},
                    "verdicts": {"company": "matches", "date": "matches", "total": "matches"},
                }
            )
        return LLMResponse(
            text=text, prompt_tokens=100, completion_tokens=50, latency_s=0.1
        )


@pytest.fixture
def fake_client():
    return FakeClient()


@pytest.fixture
def dataset():
    return Dataset(
        domain="test",
        output_schema=SCHEMA,
        prompt="Extract company, date and total from the receipt.",
        economics={"value_correct": 1.0, "cost_wrong": 10.0, "cost_abstain": 0.5,
                   "dollars_per_human_min": 1.0},
        items=[
            Item(
                doc="ACME SDN BHD\n1 Feb 2024\nTOTAL: RM42.00",
                gold={"company": "ACME SDN BHD", "date": "01/02/2024", "total": "42.00"},
                trusted_record={"company": "ACME SDN BHD", "date": "01/02/2024", "total": "42.00"},
            ),
            Item(
                doc="BETA STORE\n2 Feb 2024\nTOTAL: RM10.00",
                gold={"company": "BETA STORE", "date": "02/02/2024", "total": "10.00"},
                trusted_record={"company": "BETA STORE", "date": "02/02/2024", "total": "99.00"},
            ),
        ],
    )


@pytest.fixture
def extraction_dataset(dataset):
    return Dataset(
        domain="test_extract",
        output_schema=SCHEMA,
        prompt=dataset.prompt,
        economics=dataset.economics,
        items=[Item(doc=i.doc, gold=i.gold, trusted_record=None) for i in dataset.items],
    )

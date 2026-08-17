# Data format — bring your own dataset

One JSON file gets you your own reliability curve. Nothing in your file is ever
shared: with a local (Ollama) model, documents never leave your machine.

```json
{
  "domain": "my_task",                  // any short name
  "prompt": "Extract ... from ...",     // optional — your task instruction
  "prompt_file": "prompt.txt",          // OR: read a long prompt from a plain text
                                        //     file next to this JSON (line breaks OK)
  "output_schema": { ... },             // JSON Schema of the output you want
  "economics": { ... },                 // optional — used by the dashboard
  "items": [                            // ~50-100 items; each = one input + its answer key
    {
      "doc": "raw text of ONE input document...",        // the INPUT the model sees
      "gold": { "total": 42.0, "date": "2024-01-15" },   // the CORRECT output for it
      "trusted_record": { ... }                          // optional, verification only
    }
  ]
}
```

Each item pairs one **input** (`doc`) with its **expected output** (`gold`,
shaped like `output_schema`). Think of an exam: `prompt` is the instructions,
each `doc` is a question, each `gold` is the answer sheet — the model never
sees `gold`; it's only used to score the model's answers.

## output_schema

A standard JSON Schema describing the output object. Nesting and arrays are
allowed; every leaf becomes a scored field.

- `"type": "number"` or `"format": "currency"` → values are compared numerically
  ("RM42.00" equals 42.0).
- `"format": "date"` → dates are compared after parsing ("25/12/2018" equals
  "2018-12-25").
- plain strings → compared case- and whitespace-insensitively.

A flat list like `"fields": ["total", "date"]` also works (legacy form).

## items

Each item:

| key | required | meaning |
|---|---|---|
| `doc` | yes | raw input text (the document) |
| `gold` | yes | the correct output object — the answer key; never shown to the model |
| `trusted_record` | no | reference values the model should verify the document against |

With `trusted_record` present, the task is **verification**: the model reports
per-field verdicts (matches / conflicts / not_found). Without it, the task is
pure **extraction**.

## economics (optional, adjustable live in the app)

```json
{
  "value_correct": 1.0,          // $ value of a correct answer
  "cost_wrong": 10.0,            // $ cost of a wrong answer that slips through
  "cost_abstain": 0.5,           // $ cost of a "don't know"
  "dollars_per_human_min": 1.0   // $ per minute of human review (rung 6)
}
```

## Checking your file

```bash
python -m bench.cli validate path/to/your_data.json
```

Errors are plain language ("item 12: gold.total is \"n/a\" but output_schema
says it should be a number"). The app runs the same check on upload.

A complete tiny example lives at `data/example_upload.json`.

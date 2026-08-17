"""Offline converter: raw SROIE2019 -> data/sroie_v1.json (standard v2 upload shape).

SROIE is treated as the first "user" of the data-agnostic pipeline: this script
runs once and produces exactly the JSON a user would upload — prompt included.

Raw layout (as downloaded):
  0325updated.task1train(626p)/X*.txt  -> OCR lines: x1,y1,...,x4,y4,TEXT
  0325updated.task2train(626p)/X*.txt  -> gold entities JSON {company,date,address,total}

Trusted records are the gold values with ~25% of items given ONE deliberately
perturbed field (-> a "conflicts" verdict for the model to catch). Fixed seed:
the file is reproducible.

Usage:
  python -m bench.adapters.sroie --raw data/SROIE2019 --out data/sroie_v1.json
"""

from __future__ import annotations

import argparse
import json
import random
from datetime import datetime, timedelta
from pathlib import Path

OCR_DIR = "0325updated.task1train(626p)"
GOLD_DIR = "0325updated.task2train(626p)"
FIELDS = ["company", "date", "address", "total"]

PROMPT = (
    "You are given the OCR text of a retail receipt and a trusted reference "
    "record. Extract the following fields from the receipt text: company (the "
    "store name), date (the transaction date), address (the store address), and "
    "total (the final amount paid). Compare each extracted value to the trusted "
    "reference record and decide whether the receipt matches the record, "
    "conflicts with it, or the field is not found in the receipt."
)

OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "company": {"type": "string"},
        "date": {"type": "string", "format": "date"},
        "address": {"type": "string"},
        "total": {"type": "number", "format": "currency"},
    },
    "required": FIELDS,
}

ECONOMICS = {
    "value_correct": 1.0,
    "cost_wrong": 10.0,
    "cost_abstain": 0.5,
    "dollars_per_human_min": 1.0,
}


def ocr_text(path: Path) -> str:
    lines = []
    for raw in path.read_text(errors="ignore").splitlines():
        parts = raw.split(",")
        if len(parts) > 8:
            text = ",".join(parts[8:]).strip()
            if text:
                lines.append(text)
    return "\n".join(lines)


def _shift_date(value: str, days: int) -> str | None:
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d", "%d %b %Y"):
        try:
            return (datetime.strptime(value.strip(), fmt) + timedelta(days=days)).strftime(fmt)
        except ValueError:
            continue
    return None


def perturb(field: str, value: str, rng: random.Random, pool: list[dict]) -> str | None:
    """Return a value guaranteed to differ, or None if this field can't be perturbed."""
    if field == "total":
        try:
            return f"{float(value.replace(',', '')) + rng.choice([1.0, 2.5, 10.0]):.2f}"
        except ValueError:
            return None
    if field == "date":
        return _shift_date(value, rng.randint(1, 5))
    # company / address: borrow a different receipt's value
    candidates = [g.get(field) for g in pool if g.get(field) and g.get(field) != value]
    return rng.choice(candidates) if candidates else None


def convert(raw_dir: Path, n: int, seed: int, conflict_rate: float) -> dict:
    rng = random.Random(seed)
    gold_files = sorted((raw_dir / GOLD_DIR).glob("X*.txt"))
    # skip "(1)"-style duplicate scans
    stems = [f.stem for f in gold_files if "(" not in f.stem]
    usable = [
        s for s in stems
        if (raw_dir / OCR_DIR / f"{s}.txt").exists()
    ]
    rng.shuffle(usable)
    chosen = usable[:n]

    golds = []
    for stem in chosen:
        g = json.loads((raw_dir / GOLD_DIR / f"{stem}.txt").read_text(errors="ignore"))
        golds.append({f: g.get(f) for f in FIELDS})

    items = []
    n_conflicts = 0
    for stem, gold in zip(chosen, golds):
        doc = ocr_text(raw_dir / OCR_DIR / f"{stem}.txt")
        trusted = dict(gold)
        if rng.random() < conflict_rate:
            for field in rng.sample(FIELDS, len(FIELDS)):
                if not gold.get(field):
                    continue
                new = perturb(field, str(gold[field]), rng, golds)
                if new is not None:
                    trusted[field] = new
                    n_conflicts += 1
                    break
        items.append({"doc": doc, "gold": gold, "trusted_record": trusted, "_id": stem})

    print(f"{len(items)} items, {n_conflicts} with an injected conflict "
          f"({n_conflicts / max(len(items), 1):.0%})")
    return {
        "domain": "sroie",
        "prompt": PROMPT,
        "output_schema": OUTPUT_SCHEMA,
        "economics": ECONOMICS,
        "items": items,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", default="data/SROIE2019", type=Path)
    ap.add_argument("--out", default="data/sroie_v1.json", type=Path)
    ap.add_argument("--n", default=60, type=int)
    ap.add_argument("--seed", default=42, type=int)
    ap.add_argument("--conflict-rate", default=0.25, type=float)
    args = ap.parse_args()

    data = convert(args.raw, args.n, args.seed, args.conflict_rate)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(data, indent=1, ensure_ascii=False))
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()

"""The per-record, per-rung trace — the join four open items each needed.

Written 2026-09-03 for plan item 12. Until then a run left the ledger (one
row per record per rung: verdict, zone, cost — but rung 0 and rung 3 log per
DOCUMENT), the FINAL records file, results.csv and a manifest copy. Nothing
said *this record, at this rung, held this code, and it was right*, because
correctness was computed afterwards by `score_run` and never joined back, and
the model's prompts and replies lived only in a content-addressed cache no
reader can open by record. Rung 3's changes could not be cross-tabbed
against rung 1's lanes; the 38 records rung 3 never re-found could not be
checked against whether rung 0 had them right; the ACCEPT-lane figures could
not be reproduced under a stated denominator; FiNER had no agreement
figures. Each was a re-run that should have been a join.

Two tables, both written beside the records by `run.run_ladder`:

  <run>.state.jsonl       one row per record per rung — `state_rows`
  <run>.r<N>.calls.jsonl  every model call rung N made — `CallTrace`

The state row is scored against gold AT THE RUNG, by span (never by
position — `score._find_gold`), so a rung that changed a record's code is
credited or blamed on the row it wrote. `outcome` distinguishes `unmatched`
(no gold mention at this span: a detection miss) from `incorrect` (a gold
mention, wrong code: a coding miss); `score.outcome` pools those into
INCORRECT because it grades an answer, and the error budget must not.

The call trace keeps the FULL prompt and the RAW reply. Prompts carry corpus
text verbatim, so these files live under the gitignored `out/` and are never
committed — the same rule as the LLM cache, and preflight.py stands guard.

The standing rule both tables carry: a rung that cannot say what it did to an
individual record cannot be credited or blamed for the aggregate.
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any

from ladder.schema import Record

OUTCOME_UNMATCHED = "unmatched"
OUTCOME_UNSCORED = "unscored"

#: The fields whose change between two rungs counts as "this rung changed the
#: record". `checks` is deliberately NOT tracked as a whole: every rung writes
#: bookkeeping there, and a row that said "changed" on every rung would say
#: nothing.
TRACKED_FIELDS = ("sct", "sct_label", "spans", "text", "zone", "reason")


def _spans(rec: Record) -> list[list[int]]:
    return [[int(a), int(b)] for a, b in rec.spans]


def _field(rec: Record, name: str) -> Any:
    if name == "spans":
        return _spans(rec)
    return getattr(rec, name)


def _score(rec: Record, gold: Any, vocab: Any) -> tuple[str, bool | None, list[str]]:
    """(outcome, correct, gold_codes) for one record against the gold set,
    paired EXACTLY by span — the headline pairing."""
    if gold is None:
        return OUTCOME_UNSCORED, None, []
    try:
        from ladder import score
    except ModuleNotFoundError:  # pragma: no cover - a checkout without a scorer
        return OUTCOME_UNSCORED, None, []
    g = score._find_gold(rec, gold)
    if g is None:
        return OUTCOME_UNMATCHED, False, []
    got = score.outcome(rec, g, vocab)
    return got, got == score.CORRECT, [str(c) for c in (g.sct or [])]


def _score_overlap(rec: Record, gold: Any, vocab: Any) -> tuple[str, bool | None]:
    """The same judgement paired by span OVERLAP: the first gold mention in
    the document whose span touches the record's. Per record and not
    one-to-one — the aggregate overlap F1 is `score_run`'s, greedy over the
    prediction list; this column says whether THIS record sits on a gold
    mention at all, which is what separates a boundary miss from a
    detection miss in the error budget."""
    if gold is None:
        return OUTCOME_UNSCORED, None
    try:
        from ladder import score
    except ModuleNotFoundError:  # pragma: no cover
        return OUTCOME_UNSCORED, None
    mentions = gold.values() if isinstance(gold, dict) else gold
    for g in mentions:
        if g.doc_id == rec.doc_id and score._overlaps(rec.spans, g.spans):
            got = score.outcome(rec, g, vocab)
            return got, got == score.CORRECT
    return OUTCOME_UNMATCHED, False


def state_rows(
    rung: int,
    before: dict[str, Record],
    after: list[Record],
    gold: Any = None,
    vocab: Any = None,
    run_id: str = "",
) -> list[dict[str, Any]]:
    """One row per record per rung: what it holds now, what changed, and
    whether it is right. `before` is the record set as the PREVIOUS rung left
    it, keyed by record_id; an id absent from it was created here, and an id
    absent from `after` was dropped here — both are rows."""
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for rec in after:
        seen.add(rec.record_id)
        prev = before.get(rec.record_id)
        created = prev is None
        changed_fields = [] if created else [
            f for f in TRACKED_FIELDS if _field(rec, f) != _field(prev, f)
        ]
        outcome, correct, gold_codes = _score(rec, gold, vocab)
        outcome_overlap, correct_overlap = _score_overlap(rec, gold, vocab)
        c = rec.checks
        r3 = c.get("r3") or {}
        rows.append({
            "run_id": run_id,
            "rung": rung,
            "record_id": rec.record_id,
            "doc_id": rec.doc_id,
            "text": rec.text,
            "spans": _spans(rec),
            "sct": rec.sct,
            "sct_label": rec.sct_label,
            "confidence": rec.confidence,
            "zone": rec.zone,
            "reason": rec.reason,
            "created_this_rung": created,
            "dropped_this_rung": False,
            "changed_this_rung": created or bool(changed_fields),
            "changed_fields": changed_fields,
            "was_sct": None if created else prev.sct,
            "was_zone": None if created else prev.zone,
            "r1_verdict": c.get("r1_verdict"),
            "r1_reason": c.get("r1_reason"),
            "r4_verdict": c.get("r4_verdict"),
            "r3_changed": bool(r3.get("changed", False)) if r3 else None,
            "pick_fallback": c.get("pick_fallback"),
            "outcome": outcome,
            "correct": correct,
            "outcome_overlap": outcome_overlap,
            "correct_overlap": correct_overlap,
            "gold_codes": gold_codes,
        })
    for rid, prev in before.items():
        if rid in seen:
            continue
        rows.append({
            "run_id": run_id,
            "rung": rung,
            "record_id": rid,
            "doc_id": prev.doc_id,
            "text": prev.text,
            "spans": _spans(prev),
            "sct": None,
            "sct_label": None,
            "confidence": prev.confidence,
            "zone": None,
            "reason": None,
            "created_this_rung": False,
            "dropped_this_rung": True,
            "changed_this_rung": True,
            "changed_fields": ["dropped"],
            "was_sct": prev.sct,
            "was_zone": prev.zone,
            "r1_verdict": prev.checks.get("r1_verdict"),
            "r1_reason": prev.checks.get("r1_reason"),
            "r4_verdict": prev.checks.get("r4_verdict"),
            "r3_changed": None,
            "pick_fallback": prev.checks.get("pick_fallback"),
            "outcome": OUTCOME_UNSCORED,
            "correct": None,
            "outcome_overlap": OUTCOME_UNSCORED,
            "correct_overlap": None,
            "gold_codes": [],
        })
    return rows


def write_rows(path: str | Path, rows: list[dict[str, Any]]) -> None:
    """Append rows as JSONL. Append, because the table grows one rung at a time
    and a run that dies at rung 3 must still leave rungs 0-2 on disk."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")


def read_rows(path: str | Path) -> list[dict[str, Any]]:
    return [json.loads(l) for l in Path(path).read_text(encoding="utf-8").splitlines()
            if l.strip()]


class CallTrace:
    """Every model call one rung made: full prompt, raw reply, cost, document.

    Attached to a `llm.Caller` as `.trace`; the Caller records into it from
    `__call__`, which is the one path every rung's calls go through (rung 3's
    sampler included). The document is INFERRED from the prompt — the longest
    source text contained in it — rather than threaded through every rung's
    `llm(prompt, text, mode)` call, which is a frozen contract with stubs and
    tests behind it. Rung 0/2/3 pass the source as `text`, rung 4 embeds it
    in its template; both put it in the content.
    """

    def __init__(self, path: str | Path | None, rung: int,
                 sources: dict[str, str] | None = None,
                 role: str = "", spec: str = ""):
        self.path = Path(path) if path else None
        self.rung = rung
        self.role = role
        self.spec = spec
        self.sources = {k: v for k, v in (sources or {}).items() if v}
        self.n = 0
        self._fh = None
        if self.path is not None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._fh = self.path.open("a", encoding="utf-8")

    def infer_doc(self, content: str) -> str | None:
        best: tuple[str, int] | None = None
        for doc_id, text in self.sources.items():
            if text in content and (best is None or len(text) > best[1]):
                best = (doc_id, len(text))
        return best[0] if best else None

    def record(self, *, content: str, raw: str, normalised: str, mode: str,
               usage: dict[str, Any], temperature: float,
               sample_index: int) -> dict[str, Any]:
        row = {
            "call_index": self.n,
            "rung": self.rung,
            "role": self.role,
            "model": self.spec or usage.get("model"),
            "mode": mode,
            "doc_id": self.infer_doc(content),
            "prompt": content,
            "raw": raw,
            "normalised": normalised,
            "cached": bool(usage.get("cached", False)),
            "tokens_in": usage.get("in", 0),
            "tokens_out": usage.get("out", 0),
            "seconds": usage.get("seconds", 0.0),
            "timed_out": bool(usage.get("timed_out", False)),
            "truncated": bool(usage.get("truncated", False)),
            "temperature": temperature,
            "sample_index": sample_index,
            "sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
            "ts": time.time(),
        }
        self.n += 1
        if self._fh is not None:
            self._fh.write(json.dumps(row, ensure_ascii=False) + "\n")
            self._fh.flush()
        return row

    def close(self) -> None:
        if self._fh is not None:
            self._fh.close()
            self._fh = None

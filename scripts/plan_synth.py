"""A synthetic stand-in for a post the public page may not carry.

CADEC is non-transferable, so `docs/plan.html` could show a CADEC document
only as grey blocks with the quoted spans filled in — and grey blocks were
judged unreadable. The stand-in keeps exactly what the page already
publishes, in place: the annotators' spans and the model's quotes (each
within the seven-word precedent) at the word positions the post had. Every
other word is invented from a phrase bank of first-person drug-review prose
with no symptom words in it, so nothing in the filler can be mistaken for an
annotation. The generator is handed the reduced document — positions and
spans, never the post — and `build_documents` still runs the leak check over
the result against the real post's windows.

The local copy (`scripts/plan_local.py`, written under `out/` only) carries
the real post instead; `PD.local_text` tells the page which it is drawing.
"""
from __future__ import annotations

import copy
import hashlib
import random

# first-person review prose, no symptom or body words: filler must never read as a missed annotation.
# A gap between two quoted spans is AFTER + MID* + BEFORE, so the words either side of a span read on.
_OPEN = [   # the post starts here
    "I have been on this for about a year now and", "My doctor started me on this a while back and",
    "Been taking the usual dose for a few months and", "I was put on this last spring and",
    "Just wanted to write up my experience with this one because", "Started this in the winter and", "So far", "Well",
]
_AFTER = [  # follows a quoted span
    "which was not great", "for about a week", "most days", "on and off", "which I did not expect",
    "and I mentioned it at my next appointment", "so I called the surgery", "which the leaflet did not mention",
    "for the first few weeks", "and my wife noticed it before I did", "which has eased off a bit now", "again",
]
_MID = [
    "then after a couple of weeks", "so I kept going with it for a while", "I asked the pharmacist about it",
    "the leaflet did not really say much", "it went on like that for most of the month",
    "I took a break from it over the weekend", "they said to keep an eye on it", "I am on a few other things as well",
    "so it is hard to say what is what", "I cut the dose in half", "not sure I will stay on it",
    "I am writing this mostly so other people know", "your mileage may vary of course", "I went back to the doctor about it",
    "we are trying something else next month", "it did do what it was meant to do", "so I am a bit torn",
    "I will update this if anything changes", "for the record I am in my fifties", "I had never had anything like it",
    "then last week", "a month in", "by the second box", "honestly",
]
_BEFORE = [  # leads into the next quoted span
    "and then", "plus", "along with", "followed by", "and some", "then came the", "and after that", "and a few days later some",
    "then over the weekend", "and on top of that", "with", "and by the end",
]
_CLOSE = [   # the post ends here
    "so that is where I am with it.", "anyway that is my experience so far.", "I will see what the doctor says next.",
    "would be interested to hear if anyone else had the same.", "and I am done with it for now.", "so far.", "for now.",
]
_PAD = ["also", "still", "really", "then", "honestly", "again", "anyway", "now", "too", "though", "and", "but", "so"]


def _rng(doc: dict) -> random.Random:
    key = f"{doc.get('run')}|{doc.get('doc_id')}".encode("utf-8")
    return random.Random(int.from_bytes(hashlib.blake2b(key, digest_size=8).digest(), "big"))


def _pick(rng: random.Random, bank: list[str], n: int, exact: bool = False) -> list[str] | None:
    fits = [p.split() for p in bank if (len(p.split()) == n if exact else len(p.split()) <= n)]
    return rng.choice(fits) if fits else None


def filler(rng: random.Random, n: int, at_start: bool, at_end: bool) -> list[str]:
    """`n` invented words for one run of unquoted slots: an opener or an
    after-span phrase, middle sentences, and a lead-in to the next span or a
    closing line. Full stops end sentences; the post opens with a capital."""
    if n <= 0:
        return []
    head = _pick(rng, _OPEN if at_start else _AFTER, n) or []
    tail_bank = _CLOSE if at_end else _BEFORE
    tail = _pick(rng, tail_bank, n - len(head)) or [] if n - len(head) > 0 else []
    mid: list[str] = []
    left = n - len(head) - len(tail)
    while left > 0:
        p = _pick(rng, _MID, left) if left > 1 else None
        if p is None:
            p = [rng.choice([w for w in _PAD if not mid or w != mid[-1]])]
        mid += p
        left -= len(p)
        if left > 1 and len(p) >= 4 and rng.random() < 0.25:   # a sentence ends on a full phrase, now and then
            mid[-1] += "."
    out = head + mid + tail
    if head and mid and len(head) >= 4 and not head[-1].endswith(".") and rng.random() < 0.5:
        head_end = len(head) - 1
        out[head_end] += "."
    if at_end and not out[-1].endswith("."):
        out[-1] += "."
    if at_start:
        out[0] = out[0][0].upper() + out[0][1:]
    for i in range(1, len(out)):
        if out[i - 1].endswith("."):
            out[i] = out[i][0].upper() + out[i][1:]
    return out


def _shown(doc: dict) -> list[dict]:
    """The spans whose words the page may print: the annotators' and the model's,
    each within the precedent — the same rule the page's redacted view uses."""
    def ok(s):
        return bool(s) and not s.endswith("withheld)") and s != "(not published)"
    shown = []
    for p in doc.get("pairs", []):
        g = p["gold"]
        if ok(g.get("span")) and g.get("spans"):
            shown.append({"kind": "gold", "rid": g["record_id"], "segs": g["spans"], "words": g["span"].split()})
    for r in doc.get("records", []):
        # a quote rung 1 could not locate at its offsets is not printed there:
        # the offsets are wrong, and that is the record's finding
        if (r.get("r1") or {}).get("reason") == "span_ungrounded":
            continue
        if ok(r.get("span")) and r.get("spans"):
            shown.append({"kind": "model", "rid": r["record_id"], "segs": r["spans"], "words": r["span"].split()})
    return shown


def stand_in(doc: dict) -> dict:
    """The document with a synthetic post in `text`: the shown spans at the
    word positions the post had, filler everywhere else, offsets recomputed."""
    slots = doc.get("word_spans") or []
    n = len(slots)
    text_of: list[str | None] = [None] * n
    shown = _shown(doc)
    wrote: list[list[tuple[int, int]]] = []   # per shown span: (slot, word index) it wrote
    for sp in shown:                            # gold first, then the model's quote wins a shared slot
        covered = [i for seg in sp["segs"] for i in range(n)
                   if slots[i][0] < seg[1] and slots[i][1] > seg[0]]
        seen, order = set(), []                 # slot order, no repeats across overlapping segments
        for i in covered:
            if i not in seen:
                seen.add(i)
                order.append(i)
        mine = []
        for k, i in enumerate(order[:len(sp["words"])]):
            text_of[i] = sp["words"][k]
            mine.append((i, k))
        wrote.append(mine)
    # a slot carries one word: a span keeps only the slots that still carry its own word,
    # in maximal runs of consecutive slots, so every offset reads back as that span's text
    placed: dict[tuple, list[list[int]]] = {}
    for sp, mine in zip(shown, wrote):
        kept = [i for i, k in mine if text_of[i] == sp["words"][k]]
        runs: list[list[int]] = []
        for i in kept:
            if runs and i == runs[-1][-1] + 1:
                runs[-1].append(i)
            else:
                runs.append([i])
        placed[(sp["kind"], sp["rid"])] = runs
    rng = _rng(doc)
    i = 0
    while i < n:
        if text_of[i] is not None:
            i += 1
            continue
        j = i
        while j < n and text_of[j] is None:
            j += 1
        words = filler(rng, j - i, at_start=(i == 0), at_end=(j == n))
        text_of[i:j] = words
        i = j
    words_out = [w or "" for w in text_of]
    offsets, pos = [], 0
    for w in words_out:
        offsets.append([pos, pos + len(w)])
        pos += len(w) + 1
    text = " ".join(words_out)

    def segs_for(kind, rid):
        return [[offsets[ix[0]][0], offsets[ix[-1]][1]] for ix in placed.get((kind, rid), []) if ix]

    out = copy.deepcopy(doc)
    out["text"], out["synthetic"] = text, True
    out["chars"], out["word_spans"] = len(text), offsets
    for r in out["records"]:
        r["spans"] = segs_for("model", r["record_id"])
    out["gold_spans"] = []
    for p in out["pairs"]:
        g = p["gold"]
        g["spans"] = segs_for("gold", g["record_id"])
        if g["spans"]:
            out["gold_spans"].append({"record_id": g["record_id"], "spans": g["spans"], "excluded": False})
    return out


def public_document(doc: dict) -> dict:
    """What the public page carries for this document: the text it already has
    (FiNER-139, CC-BY-SA), a stand-in where there are quoted spans to place
    (CADEC), or the document unchanged where nothing is quotable (PsyTAR's
    stripped records, which the page draws as a span map)."""
    if doc.get("text"):
        return doc
    if not doc.get("word_spans") or not _shown(doc):
        return doc
    return stand_in(doc)

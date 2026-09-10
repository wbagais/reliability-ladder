"""The public page may not carry a CADEC post, and grey blocks were judged
unreadable. So each CADEC demo document gets a SYNTHETIC STAND-IN: the real
annotated spans and the model's quotes stay in place, at the word positions
the post had, and every other word is invented from a phrase bank. The
generator reads only the fields the page already publishes (word positions,
the spans within the seven-word precedent) and never the post — the doc it
takes has no `text`."""
from __future__ import annotations

import json

import pytest

from scripts.plan_synth import stand_in, public_document

POST = ("I have been on this drug for well over a year now and last month I got extremely sick "
        "after two days and my rectal bleeding got worse than it had ever been before .")


def _slots(post):
    import re
    return [[m.start(), m.end()] for m in re.finditer(r"\S+", post)]


def _at(post, phrase):
    i = post.index(phrase)
    return [[i, i + len(phrase)]]


def _doc(corpus="cadec"):
    """A reduced document the way reduce_document leaves it for CADEC: positions, no text."""
    return {
        "doc_id": "TOY.1", "corpus": corpus, "run": "toy-d0", "words": len(POST.split()), "chars": len(POST),
        "word_spans": _slots(POST),
        "records": [
            {"record_id": "TOY.1#0", "span": "extremely sick", "spans": _at(POST, "extremely sick"),
             "r1": {"verdict": "BAND"}, "final": {"zone": "VERIFIED", "sct": "1"}},
            {"record_id": "TOY.1#1", "span": "rectal bleeding", "spans": _at(POST, "rectal bleeding"),
             "r1": {"verdict": "ACCEPT"}, "final": {"zone": "VERIFIED", "sct": "2"}},
            # a discontinuous quote: two segments, words indexed across both
            {"record_id": "TOY.1#2", "span": "sick worse", "spans": _at(POST, "sick") + _at(POST, "worse"),
             "r1": {"verdict": "BAND"}, "final": {"zone": "ESCALATE", "sct": "3"}},
        ],
        "pairs": [
            {"gold": {"record_id": "TOY.1#0", "span": "extremely sick", "spans": _at(POST, "extremely sick"), "sct": ["1"]},
             "span_match": "exact", "pred": "TOY.1#0", "code": "correct"},
            {"gold": {"record_id": "TOY.1#1", "span": "bleeding", "spans": _at(POST, "bleeding"), "sct": ["2"]},
             "span_match": "overlap", "pred": "TOY.1#1", "code": "correct"},
            {"gold": {"record_id": "TOY.1#3", "span": "(8-word quote withheld)", "spans": _at(POST, "worse than it had ever been before ."), "sct": ["4"]},
             "span_match": "missed", "pred": None, "code": None},
        ],
        "spurious": [],
    }


def _quoted(text, segs):
    return " ".join(text[a:b] for a, b in segs)


def test_every_shown_span_sits_at_its_new_offsets_and_the_shape_is_the_posts():
    d = stand_in(_doc())
    assert d["synthetic"] is True and isinstance(d["text"], str)
    assert len(d["text"].split()) == d["words"] == len(POST.split())
    assert d["chars"] == len(d["text"]) and len(d["word_spans"]) == d["words"]
    by = {r["record_id"]: r for r in d["records"]}
    assert _quoted(d["text"], by["TOY.1#0"]["spans"]) == "extremely sick"
    assert _quoted(d["text"], by["TOY.1#1"]["spans"]) == "rectal bleeding"
    assert _quoted(d["text"], by["TOY.1#2"]["spans"]) == "sick worse"
    assert len(by["TOY.1#2"]["spans"]) == 2, "a discontinuous quote keeps its two segments"
    gold = {g["record_id"]: g for g in d["gold_spans"]}
    assert _quoted(d["text"], gold["TOY.1#0"]["spans"]) == "extremely sick"
    assert _quoted(d["text"], gold["TOY.1#1"]["spans"]) == "bleeding"
    pairs = {p["gold"]["record_id"]: p for p in d["pairs"]}
    assert pairs["TOY.1#1"]["gold"]["spans"] == gold["TOY.1#1"]["spans"]
    # the word positions are the post's: same word index for every shown word
    i_post = POST.split().index("extremely")
    assert d["text"].split()[i_post] == "extremely"


def test_no_window_of_the_post_survives_and_the_input_carries_no_text():
    from dashboard.scrub import assert_clean
    doc = _doc()
    assert "text" not in doc, "the generator is handed a document with no post in it"
    d = stand_in(doc)
    windows = [POST[i:i + 24] for i in range(len(POST) - 23)]
    assert_clean(json.dumps(d), windows)   # raises CorpusTextLeak on any 24-character run of the post
    hidden = {"drug", "days", "got"}   # content words of the post the spans do not cover, and the bank does not use
    assert not hidden & set(d["text"].replace(".", "").split()), "an unquoted content word of the post came through"


def test_a_withheld_span_is_filler_and_carries_no_offsets():
    d = stand_in(_doc())
    assert "TOY.1#3" not in {g["record_id"] for g in d["gold_spans"]}
    p = next(p for p in d["pairs"] if p["gold"]["record_id"] == "TOY.1#3")
    assert p["gold"]["spans"] == [] and p["gold"]["span"] == "(8-word quote withheld)"
    assert "ever been before" not in d["text"]


def test_the_stand_in_reads_as_prose_and_is_a_pure_function_of_the_document():
    a, b = stand_in(_doc()), stand_in(_doc())
    assert a == b
    assert a["text"][0].isupper() and a["text"].rstrip().endswith(".")
    other = _doc(); other["doc_id"] = "TOY.2"
    assert stand_in(other)["text"] != a["text"], "a different document gets different filler"
    for w in a["text"].split():
        assert w.replace(".", "").replace(",", "").replace("'", "").isalpha(), w


def test_public_document_attaches_the_stand_in_only_where_it_is_needed():
    # CADEC: no text may be carried, so the stand-in goes in
    assert public_document(_doc())["synthetic"] is True
    # FiNER: the excerpt is already there and stays
    f = _doc("finer"); f["text"] = POST
    assert public_document(f) == f and "synthetic" not in public_document(f)
    # a document with nothing quotable (PsyTAR's stripped records) stays a span map
    p = _doc("psytar")
    for r in p["records"]:
        r["span"] = "(not published)"
    p["pairs"] = []
    assert "text" not in public_document(p)


def test_a_slot_two_quotes_contest_goes_to_the_later_quote_and_the_other_offsets_shrink():
    """Two model quotes can overlap ("muscle pain in shoulders" and a later
    "shoulders hip" indexed across two segments). One slot carries one word;
    a quote whose word lost the slot must not point at it, so every offset of
    every quote still reads back as that quote's own words."""
    post = "and then EXTREME MUSCLE PAIN IN SHOULDERS and HIP too ."
    d = _doc()
    d["words"], d["chars"], d["word_spans"] = len(post.split()), len(post), _slots(post)
    d["pairs"], d["records"] = [], [
        {"record_id": "TOY.1#0", "span": "EXTREME MUSCLE PAIN IN SHOULDERS", "spans": _at(post, "EXTREME MUSCLE PAIN IN SHOULDERS"),
         "r1": {"verdict": "BAND"}, "final": {"zone": "VERIFIED", "sct": "1"}},
        {"record_id": "TOY.1#1", "span": "PAIN HIP", "spans": _at(post, "PAIN IN SHOULDERS") + _at(post, "HIP"),
         "r1": {"verdict": "BAND"}, "final": {"zone": "ESCALATE", "sct": "2"}},
    ]
    out = stand_in(d)
    by = {r["record_id"]: r for r in out["records"]}
    for r in out["records"]:
        for a, b in r["spans"]:
            assert out["text"][a:b] in r["span"], (r["record_id"], out["text"][a:b])
    # the later quote wrote PAIN onto the shared slot and HIP onto its second segment (the slots IN and SHOULDERS have no word from it)
    assert _quoted(out["text"], by["TOY.1#1"]["spans"]) == "PAIN HIP"
    assert "PAIN" not in _quoted(out["text"], by["TOY.1#0"]["spans"]) or _quoted(out["text"], by["TOY.1#0"]["spans"]).startswith("EXTREME MUSCLE")


def test_a_quote_rung_1_could_not_ground_gets_no_offsets_and_overwrites_nothing():
    """Rung 1's `span_ungrounded` means the quote is not at its offsets. The
    page does not print it there: it keeps its row, loses its highlight, and
    cannot overwrite a grounded quote's word."""
    post = "and then EXTREME MUSCLE PAIN IN SHOULDERS and HIP too ."
    d = _doc()
    d["words"], d["chars"], d["word_spans"] = len(post.split()), len(post), _slots(post)
    d["pairs"], d["records"] = [], [
        {"record_id": "TOY.1#0", "span": "MUSCLE PAIN IN SHOULDERS", "spans": _at(post, "MUSCLE PAIN IN SHOULDERS"),
         "r1": {"verdict": "BAND", "reason": "no lexical match"}, "final": {"zone": "VERIFIED", "sct": "1"}},
        {"record_id": "TOY.1#1", "span": "MUSCLE PAIN IN HIP", "spans": _at(post, "MUSCLE PAIN IN SHOULDERS"),
         "r1": {"verdict": "REJECT", "reason": "span_ungrounded"}, "final": {"zone": "ESCALATE", "sct": "2"}},
    ]
    out = stand_in(d)
    by = {r["record_id"]: r for r in out["records"]}
    assert by["TOY.1#1"]["spans"] == []
    assert _quoted(out["text"], by["TOY.1#0"]["spans"]) == "MUSCLE PAIN IN SHOULDERS"

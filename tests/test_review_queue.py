"""The rung-6 live review queue's state guards.

Regression: escalations cached in Streamlit session state survived into a later
run with fewer items, so `ds.items[e["item"]]` raised IndexError.
"""

from app.review import escalations_fit, resolver_index
from schemas.adapter import Item


def test_escalations_fit_current_run():
    esc = [{"item": 0, "path": "total"}, {"item": 2, "path": "date"}]
    assert escalations_fit(esc, 3)
    assert escalations_fit([], 3)


def test_stale_escalations_from_a_larger_run_are_rejected():
    esc = [{"item": 0, "path": "total"}, {"item": 40, "path": "date"}]
    assert not escalations_fit(esc, 3)   # would have raised IndexError


def test_negative_index_rejected():
    assert not escalations_fit([{"item": -1, "path": "x"}], 3)


def test_resolver_index_keys_on_doc_not_identity():
    items = [Item(doc="doc A", gold={}), Item(doc="doc B", gold={})]
    idx = resolver_index(items)
    assert idx == {"doc A": 0, "doc B": 1}
    # a rebuilt Dataset (new objects, same text) still resolves
    rebuilt = Item(doc="doc B", gold={})
    assert idx[rebuilt.doc] == 1

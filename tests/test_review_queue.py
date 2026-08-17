"""The rung-6 live review queue's state guards.

Regression: escalations cached in Streamlit session state survived into a later
run with fewer items, so `ds.items[e["item"]]` raised IndexError.
"""

from datetime import datetime
from pathlib import Path

from app.review import escalations_fit, resolver_index, run_output_path
from schemas.adapter import Item


def test_run_output_path_is_unique_per_run():
    """Regression: the app wrote every run to results.json, so a small run
    silently destroyed a finished 60-item benchmark."""
    d = Path("/tmp/results")
    a = run_output_path(d, "sroie", 60, 10, now=datetime(2026, 8, 17, 3, 9, 13))
    b = run_output_path(d, "sop_materials", 3, 3, now=datetime(2026, 8, 17, 4, 0, 0))
    assert a.name == "sroie_60x10_20260817-030913.json"
    assert b.name == "sop_materials_3x3_20260817-040000.json"
    assert a != b


def test_run_output_path_sanitises_domain():
    p = run_output_path(Path("/tmp"), "My Task/v2!", 5, 2,
                        now=datetime(2026, 1, 1, 0, 0, 0))
    assert p.name == "my_task_v2_5x2_20260101-000000.json"


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

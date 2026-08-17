"""Pure helpers for the rung-6 live review queue.

Kept out of streamlit_app.py so they can be imported (and tested) without
executing the Streamlit script.
"""

from __future__ import annotations


def escalations_fit(escalations: list[dict], n_items: int) -> bool:
    """Do cached escalations belong to a run with this many items?

    Streamlit keeps the escalation list in session state; a later, smaller run
    would otherwise index past the end of its item list.
    """
    return all(0 <= e["item"] < n_items for e in escalations)


def resolver_index(items) -> dict[str, int]:
    """Map an item's doc text to its index.

    Keyed on the doc rather than object identity: the harness rebuilds the
    Dataset, and an identity miss would silently drop the human's answers
    instead of failing loudly.
    """
    return {it.doc: i for i, it in enumerate(items)}

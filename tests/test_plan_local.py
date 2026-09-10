"""scripts/plan_local.py builds a LOCAL copy of docs/plan.html with the
full posts in the demo — for the licensee's own screen, never for git.

The published page shows a CADEC post as blank blocks with only the quoted
spans filled in, because the corpus is non-transferable. The owner wants to
read the whole post beside the ladder's verdicts on their own machine, which
the licence allows. So the local build keeps the text, and two guards keep
it local: the output path must sit under `out/` (gitignored), and the
script refuses to write anywhere else.
"""
from __future__ import annotations

import json
import pathlib

import pytest

from scripts.plan_local import LocalOnly, splice_documents, write_local_page

PAGE = ('<!doctype html><title>x</title><script id="plan-data" type="application/json">\n'
        '{"version": 19, "documents": [{"doc_id": "D.1", "corpus": "cadec"}]}\n</script><script>1</script>')


def test_splice_replaces_the_documents_and_marks_the_page_local():
    docs = [{"doc_id": "D.1", "corpus": "cadec", "text": "the whole post"}]
    out = splice_documents(PAGE, docs)
    data = json.loads(out.split('type="application/json">\n', 1)[1].split("\n</script>", 1)[0])
    assert data["documents"][0]["text"] == "the whole post"
    assert data["local_text"] is True
    assert "LOCAL COPY" in out


def test_the_local_page_is_written_only_under_out(tmp_path: pathlib.Path):
    root = tmp_path
    (root / "docs").mkdir()
    (root / "docs" / "plan.html").write_text(PAGE)
    (root / "out").mkdir()
    docs = [{"doc_id": "D.1", "corpus": "cadec", "text": "the whole post"}]
    dest = write_local_page(root, docs, root / "out" / "plan-local.html")
    assert dest.exists() and "the whole post" in dest.read_text()
    for bad in (root / "docs" / "plan.html", root / "plan-local.html", tmp_path.parent / "elsewhere.html"):
        with pytest.raises(LocalOnly):
            write_local_page(root, docs, bad)

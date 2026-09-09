"""Every local link and in-page anchor in the README resolves.

The README was cut from 773 lines to 262 on 2026-09-09 and the material moved
into docs/. Links are the seams. A moved section whose old anchor is still
linked, or a doc renamed out from under the README, is a defect the reader
finds and nobody here does — the same "recorded once, never read back" failure
class as everything in docs/three-checks.md, pointed at the front page.

Stdlib only: CI is python:3.12-slim with requirements.txt and pytest.
"""
from __future__ import annotations

import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]

FILES = [
    ROOT / "README.md",
    ROOT / "docs" / "RUNNING.md",
    ROOT / "docs" / "early-results.md",
    ROOT / "docs" / "three-checks.md",
]

_MD_LINK = re.compile(r"\]\(([^)\s]+)\)")
_HTML_REF = re.compile(r'(?:href|src)="([^"]+)"')
_HEADING = re.compile(r"^#{1,6}\s+(.+?)\s*$", re.M)
_FENCE = re.compile(r"```.*?```", re.S)


def github_anchor(heading: str) -> str:
    """GitHub's heading -> fragment rule: strip markdown/HTML, lower-case,
    drop everything but word characters, spaces and hyphens, spaces to
    hyphens. Good enough for the headings in this repo."""
    text = re.sub(r"<[^>]+>", "", heading)
    text = re.sub(r"[*_`]", "", text)
    text = text.lower()
    text = re.sub(r"[^\w\- ]", "", text)
    return text.replace(" ", "-")


def broken_links(path: pathlib.Path) -> list[str]:
    """Return every local target in `path` that does not resolve — a file
    path that does not exist, or a `#fragment` naming no heading in the
    file it points at. External and mailto links are not checked."""
    text = _FENCE.sub("", path.read_text())
    targets = _MD_LINK.findall(text) + _HTML_REF.findall(text)
    bad: list[str] = []
    for target in targets:
        if target.startswith(("http://", "https://", "mailto:")):
            continue
        file_part, _, fragment = target.partition("#")
        dest = (path.parent / file_part) if file_part else path
        if not dest.exists():
            bad.append(target)
            continue
        if fragment and dest.suffix == ".md":
            heads = {github_anchor(h) for h in _HEADING.findall(dest.read_text())}
            if fragment not in heads:
                bad.append(target)
    return bad


@pytest.mark.parametrize("path", FILES, ids=[p.name for p in FILES])
def test_every_local_link_resolves(path: pathlib.Path) -> None:
    assert path.exists(), path
    assert broken_links(path) == []


def test_the_checker_catches_a_broken_link_and_a_missing_anchor(tmp_path) -> None:
    """The guard on the guard: a link test that cannot fail is no test."""
    (tmp_path / "other.md").write_text("# Real heading\n")
    doc = tmp_path / "doc.md"
    doc.write_text(
        "# Title\n\n"
        "[ok file](other.md) [ok anchor](other.md#real-heading) [ok self](#title)\n"
        "[gone](missing.md) [no such](other.md#not-here) [nor this](#absent)\n"
        '<img src="img.png"> <a href="other.md">fine</a>\n'
        "```\n[inside a fence](fenced.md)\n```\n"
    )
    assert broken_links(doc) == [
        "missing.md",
        "other.md#not-here",
        "#absent",
        "img.png",
    ]


def test_anchor_rule_matches_the_headings_this_repo_uses() -> None:
    assert github_anchor("The three checks") == "the-three-checks"
    assert github_anchor("Provenance — what actually ran") == "provenance--what-actually-ran"
    assert github_anchor("The CADEC arm — five preprocessing steps") == \
        "the-cadec-arm--five-preprocessing-steps"
    assert github_anchor("Two vocabulary backends, and they are not equivalent") == \
        "two-vocabulary-backends-and-they-are-not-equivalent"


def test_three_checks_doc_describes_the_checks_that_exist() -> None:
    """docs/three-checks.md said `crosscheck` did not exist and `gatecheck`
    was prep_corpus.py for two days after both landed in ladder/checks/. The
    README links to it as the detail page, so it has to name what is there."""
    doc = (ROOT / "docs" / "three-checks.md").read_text()
    assert "does not exist" not in doc
    assert "prep_corpus.py today" not in doc
    for must in ("scripts/gatecheck.py", "scripts/crosscheck.py",
                 "ladder/checks/gate.py", "ladder/checks/cross.py",
                 "github.com/pushpdeep/stagecheck"):
        assert must in doc, must
    assert (ROOT / "docs" / "three-checks.md") in FILES, \
        "the link check must cover it too"


def test_hero_figure_carries_verdicts_not_numbers() -> None:
    """docs/figures/fig0-hero.png is the first thing a visitor sees. Its
    per-rung notes were CADEC base-run literals typed into fig0.py, and by
    2026-09-09 the ladder table beneath it quoted different figures for the
    same rungs from the matrix and the held-out split. The hero states the
    verdict per rung by colour; the table carries the numbers. Keep it so."""
    src = (ROOT / "docs" / "figures" / "fig0.py").read_text()
    block = src.split("RUNGS = [", 1)[1].split("]", 1)[0]
    notes = re.findall(r'\(\s*"[^"]*",\s*\w+,\s*"([^"]*)"\s*\)', block)
    assert len(notes) == 7, block
    assert not any(re.search(r"\d", n) for n in notes), notes
    readme = (ROOT / "README.md").read_text()
    alt = re.search(r'fig0-hero\.png"[^>]*alt="([^"]*)"', readme, re.S).group(1)
    # The alt text describes the drawing: the four legend categories, no counts.
    for phrase in ("paid for itself", "changed nothing", "read by nothing",
                   "no measured effect"):
        assert phrase in alt, phrase
    assert not re.search(r"\b(two|three|four|five)\b", alt), alt

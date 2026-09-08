"""The InfoQ article keeps the submission rules it was checked against on 2026-09-08.

InfoQ's checklist has ten items. Six are mechanical and are enforced here on
`docs/article-infoq-CADEC.md` and its Word export, so an edit that breaks one
fails in CI rather than at submission; the other four (the generative-AI
disclosure, image copyright, editor access, a proofreading pass) are people's
work and are listed in docs/INFOQ-SUBMISSION.md. Rules:

  - 2,000 to 3,000 words, counting everything except fenced code blocks, HTML
    comments and the "About the authors" section (tables, captions, takeaways
    and references count — the strict reading of "excluding code snippets";
    bios are author metadata InfoQ displays beside the article, not in it);
  - two author bios of about 75 words each under "About the authors";
  - exactly five key takeaways, each a full sentence, at most 130 words together;
  - the authors named under the title;
  - every image followed by an italic caption that names the image source;
  - no tracking parameters in links;
  - one Word file named "Group <N> – <title>.docx", regenerated after the last
    edit to the markdown (its text must contain the current title and the
    current first takeaway).
"""

import html
import pathlib
import re
import zipfile

import pytest

ROOT = pathlib.Path(__file__).parent.parent
ARTICLE = ROOT / "docs" / "article-infoq-CADEC.md"
DOCX_NAME = re.compile(r"^Group \d+ – .+\.docx$")

WORD = re.compile(r"\b[\w'’.-]+\b")


def _text() -> str:
    return ARTICLE.read_text(encoding="utf-8")


def _body(text: str) -> str:
    """Everything that counts toward the budget: no fenced code, no HTML
    comments, and nothing from "About the authors" on (bios are metadata)."""
    text = text.split("\n## About the authors", 1)[0]
    text = re.sub(r"```.*?```", "", text, flags=re.S)
    return re.sub(r"<!--.*?-->", "", text, flags=re.S)


def _bios(text: str) -> list[str]:
    sec = text.split("\n## About the authors", 1)[1]
    sec = re.sub(r"<!--.*?-->", "", sec, flags=re.S)
    return [p.strip() for p in sec.split("\n\n") if p.strip().startswith("**")]


def _words(s: str) -> int:
    return len(WORD.findall(s))


def _takeaways(text: str) -> list[str]:
    sec = text.split("## Key takeaways", 1)[1].split("\n---", 1)[0]
    return [l for l in sec.splitlines() if l.startswith("- ")]


def test_word_budget_2000_to_3000_excluding_code():
    n = _words(_body(_text()))
    assert 2000 <= n <= 3000, f"{n} words excluding code blocks (limit 2,000–3,000)"


def test_word_budget_does_not_count_the_author_bios():
    text = _text()
    assert "\n## About the authors" in text
    assert _words(_body(text)) < _words(_body(text.replace("\n## About the authors", "\n## Authors")))


@pytest.mark.xfail(strict=True, reason="Pushpdeep's bio is still a placeholder")
def test_two_author_bios_of_about_75_words():
    bios = _bios(_text())
    assert len(bios) == 2, f"expected two bios, got {len(bios)}"
    for b in bios:
        n = _words(b)
        assert 50 <= n <= 100, f"bio should be about 75 words, got {n}: {b[:40]!r}"


def test_five_key_takeaways_as_full_sentences_within_130_words():
    tk = _takeaways(_body(_text()))
    assert len(tk) == 5, f"{len(tk)} takeaways, need exactly 5"
    total = sum(_words(l) for l in tk)
    assert total <= 130, f"takeaways are {total} words together (limit 130)"
    for l in tk:
        sentence = l[2:].strip()
        assert sentence[0].isupper() and sentence.endswith("."), f"not a full sentence: {sentence[:60]}"
        assert _words(sentence) >= 8, f"reads as a headline, not a sentence: {sentence}"


def test_authors_are_named_under_the_title():
    lines = [l for l in _text().splitlines() if l.strip() and not l.startswith("<!--")]
    assert lines[0].startswith("# "), "first line is the title"
    byline = lines[1]
    assert byline.startswith("*") and byline.endswith("*") and " and " in byline, \
        f"the line under the title must name the authors, got: {byline!r}"


def test_every_image_has_a_caption_naming_its_source():
    text = _body(_text())
    images = list(re.finditer(r"!\[[^\]]*\]\(([^)]+)\)\n\n(\*[^\n]*\*)?", text))
    assert images, "no images found"
    for m in images:
        src, cap = m.group(1), m.group(2)
        assert cap, f"{src}: no italic caption on the line after the image"
        assert re.match(r"\*Figure \d+: ", cap), f"{src}: caption must start '*Figure N: '"
        assert "Image: " in cap, f"{src}: caption must name the image source ('Image: …')"
        assert (ROOT / "docs" / src).is_file(), f"{src}: file missing"


def test_links_carry_no_tracking_parameters():
    text = _body(_text())
    urls = re.findall(r"(?:https?://)?(?:www\.)?[a-z0-9.-]+\.(?:org|com|io|net)/[^\s)\]`*]+", text)
    assert urls, "no links found"
    bad = [u for u in urls if re.search(r"[?&](utm_|fbclid|gclid|ref=|mc_)", u)]
    assert bad == [], f"tracking parameters: {bad}"


def _docx() -> pathlib.Path:
    files = sorted(p for p in (ROOT / "docs").glob("*.docx"))
    assert len(files) == 1, f"exactly one Word export in docs/, found {[f.name for f in files]}"
    assert DOCX_NAME.match(files[0].name), f"Word file must be named 'Group <N> – <title>.docx', got {files[0].name!r}"
    return files[0]


def _docx_text(path: pathlib.Path) -> str:
    with zipfile.ZipFile(path) as z:
        xml = z.read("word/document.xml").decode("utf-8")
    return html.unescape(re.sub(r"<[^>]+>", "", xml))


def _plain(md: str) -> str:
    """Markdown inline markup stripped, and quotes straightened: pandoc turns
    ' and " into their curly forms, so both sides are compared straight."""
    s = re.sub(r"[*`]", "", md)
    return s.translate(str.maketrans("’‘“”", "''\"\"")).strip()


def test_the_word_export_is_named_to_convention_and_matches_the_markdown():
    """Every takeaway and every caption, verbatim, must be in the Word file:
    an edit to the markdown that is not followed by the pandoc command fails
    here. (Checking only the title let a stale export pass on 2026-09-08.)"""
    doc = _plain(re.sub(r"\s+", " ", _docx_text(_docx())))
    text = _body(_text())
    title = text.splitlines()[0][2:].strip()
    assert title in doc, "the Word file does not carry the current title — regenerate it"
    for l in _takeaways(text):
        s = _plain(l[2:])
        assert s in doc, f"takeaway not in the Word file — regenerate it (docs/INFOQ-SUBMISSION.md): {s[:70]}"
    for cap in re.findall(r"^\*Figure \d+: [^\n]*\*$", text, flags=re.M):
        assert _plain(cap) in doc, f"caption not in the Word file — regenerate it: {cap[:60]}"

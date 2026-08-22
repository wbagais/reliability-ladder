#!/usr/bin/env python3
"""Build the HTML wiki from docs/wiki/content/*.md. Standard library only.

    python docs/wiki/build.py            # -> docs/wiki/site/
    python docs/wiki/build.py --check    # fail on broken [[links]] / orphans

PAGES below is the single source of truth for navigation. Adding a page means
adding one line here and one file in content/; the sidebar, the Home index and
the link checker all read from it.

Markdown subset, deliberately small: #/##/###, - bullets (nested by 2 spaces),
| tables |, ```fences```, > quotes, ---, `code`, **bold**, [text](url),
[[slug]] wiki links, {{done|LABEL}} / {{todo|LABEL}} status badges, and
```mermaid blocks passed through to mermaid.js.
"""
from __future__ import annotations

import argparse
import html
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CONTENT = ROOT / "content"
SITE = ROOT / "site"

#: (slug, title, section). Section groups the sidebar; "" pins to the top.
PAGES: list[tuple[str, str, str]] = [
    ("index",           "Home",                  ""),
    ("getting-started", "Getting Started",       ""),
    ("architecture",    "Architecture",          ""),
    ("contributing",    "Contributing",          ""),
    ("glossary",        "Glossary",              ""),
    ("troubleshooting", "Troubleshooting",       ""),
    ("authorship",      "Authorship",            ""),

    ("rungs",           "The Ladder",            "Rungs"),
    ("r0",              "Rung 0 · bare LLM",     "Rungs"),
    ("r1",              "Rung 1 · deterministic","Rungs"),
    ("r2",              "Rung 2 · abstention",   "Rungs"),
    ("r3",              "Rung 3 · self-correct", "Rungs"),
    ("r4",              "Rung 4 · LLM judge",    "Rungs"),
    ("r5",              "Rung 5 · voting",       "Rungs"),
    ("r6",              "Rung 6 · human loop",   "Rungs"),

    ("record",          "Record & zones",        "Reference"),
    ("ledger",          "Ledger & cost",         "Reference"),
    ("corpus",          "Corpus & splits",       "Reference"),
    ("vocabulary",      "Vocabulary backends",   "Reference"),
    ("manifest",        "manifest.json",         "Reference"),
    ("runner",          "Runner & CLI",          "Reference"),
    ("measurement",     "Measurement tools",     "Reference"),
    ("data-licences",   "Data & licences",       "Reference"),
    ("testing",         "Testing & CI",          "Reference"),
]

TITLES = {slug: title for slug, title, _ in PAGES}

CSS = """
:root{--bg:#fff;--fg:#1a1d21;--muted:#5b6470;--line:#e3e6ea;--accent:#0b5fff;
--code-bg:#f5f7f9;--side:#fafbfc;--warn-bg:#fff8e6;--warn-line:#e0a800;
--ok-bg:#eefaf1;--ok-line:#2f9e5e;--mono:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}
@media (prefers-color-scheme:dark){:root:not([data-theme=light]){
--bg:#14171a;--fg:#e6e9ed;--muted:#98a2ae;--line:#2a2f36;--accent:#6ea8ff;
--code-bg:#1c2126;--side:#171b1f;--warn-bg:#2e2712;--warn-line:#b8860b;
--ok-bg:#14261b;--ok-line:#3aa76d}}
:root[data-theme=dark]{--bg:#14171a;--fg:#e6e9ed;--muted:#98a2ae;--line:#2a2f36;
--accent:#6ea8ff;--code-bg:#1c2126;--side:#171b1f;--warn-bg:#2e2712;
--warn-line:#b8860b;--ok-bg:#14261b;--ok-line:#3aa76d}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);
font:15px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;
display:grid;grid-template-columns:264px minmax(0,1fr)}
nav{background:var(--side);border-right:1px solid var(--line);padding:20px 16px;
height:100vh;position:sticky;top:0;overflow-y:auto}
nav .brand{font-weight:700;font-size:15px;letter-spacing:-.01em;margin-bottom:2px}
nav .tag{color:var(--muted);font-size:11.5px;margin-bottom:16px}
nav h4{font-size:10.5px;text-transform:uppercase;letter-spacing:.09em;
color:var(--muted);margin:18px 0 6px}
nav a{display:block;padding:4px 8px;margin:1px -8px;border-radius:5px;
color:var(--fg);text-decoration:none;font-size:13.5px}
nav a:hover{background:var(--line)}
nav a.on{background:var(--accent);color:#fff;font-weight:600}
main{padding:36px 40px 80px;max-width:920px;overflow-x:auto}
h1{font-size:27px;letter-spacing:-.02em;margin:0 0 4px}
h2{font-size:19px;margin:32px 0 8px;padding-top:14px;border-top:1px solid var(--line)}
h3{font-size:15.5px;margin:20px 0 6px}
p{margin:8px 0}
ul{margin:6px 0;padding-left:20px}
li{margin:3px 0}
li>ul{margin:2px 0}
code{font-family:var(--mono);font-size:12.5px;background:var(--code-bg);
padding:1.5px 5px;border-radius:4px}
pre{background:var(--code-bg);padding:12px 14px;border-radius:7px;
overflow-x:auto;border:1px solid var(--line)}
pre code{background:none;padding:0;font-size:12.5px;line-height:1.5}
table{border-collapse:collapse;margin:10px 0;font-size:13.5px;display:block;
overflow-x:auto;white-space:nowrap}
th,td{border:1px solid var(--line);padding:6px 11px;text-align:left}
th{background:var(--code-bg);font-weight:600}
blockquote{margin:10px 0;padding:9px 14px;background:var(--warn-bg);
border-left:3px solid var(--warn-line);border-radius:0 5px 5px 0}
blockquote p{margin:2px 0}
a{color:var(--accent)}
hr{border:0;border-top:1px solid var(--line);margin:22px 0}
.crumb{color:var(--muted);font-size:12px;margin-bottom:18px}
.status{display:inline-block;font-size:11px;font-weight:700;padding:2px 8px;
border-radius:10px;vertical-align:middle;margin-left:8px}
.status.done{background:var(--ok-bg);color:var(--ok-line);border:1px solid var(--ok-line)}
.status.todo{background:var(--warn-bg);color:var(--warn-line);border:1px solid var(--warn-line)}
.mermaid{background:var(--code-bg);border:1px solid var(--line);
border-radius:7px;padding:14px;margin:12px 0;overflow-x:auto}
.mermaid svg{max-width:100%;height:auto;display:block;margin:0 auto}
@media (max-width:820px){body{grid-template-columns:1fr}
nav{height:auto;position:static;border-right:0;border-bottom:1px solid var(--line)}
main{padding:24px 18px 60px}}
"""


# ---------------------------------------------------------------- markdown

def _inline(s: str) -> str:
    s = html.escape(s, quote=False)
    # Code spans are parked before link substitution so a literal [[slug]] shown
    # as an example never registers as a link (or a broken one).
    parked: list[str] = []
    def park(m):
        parked.append(m.group(1))
        return f"\x00{len(parked) - 1}\x00"
    s = re.sub(r"`([^`]+)`", park, s)
    s = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", s)
    # {{done|BUILT}} / {{todo|NOT STARTED}} — raw HTML in content stays escaped,
    # so status badges get a marker rather than a passthrough hole.
    s = re.sub(r"\{\{(done|todo)\|([^}]+)\}\}",
               lambda m: f'<span class="status {m.group(1)}">{m.group(2)}</span>', s)
    # [[slug]] and [[slug|label]]
    def wiki(m):
        raw = m.group(1)
        slug, _, label = raw.partition("|")
        slug = slug.strip()
        label = (label or TITLES.get(slug, slug)).strip()
        cls = "" if slug in TITLES else ' style="color:red"'
        return f'<a href="{slug}.html"{cls}>{label}</a>'
    s = re.sub(r"\[\[([^\]]+)\]\]", wiki, s)
    s = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', s)
    s = re.sub(r"\x00(\d+)\x00", lambda m: f"<code>{parked[int(m.group(1))]}</code>", s)
    return s


def render(md: str) -> tuple[str, list[str]]:
    """Return (html, wiki-link slugs found)."""
    out: list[str] = []
    links = [m.partition("|")[0].strip() for m in re.findall(r"\[\[([^\]]+)\]\]", md)]
    lines = md.split("\n")
    i = 0
    stack = 0  # open <ul> depth

    def close_lists(to: int = 0):
        nonlocal stack
        while stack > to:
            out.append("</ul>")
            stack -= 1

    while i < len(lines):
        ln = lines[i]

        if ln.startswith("```"):
            lang = ln[3:].strip()
            body: list[str] = []
            i += 1
            while i < len(lines) and not lines[i].startswith("```"):
                body.append(lines[i]); i += 1
            i += 1
            close_lists()
            text = html.escape("\n".join(body), quote=False)
            if lang == "mermaid":
                out.append(f'<pre class="mermaid">{text}</pre>')
            else:
                out.append(f"<pre><code>{text}</code></pre>")
            continue

        if ln.startswith("|") and i + 1 < len(lines) and set(lines[i + 1].replace("|", "").strip()) <= set("-: "):
            close_lists()
            head = [c.strip() for c in ln.strip("|").split("|")]
            i += 2
            rows = []
            while i < len(lines) and lines[i].startswith("|"):
                rows.append([c.strip() for c in lines[i].strip("|").split("|")]); i += 1
            out.append("<table><thead><tr>" + "".join(f"<th>{_inline(c)}</th>" for c in head) + "</tr></thead><tbody>")
            for r in rows:
                out.append("<tr>" + "".join(f"<td>{_inline(c)}</td>" for c in r) + "</tr>")
            out.append("</tbody></table>")
            continue

        m = re.match(r"^(#{1,3})\s+(.*)$", ln)
        if m:
            close_lists()
            lvl = len(m.group(1))
            out.append(f"<h{lvl}>{_inline(m.group(2))}</h{lvl}>")
            i += 1
            continue

        m = re.match(r"^(\s*)[-*]\s+(.*)$", ln)
        if m:
            depth = len(m.group(1)) // 2 + 1
            while stack < depth:
                out.append("<ul>"); stack += 1
            close_lists(depth)
            out.append(f"<li>{_inline(m.group(2))}</li>")
            i += 1
            continue

        if ln.startswith(">"):
            close_lists()
            buf = []
            while i < len(lines) and lines[i].startswith(">"):
                buf.append(lines[i].lstrip("> ").rstrip()); i += 1
            out.append("<blockquote><p>" + _inline(" ".join(buf)) + "</p></blockquote>")
            continue

        if ln.strip() == "---":
            close_lists(); out.append("<hr>"); i += 1; continue

        if ln.strip() == "":
            close_lists(); i += 1; continue

        close_lists()
        out.append(f"<p>{_inline(ln)}</p>")
        i += 1

    close_lists()
    return "\n".join(out), links


# ---------------------------------------------------------------- shell

def sidebar(active: str) -> str:
    parts = ['<div class="brand">Reliability Ladder</div>',
             '<div class="tag">engineering wiki</div>']
    section = None
    for slug, title, sec in PAGES:
        if sec != section:
            if sec:
                parts.append(f"<h4>{sec}</h4>")
            section = sec
        on = " class=on" if slug == active else ""
        parts.append(f'<a href="{slug}.html"{on}>{html.escape(title)}</a>')
    return "\n".join(parts)


SHELL = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title} · Reliability Ladder</title>
<style>{css}</style></head>
<body>
<nav>{nav}</nav>
<main>{crumb}{body}</main>
<script type="module">
import mermaid from "https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.esm.min.mjs";
const dark = matchMedia("(prefers-color-scheme: dark)").matches;
mermaid.initialize({{startOnLoad:true, theme: dark ? "dark" : "default"}});
</script>
</body></html>
"""


def build(check: bool = False) -> int:
    SITE.mkdir(parents=True, exist_ok=True)
    problems: list[str] = []
    seen_links: set[str] = set()

    for slug, title, _sec in PAGES:
        src = CONTENT / f"{slug}.md"
        if not src.exists():
            problems.append(f"missing content: content/{slug}.md")
            continue
        body, links = render(src.read_text(encoding="utf-8"))
        seen_links |= set(links)
        for l in links:
            if l not in TITLES:
                problems.append(f"{slug}.md -> broken [[{l}]]")
        crumb = "" if slug == "index" else '<div class="crumb"><a href="index.html">Home</a> / ' + html.escape(title) + "</div>"
        (SITE / f"{slug}.html").write_text(
            SHELL.format(title=html.escape(title), css=CSS, nav=sidebar(slug),
                         crumb=crumb, body=body), encoding="utf-8")

    orphans = [s for s, _, _ in PAGES if s not in seen_links and s != "index"]
    if orphans:
        problems.append("unlinked from any page: " + ", ".join(orphans))

    print(f"built {len(PAGES)} pages -> {SITE}")
    for p in problems:
        print(f"  WARN  {p}")
    if check and problems:
        return 1
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    sys.exit(build(ap.parse_args().check))

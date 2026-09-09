#!/usr/bin/env python3
"""
readme_nav.py — three things: a nav that reads as four links rather than one
sentence, both remotes stated at the end, and the two GitLab-suggested files
that actually apply.

ON THE SUGGESTION LIST

GitLab offers six. Two apply:

    CHANGELOG        yes — there is real history and the article cites numbers
                     that moved. A reader needs to know which version produced
                     which figure.
    CONTRIBUTING     yes, but honestly: this is a two-owner research repository
                     with a non-transferable corpus, not a project seeking
                     pull requests. Saying so is more useful than a template.

Four do not:

    Kubernetes       nothing deploys. The runner takes a corpus split
                     identifier and writes files.
    Wiki             `docs/decisions.md` already is one, dated and in git. A
                     second place to write things down is how two records start
                     disagreeing — which is the defect this whole study is
                     about.
    Integrations     a settings page, not a file in the repository.
    Observability    there is no service to observe.

    python3 scripts/readme_nav.py --dry-run
    python3 scripts/readme_nav.py
"""
from __future__ import annotations

import argparse
import pathlib
import sys

GITLAB = "https://gitlab.com/pushpdeep/ai-reliability-ladder"
GITHUB = "https://github.com/wbagais/reliability-ladder"
STAGECHECK = "https://github.com/pushpdeep/stagecheck"

# ── 1 · the nav ──────────────────────────────────────────────────────
OLD_NAV = """<p align="center">
  <a href="docs/article-v3.md">the article</a> ·
  <a href="docs/decisions.md">the decision log</a> ·
  <a href="#three-checks-this-study-produced">the three checks</a> ·
  <a href="docs/figures/">figure sources</a>
</p>"""

NEW_NAV = """<table align="center">
<tr>
<td align="center"><a href="docs/article-v3.md"><b>the article</b></a></td>
<td align="center"><a href="docs/decisions.md"><b>the decision log</b></a></td>
<td align="center"><a href="#three-checks-this-study-produced"><b>the three checks</b></a></td>
<td align="center"><a href="runs/archive/matrix-2026-09-07/"><b>the run archive</b></a></td>
</tr>
<tr>
<td align="center"><sub>what we measured, and what it cost</sub></td>
<td align="center"><sub>every finding, dated, beside its corrections</sub></td>
<td align="center"><sub>gatecheck · crosscheck · stagecheck</sub></td>
<td align="center"><sub>~50 cells, re-scoreable from this repo</sub></td>
</tr>
</table>"""

# ── 2 · where this lives ─────────────────────────────────────────────
WHERE = f"""## Where this lives

| | |
|---|---|
| **GitLab** *(primary)* | [{GITLAB.split('//')[1]}]({GITLAB}) — CI publishes the plan and demo from here |
| **GitHub** *(mirror)* | [{GITHUB.split('//')[1]}]({GITHUB}) — the address the article prints |
| **stagecheck** *(separate)* | [{STAGECHECK.split('//')[1]}]({STAGECHECK}) — installable on its own, no dependencies |

The two ladder remotes are the same repository. **If they have diverged, the
GitLab one is ahead:** it is where the runs, the decision log and the archive
are pushed from.

"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    p = pathlib.Path("README.md")
    if not p.is_file():
        sys.exit("README.md not found — run from the repository root")
    s = p.read_text()
    done, missed = [], []

    if OLD_NAV in s:
        s = s.replace(OLD_NAV, NEW_NAV, 1)
        done.append("nav is now four labelled links, not one sentence")
    elif "the run archive" in s:
        done.append("nav already replaced")
    else:
        missed.append("the nav block — it has been edited since")

    if "## Where this lives" in s:
        done.append("remotes section already present")
    elif "## Licence" in s:
        s = s.replace("## Licence", WHERE + "## Licence", 1)
        done.append("remotes section added before the licence")
    else:
        missed.append("no `## Licence` heading to place the remotes before")

    for d in done:
        print(f"  ok      {d}")
    for m in missed:
        print(f"  MISSED  {m}")

    if a.dry_run:
        print("\n  --dry-run: nothing written\n")
        return 0
    if missed:
        print("\n  REFUSING to write a partially-edited README.\n")
        return 1
    p.write_text(s)
    print("\n  wrote README.md")
    print("  now re-run scripts/readme_toc.py to pick up the new section\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

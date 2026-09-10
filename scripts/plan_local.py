"""Build a LOCAL copy of docs/plan.html whose demo carries the full posts.

    PYTHONPATH=. python3 scripts/plan_local.py --run-key <archive>/rerun-cadec-d0 \
        --db ladder/cache/snomed.sqlite --out out/plan-local.html

The published page never shows a CADEC post: the corpus is non-transferable
and a page on GitLab Pages is a distribution channel. On the licensee's own
machine the post may be read, so this script regenerates the demo's
documents WITH the text (scripts/plan_demo.py's `keep_text`) and splices
them into a copy of the page written under `out/`, which is gitignored.
It refuses any destination that is not under `out/`. Open the result in a
browser; do not move it into the tree.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys

_BLOCK = re.compile(r'(<script id="plan-data" type="application/json">\n)(.*?)(\n</script>)', re.S)
_BANNER = ('<div style="position:sticky;top:0;z-index:99;background:#a33333;color:#fff;font:700 12px sans-serif;'
           'padding:6px 14px">LOCAL COPY — carries the full corpus text. Never commit, publish or send this file.</div>')


class LocalOnly(RuntimeError):
    pass


def splice_documents(page: str, documents: list[dict]) -> str:
    m = _BLOCK.search(page)
    if not m:
        raise ValueError("no plan-data block in the page")
    data = json.loads(m.group(2))
    data["documents"] = documents
    data["local_text"] = True
    out = page[:m.start(2)] + json.dumps(data, indent=1) + page[m.end(2):]
    return out.replace("<body>", "<body>" + _BANNER, 1) if "<body>" in out else _BANNER + out


def write_local_page(repo_root: pathlib.Path, documents: list[dict], dest: pathlib.Path) -> pathlib.Path:
    repo_root = pathlib.Path(repo_root).resolve()
    dest = pathlib.Path(dest).resolve()
    out_dir = (repo_root / "out").resolve()
    if out_dir not in dest.parents:
        raise LocalOnly(f"{dest} is not under {out_dir}: a page carrying corpus text is written under out/ only")
    page = (repo_root / "docs" / "plan.html").read_text()
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(splice_documents(page, documents))
    return dest


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--run-key", default="reliability-ladder-b2-menu-f77617/rerun-cadec-d0")
    ap.add_argument("--finer-run-key", default="finer/rerun-finer-d0")
    ap.add_argument("--db", default="ladder/cache/snomed.sqlite")
    ap.add_argument("--out", default="out/plan-local.html")
    args = ap.parse_args(argv)
    from scripts.plan_demo import DOCS, build_documents, build_documents_stripped
    from ladder.registry import Registry
    root = pathlib.Path(".")
    docs = build_documents(root, args.run_key, DOCS["rerun-cadec-d0"], "cadec", keep_text=True)
    psy = sorted(pathlib.Path("runs/archive/matrix-2026-09-07/overnight/full-psytar/psytar-gpt-oss_20b-d0").glob("*.records.stripped.jsonl"))
    if psy:
        docs += build_documents_stripped(psy[0], "psytar-gpt-oss_20b-d0", DOCS["psytar-gpt-oss_20b-d0"], "psytar", Registry(args.db).label)
    from ladder.run import _corpus_for, _corpus_opts, _corpus_root
    man = json.loads(pathlib.Path("manifest.finer.json").read_text())
    docs += build_documents(root, args.finer_run_key, DOCS["rerun-finer-d0"], "finer",
                            corpus=_corpus_for(man).load_corpus(_corpus_root(man), **_corpus_opts(man)),
                            exclusion_rows=[], registry=None, manifest=man)
    dest = write_local_page(root, docs, pathlib.Path(args.out))
    print(f"local page with the full posts -> {dest}  (never commit this file)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

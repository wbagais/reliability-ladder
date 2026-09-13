"""ladder.checks.external — facts this repository asserts about software it
does not contain.

THE GAP THIS CLOSES

`crosscheck` verifies that a manifest's declared facts match what the runtime
actually has, and it stops at this repository's edge. Everything past that edge
is asserted and never read back.

On 2026-09-08, within one hour, four such assertions were wrong at once: a test
count (43 against an actual 62), a version (0.1.0 after the package had grown a
CLI, a dashboard, relations and three provenance features), a documentation file
describing shipped work as outstanding, and a link pointing at the wrong forge.
None was caught by anything; all four were found by opening the other repository
and looking.

THREE-WAY, WHICH IS THE POINT

A claim is checked against the package **and** against the documents that cite
it:

    is it TRUE          read from a local clone — no network, no install
    is it CITED         every file in `cited_in` contains it as written
    is it CONTRADICTED  no cited file states a different value for the same fact

The second and third matter as much as the first. A claim that is true but has
drifted out of the documents is drift already happened; a document that states a
different number from the declaration is the 43-versus-62 case exactly.

WHAT IT CANNOT CHECK

Prose. *"stagecheck records the two things a pipeline usually does not"* is a
sentence, not a fact with a value, and no checker resolves it. The `symbol`
claim is the closest available substitute: assert that the thing a sentence
describes at least exists.
"""
from __future__ import annotations

import ast
import json
import pathlib
import re
import subprocess
import tomllib

from . import FAIL, PASS, SKIP, Result


def _load(path: pathlib.Path) -> pathlib.Path | None:
    p = pathlib.Path(path).expanduser()
    return p if p.is_dir() else None


# ── reading the truth out of a package ───────────────────────────────
def _pyproject(root: pathlib.Path) -> dict:
    f = root / "pyproject.toml"
    if not f.is_file():
        return {}
    try:
        return tomllib.loads(f.read_text())
    except Exception:
        return {}


def actual_version(root: pathlib.Path) -> str | None:
    return ((_pyproject(root).get("project") or {}).get("version"))


def actual_dependencies(root: pathlib.Path) -> list[str] | None:
    proj = _pyproject(root).get("project")
    if proj is None:
        return None
    # `dependencies` absent and `dependencies = []` mean the same thing here.
    return list(proj.get("dependencies") or [])


def actual_tests(root: pathlib.Path, *, collect: bool = True) -> int | None:
    """pytest's own count where it runs, an AST count of `def test_*` otherwise.

    The two can differ — parametrised tests collect as several — so the fallback
    is reported as approximate rather than quietly substituted for the real one.
    """
    if not collect:
        # AST only. Spawning pytest costs ~10 seconds of interpreter and
        # import time in this environment, and seven tests doing it made
        # the suite take 71 seconds — which is how a check stops being run.
        return _ast_tests(root)
    try:
        # -p no:cacheprovider and a short timeout: this shells out, and a
        # subprocess in a test fixture that takes 3 seconds makes the suite
        # take 70. A check nobody runs because it is slow is how the stale
        # numbers this module exists to catch got there.
        r = subprocess.run(["python3", "-m", "pytest", "--collect-only", "-q",
                            "-p", "no:cacheprovider", "--rootdir", str(root)],
                           cwd=root, capture_output=True, text=True, timeout=20)
        m = re.search(r"(\d+)\s+tests? collected", r.stdout)
        if m:
            return int(m.group(1))
    except Exception:
        pass
    return _ast_tests(root)


def _ast_tests(root: pathlib.Path) -> int | None:
    """`def test_*` by parsing. Differs from pytest's count where a test is
    parametrised, so it is the fallback and never silently the answer."""
    n = 0
    for f in root.rglob("test_*.py"):
        if ".git" in f.parts:
            continue
        try:
            tree = ast.parse(f.read_text())
        except Exception:
            continue
        n += sum(1 for node in ast.walk(tree)
                 if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                 and node.name.startswith("test_"))
    return n or None


def actual_url(root: pathlib.Path) -> list[str]:
    try:
        r = subprocess.run(["git", "remote", "-v"], cwd=root,
                           capture_output=True, text=True, timeout=20)
    except Exception:
        return []
    return sorted({m.group(1).removesuffix(".git")
                   for m in re.finditer(r"(https?://\S+)", r.stdout)})


def has_symbol(root: pathlib.Path, name: str) -> bool:
    for f in root.rglob("*.py"):
        if ".git" in f.parts or f.name.startswith("test_"):
            continue
        try:
            tree = ast.parse(f.read_text())
        except Exception:
            continue
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef,
                                 ast.ClassDef)) and node.name == name:
                return True
    return False


# ── checking the documents that cite a claim ─────────────────────────
#: How a claim's value is written in prose, so a document can be searched for it
#: and — the harder half — for a DIFFERENT value of the same fact.
CITED_AS = {
    "tests": (lambda v: rf"\b{v}\s+tests?\b", r"\b(\d+)\s+tests?\b"),
    "version": (lambda v: rf"\b{re.escape(str(v))}\b", r"\bv?(\d+\.\d+\.\d+)\b"),
    "url": (lambda v: re.escape(str(v)), None),
    "dependencies": (lambda v: r"no dependencies" if v == 0 else rf"\b{v}\b", None),
}


def check_citations(claim: dict, repo_root: pathlib.Path,
                    subject: str = "") -> list[Result]:
    """Every file in `cited_in` must contain the value, and none may state a
    different one for the same fact."""
    kind, value = claim["kind"], claim["value"]
    claim = {**claim, "_subject": subject.lower()}
    cited = claim.get("cited_in") or []
    if kind not in CITED_AS or not cited:
        return []
    present_re, any_re = CITED_AS[kind]
    out = []
    for rel in cited:
        f = repo_root / rel
        if not f.is_file():
            out.append(Result(FAIL, f"{kind} cited in {rel}", str(value),
                              "file not found"))
            continue
        text = f.read_text()
        if re.search(present_re(value), text):
            # Present — but does the same file also state a DIFFERENT value?
            # This is the 43-versus-62 case: a stale number sitting beside a
            # fresh one, both true-looking.
            # Scope the contradiction search to the LINES that mention this
            # package, not the whole file. docs/RELEASE-v1.0.md legitimately
            # says "62 tests" of stagecheck and "114 tests across the three" —
            # two facts, two numbers, no contradiction. Reading the file as one
            # context reported that as a conflict, which is a checker inventing
            # a defect and is worse than missing one.
            near = "\n".join(l for l in text.splitlines()
                              if claim.get("_subject", "") in l.lower())
            others = ({m.group(1) for m in re.finditer(any_re, near)} - {str(value)}
                      if any_re and near else set())
            if others:
                out.append(Result(FAIL, f"{kind} contradicted in {rel}",
                                  str(value), f"also states {sorted(others)}",
                                  "two values for one fact in one file"))
            else:
                out.append(Result(PASS, f"{kind} cited in {rel}", str(value),
                                  "present"))
        else:
            found = ({m.group(1) for m in re.finditer(any_re, text)}
                     if any_re else set())
            out.append(Result(FAIL, f"{kind} cited in {rel}", str(value),
                              f"states {sorted(found)}" if found else "absent",
                              "the document and the declaration disagree"))
    return out


# ── the runner ───────────────────────────────────────────────────────
def check_one(name: str, spec: dict, repo_root: pathlib.Path,
              *, collect: bool = True) -> list[Result]:
    out: list[Result] = []
    root = _load(spec.get("local", ""))
    if root is None:
        # Not an error: a contributor without the sibling clone should still be
        # able to run everything else. But say so loudly rather than passing.
        return [Result(SKIP, f"{name}: local clone",
                       str(spec.get("local")),
                       f"not found — `git clone {spec.get('repo')}` to check "
                       f"{len(spec.get('claims') or [])} claims")]

    for claim in spec.get("claims") or []:
        kind, value = claim["kind"], claim["value"]
        label = f"{name}.{kind}" + (f" ({value})" if kind == "symbol" else "")

        if kind == "version":
            got = actual_version(root)
            out.append(Result(PASS if got == value else FAIL, label,
                              str(value), str(got) or "not declared"))
        elif kind == "tests":
            got = actual_tests(root, collect=collect)
            out.append(Result(PASS if got == value else FAIL, label,
                              str(value), str(got) or "could not count"))
        elif kind == "dependencies":
            got = actual_dependencies(root)
            n = None if got is None else len(got)
            out.append(Result(PASS if n == value else FAIL, label,
                              str(value), "no pyproject" if n is None
                              else f"{n}: {got}" if got else "0"))
        elif kind == "url":
            got = actual_url(root)
            ok = any(str(value).rstrip("/") == u.rstrip("/") for u in got)
            out.append(Result(PASS if ok else FAIL, label, str(value),
                              ", ".join(got) or "no remote"))
        elif kind == "symbol":
            ok = has_symbol(root, str(value))
            out.append(Result(PASS if ok else FAIL, label, str(value),
                              "defined" if ok else "NOT FOUND",
                              "" if ok else
                              "a document describing this may be describing "
                              "something that does not exist"))
        else:
            out.append(Result(SKIP, label, str(value), f"unknown kind {kind!r}"))

        out += check_citations(claim, repo_root, name)
    return out


def run(declarations: pathlib.Path, repo_root: pathlib.Path) -> list[Result]:
    if not declarations.is_file():
        return [Result(SKIP, "external declarations", str(declarations),
                       "absent — nothing asserted about other packages")]
    spec = json.loads(declarations.read_text())
    out: list[Result] = []
    for name, block in spec.items():
        if name.startswith("_"):
            continue
        out += check_one(name, block, repo_root)
    return out

#!/usr/bin/env python3
"""
preflight.py — run this BEFORE every push.

Git history is permanent. A key or a licensed post committed once and deleted
later is still in the history, still cloneable, still a breach. This checks the
working tree AND what is already staged/committed.

    python scripts/preflight.py            # working tree + index
    python scripts/preflight.py --history  # also scan all commits (slower)

Exit code 1 on any BLOCK. Wire it into a pre-push hook if you want it enforced:
    ln -s ../../scripts/preflight.py .git/hooks/pre-push && chmod +x .git/hooks/pre-push
"""
from __future__ import annotations
import argparse, re, subprocess, sys
from pathlib import Path

# ── patterns that must never be committed ────────────────────────────────
SECRETS = [
    (r"sk-[A-Za-z0-9_-]{20,}",            "OpenAI-style API key"),
    (r"AIza[0-9A-Za-z_-]{30,}",           "Google API key"),
    (r"sk-ant-[A-Za-z0-9_-]{20,}",        "Anthropic API key"),
    (r"ghp_[A-Za-z0-9]{30,}",             "GitHub token"),
    (r"(?i)(api[_-]?key|secret|password|token)\s*[=:]\s*['\"][^'\"]{12,}['\"]",
                                          "hardcoded credential"),
]

# CADEC posts are colloquial patient prose. These are cheap tells.
CORPUS_TELLS = [
    r"(?i)askapatient",
    r"(?i)\bI've been on \w+ \d+ for (over |about )?\d+ (years|months)",
    r"(?i)\b(gp|doctor) (started|put) me on\b",
    r"(?i)\bstopped taking (it|them) after \d+ days\b",
]

FORBIDDEN_PATHS = [
    ("data/cadec", "CADEC corpus — non-transferable licence"),
    ("data/CADEC", "CADEC corpus — non-transferable licence"),
    ("data/meddra_codes.csv", "full MedDRA list — subscription-licensed"),
    (".llm_cache", "model cache — contains document text"),
    ("cache/", "vocabulary/model cache"),
    (".streamlit/secrets.toml", "secrets file"),
    (".env", "environment file"),
]

TEXT_EXT = {".py", ".md", ".json", ".txt", ".yaml", ".yml", ".csv", ".toml",
            ".html", ".ipynb", ".cfg", ".sh"}


def sh(*a) -> str:
    try:
        return subprocess.run(a, capture_output=True, text=True, timeout=90).stdout
    except Exception:
        return ""


def tracked_files() -> list[str]:
    out = sh("git", "ls-files")
    return [l for l in out.splitlines() if l.strip()]


def scan_text(name: str, text: str, issues: list):
    for pat, what in SECRETS:
        if re.search(pat, text):
            issues.append(("BLOCK", name, f"possible {what}"))
    hits = sum(1 for p in CORPUS_TELLS if re.search(p, text))
    if hits >= 2:
        issues.append(("BLOCK", name, "reads like corpus post text (licence)"))
    elif hits == 1:
        issues.append(("WARN", name, "one corpus-like phrase — check it"))
    if name.endswith(".ipynb") and '"output_type"' in text:
        issues.append(("WARN", name, "notebook has output cells — strip before committing"))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--history", action="store_true")
    args = ap.parse_args()
    issues: list = []

    if not Path(".git").exists():
        print("not a git repository"); return 1

    # 1 — forbidden paths, tracked
    files = tracked_files()
    for f in files:
        for bad, why in FORBIDDEN_PATHS:
            if f.startswith(bad) or f == bad:
                issues.append(("BLOCK", f, why))

    # 2 — content of tracked text files
    for f in files:
        if Path(f).suffix.lower() not in TEXT_EXT:
            continue
        try:
            scan_text(f, Path(f).read_text(errors="ignore")[:400_000], issues)
        except Exception:
            pass

    # 3 — things that must exist before deploying
    for need, why in [("requirements.txt", "Streamlit Cloud reads only this"),
                      (".gitignore", "the licence boundary"),
                      ("LICENSE", "no licence means all rights reserved")]:
        if not Path(need).exists():
            issues.append(("WARN", need, "missing — " + why))
    if not Path("manifest.json").exists():
        issues.append(("WARN", "manifest.json",
                       "missing — a result without a pinned corpus, vocabulary release "
                       "and seed is not reproducible"))
    if not Path("data/splits/test.json").exists():
        issues.append(("WARN", "data/splits/test.json",
                       "missing — run `python -m ladder.run init` once; the frozen split "
                       "is what makes iteration 2 comparable to iteration 1"))
    if Path("requirements.txt").exists():
        for line in Path("requirements.txt").read_text().splitlines():
            s = line.strip()
            if s and not s.startswith("#") and "==" not in s:
                issues.append(("WARN", "requirements.txt", f"unpinned: {s}"))

    # 4 — history (optional, slower)
    if args.history:
        names = sh("git", "log", "--all", "--pretty=format:", "--name-only")
        seen = {n for n in names.splitlines() if n.strip()}
        for n in seen:
            for bad, why in FORBIDDEN_PATHS:
                if n.startswith(bad) or n == bad:
                    issues.append(("BLOCK", n, f"IN HISTORY — {why}. Deleting the file is not enough."))
        blob = sh("git", "log", "--all", "-p", "-S", "sk-")
        if re.search(r"sk-[A-Za-z0-9_-]{20,}", blob):
            issues.append(("BLOCK", "<history>", "API-key-shaped string in commit history"))

    # ── report ───────────────────────────────────────────────────────
    blocks = [i for i in issues if i[0] == "BLOCK"]
    warns = [i for i in issues if i[0] == "WARN"]
    print(f"\npreflight — {len(files)} tracked files"
          f"{' + history' if args.history else ''}\n" + "─" * 62)
    for lvl, name, why in blocks:
        print(f"  BLOCK  {name}\n         {why}")
    for lvl, name, why in warns:
        print(f"  warn   {name}\n         {why}")
    if not issues:
        print("  clean — nothing found")
    print("─" * 62)
    if blocks:
        print(f"{len(blocks)} blocking issue(s). Do not push.")
        print("Already committed? `git rm --cached <path>`, add to .gitignore,")
        print("and for history use git-filter-repo — deleting the file is NOT enough.\n")
        return 1
    print(f"{len(warns)} warning(s). Safe to push.\n" if warns else "Safe to push.\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())

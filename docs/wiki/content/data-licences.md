# Data & licences

**No corpus is in this repository, and none can be.**

## The three sources

| Source | Terms | Where it lives |
|---|---|---|
| **CADEC v2** | CSIRO Data Licence — non-commercial, **NON-TRANSFERABLE**, no redistribution | csiro:10948. Each team member accepts it individually; the download directory is gitignored |
| **SNOMED CT** | affiliate licence for full releases | a local RF2 release indexed by `registry.py`, or EBI OLS4 at run time — free, no key |
| **MedDRA** | subscription (MSSO) | only `data/meddra_codes.example.csv` (10 rows, for tests) is committed |

## Hard rules

- **Never commit corpus text.** Including notebook output cells — the classic leak.
- **Never put a real API key in a tracked file.**
- **Run `python scripts/preflight.py --history` before any commit.** Exits 1 on a breach. CI runs it too.

## What is committed

- `data/splits/*.json` — **document IDs only**. No post text, no annotations. Anyone with their own licensed copy reproduces the exact splits; nobody obtains the corpus from here.
- `docs/cadec-checksums.txt` — hashes, to verify your own copy.
- `data/meddra_codes.example.csv` — 10 rows.

## Forbidden paths

Preflight blocks these in the tree **and in history**:

- `data/cadec`, `data/CADEC*` · `data/meddra_codes.csv` · `.llm_cache` · `cache/` · `.streamlit/secrets.toml` · `.env`

> Deleting a file is **not** enough. Git history is permanent — a licensed post committed once and deleted later is still cloneable. Use `git-filter-repo`.

## Preflight is a backstop, not the definition

- Its corpus detector is four narrow regexes; two hits block, one warns.
- Real corpus text can pass it. **The rule is the rule regardless of what the scanner catches.**

## Writing docs and comments

- Use **synthetic** examples. Every example in this wiki is synthetic for that reason.
- Short mention spans with offsets are established practice (`ladder/fixture.py`), full post text is not.
- `docs/plan.html` is **published publicly** by CI and currently carries a verbatim sentence fragment. Preflight warns on it. Worth resolving.

## What CI publishes

- The pages job copies `docs/plan.html` only, by name. **Never widen it to a glob** — that would publish the raw build log and article drafts, and the corpus fragments in them.

## Related

- [[corpus]] · [[contributing]] · [[testing]]

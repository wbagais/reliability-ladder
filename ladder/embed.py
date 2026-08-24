"""Dense retrieval over the keyword table — S2's candidate shortlist.

    python -m ladder.embed --build

WHY THIS EXISTS: two defects in the lexical shortlist, both structural.

  1. JACCARD'S DENOMINATOR PENALISES LONG TERMS. `Registry.shortlist` scores
     |shared| / |query ∪ term|. For "extreme rectal bleed", |Rectal| scores
     1/3 = 0.33 and |Rectal hemorrhage| scores 1/4 = 0.25 — the single word
     outranks the right concept, and every extra word in a correct term is a
     penalty. That is not a weighting choice; it is what set overlap does.

  2. NO STEMMING. "bleed" never reaches "bleeding", "cramping" never reaches
     "cramp". The patient writes one and SNOMED stores the other. Hand-writing
     a morphology table for a 227,554-row vocabulary is not the answer.

Embeddings fix both without a hand-written rule, at the cost of a build step
and a 350 MB matrix. THE LEXICAL PATH STAYS, behind `rung0_retrieval`, so the
two are comparable on the same corpus, the same k and the same answer key. A
retrieval change measured against nothing is a change of subject.

MODEL: `granite-embedding:30m` through ollama, 384 dimensions, local like
everything else — rung 0's prompts carry CADEC text verbatim and the same
rule applies to anything that sees a keyword or a mention.

WHERE IT LIVES: `ladder/cache/` — a CACHE, unlike `data/keywords.csv`. It is
derived from the keyword table by a fixed function and can be rebuilt from it
in minutes, so it belongs beside `snomed.sqlite` rather than with the corpus.
Rebuild it whenever the keyword table changes: the sidecar pins the row count,
not the table's contents, so a stale matrix answers with confident nonsense
rather than failing.

STORED NORMALISED, IN FLOAT16. Cosine over pre-normalised rows is one matrix
multiply; normalising at query time would repeat 227,554 square roots per
mention. float16 halves the file to 175 MB and costs nothing measurable — the
scores decide a top-20 cut, not a threshold.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence

DEFAULT_MODEL = "granite-embedding:30m"
DEFAULT_PREFIX = Path("ladder/cache/keywords")
DEFAULT_BATCH = 512

#: Ollama's own endpoint, not the OpenAI-compatible one: /api/embed takes a
#: LIST and returns a list, which is the whole reason the build is minutes
#: rather than hours.
DEFAULT_ENDPOINT = "http://localhost:11434/api/embed"


def _np():
    """numpy, imported late with an actionable message.

    It is a local-only extra, like openai and pytest: needed to PRODUCE
    results, never to read them. A checkout that only reads out/*.csv should
    not have to install it.
    """
    try:
        import numpy
    except ImportError as exc:  # pragma: no cover - environment dependent
        raise RuntimeError(
            "dense retrieval needs numpy (a local-only extra, see "
            "requirements.txt):\n    pip install numpy==2.3.3"
        ) from exc
    return numpy


# --- the embedder ------------------------------------------------------------


def ollama_embedder(
    model: str = DEFAULT_MODEL, endpoint: str = DEFAULT_ENDPOINT, timeout: float = 300.0
) -> Callable[[Sequence[str]], list[list[float]]]:
    """A batch embedder over a local ollama. One HTTP call per batch."""
    import httpx

    def embed(texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        r = httpx.post(
            endpoint, json={"model": model, "input": list(texts)}, timeout=timeout
        )
        r.raise_for_status()
        got = r.json()["embeddings"]
        if len(got) != len(texts):
            raise RuntimeError(
                f"{endpoint} returned {len(got)} embeddings for {len(texts)} "
                "inputs. A short batch would silently shift every later row "
                "against its code."
            )
        return got

    return embed


# --- the maths ---------------------------------------------------------------


def cosine_top_k(query, matrix, k: int) -> list[tuple[int, float]]:
    """(row, score) for the k rows closest to `query`, best first.

    `matrix` rows are already unit length, so cosine is a dot product and the
    whole search is one matrix-vector multiply.
    """
    np = _np()
    q = np.asarray(query, dtype=np.float32)
    n = float(np.linalg.norm(q))
    if not n:
        # A zero vector has no angle. Returning rows anyway would rank NaNs as
        # if they were scores.
        return []
    q = q / n
    scores = (np.asarray(matrix, dtype=np.float32) @ q).astype(np.float32)
    k = min(int(k), scores.shape[0])
    if k <= 0:
        return []
    # argpartition first: a full sort of 227,554 scores per mention is the
    # cost this avoids.
    top = np.argpartition(-scores, k - 1)[:k]
    top = top[np.argsort(-scores[top], kind="stable")]
    return [(int(i), float(scores[i])) for i in top]


# --- the build ---------------------------------------------------------------


def _rows_from_table(path: str | Path) -> list[tuple[str, str]]:
    from ladder.keywords import DEFAULT_OUT

    path = Path(path or DEFAULT_OUT)
    with path.open(encoding="utf-8", newline="") as fh:
        r = csv.reader(fh)
        header = next(r, None)
        if header != ["keyword", "code"]:
            raise ValueError(f"{path} is not a keyword table (header {header!r})")
        return [(row[0], row[1]) for row in r if len(row) == 2]


def build_index(
    rows: Iterable[tuple[str, str]],
    prefix: str | Path = DEFAULT_PREFIX,
    embedder: Callable[[Sequence[str]], list[list[float]]] | None = None,
    batch: int = DEFAULT_BATCH,
    progress: bool = False,
) -> dict[str, Any]:
    """Embed every keyword and write `<prefix>.vectors.npy` + `.rows.json`.

    The sidecar keeps (keyword, code) in MATRIX ORDER. The matrix carries no
    labels of its own, so if the two ever drift apart every hit is attributed
    to whatever concept happens to sit at that row — which is why the loader
    checks their lengths agree rather than trusting the pair.
    """
    np = _np()
    rows = [(str(k), str(c)) for k, c in rows]
    embedder = embedder or ollama_embedder()
    prefix = Path(prefix)
    prefix.parent.mkdir(parents=True, exist_ok=True)

    vectors: list[list[float]] = []
    t0 = time.time()
    for start in range(0, len(rows), batch):
        chunk = [k for k, _ in rows[start:start + batch]]
        vectors.extend(embedder(chunk))
        if progress and start and not (start // batch) % 20:
            done = start + len(chunk)
            rate = done / max(time.time() - t0, 1e-6)
            print(
                f"[embed] {done:,}/{len(rows):,}  {rate:.0f}/s  "
                f"eta {(len(rows) - done) / max(rate, 1e-6) / 60:.1f} min",
                file=sys.stderr,
            )

    m = np.asarray(vectors, dtype=np.float32)
    if m.ndim != 2 or m.shape[0] != len(rows):
        raise RuntimeError(
            f"embedder returned {m.shape} for {len(rows)} keywords. A matrix "
            "that is not one row per keyword cannot be indexed by row."
        )
    norms = np.linalg.norm(m, axis=1, keepdims=True)
    # A keyword the embedder cannot place is a zero row. It stays zero rather
    # than becoming NaN, and scores 0 against every query — invisible, which
    # is the correct treatment for a vector carrying no information.
    norms[norms == 0] = 1.0
    m = (m / norms).astype(np.float16)

    np.save(prefix.with_suffix(".vectors.npy"), m)
    prefix.with_suffix(".rows.json").write_text(
        json.dumps(rows), encoding="utf-8"
    )
    return {
        "rows": len(rows),
        "dim": int(m.shape[1]) if m.size else 0,
        "seconds": round(time.time() - t0, 1),
        "prefix": str(prefix),
    }


# --- the index ---------------------------------------------------------------


class EmbeddingIndex:
    """Cosine top-k over the keyword table. Same hit shape as `shortlist`."""

    def __init__(
        self,
        prefix: str | Path = DEFAULT_PREFIX,
        embedder: Callable[[Sequence[str]], list[list[float]]] | None = None,
    ):
        np = _np()
        prefix = Path(prefix)
        vec_path = prefix.with_suffix(".vectors.npy")
        row_path = prefix.with_suffix(".rows.json")
        if not vec_path.exists() or not row_path.exists():
            raise FileNotFoundError(
                f"{vec_path} missing. Build it once (minutes) with:\n"
                "    python -m ladder.embed --build\n"
                "It is derived from data/keywords.csv, so rebuild it whenever "
                "the keyword table changes."
            )
        self.prefix = prefix
        self.matrix = np.load(vec_path)
        self.rows: list[tuple[str, str]] = [
            (k, c) for k, c in json.loads(row_path.read_text(encoding="utf-8"))
        ]
        if len(self.rows) != self.matrix.shape[0]:
            raise ValueError(
                f"{prefix}: {self.matrix.shape[0]} vector rows against "
                f"{len(self.rows)} keyword rows. The matrix carries no labels "
                "of its own, so answering from a mismatched pair attributes "
                "every hit to whatever code sits at that row. Rebuild with "
                "`python -m ladder.embed --build`."
            )
        self._embed = embedder or ollama_embedder()

    def __len__(self) -> int:
        return len(self.rows)

    def search(self, text: str | None, k: int = 20) -> list[dict]:
        """Top-k candidates for a mention, best first, numbered for the model.

        The `i` is what a pick answers with: 76.8% of multi-candidate sets over
        CADEC gold contain two concepts sharing an IDENTICAL label, so a model
        answering with a name is ambiguous more often than not.
        """
        if not text or not str(text).strip():
            return []
        got = self._embed([str(text)])
        if not got:
            return []
        out = []
        for row, score in cosine_top_k(got[0], self.matrix, k):
            keyword, code = self.rows[row]
            out.append({
                "i": len(out),
                "code": code,
                "label": keyword,
                "fsn": keyword,
                "score": round(score, 4),
                "via": "dense",
            })
        return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--build", action="store_true")
    ap.add_argument("--table", default=None, help="defaults to data/keywords.csv")
    ap.add_argument("--prefix", default=str(DEFAULT_PREFIX))
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--batch", type=int, default=DEFAULT_BATCH)
    ap.add_argument("--query", nargs="*", help="search the built index")
    a = ap.parse_args(argv)
    if not a.build and a.query is None:
        ap.error("nothing to do — pass --build or --query")

    if a.build:
        rows = _rows_from_table(a.table)
        print(f"[embed] {len(rows):,} keywords through {a.model}", file=sys.stderr)
        stats = build_index(
            rows, a.prefix, ollama_embedder(a.model), a.batch, progress=True
        )
        print(
            f"[embed] {stats['rows']:,} vectors, dim {stats['dim']}, "
            f"{stats['seconds']}s -> {stats['prefix']}.vectors.npy",
            file=sys.stderr,
        )
    if a.query:
        idx = EmbeddingIndex(a.prefix, ollama_embedder(a.model))
        for q in a.query:
            print(f"\n{q!r}")
            for h in idx.search(q, k=10):
                print(f"  [{h['i']:2d}] {h['score']:.3f}  {h['code']:<18} {h['label']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

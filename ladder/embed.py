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


# --- which encoder builds the menu (B2, 2026-08-31) --------------------------
#
# ONE KEY NAMES AN ENCODER, not a model string plus a prefix, because those two
# must move together: a 768-dim matrix read with a 384-dim query embedder does
# not fail, it ranks noise. Same reason `manifest.model` is the one place a
# model is named.
#
# `granite` is the default and the whole shipped record. `sapbert` is the arm
# the offline menu-recall probe justified: recall@20 87.0% -> 88.4%, recall@1
# 63.7% -> 66.1% over the same 6,595 gold mentions, same corpus, same k
# (docs/decisions.md 2026-08-31). It is a LOCAL model like everything else --
# rung 0's prompts carry CADEC text verbatim and the same rule applies to
# anything that sees a keyword or a mention -- but it runs through
# transformers rather than ollama, because no GGUF conversion of it exists.

ENCODERS: dict[str, dict[str, Any]] = {
    "granite": {
        "model": "granite-embedding:30m",
        "backend": "ollama",
        "dim": 384,
        "suffix": "",
    },
    "sapbert": {
        "model": "cambridgeltl/SapBERT-from-PubMedBERT-fulltext",
        "backend": "transformers",
        "dim": 768,
        # SapBERT's training objective and its own model card pool on [CLS].
        # Mean pooling is a silent quality loss here, never an error.
        "pooling": "cls",
        "max_length": 32,
        "suffix": "-sapbert",
    },
}

DEFAULT_ENCODER = "granite"


def encoder_for(name: str | None = None) -> dict[str, Any]:
    """The registry entry for `name`. RAISES on one nobody registered.

    No silent fallback, for the reason `llm.resolve` has none: a default that
    answers for an unknown name gives "which encoder produced this number" two
    answers depending on whether the name reached the lookup.
    """
    name = name or DEFAULT_ENCODER
    if name not in ENCODERS:
        raise ValueError(
            f"rung0_encoder={name!r} is not registered. Known: "
            f"{', '.join(sorted(ENCODERS))}. An unregistered encoder would "
            "report a run under a label the article cannot explain."
        )
    return ENCODERS[name]


def prefix_for(base: str | Path, name: str | None = None) -> Path:
    """Where `name`'s index lives, given the manifest's `embed_prefix`.

    The suffix is a HYPHEN, not a dot: `EmbeddingIndex` builds its filenames
    with `Path.with_suffix`, which REPLACES a dotted tail, so a prefix of
    "keywords.sapbert" would quietly load granite's matrix and rank 768-dim
    queries against 384-dim rows.
    """
    base = Path(base or DEFAULT_PREFIX)
    return base.with_name(base.name + encoder_for(name)["suffix"])


def transformers_embedder(
    model: str, pooling: str = "cls", max_length: int = 32, device: str | None = None,
    batch: int = 256,
) -> Callable[[Sequence[str]], list[list[float]]]:
    """A batch embedder over a local HuggingFace encoder.

    torch and transformers are imported LATE with an actionable message, the
    same way numpy is: they are needed to run ONE arm, and a checkout that
    never touches it should not carry 2.5 GB to read a CSV.
    """
    try:
        import torch
        from transformers import AutoModel, AutoTokenizer
    except ImportError as exc:  # pragma: no cover - environment dependent
        raise RuntimeError(
            f"rung0_encoder names {model!r}, which runs through transformers "
            "(a local-only extra, see requirements.txt):\n"
            "    pip install torch transformers\n"
            "The default encoder is 'granite' and needs neither."
        ) from exc

    if device is None:
        device = ("mps" if torch.backends.mps.is_available()
                  else "cuda" if torch.cuda.is_available() else "cpu")
    tok = AutoTokenizer.from_pretrained(model)
    mdl = AutoModel.from_pretrained(model).to(device).eval()

    def embed(texts: Sequence[str]) -> list[list[float]]:
        texts = [str(t) for t in texts]
        if not texts:
            return []
        out: list[list[float]] = []
        for i in range(0, len(texts), batch):
            enc = tok(texts[i:i + batch], padding=True, truncation=True,
                      max_length=max_length, return_tensors="pt").to(device)
            with torch.no_grad():
                h = mdl(**enc).last_hidden_state
            if pooling == "cls":
                v = h[:, 0, :]
            else:
                m = enc["attention_mask"].unsqueeze(-1).to(h.dtype)
                v = (h * m).sum(1) / m.sum(1).clamp(min=1e-9)
            out.extend(v.float().cpu().tolist())
        if len(out) != len(texts):
            raise RuntimeError(
                f"{model} returned {len(out)} embeddings for {len(texts)} "
                "inputs. A short batch would silently shift every later row "
                "against its code."
            )
        return out

    return embed


def lazy_embedder_for(name: str | None = None, **kw: Any) -> Callable[
    [Sequence[str]], list[list[float]]
]:
    """`embedder_for`, built on the FIRST QUERY rather than at construction.

    Order matters here and a test pins it: building the embedder eagerly loads
    a 440 MB checkpoint before anything has checked that the index it is meant
    to search exists, so a missing index reported "install torch" instead of
    "build the index". The cheap check must fail first.
    """
    held: dict[str, Callable[[Sequence[str]], list[list[float]]]] = {}

    def embed(texts: Sequence[str]) -> list[list[float]]:
        if "f" not in held:
            held["f"] = embedder_for(name, **kw)
        return held["f"](texts)

    return embed


def embedder_for(name: str | None = None, **kw: Any) -> Callable[
    [Sequence[str]], list[list[float]]
]:
    """The query embedder for `name`. The default path imports no torch."""
    spec = encoder_for(name)
    if spec["backend"] == "ollama":
        return ollama_embedder(spec["model"], **kw)
    return transformers_embedder(
        spec["model"], spec.get("pooling", "cls"), spec.get("max_length", 32), **kw
    )


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


DEFAULT_RETRIES = 4
DEFAULT_BACKOFF = 2.0


def _embed_chunk(
    chunk: Sequence[str],
    embedder: Callable[[Sequence[str]], list[list[float]]],
    retries: int,
    backoff: float,
    tally: dict[str, int],
) -> list[list[float] | None]:
    """Embed one batch, retrying and then splitting. Never raises for one row.

    Measured 2026-08-24: the first full build reached 184,832 of 227,554
    keywords — 24 minutes — and died on a single 400 from the local ollama.
    The same batch succeeded on a re-run, so the input was fine and the server
    was briefly unwell (another job on the same machine). A build that throws
    away 24 minutes because one HTTP call blinked is a build nobody finishes.

    TWO DIFFERENT FAILURES, HANDLED DIFFERENTLY. A batch that fails is
    RETRIED, with backoff, `retries` times. A batch that STILL fails is SPLIT
    in half and each half retried, recursively, until either it succeeds or a
    single row is isolated — and one unembeddable row costs one row.

    An isolated row comes back as None and is filled with ZEROS once the
    dimension is known from a row that worked. Zero scores 0 against every
    query, so the keyword is invisible rather than randomly close to
    something, and its POSITION is held — the sidecar indexes the matrix by
    row, and a dropped row would shift every later keyword onto another
    concept's code.
    """
    last: Exception | None = None
    for attempt in range(retries + 1):
        try:
            got = embedder(chunk)
            if attempt:
                tally["retried"] += attempt
            return got
        except Exception as exc:  # noqa: BLE001 — any transport failure
            last = exc
            if attempt < retries:
                tally["retried"] += 0
                if backoff:
                    time.sleep(backoff * (2 ** attempt))

    tally["retried"] += retries
    if len(chunk) == 1:
        # One row, retried to exhaustion. It is the input, not the server.
        tally["unembeddable"] += 1
        print(
            f"[embed] unembeddable, zeroed: {chunk[0]!r} ({last})", file=sys.stderr
        )
        return [None]

    half = len(chunk) // 2
    return (
        _embed_chunk(chunk[:half], embedder, retries, backoff, tally)
        + _embed_chunk(chunk[half:], embedder, retries, backoff, tally)
    )


def build_index(
    rows: Iterable[tuple[str, str]],
    prefix: str | Path = DEFAULT_PREFIX,
    embedder: Callable[[Sequence[str]], list[list[float]]] | None = None,
    batch: int = DEFAULT_BATCH,
    progress: bool = False,
    retries: int = DEFAULT_RETRIES,
    backoff: float = DEFAULT_BACKOFF,
) -> dict[str, Any]:
    """Embed every keyword and write `<prefix>.vectors.npy` + `.rows.json`.

    The sidecar keeps (keyword, code) in MATRIX ORDER. The matrix carries no
    labels of its own, so if the two ever drift apart every hit is attributed
    to whatever concept happens to sit at that row — which is why the loader
    checks their lengths agree rather than trusting the pair, and why a failing
    batch is split rather than skipped.
    """
    np = _np()
    rows = [(str(k), str(c)) for k, c in rows]
    embedder = embedder or ollama_embedder()
    prefix = Path(prefix)
    prefix.parent.mkdir(parents=True, exist_ok=True)

    tally = {"retried": 0, "unembeddable": 0}
    vectors: list[list[float] | None] = []
    t0 = time.time()
    for start in range(0, len(rows), batch):
        chunk = [k for k, _ in rows[start:start + batch]]
        got = _embed_chunk(chunk, embedder, retries, backoff, tally)
        if len(got) != len(chunk):
            raise RuntimeError(
                f"batch at {start} returned {len(got)} vectors for {len(chunk)} "
                "keywords. A short batch shifts every later row against its code."
            )
        # A whole batch with nothing usable in it is a broken EMBEDDER, not 512
        # simultaneously bad keywords. Raising here fails at minute 24 instead
        # of writing a 175 MB matrix of zeroes that answers every query with
        # silence and looks like a retrieval result.
        if len(chunk) > 1 and not any(v for v in got):
            raise RuntimeError(
                f"every keyword in the batch at {start} failed to embed. That "
                "is the embedder, not the input — check that ollama is running "
                "and the model is pulled. Nothing was written."
            )
        vectors.extend(got)
        if progress and start and not (start // batch) % 20:
            done = start + len(chunk)
            rate = done / max(time.time() - t0, 1e-6)
            print(
                f"[embed] {done:,}/{len(rows):,}  {rate:.0f}/s  "
                f"eta {(len(rows) - done) / max(rate, 1e-6) / 60:.1f} min"
                + (f"  ({tally['retried']} retries)" if tally["retried"] else ""),
                file=sys.stderr,
            )

    dim = next((len(v) for v in vectors if v), 0)
    if not dim:
        raise RuntimeError(
            "no keyword could be embedded. Nothing was written — an index of "
            "zeroes answers every query with silence and looks like a result."
        )
    # Isolated rows become zeros only now, when the dimension is known from a
    # row that worked. Guessing it earlier produced a ragged matrix.
    m = np.asarray([v if v else [0.0] * dim for v in vectors], dtype=np.float32)
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
        **tally,
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
        # k means k CONCEPTS. Synonyms of one concept cluster in embedding
        # space, so an undeduped top-k spends several slots saying the same
        # thing (46.8% of codes carry more than one keyword; a live top-5 held
        # 12063002 twice). Registry.shortlist already dedupes by concept, and
        # the two retrievers must agree on what a slot is. Each concept keeps
        # its best-scoring keyword; over-fetch, then widen to the whole index
        # only if synonyms crowded out the k-th concept.
        out, seen = [], set()
        for fetch in (min(4 * k, len(self.rows)), len(self.rows)):
            out, seen = [], set()
            for row, score in cosine_top_k(got[0], self.matrix, fetch):
                keyword, code = self.rows[row]
                if code in seen:
                    continue
                seen.add(code)
                out.append({
                    "i": len(out),
                    "code": code,
                    "label": keyword,
                    "fsn": keyword,
                    "score": round(score, 4),
                    "via": "dense",
                })
                if len(out) >= k:
                    return out
            if fetch >= len(self.rows):
                break
        return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--build", action="store_true")
    ap.add_argument("--table", default=None, help="defaults to data/keywords.csv")
    ap.add_argument("--prefix", default=str(DEFAULT_PREFIX))
    ap.add_argument("--encoder", default=DEFAULT_ENCODER,
                    help=f"one of {sorted(ENCODERS)} - picks the model, the\n"
                         " pooling and the index path together")
    ap.add_argument("--model", default=None,
                    help="override the encoder's model (ollama backend only)")
    ap.add_argument("--batch", type=int, default=DEFAULT_BATCH)
    ap.add_argument("--retries", type=int, default=DEFAULT_RETRIES)
    ap.add_argument("--backoff", type=float, default=DEFAULT_BACKOFF)
    ap.add_argument("--query", nargs="*", help="search the built index")
    a = ap.parse_args(argv)
    if not a.build and a.query is None:
        ap.error("nothing to do — pass --build or --query")

    spec = encoder_for(a.encoder)
    prefix = prefix_for(a.prefix, a.encoder)
    if a.build:
        rows = _rows_from_table(a.table)
        model = a.model or spec["model"]
        print(f"[embed] {len(rows):,} keywords through {model} -> {prefix}",
              file=sys.stderr)
        embedder = (ollama_embedder(model) if spec["backend"] == "ollama"
                    else embedder_for(a.encoder))
        stats = build_index(
            rows, prefix, embedder, a.batch, progress=True,
            retries=a.retries, backoff=a.backoff,
        )
        print(
            f"[embed] {stats['rows']:,} vectors, dim {stats['dim']}, "
            f"{stats['seconds']}s  {stats['retried']} retries, "
            f"{stats['unembeddable']} zeroed -> {stats['prefix']}.vectors.npy",
            file=sys.stderr,
        )
    if a.query:
        # Through the SAME registry as --build. `--model` is an override that
        # defaults to None, and passing that straight to ollama_embedder asked
        # the server to embed with model None; searching an index under a
        # different encoder from the one that built it is worse than failing.
        embedder = (ollama_embedder(a.model or spec["model"])
                    if spec["backend"] == "ollama" else embedder_for(a.encoder))
        idx = EmbeddingIndex(prefix, embedder)
        for q in a.query:
            print(f"\n{q!r}")
            for h in idx.search(q, k=10):
                print(f"  [{h['i']:2d}] {h['score']:.3f}  {h['code']:<18} {h['label']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

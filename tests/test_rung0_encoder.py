"""`rung0_encoder` — which encoder builds S2's candidate menu.

B2, 2026-08-31. The offline probe (`ladder/menurecall.py`) measured that a
domain-adapted encoder puts gold on the menu more often than the general-
purpose 30M one: recall@20 87.0% -> 88.4%, recall@1 63.7% -> 66.1%. This is
the arm that asks whether the pick converts any of it.

OFF BY DEFAULT, one manifest key, and the key names an ENCODER rather than a
model string plus a prefix - because those two must move together. A 768-dim
matrix read with a 384-dim query embedder does not fail, it ranks noise.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ladder.embed import ENCODERS, embedder_for, encoder_for, prefix_for

_ROOT = Path(__file__).resolve().parent.parent


# --- the registry ------------------------------------------------------------


def test_the_two_encoders_are_registered_with_the_pieces_that_must_agree():
    g, s = encoder_for("granite"), encoder_for("sapbert")
    assert (g["backend"], g["dim"]) == ("ollama", 384)
    assert (s["backend"], s["dim"]) == ("transformers", 768)
    assert g["model"] == "granite-embedding:30m"
    assert s["model"] == "cambridgeltl/SapBERT-from-PubMedBERT-fulltext"
    # SapBERT's own objective and model card pool on [CLS], not the mean. The
    # wrong pooling is a silent quality loss, never an error.
    assert s["pooling"] == "cls"


def test_an_unknown_encoder_raises_rather_than_falling_back():
    # The `llm.resolve` precedent: a default that answers for a name nobody
    # registered gives "which encoder produced this number" two answers.
    with pytest.raises(ValueError) as exc:
        encoder_for("sapbert-large")
    assert "sapbert-large" in str(exc.value)
    assert "granite" in str(exc.value)  # the message names what IS registered


def test_every_registered_encoder_has_its_own_index_path():
    prefixes = {n: str(prefix_for("ladder/cache/keywords", n)) for n in ENCODERS}
    assert len(set(prefixes.values())) == len(ENCODERS)
    assert prefixes["granite"] == "ladder/cache/keywords"


def test_a_non_default_prefix_survives_with_suffix():
    # `EmbeddingIndex` builds its filenames with Path.with_suffix, which
    # REPLACES a dotted tail. A prefix of "keywords.sapbert" would load
    # granite's matrix under SapBERT's name and rank 768-dim queries against
    # 384-dim rows without erroring.
    p = prefix_for("ladder/cache/keywords", "sapbert")
    assert Path(p).with_suffix(".vectors.npy").name == "keywords-sapbert.vectors.npy"
    assert Path(p).with_suffix(".rows.json").name == "keywords-sapbert.rows.json"


def test_embedder_for_granite_does_not_need_torch():
    # The default path must not import a 2.5 GB optional dependency.
    assert callable(embedder_for("granite"))


# --- the wiring --------------------------------------------------------------


def test_rung0_defaults_declare_the_encoder_and_it_is_granite():
    from ladder.rungs import r0

    assert r0.DEFAULTS["rung0_encoder"] == "granite"


def test_the_dense_retriever_looks_for_the_encoder_named_in_cfg():
    from ladder.rungs import r0

    with pytest.raises(RuntimeError) as exc:
        r0._retriever({"rung0_retrieval": "dense", "rung0_encoder": "sapbert",
                       "embed_prefix": "/nonexistent/keywords"})
    assert "keywords-sapbert" in str(exc.value)


def test_an_unknown_encoder_is_refused_at_the_retriever_too():
    from ladder.rungs import r0

    with pytest.raises(ValueError):
        r0._retriever({"rung0_retrieval": "dense", "rung0_encoder": "nope",
                       "embed_prefix": "/nonexistent/keywords"})


# --- the manifests -----------------------------------------------------------


def test_the_shipped_manifest_declares_the_encoder_explicitly():
    """The 2026-08-30 rule: the declared configuration must be the measured
    one and must not lean on a code default that can move."""
    man = json.load(open(_ROOT / "manifest.json"))
    assert man["rungs"]["0"]["rung0_encoder"] == "granite"


def test_the_sapbert_arm_manifest_differs_from_the_shipped_one_by_exactly_one_key():
    a = json.load(open(_ROOT / "manifest.json"))
    b = json.load(open(_ROOT / "manifest.sapbertarm.json"))
    b.pop("_sapbertarm_note", None)

    def walk(x, y, path=""):
        if isinstance(x, dict) and isinstance(y, dict):
            for k in sorted(set(x) | set(y)):
                yield from walk(x.get(k), y.get(k), f"{path}.{k}")
        elif x != y:
            yield path

    assert list(walk(a, b)) == [".rungs.0.rung0_encoder"]
    assert b["rungs"]["0"]["rung0_encoder"] == "sapbert"


def test_a_missing_index_is_reported_before_a_missing_torch():
    """The cheap check fails first.

    Building the embedder eagerly loads a 440 MB checkpoint before anything
    has checked the index it is meant to search exists, so a missing index
    reported "install torch". Two different problems, and only one of them is
    the user's.
    """
    from ladder.embed import lazy_embedder_for

    e = lazy_embedder_for("sapbert")   # must not import torch yet
    assert callable(e)


def test_the_query_cli_resolves_the_encoder_like_the_build_does(monkeypatch):
    """`--query` must go through the SAME registry as `--build`.

    It did not: after `--model` was demoted to an override it defaults to None,
    and the query path passed that straight to `ollama_embedder`, which asked
    the server to embed with model `None`. A search tool that answers under a
    different encoder from the index it is searching is worse than one that
    fails.
    """
    from ladder import embed as E

    seen = {}

    class _Idx:
        def __init__(self, prefix, embedder=None):
            seen["prefix"] = str(prefix)
        def search(self, q, k=20):
            return []

    monkeypatch.setattr(E, "EmbeddingIndex", _Idx)
    monkeypatch.setattr(E, "ollama_embedder",
                        lambda model=None, *a, **kw: seen.__setitem__("model", model))
    E.main(["--query", "rash"])
    assert seen["model"] == "granite-embedding:30m"
    assert seen["prefix"] == "ladder/cache/keywords"

    seen.clear()
    monkeypatch.setattr(E, "embedder_for", lambda name, **kw: seen.__setitem__("enc", name))
    E.main(["--query", "rash", "--encoder", "sapbert"])
    assert seen["prefix"] == "ladder/cache/keywords-sapbert"
    assert seen["enc"] == "sapbert"

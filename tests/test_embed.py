"""Dense retrieval over the keyword table — S2's candidate shortlist.

WHY: two measured defects in the lexical shortlist, both structural rather
than tunable.

  1. Jaccard's denominator penalises long terms. For "extreme rectal bleed",
     |Rectal| scores 1/3 = 0.33 and |Rectal hemorrhage| scores 1/4 = 0.25, so
     the single word outranks the right concept. Every extra word in a correct
     term is a penalty.
  2. No stemming. "bleed" never reaches "bleeding", "cramping" never reaches
     "cramp", and the patient writes one while SNOMED stores the other.

Neither is fixable by weighting: they are properties of set overlap over raw
tokens. Embeddings are the alternative that does not need a hand-written
morphology table for a 227,554-row vocabulary.

MEASURE BEFORE WIRING. The lexical path stays behind a flag so the two are
comparable on the same corpus, the same k and the same answer key. A retrieval
change that is not measured against the number it replaces is a change of
subject.

No ollama and no 350 MB matrix here: the embedder is a scripted callable and
the index is three vectors.
"""

import json

import pytest

np = pytest.importorskip("numpy")

from ladder.embed import EmbeddingIndex, build_index, cosine_top_k


class FakeEmbedder:
    """Deterministic 3-d vectors, one axis per concept family.

    Not a model: a fixture that makes "close" and "far" arithmetic rather than
    a matter of what a 30M-parameter model happens to think today.
    """

    VECTORS = {
        "rectal hemorrhage": [1.0, 0.0, 0.0],
        "rectal": [0.8, 0.0, 0.0],
        "generally unwell": [0.0, 1.0, 0.0],
        "drowsy": [0.0, 0.0, 1.0],
        # the query
        "extreme rectal bleed": [0.9, 0.1, 0.0],
        "feeling rough": [0.1, 0.95, 0.0],
    }

    def __init__(self):
        self.calls = 0

    def __call__(self, texts):
        self.calls += 1
        return [self.VECTORS.get(t, [0.0, 0.0, 0.0]) for t in texts]


ROWS = [
    ("rectal hemorrhage", "12063002"),
    ("rectal", "72002"),
    ("generally unwell", "213257006"),
    ("drowsy", "271782001"),
]


@pytest.fixture
def index(tmp_path):
    build_index(ROWS, tmp_path / "kw", FakeEmbedder(), batch=2)
    return EmbeddingIndex(tmp_path / "kw", FakeEmbedder())


# --- the maths ---------------------------------------------------------------


def test_cosine_ranks_by_angle_not_by_magnitude():
    """|Rectal| and |Rectal hemorrhage| point the same way; cosine must not
    prefer the shorter string for being shorter. That preference IS the
    Jaccard bug."""
    m = np.array([[1.0, 0.0], [0.5, 0.0]], dtype=np.float32)
    m /= np.linalg.norm(m, axis=1, keepdims=True)
    got = cosine_top_k(np.array([1.0, 0.0], dtype=np.float32), m, k=2)
    assert [i for i, _ in got] == [0, 1]
    assert got[0][1] == pytest.approx(got[1][1])


def test_top_k_is_ordered_best_first():
    m = np.array([[1.0, 0.0], [0.0, 1.0], [0.7, 0.7]], dtype=np.float32)
    m /= np.linalg.norm(m, axis=1, keepdims=True)
    got = cosine_top_k(np.array([1.0, 0.0], dtype=np.float32), m, k=3)
    scores = [s for _, s in got]
    assert scores == sorted(scores, reverse=True)


def test_k_larger_than_the_index_returns_everything_once():
    m = np.eye(2, dtype=np.float32)
    got = cosine_top_k(np.array([1.0, 0.0], dtype=np.float32), m, k=99)
    assert len(got) == 2


# --- the index ---------------------------------------------------------------


def test_search_finds_the_right_concept_for_a_layperson_phrase(index):
    """The whole point: "extreme rectal bleed" matches no SNOMED description
    exactly, and the lexical path ranks |Rectal| above |Rectal hemorrhage|."""
    got = index.search("extreme rectal bleed", k=2)
    assert got[0]["code"] == "12063002"


def test_the_long_correct_term_beats_the_short_wrong_one(index):
    got = index.search("extreme rectal bleed", k=4)
    codes = [h["code"] for h in got]
    assert codes.index("12063002") < codes.index("72002")


def test_hits_carry_an_index_a_model_can_answer_with(index):
    """76.8% of multi-candidate sets share an identical label, so a pick is an
    INDEX and never a label string. Same contract as Registry.shortlist."""
    got = index.search("extreme rectal bleed", k=3)
    assert [h["i"] for h in got] == [0, 1, 2]
    for h in got:
        assert set(h) >= {"i", "code", "label", "score", "via"}
    assert got[0]["via"] == "dense"


def test_k_is_respected(index):
    assert len(index.search("extreme rectal bleed", k=2)) == 2


def test_an_empty_query_returns_nothing(index):
    assert index.search("", k=5) == []
    assert index.search(None, k=5) == []


def test_a_query_the_embedder_cannot_place_still_returns_k(index):
    """A zero vector has no angle. It must return an empty list rather than
    NaNs ranked as if they were scores."""
    assert index.search("qwertyuiop", k=3) == []


# --- the build ---------------------------------------------------------------


def test_the_build_writes_vectors_and_their_codes(tmp_path):
    stats = build_index(ROWS, tmp_path / "kw", FakeEmbedder(), batch=2)
    assert stats["rows"] == 4
    assert (tmp_path / "kw.vectors.npy").exists()
    assert (tmp_path / "kw.rows.json").exists()


def test_vectors_are_stored_normalised(tmp_path):
    """Cosine over pre-normalised rows is one matrix multiply. Normalising at
    query time instead would repeat 227,554 square roots per mention."""
    build_index(ROWS, tmp_path / "kw", FakeEmbedder(), batch=2)
    m = np.load(tmp_path / "kw.vectors.npy")
    norms = np.linalg.norm(m.astype(np.float32), axis=1)
    assert np.allclose(norms, 1.0, atol=1e-2)


def test_the_build_batches_rather_than_one_call_per_keyword(tmp_path):
    """227,554 single-row HTTP round trips is hours. Batching is why it is
    minutes."""
    e = FakeEmbedder()
    build_index(ROWS, tmp_path / "kw", e, batch=2)
    assert e.calls == 2


def test_the_row_file_keeps_keyword_and_code_in_matrix_order(tmp_path):
    """The matrix has no labels. If the sidecar's order drifts from the
    matrix's, every hit is silently attributed to the wrong concept."""
    build_index(ROWS, tmp_path / "kw", FakeEmbedder(), batch=3)
    rows = json.loads((tmp_path / "kw.rows.json").read_text())
    assert [tuple(r) for r in rows] == ROWS


def test_a_missing_index_says_how_to_build_it(tmp_path):
    with pytest.raises(FileNotFoundError, match="ladder.embed --build"):
        EmbeddingIndex(tmp_path / "absent", FakeEmbedder())


def test_an_index_whose_sidecar_disagrees_with_its_matrix_is_refused(tmp_path):
    """Truncated write, interrupted build, half-copied cache. Answering from a
    mismatched pair attributes every hit to whatever code sits at that row."""
    build_index(ROWS, tmp_path / "kw", FakeEmbedder(), batch=2)
    (tmp_path / "kw.rows.json").write_text(json.dumps(ROWS[:2]))
    with pytest.raises(ValueError, match="rows"):
        EmbeddingIndex(tmp_path / "kw", FakeEmbedder())

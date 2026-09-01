"""`bench/align.py` is deleted — these keep the repo down to ONE scorer.

Until 2026-08-31 this project had two, reporting under the same words:

  * `ladder/score.py` — span-KEYED, `exact` or `overlap` declared per call,
    detection and coding reported as separate layers. Every figure in
    docs/decisions.md comes from here.
  * the deleted `bench/align.py` — character IoU >= 0.5, bipartite (Hungarian)
    assignment. One caller ever, `scripts/full_run.py`.

Neither was wrong. The hazard was that "precision" meant two different things
depending on which entry point produced it, with nothing on either number
saying which. This repo's own findings are largely about denominators and
definitions moving silently; a second matcher behind the same vocabulary is
that failure waiting in the reporting layer.

`full_run.py` now scores through `score_run`, so the IoU matcher has no caller.
"""
import pathlib

_ROOT = pathlib.Path(__file__).resolve().parents[1]

#: Record files may NAME a deleted thing — that is what a record is for.
_RECORDS = {"decisions.md", "CLAUDE.md", "test_one_scorer.py"}


def test_the_bench_package_is_gone():
    assert not (_ROOT / "bench").exists()


def test_nothing_imports_the_second_scorer():
    """Guarded across the repo, not just in scripts/."""
    hits, looked = [], 0
    for pattern in ("**/*.py", "**/*.md", "**/*.yml"):
        for path in _ROOT.glob(pattern):
            rel = path.relative_to(_ROOT)
            if any(part in (".git", "out", "runs", ".claude", "public",
                            "versions", "__pycache__") for part in rel.parts):
                continue
            if path.name in _RECORDS or path.name.startswith("MR-"):
                continue
            looked += 1
            text = path.read_text(errors="ignore")
            if "from bench import" in text or "bench.align" in text:
                hits.append(str(rel))
    # THE GUARD ON THE GUARD, copied deliberately from
    # test_nothing_references_the_deleted_exporter: that test passed vacuously
    # when written, because this repo is worked in worktrees under .claude/ and
    # an absolute-path filter excluded every file. A count of what was actually
    # opened is what makes an empty result mean anything.
    assert looked > 50, f"only read {looked} files — the walk is broken, not clean"
    assert not hits, "these still reach for the deleted scorer: " + ", ".join(sorted(hits))


def test_full_run_scores_through_the_ladder_scorer():
    """Its only consumer must have moved, not merely stopped importing."""
    src = (_ROOT / "scripts" / "full_run.py").read_text()
    assert "from ladder.score import score_run" in src
    assert "score_run(recs, GOLDS" in src

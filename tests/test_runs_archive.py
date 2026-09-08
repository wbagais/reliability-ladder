"""The consolidated re-run's corpus-free files are TRACKED, complete, and clean.

Every dev-side number in the article comes from the 2026-09-03 consolidated
re-run (`scripts/consolidated_rerun.sh`) and the reports
`scripts/rerun_analysis.py` derives from it. The raw run lives under the
gitignored `out/` because records, state rows and call traces carry corpus
text. The four files per run that carry NONE — the aggregates, the ledger,
the results csv and the saved manifest — plus the derived reports are kept
under `runs/archive/consolidated-2026-09-03/` so a reader of the article can
open the number's source without the corpus or the machine that ran it.

These tests are the guard: a run missing from the set, a corpus-carrying file
kind that slips in, or a report that is not the version the article was
audited against, each fails here rather than in a licence review.
"""

import json
import pathlib
import re
import subprocess
import sys

import pytest

ROOT = pathlib.Path(__file__).parent.parent
ARCHIVE = ROOT / "runs" / "archive" / "consolidated-2026-09-03"
SCRIPTS = ROOT / "scripts"

#: Every run id the re-run produced, by the sub-directory the driver wrote it to.
#: Pinned so a run that goes missing is a failure, not a smaller table.
CADEC_BASE = [f"rerun-cadec-d{d}" for d in range(3)]
CADEC_ARMS = [f"rerun-cadec-d{d}-{arm}" for d in range(3)
              for arm in ("judgemenu", "judgeshuffle", "lexarm", "spine")]
CADEC_STEPS = [f"rerun-cadec-s{s}-d{d}" for s in (0, 1) for d in range(3)]
FINER = [f"rerun-finer-d{d}" for d in range(3)] + \
        [f"rerun-finer-d{d}-{arm}" for d in range(3)
         for arm in ("judgemenu", "judgeshuffle", "spine")]
FINER_TYPECHECK = [f"rerun-finer-d{d}-typecheck" for d in range(3)]
RUNS = {
    "": CADEC_BASE + CADEC_ARMS + CADEC_STEPS,
    "finer": FINER,
    "finer-typecheck": FINER_TYPECHECK,
}
ALL_RUNS = [(sub, rid) for sub, ids in RUNS.items() for rid in ids]

#: The four per-run file kinds that carry no corpus text.
CORPUS_FREE = ("aggregates.json", "ledger.jsonl", "results.csv", "manifest.json")
#: The kinds that do, and must never be archived.
CORPUS_CARRYING = re.compile(r"\.(records|state|calls)\.jsonl$")

#: The derived reports the articles and decisions cite.
REPORTS = [
    "cadec.md", "cadec.json", "cadec-s0.md", "cadec-s0.json",
    "cadec-s1.md", "cadec-s1.json", "finer.md", "finer.json",
    "cadec-probe-all-exact.json", "cadec-probe-all-contained.json",
    "cadec-probe-dev-exact.json", "cadec-probe-dev-contained.json",
]

#: The one-off drivers behind the S0/S1 draws and the FiNER type-check arm.
DRIVERS = ("rerun_all.sh", "rerun_steps.sh", "rerun_typecheck.sh")


def _run_file(sub: str, rid: str, kind: str) -> pathlib.Path:
    return ARCHIVE / sub / f"{rid}.{kind}"


def test_the_archive_exists_and_is_documented():
    assert ARCHIVE.is_dir(), f"{ARCHIVE} is missing"
    readme = (ROOT / "runs" / "archive" / "README.md").read_text()
    assert "consolidated-2026-09-03" in readme


def test_the_run_count_is_the_one_the_re_run_produced():
    assert len(ALL_RUNS) == 36


@pytest.mark.parametrize("sub,rid", ALL_RUNS, ids=[r for _, r in ALL_RUNS])
def test_every_run_has_its_four_corpus_free_files(sub, rid):
    missing = [k for k in CORPUS_FREE if not _run_file(sub, rid, k).is_file()]
    assert not missing, f"{rid}: missing {missing}"


@pytest.mark.parametrize("sub,rid", ALL_RUNS, ids=[r for _, r in ALL_RUNS])
def test_aggregates_name_the_run_they_belong_to(sub, rid):
    agg = json.loads(_run_file(sub, rid, "aggregates.json").read_text())
    assert agg["run_id"] == rid
    assert agg["split"] == "dev", "the held-out split was spent once and is not here"


def test_no_corpus_carrying_file_kind_is_archived():
    bad = [p for p in (ROOT / "runs" / "archive").rglob("*") if CORPUS_CARRYING.search(p.name)]
    assert bad == [], f"records/state/calls carry corpus text: {bad}"


@pytest.mark.parametrize("sub,rid", ALL_RUNS, ids=[r for _, r in ALL_RUNS])
def test_ledger_rows_carry_ids_costs_and_verdicts_only(sub, rid):
    forbidden = {"text", "prompt", "reply", "raw", "content", "spans"}
    for line in _run_file(sub, rid, "ledger.jsonl").read_text().splitlines():
        row = json.loads(line)
        extra = row.get("extra") or {}
        keys = set(row) | (set(extra) if isinstance(extra, dict) else set())
        assert not (keys & forbidden), f"{rid}: ledger row carries {keys & forbidden}"


@pytest.mark.parametrize("name", REPORTS)
def test_every_cited_report_is_archived(name):
    assert (ARCHIVE / "rerun" / name).is_file(), name


def test_the_cadec_report_is_the_version_the_article_was_audited_against():
    # The 2026-09-04 regeneration added the gold-lane occupancy section (the
    # 32%/68% ceiling). The 2026-09-03 file without it is a different answer.
    text = (ARCHIVE / "rerun" / "cadec.md").read_text()
    assert "Gold lane occupancy" in text


def test_archive_passes_the_licence_scan():
    sys.path.insert(0, str(SCRIPTS))
    import preflight  # noqa: E402
    issues: list = []
    for p in sorted(ARCHIVE.rglob("*")):
        if p.is_file():
            preflight.scan_text(str(p.relative_to(ROOT)), p.read_text(errors="ignore")[:400_000], issues)
    blocks = [i for i in issues if i[0] == "BLOCK"]
    assert blocks == [], blocks


@pytest.mark.parametrize("name", DRIVERS)
def test_each_driver_script_is_tracked_and_parses(name):
    path = SCRIPTS / name
    assert path.is_file(), f"scripts/{name} is missing"
    subprocess.run(["bash", "-n", str(path)], check=True)


@pytest.mark.parametrize("article", ["docs/article-v3-CADEC.md", "docs/article-v3.md"])
def test_articles_cite_the_tracked_report_not_a_scratch_path(article):
    text = (ROOT / article).read_text()
    assert "out/rerun/cadec.md" not in text, "cites a gitignored path nobody else can open"
    for cited in re.findall(r"`(runs/archive/[^`]+)`", text):
        assert (ROOT / cited).exists(), f"{article} cites {cited}, which does not exist"
    assert "runs/archive/consolidated-2026-09-03/rerun/cadec.md" in text

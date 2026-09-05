#!/usr/bin/env python3
"""
prep_psytar_arm.py — the manifest, the splits, and the proof it is one variable.

THE EXPERIMENT

The free half is done and measured on gold: PsyTAR's ACCEPT lane holds **26.2%**
of mentions against CADEC's 42.4%. That is lane OCCUPANCY, and it is not the
number the article claims.

The article's claim is about lane **CORRECTNESS** — *"75–82% of what lands in
ACCEPT is correct"* — and section 11 asks whether that belongs to controlled
vocabularies in general or to SNOMED in particular. Occupancy is free;
correctness needs a model, because it needs the model's answers to score.

So: run the ladder on PsyTAR and read the ACCEPT lane's correctness.

    if it lands near 75-82%   the lane's PRECISION is a property of the
                              vocabulary, and only its SIZE moved. That is the
                              stronger result for the article: the check works
                              on a corpus it has never seen, it just fires less
                              often.

    if it lands far below     the lane was CADEC's, both in size and in worth,
                              and the article's central claim needs narrowing
                              to the corpus it was measured on.

Either way the answer is attributable, because only one thing differs.

WHY THE MANIFEST IS DERIVED RATHER THAN WRITTEN

A hand-written manifest would differ from CADEC's in ways nobody intended, and
then a difference in the lane could be caused by a sampling setting or a
retrieval mode instead of by the corpus. So this COPIES `manifest.json` and
changes only the corpus block — and then `scripts/manifest_diff.py` is run to
prove it, which is the check that would have caught the spine ablation's
unsynchronised rung 0 had it existed at the time.

    PYTHONPATH=. python3 scripts/prep_psytar_arm.py
    PYTHONPATH=. python3 scripts/manifest_diff.py manifest.json manifest.psytar.json --declared corpus
"""
from __future__ import annotations

import json
import pathlib
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

BASE = pathlib.Path("manifest.json")
OUT = pathlib.Path("manifest.psytar.json")


def main() -> int:
    if not BASE.is_file():
        sys.exit("manifest.json not found — run from the repo root")
    man = json.loads(BASE.read_text())

    # ── the ONLY block that changes ──────────────────────────────────────
    corpus = dict(man.get("corpus") or {})
    corpus.update({
        "name": "PsyTAR",
        "adapter": "psytar",
        "root": "data/psytar",
        "splits_dir": "data/psytar/splits",
        "entity": "ADR",
        "_source": "https://raw.githubusercontent.com/basaldella/"
                   "psytarpreprocessor/master/data/PsyTAR_dataset.xlsx",
        "_licence": "CC BY 4.0",
        "_why": "The matched comparison for CADEC: the same forum "
                "(askapatient.com), the same task, the same vocabulary "
                "(SNOMED CT), different drugs. FiNER and GeoWebNews each vary "
                "the text AND the vocabulary, so a difference on either is not "
                "attributable. This one varies the corpus alone.",
        "_no_offsets": "PsyTAR gives spans as TEXT, not character offsets, so "
                       "corpus_psytar locates them in their sentence. 573 could "
                       "not be located and were dropped; 18 occur twice and the "
                       "first was taken. Any span-grounding figure from this "
                       "arm measures OUR LOCATOR, not the model.",
    })
    # CADEC's sampling keys name drug groups that do not exist here.
    corpus.pop("sampling", None)
    corpus.pop("cadec_root", None)
    man["corpus"] = corpus

    man["output"] = {"dir": "out/psytar"}
    man["_arm"] = (
        "PsyTAR — the matched comparison. Derived from manifest.json by "
        "changing the corpus block and nothing else; scripts/manifest_diff.py "
        "proves it. The question is the ACCEPT lane's CORRECTNESS, which the "
        "free gold replay cannot answer: occupancy is 26.2% here against "
        "CADEC's 42.4%, and whether the records it admits are still 75-82% "
        "right needs the model."
    )

    OUT.write_text(json.dumps(man, indent=2) + "\n")
    print(f"  wrote {OUT}")

    # ── prove it is one variable ─────────────────────────────────────────
    print("\n  proving the arm changes one thing:")
    r = subprocess.run(
        [sys.executable, "scripts/manifest_diff.py", str(BASE), str(OUT),
         "--declared", "corpus", "output"],
        capture_output=True, text=True)
    print(r.stdout or r.stderr)
    if r.returncode != 0:
        print("  ! The diff found an undeclared difference. Fix it before running —")
        print("    an arm that changes two things cannot attribute its result to either.")
        return 1

    print("  Next:")
    print("    PYTHONPATH=. python3 -m ladder.run --manifest manifest.psytar.json init")
    print("    PYTHONPATH=. python3 -m ladder.run --manifest manifest.psytar.json ladder \\")
    print("        --split dev --limit 3 --plain")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

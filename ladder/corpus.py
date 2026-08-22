"""CADEC v3 reader + the frozen splits.

The corpus itself is never redistributed: this module reads the licensed local
copy, and `data/splits/*.json` stores document IDs only — no post text, no
annotations. Anyone with their own licensed copy reproduces the splits exactly;
nobody gets the corpus from this repo. See docs/licences.md.

What the annotation files actually look like (verified 2026-08-22 on v3):

    text/ARTHROTEC.1.txt        the post
    original/ARTHROTEC.1.ann    T1  ADR 9 19            bit drowsy
    sct/ARTHROTEC.1.ann         TT1 271782001 | Drowsy | 9 19   bit drowsy
    meddra/ARTHROTEC.1.ann      TT1 10013649 9 19       bit drowsy

`TTn` in sct/ and meddra/ keys back to `Tn` in original/, which carries the
entity type. Four shapes the naive parser gets wrong, all present in v3:

  * discontinuous spans  `40 44;54 62`      — 1,065 mentions (11.7%)
  * post-coordination    `A | x | + B | y |` — 252 mentions: the mention needs
                                              BOTH codes
  * disjunction          `A | x | or B | y |` — 3 mentions: EITHER is acceptable
  * CONCEPT_LESS                             — 445 mentions: gold says no code
                                              in the vocabulary is correct
  * tab/pipe sloppiness  `21499005|Feeling agitated 232 249` (no closing pipe),
                         and two lines in DICLOFENAC-SODIUM.7 that use spaces
                         where every other line uses a tab
"""

from __future__ import annotations

import json
import os
import random
import re
from dataclasses import dataclass, field
from pathlib import Path

from ladder.schema import CADEC_TYPE_MAP, CONCEPT_LESS, REACTION

# Offsets, possibly discontinuous: "9 19" or "40 44;54 62". Anchored to the end
# of the body, because a MedDRA body is all digits ("10013649 9 19") and an
# unanchored match would swallow the code as the first offset.
_SPANS = re.compile(r"(\d+ \d+(?:\s*;\s*\d+ \d+)*)\s*$")
_CODE = re.compile(r"\b\d{6,18}\b")

#: Gold answer shapes. `any_of` = credit for either code; `all_of` =
#: post-coordinated, the mention genuinely needs both.
GOLD_SINGLE = "single"
GOLD_ANY_OF = "any_of"
GOLD_ALL_OF = "all_of"
GOLD_NONE = "concept_less"


@dataclass
class GoldMention:
    doc_id: str
    index: int
    entity_type: str  # REACTION | DRUG
    cadec_type: str  # ADR | Symptom | Disease | Finding | Drug
    text: str
    spans: list[tuple[int, int]]
    sct: list[str]  # [] when concept_less
    gold_kind: str
    meddra: list[str] = field(default_factory=list)

    @property
    def record_id(self) -> str:
        return f"{self.doc_id}#{self.index}"

    def to_dict(self) -> dict:
        d = self.__dict__.copy()
        d["spans"] = [list(s) for s in self.spans]
        return d


@dataclass
class Document:
    doc_id: str
    drug_group: str  # ARTHROTEC, LIPITOR, VOLTAREN, ...
    text: str
    mentions: list[GoldMention]


def _split_row(line: str) -> tuple[str, str, str] | None:
    """CADEC rows are `tag<TAB>body<TAB>text`, except where they aren't."""
    parts = line.rstrip("\n").split("\t")
    if len(parts) >= 3:
        return parts[0].strip(), parts[1], "\t".join(parts[2:])
    # Two rows in DICLOFENAC-SODIUM.7 use runs of spaces instead of tabs.
    parts = re.split(r"\s{2,}", line.rstrip("\n"))
    if len(parts) >= 3:
        return parts[0].strip(), parts[1], " ".join(parts[2:])
    return None


def _parse_spans(raw: str) -> list[tuple[int, int]]:
    out = []
    for seg in raw.split(";"):
        a, b = seg.split()
        out.append((int(a), int(b)))
    return out


def _parse_original(path: Path) -> dict[str, str]:
    """`Tn -> CADEC entity type`. Annotator-note rows (`#n`) are skipped."""
    types: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.startswith("T") or line.startswith("#"):
            continue
        row = _split_row(line)
        if not row:
            continue
        tag, body, _ = row
        m = re.match(r"^(\w+)\s+[\d ;]+$", body.strip())
        if m:
            types[tag] = m.group(1)
    return types


def _parse_codes(path: Path) -> dict[str, tuple[list[str], str, list[tuple[int, int]], str]]:
    """`TTn -> (codes, gold_kind, spans, quoted_text)` for sct/ or meddra/."""
    out = {}
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        row = _split_row(line)
        if row:
            tag, body, text = row
        else:
            # No text column at all — still try to recover tag + body.
            bits = line.rstrip("\n").split("\t")
            if len(bits) < 2:
                continue
            tag, body, text = bits[0].strip(), bits[1], ""
        match = _SPANS.search(body.rstrip())
        if not match:
            continue
        spans = _parse_spans(match.group(1))
        payload = body[: match.start()].strip()
        if payload.upper().strip("| ").strip() == CONCEPT_LESS:
            out[tag] = ([], GOLD_NONE, spans, text.strip())
            continue
        codes = _CODE.findall(payload)
        if not codes:
            continue
        if len(codes) == 1:
            kind = GOLD_SINGLE
        elif re.search(r"\bor\b", payload, re.I):
            kind = GOLD_ANY_OF
        else:
            kind = GOLD_ALL_OF  # "+" post-coordination, and anything unlabelled
        out[tag] = (codes, kind, spans, text.strip())
    return out


def load_corpus(root: str | os.PathLike) -> dict[str, Document]:
    """Read every post + its three annotation layers into memory (~35 MB)."""
    root = Path(root)
    tdir, odir, sdir, mdir = (root / "text", root / "original", root / "sct", root / "meddra")
    if not tdir.is_dir():
        raise FileNotFoundError(
            f"CADEC text/ not found under {root}. Download CADEC v3 (csiro:10948), "
            "accept the CSIRO Data Licence yourself, and point manifest.json at it."
        )
    docs: dict[str, Document] = {}
    for txt in sorted(tdir.glob("*.txt")):
        doc_id = txt.stem
        text = txt.read_text(encoding="utf-8", errors="replace")
        types = _parse_original(odir / f"{doc_id}.ann")
        sct = _parse_codes(sdir / f"{doc_id}.ann")
        med = _parse_codes(mdir / f"{doc_id}.ann")
        mentions = []
        for i, (tag, (codes, kind, spans, quoted)) in enumerate(sorted(sct.items(), key=_tag_key)):
            cadec_type = types.get("T" + tag[2:], "ADR")
            mentions.append(
                GoldMention(
                    doc_id=doc_id,
                    index=i,
                    entity_type=CADEC_TYPE_MAP.get(cadec_type, REACTION),
                    cadec_type=cadec_type,
                    text=quoted,
                    spans=spans,
                    sct=codes,
                    gold_kind=kind,
                    meddra=med.get(tag, ([], "", [], ""))[0],
                )
            )
        docs[doc_id] = Document(
            doc_id=doc_id, drug_group=doc_id.split(".")[0], text=text, mentions=mentions
        )
    return docs


def _tag_key(item):
    tag = item[0]
    digits = re.sub(r"\D", "", tag)
    return (int(digits) if digits else 0, tag)


# --- splits -----------------------------------------------------------------

#: CADEC is 80% Lipitor posts. Sampling without stratifying would give a test
#: split that is almost entirely one drug family, and the human-agreement
#: ceiling quoted in the plan (~0.69 strict span) was measured on the
#: diclofenac posts — so both families have to be present to cite it.
LIPITOR = "LIPITOR"


def family(drug_group: str) -> str:
    return "lipitor" if drug_group == LIPITOR else "diclofenac"


def make_splits(
    docs: dict[str, Document],
    seed: int = 42,
    n_dev: int = 40,
    n_test: int = 60,
) -> dict[str, list[str]]:
    """Document-level, stratified by drug family, deterministic in `seed`.

    Split by DOCUMENT, not by mention: mentions from one post share its wording
    and its annotator, so a mention-level split leaks dev into test.

    The plan says "dev 40, test 60" in step 0 and "n (test) = 60" in §7.1, while
    §6 asks for a "600-800 frozen test split" of mention records. Both are
    satisfied by reading 40/60 as DOCUMENTS: 60 posts carry roughly 430 mention
    records and still cost only 60 rung-0 calls. See docs/decisions.md.
    """
    rng = random.Random(seed)
    by_family: dict[str, list[str]] = {}
    for doc_id, doc in docs.items():
        by_family.setdefault(family(doc.drug_group), []).append(doc_id)
    for ids in by_family.values():
        ids.sort()
        rng.shuffle(ids)

    total = sum(len(v) for v in by_family.values())
    share = {fam: len(ids) / total for fam, ids in by_family.items()}
    splits: dict[str, list[str]] = {"dev": [], "test": []}
    for name, n in (("dev", n_dev), ("test", n_test)):
        # Largest-remainder allocation so the split hits exactly n documents.
        want = {fam: n * share[fam] for fam in share}
        take = {fam: int(want[fam]) for fam in share}
        for fam in sorted(share, key=lambda f: -(want[f] - take[f])):
            if sum(take.values()) >= n:
                break
            take[fam] += 1
        for fam in sorted(by_family):
            splits[name].extend(by_family[fam][: take[fam]])
            by_family[fam] = by_family[fam][take[fam] :]
        splits[name].sort()
    splits["pool"] = sorted(i for ids in by_family.values() for i in ids)
    return splits


def write_splits(splits: dict[str, list[str]], out_dir: str | os.PathLike, meta: dict) -> None:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    for name, ids in splits.items():
        (out / f"{name}.json").write_text(
            json.dumps({"split": name, "n_docs": len(ids), "doc_ids": ids, **meta}, indent=2)
        )


def read_split(out_dir: str | os.PathLike, name: str) -> list[str]:
    path = Path(out_dir) / f"{name}.json"
    if not path.exists():
        raise FileNotFoundError(
            f"{path} missing — run `python -m ladder.run splits` once, then never again."
        )
    return json.loads(path.read_text())["doc_ids"]


def gold_records(docs: dict[str, Document], doc_ids: list[str]) -> list[GoldMention]:
    return [m for d in doc_ids for m in docs[d].mentions]

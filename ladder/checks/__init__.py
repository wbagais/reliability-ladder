"""ladder.checks — the shared core of `gatecheck` and `crosscheck`.

WHY THIS EXISTS

The two checks were written as flat scripts on 2026-09-07 and each loaded a
corpus its own way, resolved a vocabulary its own way, and reached into
`ladder.run`'s underscore-prefixed helpers for both. That is workable for two
files and it has three costs:

  · a manifest is read into a corpus in two places, so the two can drift
  · `crosscheck` was ONE function with nine checks inlined — no check could be
    tested alone, and adding a tenth meant editing the other nine
  · both depend on `_corpus_for` and friends, which are private and were never
    an interface

`Arm` is the one place a manifest becomes a loaded corpus, a gold set and a
vocabulary. `Result` is what a single check returns. Everything else is a
function from one to the other, which makes each check independently testable
and makes adding one a matter of writing a function rather than editing a
paragraph.

It also makes the eventual extraction mechanical: move this package, keep the
CLI wrappers.

WHAT IT DELIBERATELY DOES NOT DO

It does not decide anything. `Arm` loads and reports what failed to load;
`gate` predicts a ceiling; `cross` compares declared facts against found ones.
None of them knows whether a thin ceiling is a finding or a bug, and none of
them should.
"""
from __future__ import annotations

import functools
import json
import pathlib
from dataclasses import dataclass, field
from typing import Any, Callable

PASS, FAIL, SKIP = "pass", "FAIL", "skip"


@dataclass
class Result:
    """One check's verdict, with both sides of the comparison kept.

    `declared` and `found` are the point: a check that reports only a verdict
    tells you something is wrong and not what disagreed with what. Every defect
    this package exists to catch was a fact recorded in one place and
    contradicted in another, and the report has to show both.
    """
    status: str
    check: str
    declared: str = ""
    found: str = ""
    note: str = ""

    @property
    def failed(self) -> bool:
        return self.status == FAIL


@dataclass
class Arm:
    """A manifest, loaded: the corpus, its gold, its vocabulary, its splits.

    Constructed once and passed to every check. Loading failures are recorded
    rather than raised, because a check run that dies on the first problem
    reports one defect where there may be five — and the whole point is to see
    them all before booking a card.
    """
    path: str
    manifest: dict
    docs: dict = field(default_factory=dict)
    registry: Any = None
    errors: list[Result] = field(default_factory=list)

    # ── construction ─────────────────────────────────────────────────
    @classmethod
    def load(cls, path: str) -> "Arm":
        from ladder.run import (_corpus_for, _corpus_opts, _corpus_root,
                                _vocab_for, load_manifest)
        man = load_manifest(path)
        arm = cls(path=path, manifest=man)

        try:
            arm._mod = _corpus_for(man)
            arm._opts = _corpus_opts(man)
            arm.docs = arm._mod.load_corpus(_corpus_root(man), **arm._opts)
        except Exception as exc:
            arm._mod, arm._opts = None, {}
            arm.errors.append(Result(FAIL, "corpus loads",
                                     str(arm.corpus.get("root")), str(exc)[:120]))

        try:
            arm.registry = _vocab_for(man)
        except Exception as exc:
            arm.errors.append(Result(FAIL, "vocabulary loads",
                                     str(arm.vocabulary.get("snomed_db")),
                                     str(exc)[:120]))
        return arm

    # ── the manifest, by section ─────────────────────────────────────
    @property
    def corpus(self) -> dict:
        return self.manifest.get("corpus") or {}

    @property
    def vocabulary(self) -> dict:
        return self.manifest.get("vocabulary") or {}

    @property
    def rung0(self) -> dict:
        return (self.manifest.get("rungs") or {}).get("0", {})

    @property
    def prompts(self) -> dict:
        return self.corpus.get("prompts") or {}

    @property
    def name(self) -> str:
        return self.corpus.get("name") or pathlib.Path(self.path).stem

    @property
    def entity(self) -> str:
        p = self.prompts
        return (p.get("entity_short") or p.get("entity") or "").lower()

    # ── derived, and cached: a check should not reload a corpus ──────
    @functools.cached_property
    def gold(self) -> list:
        return [m for d in self.docs.values() for m in d.mentions]

    @functools.cached_property
    def loader(self) -> Callable | None:
        if self._mod is None:
            return None
        return functools.partial(self._mod.load_corpus, **self._opts)

    def split(self, name: str) -> list[str] | None:
        """A frozen split's document ids, or None if the file is absent.

        None and [] are different answers and are kept apart: an absent split
        has not been frozen, and an empty one was frozen wrongly. LINNAEUS's
        pool was empty because 40 dev + 60 test exhausted a 95-document corpus,
        and reporting that as "absent" would have hidden the cause.
        """
        f = pathlib.Path(self.corpus.get("splits_dir", "")) / f"{name}.json"
        if not f.is_file():
            return None
        d = json.loads(f.read_text())
        return d if isinstance(d, list) else d.get("doc_ids", [])

    def rendered_prompt(self) -> str:
        """The text rung 0 would actually send, rendered exactly as it would be.

        This is the check that matters most and the one nothing did before
        2026-09-07: `corpus.prompts` was declared on four arms and never read
        back, and twelve cells asked for adverse drug reactions in papers about
        places, species and diseases.
        """
        from ladder.rungs.r0 import prepare, find_prompt, _extraction_prompt
        cfg = {"manifest": self.manifest, "registry": self.registry,
               "prompt_slots": self.prompts or None,
               "corpus_loader": self.loader, **self.rung0}
        cfg = prepare(cfg)
        return _extraction_prompt(find_prompt(cfg.get("prompt_slots")), cfg)


def report(name: str, results: list[Result], quiet: bool = False) -> int:
    """Print one arm's results and return the failure count."""
    failed = sum(1 for r in results if r.failed)
    if quiet and not failed:
        print(f"  {name:26} {len(results)} checks, all pass")
        return 0
    print(f"\n  ── {name}\n")
    for r in results:
        mark = " !" if r.failed else "  "
        print(f"  {mark} {r.status:4} {r.check}")
        if r.failed or r.note:
            if r.declared:
                print(f"          declared : {r.declared}")
            if r.found:
                print(f"          found    : {r.found}")
            if r.note:
                print(f"          {r.note}")
    print(f"\n      {len(results)} checks, {failed} failed")
    return failed

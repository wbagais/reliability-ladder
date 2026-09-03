#!/usr/bin/env python3
"""Does the same prompt answer the same way, and what changes it?

Registered 2026-09-03 from the consolidated re-run: draws 0 and 1 of
`rerun-cadec` were byte-identical at rung 0 (94 real calls each, none cached),
draw 2 diverged on 29 of 69 shared prompts, and the same prompts answered on
2026-09-01 disagreed with today's on 34 of 64 — at the same latency. So the
model's variance on CADEC is whole runs that repeat or do not, and the candidate
cause is inference-server state between requests rather than sampling.

    python scripts/determinism_probe.py --doc LIPITOR.159 --repeats 5
    python scripts/determinism_probe.py --doc LIPITOR.159 --repeats 5 \
        --interleave ollama/ibm/granite4:micro-h

Builds rung 0's real find prompt for one dev document through r0's own path,
sends it N times with the disk cache DISABLED (a scratch cache per call), and
reports how many distinct replies came back. `--interleave` sends one short
request to another model between repeats, so the extractor is evicted and
reloaded, which is the state change the hypothesis names. RUN ONLY ON AN IDLE
GPU: it perturbs exactly the state it is probing. Dev split only.
"""

from __future__ import annotations

import argparse
import functools
import hashlib
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ladder import llm as llm_mod  # noqa: E402
from ladder.manifest import load_manifest  # noqa: E402
from ladder.run import _corpus_for, _corpus_opts, _corpus_root, _vocab_for  # noqa: E402
from ladder.rungs import r0  # noqa: E402


def find_prompt_for(man: dict, doc_id: str) -> tuple[str, str]:
    corpus = _corpus_for(man)
    docs = corpus.load_corpus(_corpus_root(man), **_corpus_opts(man))
    dev = corpus.read_split(man["corpus"]["splits_dir"], "dev")
    if doc_id not in dev:
        raise SystemExit(f"{doc_id} is not a dev document; the probe runs on dev only")
    cfg = dict(man["rungs"].get("0", {}))
    cfg.update(manifest=man, registry=_vocab_for(man),
               prompt_slots=(man.get("corpus") or {}).get("prompts"),
               corpus_loader=functools.partial(corpus.load_corpus, **_corpus_opts(man)))
    cfg = r0.prepare(cfg)
    return r0._extraction_prompt(r0.find_prompt(cfg.get("prompt_slots")), cfg), docs[doc_id].text


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--manifest", default="manifest.json")
    ap.add_argument("--doc", required=True)
    ap.add_argument("--repeats", type=int, default=5)
    ap.add_argument("--interleave", help="provider/model to call between repeats")
    a = ap.parse_args(argv)
    man = load_manifest(a.manifest)
    prompt, text = find_prompt_for(man, a.doc)
    spec = llm_mod.resolve("extractor", man)
    replies = []
    for i in range(a.repeats):
        with tempfile.TemporaryDirectory() as tmp:
            caller = llm_mod.Caller(spec, role="extractor", cache_dir=tmp,
                                    temperature=llm_mod.temperature_for(man))
            raw, usage = caller(prompt, text, "S2")
        digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]
        replies.append(digest)
        print(f"repeat {i}: {digest}  {usage['seconds']:6.1f}s  tokens {usage['in']}+{usage['out']}"
              f"  cached={usage['cached']}")
        if a.interleave and i < a.repeats - 1:
            with tempfile.TemporaryDirectory() as tmp:
                other = llm_mod.Caller(a.interleave, role="probe", cache_dir=tmp)
                other("Reply with the single word OK.", "", "probe")
            print(f"   interleaved one call to {a.interleave}")
    distinct = len(set(replies))
    print(f"\n{a.doc}: {a.repeats} repeats, {distinct} distinct repl{'y' if distinct == 1 else 'ies'}"
          f"{' with ' + a.interleave + ' interleaved' if a.interleave else ''}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

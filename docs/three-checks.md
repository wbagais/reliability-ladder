# Three checks, three moments

| tool | question | when | knows about corpora |
|---|---|---|---|
| `gatecheck` | should I run this? | before booking a card | yes |
| `crosscheck` | is it what I declared? | first line of every run | yes |
| `stagecheck` | did the run mean anything? | after | **no, deliberately** |

`gatecheck` is `scripts/prep_corpus.py` today. It reads gold and the vocabulary
and reports the free check's ceiling before any spend: FiNER 0.0% (structural),
LINNAEUS 4.8% (thin), PsyTAR 24.3% against a measured 18.6–31.0%.

`crosscheck` does not exist yet. Every defect it would catch got through on
2026-09-06/07 because a load-bearing fact was recorded ONCE and never read back:
the prompt (twelve cells ran CADEC's), the few-shot ids (from train, not the
pool the guard reads), the model (five cells ran one their name did not claim).
Everything that WAS caught worked by comparing two independent records of one
fact — the vocabulary gate, `manifest_diff`, and the directory name against the
saved manifest.

`stagecheck` is its own repo and stays that way. Three gaps are recorded in its
`docs/TODO-provenance.md`: a run stamp, hardware as configuration, and config
assertions.

**The principle underneath all three:** a load-bearing fact recorded once cannot
be checked, and will eventually be wrong silently.

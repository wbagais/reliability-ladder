# CADEC — consolidated re-run, dev split, 40 docs, 226 scorable gold mentions

## Rung 0 per draw (span-exact / overlap; F1 = score_run with exclusions)
| draw | spans | det P/R/F1 exact | coding exact | F1 exact [CI] | det F1 overlap | coding overlap | F1 overlap | sha256(r0) |
|---|---|---|---|---|---|---|---|---|
| rerun-cadec-s1-d0 | 206 | 0.510/0.438/0.471 | 0.535 | **0.252** [0.180–0.322] | 0.771 | 0.494 | 0.381 | `2d52da35` |
| rerun-cadec-s1-d1 | 204 | 0.518/0.443/0.477 | 0.530 | **0.253** [0.181–0.321] | 0.778 | 0.509 | 0.396 | `bd91b5b8` |
| rerun-cadec-s1-d2 | 207 | 0.533/0.460/0.494 | 0.558 | **0.276** [0.205–0.341] | 0.784 | 0.515 | 0.404 | `20118fde` |

## Error budget per draw (exact; one denominator: the scorable gold set)
| draw | gold | matched | missed (find) | invented | on menu | lost retrieval | correct | lost pick | pick loss by lane |
|---|---|---|---|---|---|---|---|---|---|
| rerun-cadec-s1-d0 | 226 | 99 | 127 | 95 | 55 | 44 | 53 | 2 | {'model': 2} |
| rerun-cadec-s1-d1 | 226 | 100 | 126 | 93 | 55 | 45 | 53 | 2 | {'model': 2} |
| rerun-cadec-s1-d2 | 226 | 104 | 122 | 91 | 59 | 45 | 58 | 1 | {'model': 1} |

## Rung 1 lanes per draw (n / correct exact % / on no gold / correct % on overlap-matched)
- rerun-cadec-s1-d0: 
- rerun-cadec-s1-d1: 
- rerun-cadec-s1-d2: 

## Rung 3 by rung 1 lane

## Rung 4 (blind, shipped) vs the menu arms
| draw | arm | judged | pass | fail | P(correct|pass) | P(correct|fail) | separation | span_bad | code_bad | menu shown | not-on-list | best correct | best = pick |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|

## The shipped result and the policy arms (final state rows)
| draw | arm | n | ships | coverage | accuracy | **yield** | errors | err/100 | to a person | stack F1 exact | overlap |
|---|---|---|---|---|---|---|---|---|---|---|---|
| rerun-cadec-s1-d0 | base | 206 | 144 | 0.699 | 0.368 | **0.257** | 91 | 44.2 | 0 | 0.252 | 0.381 |
| rerun-cadec-s1-d1 | base | 204 | 151 | 0.740 | 0.351 | **0.260** | 98 | 48.0 | 0 | 0.253 | 0.396 |
| rerun-cadec-s1-d2 | base | 207 | 154 | 0.744 | 0.377 | **0.280** | 96 | 46.4 | 0 | 0.276 | 0.404 |

## Cost per rung, base draws (tokens / calls / p95 s / human minutes / records routed)
- rerun-cadec-s1-d0: r0: 82,753 / 53 / 51.59 / 0.0 / 0
- rerun-cadec-s1-d1: r0: 81,546 / 55 / 44.27 / 0.0 / 0
- rerun-cadec-s1-d2: r0: 82,407 / 53 / 54.19 / 0.0 / 0

## Three-draw consensus (rung 0 output, mentions grouped by span overlap)
- byte-identical draws: False
- mentions 226: all agree 141 (62.39%), same span diff code 25, same code diff span 4, both differ 11, found by two 18, found by one 27
- same span all draws 73.45%; same code where all found 80.11%

## Provenance
- rerun-cadec-s1-d0: cache `/Users/wejdanbagais/Documents/repo/reliability-ladder/.claude/worktrees/reliability-ladder-b2-menu-f77617/.llm_cache.rerun-cadec-s1-d0`, git {'sha': 'c093eaa', 'branch': 'claude/plan-next-sessions-docs-17c0bc', 'dirty': False, 'dirty_files': 0}, 2026-09-04T01:05:43Z → 2026-09-04T01:18:24Z
- rerun-cadec-s1-d1: cache `/Users/wejdanbagais/Documents/repo/reliability-ladder/.claude/worktrees/reliability-ladder-b2-menu-f77617/.llm_cache.rerun-cadec-s1-d1`, git {'sha': 'c093eaa', 'branch': 'claude/plan-next-sessions-docs-17c0bc', 'dirty': False, 'dirty_files': 0}, 2026-09-04T01:18:25Z → 2026-09-04T01:30:34Z
- rerun-cadec-s1-d2: cache `/Users/wejdanbagais/Documents/repo/reliability-ladder/.claude/worktrees/reliability-ladder-b2-menu-f77617/.llm_cache.rerun-cadec-s1-d2`, git {'sha': 'c093eaa', 'branch': 'claude/plan-next-sessions-docs-17c0bc', 'dirty': False, 'dirty_files': 0}, 2026-09-04T01:30:35Z → 2026-09-04T01:43:13Z

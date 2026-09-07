# CADEC — consolidated re-run, dev split, 40 docs, 226 scorable gold mentions

## Rung 0 per draw (span-exact / overlap; F1 = score_run with exclusions)
| draw | spans | det P/R/F1 exact | coding exact | F1 exact [CI] | det F1 overlap | coding overlap | F1 overlap | sha256(r0) |
|---|---|---|---|---|---|---|---|---|
| rerun-cadec-s0-d0 | 179 | 0.554/0.411/0.472 | 0.065 | **0.030** [0.005–0.065] | 0.741 | 0.041 | 0.030 | `7a7b50e1` |
| rerun-cadec-s0-d1 | 186 | 0.581/0.447/0.505 | 0.059 | **0.030** [0.005–0.059] | 0.760 | 0.040 | 0.030 | `7bbc407e` |
| rerun-cadec-s0-d2 | 196 | 0.560/0.456/0.502 | 0.049 | **0.024** [0.004–0.051] | 0.766 | 0.032 | 0.024 | `1f7e6a58` |

## Error budget per draw (exact; one denominator: the scorable gold set)
| draw | gold | matched | missed (find) | invented | on menu | lost retrieval | correct | lost pick | pick loss by lane |
|---|---|---|---|---|---|---|---|---|---|
| rerun-cadec-s0-d0 | 226 | 93 | 133 | 75 | 1 | 92 | 6 | -5 | {'model': 1} |
| rerun-cadec-s0-d1 | 226 | 101 | 125 | 73 | 1 | 100 | 6 | -5 | {'model': 1} |
| rerun-cadec-s0-d2 | 226 | 103 | 123 | 81 | 1 | 102 | 5 | -4 | {'model': 1} |

## Rung 1 lanes per draw (n / correct exact % / on no gold / correct % on overlap-matched)
- rerun-cadec-s0-d0: 
- rerun-cadec-s0-d1: 
- rerun-cadec-s0-d2: 

## Rung 3 by rung 1 lane

## Rung 4 (blind, shipped) vs the menu arms
| draw | arm | judged | pass | fail | P(correct|pass) | P(correct|fail) | separation | span_bad | code_bad | menu shown | not-on-list | best correct | best = pick |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|

## The shipped result and the policy arms (final state rows)
| draw | arm | n | ships | coverage | accuracy | **yield** | errors | err/100 | to a person | stack F1 exact | overlap |
|---|---|---|---|---|---|---|---|---|---|---|---|
| rerun-cadec-s0-d0 | base | 179 | 111 | 0.620 | 0.054 | **0.034** | 105 | 58.7 | 0 | 0.030 | 0.030 |
| rerun-cadec-s0-d1 | base | 186 | 149 | 0.801 | 0.040 | **0.032** | 143 | 76.9 | 0 | 0.030 | 0.030 |
| rerun-cadec-s0-d2 | base | 196 | 165 | 0.842 | 0.030 | **0.026** | 160 | 81.6 | 0 | 0.024 | 0.024 |

## Cost per rung, base draws (tokens / calls / p95 s / human minutes / records routed)
- rerun-cadec-s0-d0: r0: 141,183 / 40 / 119.58 / 0.0 / 0
- rerun-cadec-s0-d1: r0: 147,477 / 40 / 144.14 / 0.0 / 0
- rerun-cadec-s0-d2: r0: 141,143 / 40 / 140.96 / 0.0 / 0

## Three-draw consensus (rung 0 output, mentions grouped by span overlap)
- byte-identical draws: False
- mentions 210: all agree 82 (39.05%), same span diff code 66, same code diff span 2, both differ 11, found by two 25, found by one 24
- same span all draws 70.48%; same code where all found 52.17%

## Provenance
- rerun-cadec-s0-d0: cache `/Users/wejdanbagais/Documents/repo/reliability-ladder/.claude/worktrees/reliability-ladder-b2-menu-f77617/.llm_cache.rerun-cadec-s0-d0`, git {'sha': 'd4ddf46', 'branch': 'claude/plan-next-sessions-docs-17c0bc', 'dirty': False, 'dirty_files': 0}, 2026-09-03T23:26:15Z → 2026-09-03T23:57:51Z
- rerun-cadec-s0-d1: cache `/Users/wejdanbagais/Documents/repo/reliability-ladder/.claude/worktrees/reliability-ladder-b2-menu-f77617/.llm_cache.rerun-cadec-s0-d1`, git {'sha': '956e885', 'branch': 'claude/plan-next-sessions-docs-17c0bc', 'dirty': False, 'dirty_files': 0}, 2026-09-03T23:57:51Z → 2026-09-04T00:32:09Z
- rerun-cadec-s0-d2: cache `/Users/wejdanbagais/Documents/repo/reliability-ladder/.claude/worktrees/reliability-ladder-b2-menu-f77617/.llm_cache.rerun-cadec-s0-d2`, git {'sha': 'c093eaa', 'branch': 'claude/plan-next-sessions-docs-17c0bc', 'dirty': False, 'dirty_files': 0}, 2026-09-04T00:32:09Z → 2026-09-04T01:05:43Z

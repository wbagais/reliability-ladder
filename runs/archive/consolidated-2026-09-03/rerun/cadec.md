# CADEC — consolidated re-run, dev split, 40 docs, 226 scorable gold mentions

## Rung 0 per draw (span-exact / overlap; F1 = score_run with exclusions)
| draw | spans | det P/R/F1 exact | coding exact | F1 exact [CI] | det F1 overlap | coding overlap | F1 overlap | sha256(r0) |
|---|---|---|---|---|---|---|---|---|
| rerun-cadec-d0 | 230 | 0.535/0.513/0.524 | 0.750 | **0.393** [0.310–0.468] | 0.804 | 0.590 | 0.474 | `c96289db` |
| rerun-cadec-d1 | 230 | 0.535/0.513/0.524 | 0.750 | **0.393** [0.310–0.468] | 0.804 | 0.590 | 0.474 | `c96289db` |
| rerun-cadec-d2 | 238 | 0.571/0.571/0.571 | 0.760 | **0.434** [0.360–0.505] | 0.823 | 0.613 | 0.504 | `c3626412` |

## Error budget per draw (exact; one denominator: the scorable gold set)
| draw | gold | matched | missed (find) | invented | on menu | lost retrieval | correct | lost pick | pick loss by lane |
|---|---|---|---|---|---|---|---|---|---|
| rerun-cadec-d0 | 226 | 116 | 110 | 101 | 108 | 8 | 87 | 21 | {'model': 19, 'fallback': 2} |
| rerun-cadec-d1 | 226 | 116 | 110 | 101 | 108 | 8 | 87 | 21 | {'model': 19, 'fallback': 2} |
| rerun-cadec-d2 | 226 | 129 | 97 | 97 | 121 | 8 | 98 | 23 | {'model': 22, 'fallback': 1} |

## Rung 1 lanes per draw (n / correct exact % / on no gold / correct % on overlap-matched)
- rerun-cadec-d0: ACCEPT: 53 / 75.47% / 4 / 75.51%; BAND: 175 / 26.86% / 40 / 48.89%; REJECT: 2 / 0.0% / 0 / 0.0%
- rerun-cadec-d1: ACCEPT: 53 / 75.47% / 4 / 75.51%; BAND: 175 / 26.86% / 40 / 48.89%; REJECT: 2 / 0.0% / 0 / 0.0%
- rerun-cadec-d2: ACCEPT: 51 / 82.35% / 2 / 79.59%; BAND: 184 / 30.43% / 41 / 51.05%; REJECT: 3 / 0.0% / 0 / 0.0%

## Rung 3 by rung 1 lane
- rerun-cadec-d0: by lane {'BAND': {'unanimous': 108, 'changed': 22, 'split': 21, 'tie': 14, 'not_resampled': 8, 'single_sample': 3}, 'ACCEPT': {'unanimous': 41, 'single_sample': 1, 'not_resampled': 4, 'tie': 1, 'split': 4, 'changed': 2}, 'REJECT': {'changed': 1}}; changed 25, correct destroyed 2, gained 3, net +1; not_resampled had been {'unmatched': 9, 'correct': 2, 'incorrect': 1}
    - ARTHROTEC.107#2 [BAND] 282973006 -> 151811000119109 votes {'151811000119109': 2, '54840006': 1}: unmatched -> unmatched
    - ARTHROTEC.57#1 [BAND] 246871006 -> 9126005 votes {'9126005': 3}: unmatched -> unmatched
    - ARTHROTEC.78#1 [BAND] 267055007 -> 35064005 votes {'35064005': 2}: unmatched -> unmatched
    - ARTHROTEC.8#2 [BAND] 55607006 -> 22253000 votes {'22253000': 2}: unmatched -> unmatched
    - LIPITOR.159#13 [BAND] 162471005 -> 225013001 votes {'225013001': 3}: unmatched -> unmatched
    - LIPITOR.231#1 [BAND] 82991003 -> 279044000 votes {'279044000': 2, '68962001': 1}: unmatched -> unmatched
    - LIPITOR.24#2 [BAND] CONCEPT_LESS -> 1264030002 votes {'1264030002': 2, '202490009': 1}: abstained -> incorrect
    - LIPITOR.380#0 [BAND] 40884005 -> 45326000 votes {'68962001': 1, '45326000': 2}: unmatched -> unmatched
    - LIPITOR.380#2 [REJECT] 202379000 -> 1348356003 votes {'202379000': 1, '1348356003': 2}: unmatched -> unmatched
    - LIPITOR.445#2 [BAND] 278040002 -> 56317004 votes {'56317004': 2, '278040002': 1}: correct -> incorrect
    - LIPITOR.445#7 [BAND] 59050008 -> 224233001 votes {'224233001': 3}: unmatched -> unmatched
    - LIPITOR.460#7 [BAND] 84229001 -> 84946008 votes {'84946008': 2}: incorrect -> incorrect
    - LIPITOR.460#15 [BAND] 721157004 -> 247602005 votes {'247602005': 2}: unmatched -> unmatched
    - LIPITOR.460#16 [BAND] 73145009 -> 228354000 votes {'228354000': 2}: unmatched -> unmatched
    - LIPITOR.48#5 [BAND] 301823007 -> 90673000 votes {'301823007': 1, '90673000': 2}: incorrect -> correct
    - LIPITOR.48#12 [BAND] CONCEPT_LESS -> 286783004 votes {'286783004': 2}: unmatched -> unmatched
    - LIPITOR.53#1 [BAND] 82423001 -> 22253000 votes {'22253000': 2, '10601006': 1}: unmatched -> unmatched
    - LIPITOR.54#1 [BAND] 203095000 -> 55300003 votes {'161891005': 1, '55300003': 2}: unmatched -> unmatched
    - LIPITOR.739#1 [BAND] 271327008 -> 82423001 votes {'1264024002': 1, '82423001': 2}: unmatched -> unmatched
    - LIPITOR.761#3 [BAND] 67233009 -> 301345002 votes {'301345002': 2, 'CONCEPT_LESS': 1}: incorrect -> correct
    - LIPITOR.78#0 [BAND] 276444007 -> 418290006 votes {'418290006': 3}: unmatched -> unmatched
    - LIPITOR.8#5 [ACCEPT] 22253000 -> 1144586002 votes {'1144586002': 2}: correct -> incorrect
    - LIPITOR.806#0 [BAND] 771083005 -> 76948002 votes {'76948002': 2, '15749341000119107': 1}: incorrect -> correct
    - LIPITOR.921#1 [BAND] 395080004 -> 367391008 votes {'395080004': 1, '367391008': 2}: incorrect -> incorrect
    - LIPITOR.935#9 [ACCEPT] 249489001 -> 225589000 votes {'249489001': 1, '225589000': 2}: unmatched -> unmatched
- rerun-cadec-d1: by lane {'BAND': {'unanimous': 95, 'single_sample': 3, 'split': 31, 'changed': 27, 'tie': 12, 'not_resampled': 8}, 'ACCEPT': {'unanimous': 39, 'tie': 4, 'not_resampled': 4, 'split': 5, 'changed': 1}, 'REJECT': {'tie': 1}}; changed 28, correct destroyed 3, gained 2, net -1; not_resampled had been {'correct': 5, 'unmatched': 7}
    - ARTHROTEC.57#1 [BAND] 246871006 -> 9126005 votes {'9126005': 3}: unmatched -> unmatched
    - LIPITOR.159#13 [BAND] 162471005 -> 225013001 votes {'225013001': 3}: unmatched -> unmatched
    - LIPITOR.24#0 [BAND] 49218002 -> 68962001 votes {'68962001': 2, '49218002': 1}: correct -> incorrect
    - LIPITOR.24#1 [BAND] 10601006 -> 68962001 votes {'68962001': 2, '316941000119108': 1}: incorrect -> incorrect
    - LIPITOR.24#2 [BAND] CONCEPT_LESS -> 68962001 votes {'68962001': 2, '1264030002': 1}: abstained -> incorrect
    - LIPITOR.24#3 [BAND] 262966007 -> 95847005 votes {'95847005': 2, '262966007': 1}: incorrect -> incorrect
    - LIPITOR.380#0 [BAND] 40884005 -> 45326000 votes {'68962001': 1, '45326000': 2}: unmatched -> unmatched
    - LIPITOR.401#7 [BAND] 719232003 -> 248244005 votes {'248244005': 2}: incorrect -> incorrect
    - LIPITOR.445#2 [BAND] 278040002 -> 56317004 votes {'56317004': 2, '278040002': 1}: correct -> incorrect
    - LIPITOR.445#7 [BAND] 59050008 -> 224233001 votes {'224233001': 3}: unmatched -> unmatched
    - LIPITOR.460#11 [BAND] 1071841000000108 -> 160685001 votes {'160685001': 2}: unmatched -> unmatched
    - LIPITOR.460#13 [BAND] 161873000 -> 10601006 votes {'275318002': 1, '10601006': 2}: unmatched -> unmatched
    - LIPITOR.460#15 [BAND] 721157004 -> 716442002 votes {'716442002': 2, '247602005': 1}: unmatched -> unmatched
    - LIPITOR.460#16 [BAND] 73145009 -> 228354000 votes {'228354000': 3}: unmatched -> unmatched
    - LIPITOR.48#5 [BAND] 301823007 -> 90673000 votes {'90673000': 3}: incorrect -> correct
    - LIPITOR.48#12 [BAND] CONCEPT_LESS -> 286783004 votes {'286783004': 2, 'CONCEPT_LESS': 1}: unmatched -> unmatched
    - LIPITOR.53#2 [BAND] 65124004 -> 299322007 votes {'299322007': 3}: unmatched -> unmatched
    - LIPITOR.53#4 [BAND] 22253000 -> 250044006 votes {'250044006': 2, '22253000': 1}: unmatched -> unmatched
    - LIPITOR.54#1 [BAND] 203095000 -> 55300003 votes {'55300003': 3}: unmatched -> unmatched
    - LIPITOR.54#6 [BAND] 225019002 -> 406556003 votes {'406556003': 2, '22253000': 1}: unmatched -> unmatched
    - LIPITOR.54#7 [BAND] 45352006 -> 203095000 votes {'203095000': 3}: unmatched -> unmatched
    - LIPITOR.739#1 [BAND] 271327008 -> 82423001 votes {'82423001': 2}: unmatched -> unmatched
    - LIPITOR.757#6 [BAND] 22253000 -> 76948002 votes {'76948002': 2, '22253000': 1}: unmatched -> unmatched
    - LIPITOR.761#3 [BAND] 67233009 -> 301345002 votes {'CONCEPT_LESS': 1, '301345002': 2}: incorrect -> correct
    - LIPITOR.806#0 [BAND] 771083005 -> 15749341000119107 votes {'15749341000119107': 2, '76948002': 1}: incorrect -> incorrect
    - LIPITOR.839#6 [BAND] 82991003 -> 68962001 votes {'68962001': 2}: correct -> incorrect
    - LIPITOR.853#4 [BAND] 282145008 -> 282144007 votes {'282144007': 2, '282145008': 1}: unmatched -> unmatched
    - LIPITOR.935#9 [ACCEPT] 249489001 -> 225589000 votes {'249489001': 1, '225589000': 2}: unmatched -> unmatched
- rerun-cadec-d2: by lane {'BAND': {'unanimous': 102, 'single_sample': 8, 'tie': 19, 'not_resampled': 9, 'changed': 26, 'split': 21}, 'ACCEPT': {'unanimous': 42, 'not_resampled': 3, 'tie': 2, 'split': 4}, 'REJECT': {'split': 1, 'changed': 1}}; changed 27, correct destroyed 5, gained 4, net -1; not_resampled had been {'unmatched': 9, 'incorrect': 1, 'correct': 2}
    - ARTHROTEC.78#0 [BAND] 21522001 -> 76948002 votes {'76948002': 2, '21522001': 1}: unmatched -> unmatched
    - LIPITOR.108#2 [BAND] 248277009 -> 248276000 votes {'248276000': 3}: correct -> incorrect
    - LIPITOR.159#7 [BAND] 82272006 -> 271584002 votes {'271584002': 2, '82272006': 1}: unmatched -> unmatched
    - LIPITOR.231#3 [BAND] 281016006 -> 386807006 votes {'386807006': 2}: unmatched -> unmatched
    - LIPITOR.231#4 [BAND] 282199003 -> 161898004 votes {'161898004': 2, '282199003': 1}: unmatched -> unmatched
    - LIPITOR.24#0 [BAND] 76948002 -> 68962001 votes {'68962001': 3}: correct -> incorrect
    - LIPITOR.24#3 [BAND] 262966007 -> 26544005 votes {'26544005': 2, '262966007': 1}: incorrect -> incorrect
    - LIPITOR.380#2 [REJECT] 1348356003 -> 202379000 votes {'202379000': 2, '1348356003': 1}: unmatched -> unmatched
    - LIPITOR.445#2 [BAND] 56317004 -> 278040002 votes {'278040002': 3}: incorrect -> correct
    - LIPITOR.445#4 [BAND] 271789005 -> 404640003 votes {'404640003': 2}: incorrect -> correct
    - LIPITOR.460#9 [BAND] 86597007 -> 26628009 votes {'26628009': 2, '247640008': 1}: incorrect -> incorrect
    - LIPITOR.48#4 [BAND] 90673000 -> 57143002 votes {'57143002': 2, '90673000': 1}: unmatched -> unmatched
    - LIPITOR.48#5 [BAND] 301823007 -> 1264062004 votes {'1264062004': 2, '90673000': 1}: incorrect -> incorrect
    - LIPITOR.48#6 [BAND] 80313002 -> 249390006 votes {'249390006': 2, '80313002': 1}: correct -> incorrect
    - LIPITOR.53#1 [BAND] 82423001 -> 10601006 votes {'10601006': 2, '82423001': 1}: unmatched -> unmatched
    - LIPITOR.53#2 [BAND] 65124004 -> 299322007 votes {'299322007': 3}: unmatched -> unmatched
    - LIPITOR.54#1 [BAND] 55300003 -> 203095000 votes {'203095000': 3}: correct -> incorrect
    - LIPITOR.739#1 [BAND] 271327008 -> 82423001 votes {'82423001': 2}: unmatched -> unmatched
    - LIPITOR.761#3 [BAND] CONCEPT_LESS -> 301345002 votes {'301345002': 2, 'CONCEPT_LESS': 1}: abstained -> correct
    - LIPITOR.761#5 [BAND] 225723003 -> CONCEPT_LESS votes {'CONCEPT_LESS': 2, '270903007': 1}: incorrect -> abstained
    - LIPITOR.78#0 [BAND] 276444007 -> 418290006 votes {'418290006': 3}: unmatched -> unmatched
    - LIPITOR.8#1 [BAND] 49218002 -> 78514002 votes {'78514002': 2, '49218002': 1}: correct -> correct
    - LIPITOR.8#5 [BAND] 1144586002 -> 22253000 votes {'22253000': 2}: incorrect -> correct
    - LIPITOR.839#0 [BAND] 25064002 -> 162308004 votes {'162308004': 2, '25064002': 1}: correct -> incorrect
    - LIPITOR.839#7 [BAND] 22253000 -> 367391008 votes {'367391008': 2, '22253000': 1}: unmatched -> unmatched
    - LIPITOR.853#4 [BAND] 282145008 -> 282144007 votes {'282145008': 1, '282144007': 2}: unmatched -> unmatched
    - LIPITOR.921#1 [BAND] 395080004 -> 367391008 votes {'367391008': 2, '395080004': 1}: incorrect -> incorrect

## Rung 4 (blind, shipped) vs the menu arms
| draw | arm | judged | pass | fail | P(correct|pass) | P(correct|fail) | separation | span_bad | code_bad | menu shown | not-on-list | best correct | best = pick |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| rerun-cadec-d0 | base | 223 | 136 | 87 | 0.463 | 0.276 | 1.68x | 48 | 80 | 0 | 0 | 0 | 0 |
| rerun-cadec-d0 | judgemenu | 230 | 136 | 94 | 0.544 | 0.149 | 3.65x | 11 | 93 | 230 | 70 | 78 | 145 |
| rerun-cadec-d0 | judgeshuffle | 230 | 143 | 87 | 0.524 | 0.149 | 3.51x | 14 | 85 | 230 | 66 | 77 | 150 |
| rerun-cadec-d1 | base | 226 | 137 | 89 | 0.445 | 0.270 | 1.65x | 48 | 81 | 0 | 0 | 0 | 0 |
| rerun-cadec-d1 | judgemenu | 230 | 142 | 88 | 0.528 | 0.125 | 4.23x | 12 | 87 | 230 | 69 | 77 | 147 |
| rerun-cadec-d1 | judgeshuffle | 230 | 144 | 86 | 0.521 | 0.128 | 4.07x | 14 | 84 | 230 | 66 | 77 | 153 |
| rerun-cadec-d2 | base | 231 | 142 | 89 | 0.493 | 0.292 | 1.69x | 48 | 80 | 0 | 0 | 0 | 0 |
| rerun-cadec-d2 | judgemenu | 238 | 146 | 92 | 0.562 | 0.163 | 3.44x | 8 | 91 | 238 | 65 | 85 | 152 |
| rerun-cadec-d2 | judgeshuffle | 238 | 148 | 90 | 0.561 | 0.156 | 3.61x | 10 | 89 | 238 | 65 | 85 | 153 |

## The shipped result and the policy arms (final state rows)
| draw | arm | n | ships | coverage | accuracy | **yield** | errors | err/100 | to a person | stack F1 exact | overlap |
|---|---|---|---|---|---|---|---|---|---|---|---|
| rerun-cadec-d0 | base | 230 | 53 | 0.230 | 0.736 | **0.170** | 14 | 6.1 | 177 | 0.176 | 0.172 |
| rerun-cadec-d0 | judgemenu | 230 | 53 | 0.230 | 0.736 | **0.170** | 14 | 6.1 | 177 | 0.176 | 0.172 |
| rerun-cadec-d0 | judgeshuffle | 230 | 53 | 0.230 | 0.736 | **0.170** | 14 | 6.1 | 177 | 0.176 | 0.172 |
| rerun-cadec-d0 | lexarm | 230 | 91 | 0.396 | 0.582 | **0.230** | 38 | 16.5 | 139 | 0.239 | 0.262 |
| rerun-cadec-d0 | spine | 230 | 53 | 0.230 | 0.755 | **0.174** | 13 | 5.7 | 177 | 0.181 | 0.181 |
| rerun-cadec-d1 | base | 230 | 53 | 0.230 | 0.755 | **0.174** | 13 | 5.7 | 177 | 0.181 | 0.176 |
| rerun-cadec-d1 | judgemenu | 230 | 53 | 0.230 | 0.755 | **0.174** | 13 | 5.7 | 177 | 0.181 | 0.176 |
| rerun-cadec-d1 | judgeshuffle | 230 | 53 | 0.230 | 0.755 | **0.174** | 13 | 5.7 | 177 | 0.181 | 0.176 |
| rerun-cadec-d1 | lexarm | 230 | 91 | 0.396 | 0.582 | **0.230** | 38 | 16.5 | 139 | 0.239 | 0.262 |
| rerun-cadec-d1 | spine | 230 | 53 | 0.230 | 0.755 | **0.174** | 13 | 5.7 | 177 | 0.181 | 0.181 |
| rerun-cadec-d2 | base | 238 | 51 | 0.214 | 0.824 | **0.176** | 9 | 3.8 | 187 | 0.186 | 0.186 |
| rerun-cadec-d2 | judgemenu | 238 | 51 | 0.214 | 0.824 | **0.176** | 9 | 3.8 | 187 | 0.186 | 0.186 |
| rerun-cadec-d2 | judgeshuffle | 238 | 51 | 0.214 | 0.824 | **0.176** | 9 | 3.8 | 187 | 0.186 | 0.186 |
| rerun-cadec-d2 | lexarm | 238 | 90 | 0.378 | 0.656 | **0.248** | 31 | 13.0 | 148 | 0.261 | 0.283 |
| rerun-cadec-d2 | spine | 238 | 51 | 0.214 | 0.824 | **0.176** | 9 | 3.8 | 187 | 0.186 | 0.186 |

## Every rung's verdict as a shipping rule (one denominator: all records; F1 span-exact over what ships)
| draw | ship only when… | reads rung | ships | right code, exact span | exact span, wrong code | right code, boundary off | neither | to a person | of them right | accuracy | **yield** | F1 | extra tokens |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| rerun-cadec-d0 | everything | 0 | 230 | 87 | 28 | 21 | 94 | 0 | 0 | 0.378 | **0.378** | 0.393 | 0 |
| rerun-cadec-d0 | everything_after_r3 | 3 | 230 | 88 | 28 | 23 | 91 | 0 | 0 | 0.383 | **0.383** | 0.397 | 410,638 |
| rerun-cadec-d0 | accept | 4 | 53 | 39 | 2 | 0 | 12 | 177 | 49 | 0.736 | **0.170** | 0.283 | 0 |
| rerun-cadec-d0 | accept_contained | 4 | 91 | 53 | 5 | 8 | 25 | 139 | 35 | 0.582 | **0.230** | 0.340 | 0 |
| rerun-cadec-d0 | r3_unanimous | 3 | 108 | 51 | 13 | 15 | 29 | 122 | 37 | 0.472 | **0.222** | 0.315 | 410,638 |
| rerun-cadec-d0 | r3_two_agree | 3 | 185 | 77 | 22 | 21 | 65 | 45 | 11 | 0.416 | **0.335** | 0.387 | 410,638 |
| rerun-cadec-d0 | r4_blind_pass | 4 | 136 | 63 | 16 | 15 | 42 | 94 | 25 | 0.463 | **0.274** | 0.357 | 84,036 |
| rerun-cadec-d0 | r4_menu_pass | 4 | 136 | 74 | 9 | 14 | 39 | 94 | 14 | 0.544 | **0.322** | 0.420 | 84,036 |
| rerun-cadec-d1 | everything | 0 | 230 | 87 | 28 | 21 | 94 | 0 | 0 | 0.378 | **0.378** | 0.393 | 0 |
| rerun-cadec-d1 | everything_after_r3 | 3 | 230 | 86 | 30 | 24 | 90 | 0 | 0 | 0.374 | **0.374** | 0.388 | 432,341 |
| rerun-cadec-d1 | accept | 4 | 53 | 40 | 1 | 0 | 12 | 177 | 46 | 0.755 | **0.174** | 0.290 | 0 |
| rerun-cadec-d1 | accept_contained | 4 | 91 | 53 | 5 | 8 | 25 | 139 | 33 | 0.582 | **0.230** | 0.340 | 0 |
| rerun-cadec-d1 | r3_unanimous | 3 | 116 | 57 | 10 | 15 | 34 | 114 | 29 | 0.491 | **0.248** | 0.342 | 432,341 |
| rerun-cadec-d1 | r3_two_agree | 3 | 190 | 78 | 27 | 22 | 63 | 40 | 8 | 0.411 | **0.339** | 0.386 | 432,341 |
| rerun-cadec-d1 | r4_blind_pass | 4 | 137 | 61 | 19 | 16 | 41 | 93 | 25 | 0.445 | **0.265** | 0.345 | 84,031 |
| rerun-cadec-d1 | r4_menu_pass | 4 | 142 | 75 | 14 | 15 | 38 | 88 | 11 | 0.528 | **0.326** | 0.419 | 84,031 |
| rerun-cadec-d2 | everything | 0 | 238 | 98 | 30 | 20 | 90 | 0 | 0 | 0.412 | **0.412** | 0.434 | 0 |
| rerun-cadec-d2 | everything_after_r3 | 3 | 238 | 97 | 31 | 23 | 87 | 0 | 0 | 0.408 | **0.408** | 0.429 | 431,518 |
| rerun-cadec-d2 | accept | 4 | 51 | 42 | 2 | 1 | 6 | 187 | 55 | 0.824 | **0.176** | 0.304 | 0 |
| rerun-cadec-d2 | accept_contained | 4 | 90 | 59 | 5 | 8 | 18 | 148 | 38 | 0.656 | **0.248** | 0.378 | 0 |
| rerun-cadec-d2 | r3_unanimous | 3 | 123 | 64 | 14 | 14 | 31 | 115 | 33 | 0.520 | **0.269** | 0.378 | 431,518 |
| rerun-cadec-d2 | r3_two_agree | 3 | 184 | 83 | 24 | 20 | 57 | 54 | 14 | 0.451 | **0.349** | 0.416 | 431,518 |
| rerun-cadec-d2 | r4_blind_pass | 4 | 142 | 70 | 21 | 14 | 37 | 96 | 27 | 0.493 | **0.294** | 0.389 | 88,240 |
| rerun-cadec-d2 | r4_menu_pass | 4 | 146 | 82 | 16 | 15 | 33 | 92 | 15 | 0.562 | **0.345** | 0.451 | 88,240 |
| mean of 3 | everything | 0 | 232.7 | | | | | 0.0 | 0.0 | 0.389 | **0.389** | 0.406 | 0 |
| mean of 3 | everything_after_r3 | 3 | 232.7 | | | | | 0.0 | 0.0 | 0.388 | **0.388** | 0.405 | 424,832 |
| mean of 3 | accept | 4 | 52.3 | | | | | 180.3 | 50.0 | 0.771 | **0.173** | 0.292 | 0 |
| mean of 3 | accept_contained | 4 | 90.7 | | | | | 142.0 | 35.3 | 0.607 | **0.236** | 0.353 | 0 |
| mean of 3 | r3_unanimous | 3 | 115.7 | | | | | 117.0 | 33.0 | 0.495 | **0.246** | 0.345 | 424,832 |
| mean of 3 | r3_two_agree | 3 | 186.3 | | | | | 46.3 | 11.0 | 0.426 | **0.341** | 0.396 | 424,832 |
| mean of 3 | r4_blind_pass | 4 | 138.3 | | | | | 94.3 | 25.7 | 0.467 | **0.278** | 0.363 | 85,436 |
| mean of 3 | r4_menu_pass | 4 | 141.3 | | | | | 91.3 | 13.3 | 0.545 | **0.331** | 0.430 | 85,436 |

## What `contained` admits that `exact` leaves in BAND (item 8)
- rerun-cadec-d0: moved 38; by direction {'span_in_term': {'n': 12, 'correct': 4, 'on_no_gold': 4}, 'term_in_span': {'n': 26, 'correct': 11, 'on_no_gold': 4}}
    - ARTHROTEC.78#1 "stool" -> 267055007 |black stool| via span_in_term "Black stool" extra ['black']: unmatched / incorrect
    - ARTHROTEC.78#2 "blood in my stool" -> 405729008 |blood in stool| via term_in_span "Blood in stool" extra ['my']: correct / correct
    - ARTHROTEC.8#0 "upset my stomach" -> 162059005 |upset stomach| via term_in_span "Upset stomach" extra ['my']: unmatched / incorrect
    - LIPITOR.159#2 "neck" -> 81680005 |neck pain| via span_in_term "Neck pain" extra ['pain']: unmatched / unmatched
    - LIPITOR.159#9 "constipation problems" -> 14760008 |constipation| via term_in_span "Constipation" extra ['problems']: unmatched / correct
    - LIPITOR.380#1 "EXTREME AND EXCRUCIATING MUSCLE PAIN IN NECK" -> 81680005 |neck pain| via term_in_span "Neck pain" extra ['and', 'excruciating', 'extreme', 'in', 'muscle']: unmatched / correct
    - LIPITOR.401#4 "loss of short term memory" -> 247592009 |short term memory loss| via term_in_span "Short-term memory loss" extra ['of']: correct / correct
    - LIPITOR.445#2 "hair loss" -> 278040002 |loss of hair| via span_in_term "Loss of hair" extra ['of']: correct / correct
    - LIPITOR.445#3 "pale/yellow complexion" -> 398979000 |pale complexion| via term_in_span "Pale complexion (finding)" extra ['yellow']: correct / correct
    - LIPITOR.460#4 "wild mood swings" -> 18963009 |mood swings| via term_in_span "Mood swings" extra ['wild']: correct / correct
    - LIPITOR.460#7 "extreme fatigue" -> 84229001 |fatigue| via term_in_span "Fatigue" extra ['extreme']: incorrect / incorrect
    - LIPITOR.48#2 "Terrible muscle pain" -> 68962001 |muscle pain| via term_in_span "Muscle pain" extra ['terrible']: unmatched / correct
    - LIPITOR.48#9 "weak" -> 13791008 |weakness| via span_in_term "Feeling weak" extra ['feeling']: unmatched / correct
    - LIPITOR.48#10 "difficulty walking and driving" -> 719232003 |difficulty walking| via term_in_span "Difficulty walking (finding)" extra ['and', 'driving']: unmatched / incorrect
    - LIPITOR.48#11 "dying" -> 225875000 |thoughts about dying| via span_in_term "Thoughts about dying" extra ['about', 'thoughts']: unmatched / unmatched
    - LIPITOR.53#4 "painful step" -> 22253000 |painful| via term_in_span "Painful" extra ['step']: unmatched / unmatched
    - LIPITOR.54#4 "Severe muscle pain" -> 68962001 |muscle pain| via term_in_span "Muscle pain" extra ['severe']: correct / correct
    - LIPITOR.54#7 "severe back spasm/cramp" -> 45352006 |muscle spasm| via term_in_span "Spasm" extra ['back', 'cramp', 'severe']: unmatched / incorrect
    - LIPITOR.70#4 "unknown skin condition on hands" -> 95320005 |skin condition| via term_in_span "Skin condition" extra ['hands', 'on', 'unknown']: unmatched / correct
    - LIPITOR.729#2 "occasional dizziness" -> 404640003 |dizziness| via term_in_span "Dizziness (finding)" extra ['occasional']: correct / correct
    - LIPITOR.739#0 "Chronic pain in all my joints" -> 82423001 |chronic pain| via term_in_span "Chronic pain" extra ['all', 'in', 'joints', 'my']: unmatched / incorrect
    - LIPITOR.757#6 "very very painful" -> 22253000 |pain| via term_in_span "Painful" extra ['very']: unmatched / incorrect
    - LIPITOR.757#11 "concentration" -> 26329005 |poor concentration| via span_in_term "Poor concentration" extra ['poor']: unmatched / correct
    - LIPITOR.757#14 "cholesterol" -> 365793008 |cholesterol level| via span_in_term "Cholesterol level" extra ['level']: unmatched / unmatched
    - LIPITOR.757#15 "concerned" -> 162561006 |concerned about appearance| via span_in_term "Concerned about appearance" extra ['about', 'appearance']: unmatched / unmatched
    - LIPITOR.762#0 "Nagging muscle pain between blades" -> 68962001 |muscle pain| via term_in_span "Muscle pain" extra ['between', 'blades', 'nagging']: unmatched / unmatched
    - LIPITOR.762#2 "persistent fatigue" -> 84229001 |fatigue| via term_in_span "Fatigue" extra ['persistent']: correct / correct
    - LIPITOR.762#3 "moderate insomnia" -> 193462001 |insomnia| via term_in_span "Insomnia" extra ['moderate']: correct / correct
    - LIPITOR.8#1 "hip thigh pain" -> 49218002 |hip pain| via term_in_span "Hip pain" extra ['thigh']: correct / correct
    - LIPITOR.839#5 "severe fatigue" -> 84229001 |fatigue| via term_in_span "Fatigue" extra ['severe']: correct / correct
    - LIPITOR.839#6 "aches and pains" -> 82991003 |generalized aches and pains| via span_in_term "Generalised aches and pains" extra ['generalised']: correct / correct
    - LIPITOR.853#6 "excessive sleep reqmt" -> 77692006 |excessive sleep| via term_in_span "Excessive sleep" extra ['reqmt']: unmatched / correct
    - LIPITOR.853#7 "hair loss" -> 278040002 |loss of hair| via span_in_term "Loss of hair" extra ['of']: correct / correct
    - LIPITOR.882#3 "ears ringing" -> 60862001 |ringing in ears| via span_in_term "Ringing in ears" extra ['in']: incorrect / incorrect
    - LIPITOR.935#0 "stiffness in whole body" -> 271587009 |stiffness| via term_in_span "Stiffness" extra ['body', 'in', 'whole']: correct / correct
    - LIPITOR.935#3 "loss of weight" -> 262285001 |weight loss| via term_in_span "Weight loss" extra ['of']: unmatched / unmatched
    - LIPITOR.935#13 "painful death" -> 22253000 |painful| via term_in_span "Painful" extra ['death']: unmatched / unmatched
    - LIPITOR.935#14 "ALS" -> 86044005 |amyotrophic lateral sclerosis| via span_in_term "ALS - Amyotrophic lateral sclerosis" extra ['amyotrophic', 'lateral', 'sclerosis']: correct / correct
- rerun-cadec-d1: moved 38; by direction {'span_in_term': {'n': 12, 'correct': 4, 'on_no_gold': 4}, 'term_in_span': {'n': 26, 'correct': 11, 'on_no_gold': 4}}
    - ARTHROTEC.78#1 "stool" -> 267055007 |black stool| via span_in_term "Black stool" extra ['black']: unmatched / incorrect
    - ARTHROTEC.78#2 "blood in my stool" -> 405729008 |blood in stool| via term_in_span "Blood in stool" extra ['my']: correct / correct
    - ARTHROTEC.8#0 "upset my stomach" -> 162059005 |upset stomach| via term_in_span "Upset stomach" extra ['my']: unmatched / incorrect
    - LIPITOR.159#2 "neck" -> 81680005 |neck pain| via span_in_term "Neck pain" extra ['pain']: unmatched / unmatched
    - LIPITOR.159#9 "constipation problems" -> 14760008 |constipation| via term_in_span "Constipation" extra ['problems']: unmatched / correct
    - LIPITOR.380#1 "EXTREME AND EXCRUCIATING MUSCLE PAIN IN NECK" -> 81680005 |neck pain| via term_in_span "Neck pain" extra ['and', 'excruciating', 'extreme', 'in', 'muscle']: unmatched / correct
    - LIPITOR.401#4 "loss of short term memory" -> 247592009 |short term memory loss| via term_in_span "Short-term memory loss" extra ['of']: correct / correct
    - LIPITOR.445#2 "hair loss" -> 278040002 |loss of hair| via span_in_term "Loss of hair" extra ['of']: correct / correct
    - LIPITOR.445#3 "pale/yellow complexion" -> 398979000 |pale complexion| via term_in_span "Pale complexion (finding)" extra ['yellow']: correct / correct
    - LIPITOR.460#4 "wild mood swings" -> 18963009 |mood swings| via term_in_span "Mood swings" extra ['wild']: correct / correct
    - LIPITOR.460#7 "extreme fatigue" -> 84229001 |fatigue| via term_in_span "Fatigue" extra ['extreme']: incorrect / incorrect
    - LIPITOR.48#2 "Terrible muscle pain" -> 68962001 |muscle pain| via term_in_span "Muscle pain" extra ['terrible']: unmatched / correct
    - LIPITOR.48#9 "weak" -> 13791008 |weakness| via span_in_term "Feeling weak" extra ['feeling']: unmatched / correct
    - LIPITOR.48#10 "difficulty walking and driving" -> 719232003 |difficulty walking| via term_in_span "Difficulty walking (finding)" extra ['and', 'driving']: unmatched / incorrect
    - LIPITOR.48#11 "dying" -> 225875000 |thoughts about dying| via span_in_term "Thoughts about dying" extra ['about', 'thoughts']: unmatched / unmatched
    - LIPITOR.53#4 "painful step" -> 22253000 |painful| via term_in_span "Painful" extra ['step']: unmatched / unmatched
    - LIPITOR.54#4 "Severe muscle pain" -> 68962001 |muscle pain| via term_in_span "Muscle pain" extra ['severe']: correct / correct
    - LIPITOR.54#7 "severe back spasm/cramp" -> 45352006 |muscle spasm| via term_in_span "Spasm" extra ['back', 'cramp', 'severe']: unmatched / incorrect
    - LIPITOR.70#4 "unknown skin condition on hands" -> 95320005 |skin condition| via term_in_span "Skin condition" extra ['hands', 'on', 'unknown']: unmatched / correct
    - LIPITOR.729#2 "occasional dizziness" -> 404640003 |dizziness| via term_in_span "Dizziness (finding)" extra ['occasional']: correct / correct
    - LIPITOR.739#0 "Chronic pain in all my joints" -> 82423001 |chronic pain| via term_in_span "Chronic pain" extra ['all', 'in', 'joints', 'my']: unmatched / incorrect
    - LIPITOR.757#6 "very very painful" -> 22253000 |pain| via term_in_span "Painful" extra ['very']: unmatched / incorrect
    - LIPITOR.757#11 "concentration" -> 26329005 |poor concentration| via span_in_term "Poor concentration" extra ['poor']: unmatched / correct
    - LIPITOR.757#14 "cholesterol" -> 365793008 |cholesterol level| via span_in_term "Cholesterol level" extra ['level']: unmatched / unmatched
    - LIPITOR.757#15 "concerned" -> 162561006 |concerned about appearance| via span_in_term "Concerned about appearance" extra ['about', 'appearance']: unmatched / unmatched
    - LIPITOR.762#0 "Nagging muscle pain between blades" -> 68962001 |muscle pain| via term_in_span "Muscle pain" extra ['between', 'blades', 'nagging']: unmatched / unmatched
    - LIPITOR.762#2 "persistent fatigue" -> 84229001 |fatigue| via term_in_span "Fatigue" extra ['persistent']: correct / correct
    - LIPITOR.762#3 "moderate insomnia" -> 193462001 |insomnia| via term_in_span "Insomnia" extra ['moderate']: correct / correct
    - LIPITOR.8#1 "hip thigh pain" -> 49218002 |hip pain| via term_in_span "Hip pain" extra ['thigh']: correct / correct
    - LIPITOR.839#5 "severe fatigue" -> 84229001 |fatigue| via term_in_span "Fatigue" extra ['severe']: correct / correct
    - LIPITOR.839#6 "aches and pains" -> 82991003 |generalized aches and pains| via span_in_term "Generalised aches and pains" extra ['generalised']: correct / correct
    - LIPITOR.853#6 "excessive sleep reqmt" -> 77692006 |excessive sleep| via term_in_span "Excessive sleep" extra ['reqmt']: unmatched / correct
    - LIPITOR.853#7 "hair loss" -> 278040002 |loss of hair| via span_in_term "Loss of hair" extra ['of']: correct / correct
    - LIPITOR.882#3 "ears ringing" -> 60862001 |ringing in ears| via span_in_term "Ringing in ears" extra ['in']: incorrect / incorrect
    - LIPITOR.935#0 "stiffness in whole body" -> 271587009 |stiffness| via term_in_span "Stiffness" extra ['body', 'in', 'whole']: correct / correct
    - LIPITOR.935#3 "loss of weight" -> 262285001 |weight loss| via term_in_span "Weight loss" extra ['of']: unmatched / unmatched
    - LIPITOR.935#13 "painful death" -> 22253000 |painful| via term_in_span "Painful" extra ['death']: unmatched / unmatched
    - LIPITOR.935#14 "ALS" -> 86044005 |amyotrophic lateral sclerosis| via span_in_term "ALS - Amyotrophic lateral sclerosis" extra ['amyotrophic', 'lateral', 'sclerosis']: correct / correct
- rerun-cadec-d2: moved 39; by direction {'term_in_span': {'n': 27, 'correct': 13, 'on_no_gold': 4}, 'span_in_term': {'n': 12, 'correct': 3, 'on_no_gold': 2}}
    - ARTHROTEC.57#1 "spotting problems" -> 9126005 |spotting| via term_in_span "Spotting" extra ['problems']: correct / correct
    - ARTHROTEC.78#1 "stool" -> 267055007 |black stool| via span_in_term "Black stool" extra ['black']: unmatched / incorrect
    - ARTHROTEC.78#2 "blood in my stool" -> 405729008 |blood in stool| via term_in_span "Blood in stool" extra ['my']: correct / correct
    - ARTHROTEC.8#0 "upset my stomach" -> 162059005 |upset stomach| via term_in_span "Upset stomach" extra ['my']: unmatched / incorrect
    - LIPITOR.159#7 "hands feel cold" -> 82272006 |cold| via term_in_span "Cold" extra ['feel', 'hands']: unmatched / unmatched
    - LIPITOR.159#9 "constipation problems" -> 14760008 |constipation| via term_in_span "Constipation" extra ['problems']: unmatched / correct
    - LIPITOR.171#10 "pain" -> 429038000 |pain provoked by sleeping| via span_in_term "Pain onset during sleep (finding)" extra ['during', 'onset', 'sleep']: unmatched / incorrect
    - LIPITOR.24#0 "severe muscle pain in hips" -> 76948002 |severe pain| via term_in_span "Severe pain" extra ['hips', 'in', 'muscle']: correct / correct
    - LIPITOR.24#1 "severe muscle pain in legs" -> 68962001 |muscle pain| via term_in_span "Muscle pain" extra ['in', 'legs', 'severe']: incorrect / incorrect
    - LIPITOR.380#1 "EXTREME AND EXCRUCIATING MUSCLE PAIN IN NECK" -> 81680005 |neck pain| via term_in_span "Neck pain" extra ['and', 'excruciating', 'extreme', 'in', 'muscle']: unmatched / correct
    - LIPITOR.401#4 "loss of short term memory" -> 247592009 |short term memory loss| via term_in_span "Short-term memory loss" extra ['of']: correct / correct
    - LIPITOR.445#2 "hair loss" -> 56317004 |hair loss disorder| via span_in_term "Hair loss disorder" extra ['disorder']: incorrect / incorrect
    - LIPITOR.445#3 "pale/yellow complexion" -> 398979000 |pale complexion| via term_in_span "Pale complexion (finding)" extra ['yellow']: correct / correct
    - LIPITOR.460#4 "wild mood swings" -> 18963009 |mood swings| via term_in_span "Mood swings" extra ['wild']: correct / correct
    - LIPITOR.48#2 "Terrible muscle pain" -> 68962001 |muscle pain| via term_in_span "Muscle pain" extra ['terrible']: unmatched / correct
    - LIPITOR.48#8 "weak" -> 13791008 |weakness| via span_in_term "Feeling weak" extra ['feeling']: unmatched / correct
    - LIPITOR.48#9 "difficulty walking and driving" -> 719232003 |difficulty walking| via term_in_span "Difficulty walking (finding)" extra ['and', 'driving']: unmatched / incorrect
    - LIPITOR.48#11 "dying" -> 225875000 |thoughts about dying| via span_in_term "Thoughts about dying" extra ['about', 'thoughts']: unmatched / unmatched
    - LIPITOR.54#4 "Severe muscle pain" -> 68962001 |muscle pain| via term_in_span "Muscle pain" extra ['severe']: correct / correct
    - LIPITOR.70#4 "unknown skin condition on hands" -> 95320005 |skin condition| via term_in_span "Skin condition" extra ['hands', 'on', 'unknown']: unmatched / correct
    - LIPITOR.729#2 "occasional dizziness" -> 404640003 |dizziness| via term_in_span "Dizziness (finding)" extra ['occasional']: correct / correct
    - LIPITOR.739#0 "Chronic pain in all my joints" -> 82423001 |chronic pain| via term_in_span "Chronic pain" extra ['all', 'in', 'joints', 'my']: unmatched / incorrect
    - LIPITOR.757#6 "very very painful" -> 22253000 |pain| via term_in_span "Painful" extra ['very']: unmatched / incorrect
    - LIPITOR.757#11 "concentration" -> 26329005 |poor concentration| via span_in_term "Poor concentration" extra ['poor']: unmatched / correct
    - LIPITOR.761#2 "weakness" -> 249938007 |weakness of back| via span_in_term "Weakness of back" extra ['back', 'of']: unmatched / unmatched
    - LIPITOR.762#0 "Nagging muscle pain between blades" -> 68962001 |muscle pain| via term_in_span "Muscle pain" extra ['between', 'blades', 'nagging']: unmatched / unmatched
    - LIPITOR.762#2 "persistent fatigue" -> 84229001 |fatigue| via term_in_span "Fatigue" extra ['persistent']: correct / correct
    - LIPITOR.762#3 "moderate insomnia" -> 193462001 |insomnia| via term_in_span "Insomnia" extra ['moderate']: correct / correct
    - LIPITOR.8#1 "hip thigh pain" -> 49218002 |hip pain| via term_in_span "Hip pain" extra ['thigh']: correct / correct
    - LIPITOR.8#5 "pain" -> 1144586002 |increased pain| via span_in_term "Increased pain" extra ['increased']: incorrect / incorrect
    - LIPITOR.839#5 "severe fatigue" -> 84229001 |fatigue| via term_in_span "Fatigue" extra ['severe']: correct / correct
    - LIPITOR.839#6 "aches and pains" -> 82991003 |generalized aches and pains| via span_in_term "Generalised aches and pains" extra ['generalised']: correct / correct
    - LIPITOR.853#6 "excessive sleep reqmt" -> 77692006 |excessive sleep| via term_in_span "Excessive sleep" extra ['reqmt']: unmatched / correct
    - LIPITOR.853#7 "hair loss" -> 278040002 |loss of hair| via span_in_term "Loss of hair" extra ['of']: correct / correct
    - LIPITOR.882#3 "ears ringing" -> 60862001 |ringing in ears| via span_in_term "Ringing in ears" extra ['in']: incorrect / incorrect
    - LIPITOR.935#0 "stiffness in whole body" -> 271587009 |stiffness| via term_in_span "Stiffness" extra ['body', 'in', 'whole']: correct / correct
    - LIPITOR.935#3 "loss of weight" -> 262285001 |weight loss| via term_in_span "Weight loss" extra ['of']: unmatched / unmatched
    - LIPITOR.935#13 "painful death" -> 22253000 |painful| via term_in_span "Painful" extra ['death']: unmatched / unmatched
    - LIPITOR.935#14 "ALS" -> 86044005 |amyotrophic lateral sclerosis| via span_in_term "ALS - Amyotrophic lateral sclerosis" extra ['amyotrophic', 'lateral', 'sclerosis']: correct / correct

## Cost per rung, base draws (tokens / calls / p95 s / human minutes / records routed)
- rerun-cadec-d0: r0: 161,768 / 94 / 78.79 / 0.0 / 0; r1: 0 / 0 / 0.0 / 0.0 / 0; r2: 1,259 / 2 / 6.07 / 0.0 / 0; r3: 410,638 / 266 / 117.9 / 0.0 / 0; r4: 84,036 / 230 / 1.46 / 0.0 / 0; r5: 0 / 0 / 0.0 / 0.0 / 0; r6: 0 / 0 / 0.0 / 354.0 / 177
- rerun-cadec-d1: r0: 161,768 / 94 / 83.3 / 0.0 / 0; r1: 0 / 0 / 0.0 / 0.0 / 0; r2: 1,259 / 2 / 6.06 / 0.0 / 0; r3: 432,341 / 274 / 136.87 / 0.0 / 0; r4: 84,031 / 230 / 1.44 / 0.0 / 0; r5: 0 / 0 / 0.0 / 0.0 / 0; r6: 0 / 0 / 0.0 / 354.0 / 177
- rerun-cadec-d2: r0: 155,159 / 94 / 59.21 / 0.0 / 0; r1: 0 / 0 / 0.0 / 0.0 / 0; r2: 1,631 / 3 / 5.84 / 0.0 / 0; r3: 431,518 / 273 / 144.24 / 0.0 / 0; r4: 88,240 / 238 / 1.45 / 0.0 / 0; r5: 0 / 0 / 0.0 / 0.0 / 0; r6: 0 / 0 / 0.0 / 374.0 / 187

## Three-draw consensus (rung 0 output, mentions grouped by span overlap)
- byte-identical draws: False
- mentions 233: all agree 164 (70.39%), same span diff code 22, same code diff span 1, both differ 10, found by two 15, found by one 21
- same span all draws 79.83%; same code where all found 83.76%

## Gold lane occupancy (rung 1 replayed over the split's scorable reaction gold, no model; manifest lexical_mode = exact)
| lexical_mode | n | coded | concept-less (all BAND) | ACCEPT | BAND | REJECT |
|---|---|---|---|---|---|---|
| exact | 226 | 216 | 10 | 73 (32.3%) | 153 (67.7%) | 0 (0.0%) |
| contained | 226 | 216 | 10 | 104 (46.0%) | 122 (54.0%) | 0 (0.0%) |

## Provenance
- rerun-cadec-d0: cache `/Users/wejdanbagais/Documents/repo/reliability-ladder/.claude/worktrees/reliability-ladder-b2-menu-f77617/.llm_cache.rerun-cadec-d0`, git {'sha': 'f3ff539', 'branch': 'claude/plan-next-sessions-docs-17c0bc', 'dirty': False, 'dirty_files': 0}, 2026-09-03T07:47:05Z → 2026-09-03T08:44:45Z
- rerun-cadec-d1: cache `/Users/wejdanbagais/Documents/repo/reliability-ladder/.claude/worktrees/reliability-ladder-b2-menu-f77617/.llm_cache.rerun-cadec-d1`, git {'sha': '061c6c3', 'branch': 'claude/plan-next-sessions-docs-17c0bc', 'dirty': False, 'dirty_files': 0}, 2026-09-03T08:59:40Z → 2026-09-03T09:59:44Z
- rerun-cadec-d2: cache `/Users/wejdanbagais/Documents/repo/reliability-ladder/.claude/worktrees/reliability-ladder-b2-menu-f77617/.llm_cache.rerun-cadec-d2`, git {'sha': 'c488a46', 'branch': 'claude/plan-next-sessions-docs-17c0bc', 'dirty': False, 'dirty_files': 0}, 2026-09-03T10:14:51Z → 2026-09-03T11:13:00Z

#!/usr/bin/env python3
"""Turn a consolidated re-run (plan item 0b) into the numbers the article quotes.

    python scripts/rerun_analysis.py --manifest manifest.json \
        --runs out/rerun-cadec-d0 out/rerun-cadec-d1 out/rerun-cadec-d2 \
        --arms judgemenu judgeshuffle lexarm spine \
        --out out/rerun/cadec

Reads each run's per-rung record snapshots, state table, ledger, results and
aggregates (all written by ladder/run.py since 2026-09-03), scores them
against the manifest's corpus and exclusions, and writes <out>.json and
<out>.md. Every function doing arithmetic lives in ladder/analysis.py and
ladder/score.py, with tests; this file only loads and prints.

Arms are the same run id with a suffix (`<run>-<arm>`), produced on the same
cache by scripts/consolidated_rerun.sh, so their rung 0 is byte-identical to
the base's and only the arm's own rung differs.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ladder import analysis, clean as clean_mod, score  # noqa: E402
from ladder.ledger import Ledger  # noqa: E402
from ladder.manifest import load_manifest  # noqa: E402
from ladder.run import _corpus_for, _corpus_opts, _corpus_root, _vocab_for  # noqa: E402
from ladder.schema import REACTION, loads  # noqa: E402

RUNGS = (0, 1, 2, 3, 4, 5, 6)


def load_run(prefix: str) -> dict:
    p = Path(prefix)
    run = {"prefix": str(p), "records": {}, "sha256": {}}
    for n in RUNGS:
        f = p.with_name(f"{p.name}.r{n}.records.jsonl")
        if f.exists():
            run["records"][n] = loads(f.read_text(encoding="utf-8"))
            run["sha256"][n] = analysis.sha256_file(f)
    run["final"] = loads(p.with_name(f"{p.name}.records.jsonl").read_text(encoding="utf-8"))
    run["state"] = analysis.read_jsonl(p.with_name(f"{p.name}.state.jsonl"))
    run["ledger"] = Ledger.read(p.with_name(f"{p.name}.ledger.jsonl"))
    agg = p.with_name(f"{p.name}.aggregates.json")
    run["aggregates"] = json.loads(agg.read_text()) if agg.exists() else {}
    return run


def cost_by_rung(rows, n_records: int) -> dict:
    """The ledger's three currencies per rung, never fused."""
    lg = Ledger.__new__(Ledger)
    lg.rows = rows
    out = {}
    for rung, c in lg.cost_by_rung(n_records=n_records).items():
        out[str(rung)] = {
            "tokens": int(c["tokens_in"] + c["tokens_out"]),
            "api_calls": int(c["api_calls"]),
            "p95_s": round(c["p95_latency_s"], 2),
            "usd": round(c["usd"], 4),
            "human_minutes": round(c["human_minutes"], 1),
            "records_routed": int(sum(1 for r in rows if r.rung == rung and r.human_minutes)),
        }
    return out


def score_both(records, golds, exclude, vocab) -> dict:
    out = {}
    for sm in ("exact", "overlap"):
        s = score.score_run(records, golds, span_match=sm, exclude=exclude, vocab=vocab)
        out[sm] = {
            "n_pred": s["n_pred"], "n_gold": s["n_gold"],
            "precision": round(s["precision"], 4), "recall": round(s["recall"], 4),
            "f1": round(s["f1"], 4),
            "detection": {k: round(v, 4) if isinstance(v, float) else v
                          for k, v in s["detection"].items()},
            "coding": {k: round(v, 4) if isinstance(v, float) else v
                       for k, v in s["coding"].items()},
        }
    ci = score.bootstrap_ci(records, golds, span_match="exact", exclude=exclude, vocab=vocab)
    out["exact"]["f1_ci"] = [round(ci["f1"]["lo"], 4), round(ci["f1"]["hi"], 4)]
    return out


def analyse(man: dict, prefixes: list[str], arms: list[str], full_vocab: bool) -> dict:
    corpus = _corpus_for(man)
    docs = corpus.load_corpus(_corpus_root(man), **_corpus_opts(man))
    doc_ids = corpus.read_split(man["corpus"]["splits_dir"], "dev")
    exclude = clean_mod.exclusions_for(man)
    golds = [m for d in doc_ids for m in docs[d].mentions]
    gold_scored = [g for g in golds if g.record_id not in exclude
                   and g.entity_type == REACTION]
    vocab = _vocab_for(man)
    report: dict = {"manifest": man.get("task"), "corpus": man["corpus"]["name"],
                    "n_docs": len(doc_ids), "n_gold_scored": len(gold_scored),
                    "draws": {}, "arms": {}}
    draws = []
    for prefix in prefixes:
        run = load_run(prefix)
        draws.append(run)
        r0 = run["records"][0]
        d = {
            "sha256_r0": run["sha256"].get(0),
            "sha256_final": analysis.sha256_file(Path(prefix).with_name(Path(prefix).name + ".records.jsonl")),
            "llm_cache": run["aggregates"].get("llm_cache"),
            "git": run["aggregates"].get("git"),
            "started": run["aggregates"].get("started_utc"),
            "finished": run["aggregates"].get("finished_utc"),
            "spans_proposed": len(r0),
            "rung0": score_both(r0, golds, exclude, vocab),
            "budget": {sm: analysis.error_budget(r0, golds, span_match=sm, exclude=exclude,
                                                 vocab=vocab, full_vocabulary=full_vocab)
                       for sm in ("exact", "overlap")},
            "lanes": analysis.lanes(analysis.rows_at(run["state"], 1).values()),
            "outcomes_by_rung": {str(n): analysis.outcome_counts(run["state"], n)
                                 for n in RUNGS if n in run["records"]},
            "cost": cost_by_rung(run["ledger"], len(run["final"])),
            "aggregates": run["aggregates"].get("rungs", {}),
        }
        if 3 in run["records"]:
            before = {rid: row["outcome"]
                      for rid, row in analysis.rows_at(run["state"], 2).items()}
            d["r3"] = analysis.r3_crosstab(run["records"][3],
                                           analysis.rows_at(run["state"], 3).values(), before)
        if 4 in run["records"]:
            d["r4"] = analysis.judge_summary(run["records"][4],
                                             analysis.rows_at(run["state"], 4).values())
        d["final"] = analysis.policy_row(analysis.rows_at(run["state"], max(run["records"])).values())
        d["stack_f1"] = score_both(run["final"], golds, exclude, vocab)
        report["draws"][Path(prefix).name] = d
        for arm in arms:
            ap = f"{prefix}-{arm}"
            if not Path(ap).with_name(Path(ap).name + ".records.jsonl").exists():
                continue
            a = load_run(ap)
            entry = {
                "rung0_identical_to_base": a["sha256"].get(0) == run["sha256"].get(0),
                "final": analysis.policy_row(analysis.rows_at(a["state"], max(a["records"])).values()),
                "stack_f1": score_both(a["final"], golds, exclude, vocab),
                "cost": cost_by_rung(a["ledger"], len(a["final"])),
            }
            if 1 in a["records"]:
                entry["lanes"] = analysis.lanes(analysis.rows_at(a["state"], 1).values())
            if 4 in a["records"]:
                entry["r4"] = analysis.judge_summary(a["records"][4],
                                                     analysis.rows_at(a["state"], 4).values())
            report["arms"].setdefault(arm, {})[Path(prefix).name] = entry
    if len(draws) >= 2:
        report["consensus"] = analysis.consensus([d["records"][0] for d in draws])
        report["sha256_identical_draws"] = len({d["sha256"].get(0) for d in draws}) == 1
    return report


def fmt(report: dict) -> str:
    L = [f"# {report['corpus']} — consolidated re-run, dev split, {report['n_docs']} docs, "
         f"{report['n_gold_scored']} scorable gold mentions", ""]
    L.append("## Rung 0 per draw (span-exact / overlap; F1 = score_run with exclusions)")
    L.append("| draw | spans | det P/R/F1 exact | coding exact | F1 exact [CI] | det F1 overlap | coding overlap | F1 overlap | sha256(r0) |")
    L.append("|---|---|---|---|---|---|---|---|---|")
    for name, d in report["draws"].items():
        e, o = d["rung0"]["exact"], d["rung0"]["overlap"]
        L.append(f"| {name} | {d['spans_proposed']} | {e['detection']['precision']:.3f}/{e['detection']['recall']:.3f}/{e['detection']['f1']:.3f} "
                 f"| {e['coding']['accuracy']:.3f} | **{e['f1']:.3f}** [{e['f1_ci'][0]:.3f}–{e['f1_ci'][1]:.3f}] "
                 f"| {o['detection']['f1']:.3f} | {o['coding']['accuracy']:.3f} | {o['f1']:.3f} | `{(d['sha256_r0'] or '')[:8]}` |")
    L.append("")
    L.append("## Error budget per draw (exact; one denominator: the scorable gold set)")
    L.append("| draw | gold | matched | missed (find) | invented | on menu | lost retrieval | correct | lost pick | pick loss by lane |")
    L.append("|---|---|---|---|---|---|---|---|---|---|")
    for name, d in report["draws"].items():
        b = d["budget"]["exact"]
        L.append(f"| {name} | {b['n_gold']} | {b['matched']} | {b['missed']} | {b['invented']} | {b['on_menu']} | {b['lost_retrieval']} | {b['correct']} | {b['lost_pick']} | {b['lost_pick_by_lane']} |")
    L.append("")
    L.append("## Rung 1 lanes per draw (n / correct exact % / on no gold / correct % on overlap-matched)")
    for name, d in report["draws"].items():
        cells = "; ".join(f"{k}: {v['n']} / {v['correct_pct']}% / {v['on_no_gold']} / {v['correct_pct_matched_overlap']}%"
                          for k, v in sorted(d["lanes"].items()))
        L.append(f"- {name}: {cells}")
    L.append("")
    L.append("## Rung 3 by rung 1 lane")
    for name, d in report["draws"].items():
        if "r3" not in d:
            continue
        r = d["r3"]
        L.append(f"- {name}: by lane {r['by_lane']}; changed {r['changed']}, correct destroyed {r['correct_destroyed']}, "
                 f"gained {r['correct_gained']}, net {r['net_correct']:+d}; not_resampled had been {r['not_resampled_before']}")
        for c in r["changes"]:
            L.append(f"    - {c['record_id']} [{c['lane']}] {c['was']} -> {c['now']} votes {c['votes']}: {c['before']} -> {c['after']}")
    L.append("")
    L.append("## Rung 4 (blind, shipped) vs the menu arms")
    L.append("| draw | arm | judged | pass | fail | P(correct|pass) | P(correct|fail) | separation | span_bad | code_bad | menu shown | not-on-list | best correct | best = pick |")
    L.append("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for name, d in report["draws"].items():
        rows = [("base", d.get("r4"))] + [(arm, report["arms"].get(arm, {}).get(name, {}).get("r4"))
                                          for arm in report["arms"] if arm.startswith("judge")]
        for arm, j in rows:
            if not j:
                continue
            sep = f"{j['separation']:.2f}x" if j["separation"] else "—"
            L.append(f"| {name} | {arm} | {j['judged']} | {j['pass']} | {j['fail']} | {j['correct_given_pass']:.3f} | {j['correct_given_fail']:.3f} | {sep} | {j['span_bad']} | {j['code_bad']} | {j['menu_shown']} | {j['menu_missing']} | {j['best_correct']} | {j['best_is_pick']} |")
    L.append("")
    L.append("## The shipped result and the policy arms (final state rows)")
    L.append("| draw | arm | n | ships | coverage | accuracy | **yield** | errors | err/100 | to a person | stack F1 exact | overlap |")
    L.append("|---|---|---|---|---|---|---|---|---|---|---|---|")
    for name, d in report["draws"].items():
        rows = [("base", d["final"], d["stack_f1"])] + [
            (arm, report["arms"][arm][name]["final"], report["arms"][arm][name]["stack_f1"])
            for arm in report["arms"] if name in report["arms"][arm]]
        for arm, f, sf in rows:
            L.append(f"| {name} | {arm} | {f['n']} | {f['ships']} | {f['coverage']:.3f} | {f['accuracy']:.3f} | **{f['yield']:.3f}** | {f['errors']} | {f['err_per_100']:.1f} | {f['to_person']} | {sf['exact']['f1']:.3f} | {sf['overlap']['f1']:.3f} |")
    L.append("")
    L.append("## Cost per rung, base draws (tokens / calls / p95 s / human minutes / records routed)")
    for name, d in report["draws"].items():
        cells = "; ".join(f"r{k}: {v['tokens']:,} / {v['api_calls']} / {v['p95_s']} / {v['human_minutes']} / {v['records_routed']}"
                          for k, v in sorted(d["cost"].items(), key=lambda kv: int(kv[0])))
        L.append(f"- {name}: {cells}")
    L.append("")
    if "consensus" in report:
        c = report["consensus"]
        L.append("## Three-draw consensus (rung 0 output, mentions grouped by span overlap)")
        L.append(f"- byte-identical draws: {report['sha256_identical_draws']}")
        L.append(f"- mentions {c['mentions']}: all agree {c['all_agree']} ({c['consensus_pct']}%), same span diff code {c['same_span_diff_code']}, "
                 f"same code diff span {c['same_code_diff_span']}, both differ {c['both_differ']}, found by two {c['found_by_two']}, found by one {c['found_by_one']}")
        L.append(f"- same span all draws {c['same_span_all_three_pct']}%; same code where all found {c['same_code_given_all_found_pct']}%")
    L.append("")
    L.append("## Provenance")
    for name, d in report["draws"].items():
        L.append(f"- {name}: cache `{d['llm_cache']}`, git {d['git']}, {d['started']} → {d['finished']}")
    return "\n".join(L) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--manifest", default="manifest.json")
    ap.add_argument("--runs", nargs="+", required=True, help="run prefixes, e.g. out/rerun-cadec-d0")
    ap.add_argument("--arms", nargs="*", default=[])
    ap.add_argument("--out", required=True, help="path prefix for <out>.json and <out>.md")
    ap.add_argument("--full-vocabulary", action="store_true",
                    help="the menu is the whole vocabulary (FiNER): retrieval cannot lose")
    a = ap.parse_args(argv)
    man = load_manifest(a.manifest)
    report = analyse(man, a.runs, a.arms, a.full_vocabulary)
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.with_suffix(".json").write_text(json.dumps(report, indent=2, default=str))
    out.with_suffix(".md").write_text(fmt(report))
    print(fmt(report))
    print(f"wrote {out}.json and {out}.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

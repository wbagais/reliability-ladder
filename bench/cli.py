"""CLI: validate a data file, or run the ladder.

  python -m bench.cli validate data/sroie_v1.json
  python -m bench.cli run --data data/sroie_v1.json --model ollama/gpt-oss:20b --smoke
  python -m bench.cli run --data data/sroie_v1.json --model ollama/gpt-oss:20b --k 10
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bench.adapters.user_upload import load_dataset, validate
from bench.harness import run_benchmark


def cmd_validate(args) -> int:
    data = json.loads(Path(args.data).read_text())
    errors = validate(data)
    if errors:
        print("Problems found:")
        for e in errors:
            print(f"  - {e}")
        return 1
    ds = load_dataset(data)
    mode = "verification" if ds.verification_mode else "extraction"
    print(f"OK: {len(ds.items)} items, domain '{ds.domain}', {mode} mode.")
    return 0


def cmd_run(args) -> int:
    ds = load_dataset(args.data)
    if args.smoke:
        args.n_items, args.k = args.n_items or 10, 3
    rungs = [int(r) for r in args.rungs.split(",")] if args.rungs else None

    def progress(msg: str, frac: float):
        print(f"\r[{frac:6.1%}] {msg:<60}", end="", flush=True)

    results = run_benchmark(
        ds,
        model_spec=args.model,
        k=args.k,
        n_items=args.n_items,
        rungs=rungs,
        ablations=not args.no_ablations,
        out=args.out,
        progress=progress,
    )
    print(f"\nwrote {args.out}")
    for r in results["domains"][0]["rungs"]:
        print(
            f"  rung {r['rung']} {r['name']:<16} "
            f"det={r['determinism']['field_agreement']:.3f} "
            f"acc={r['accuracy']['accuracy_on_answered']:.3f} "
            f"cov={r['accuracy']['coverage']:.3f} "
            f"$={r['cost']['dollars']:.4f} "
            f"hum={r['cost']['human_minutes']:.1f}min"
        )
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(prog="bench")
    sub = ap.add_subparsers(dest="cmd", required=True)

    v = sub.add_parser("validate", help="check a data file, plain-language errors")
    v.add_argument("data")
    v.set_defaults(fn=cmd_validate)

    r = sub.add_parser("run", help="run the ladder")
    r.add_argument("--data", required=True)
    r.add_argument("--model", required=True, help="provider/model, e.g. ollama/gpt-oss:20b")
    r.add_argument("--k", type=int, default=10)
    r.add_argument("--n-items", type=int, default=None)
    r.add_argument("--rungs", default=None, help="comma list, e.g. 0,1,2")
    r.add_argument("--no-ablations", action="store_true")
    r.add_argument("--smoke", action="store_true", help="10 items, K=3")
    r.add_argument("--out", default="results.json")
    r.set_defaults(fn=cmd_run)

    args = ap.parse_args()
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())

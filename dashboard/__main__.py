"""`python -m dashboard` — start the Workbench on loopback.

C1: the server binds to 127.0.0.1 and refuses anything else. CADEC text is
non-transferable; a dashboard reachable from another machine is a
distribution channel, so the host is validated, not defaulted.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}


def validate_host(host: str) -> str:
    if host not in LOOPBACK_HOSTS:
        raise SystemExit(
            f"refusing to bind {host!r}: the corpus is non-transferable and "
            "the Workbench serves it, so only loopback "
            f"({', '.join(sorted(LOOPBACK_HOSTS))}) is allowed (C1)."
        )
    return host


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Ladder Workbench (M1, read-only)")
    ap.add_argument("--host", default="127.0.0.1",
                    help="loopback only; anything else is refused")
    ap.add_argument("--port", type=int, default=8321)
    ap.add_argument("--repo-root", default=None,
                    help="repo checkout to serve (default: this file's repo)")
    a = ap.parse_args(argv)
    host = validate_host(a.host)

    import uvicorn

    from dashboard.app import create_app
    from dashboard.state import AppState

    root = Path(a.repo_root) if a.repo_root else Path(__file__).parent.parent
    state = AppState(repo_root=root)
    app = create_app(state)
    print(f"[workbench] M1 read-only · http://{host}:{a.port} · repo {root}")
    uvicorn.run(app, host=host, port=a.port, log_level="warning")
    return 0


if __name__ == "__main__":
    sys.exit(main())

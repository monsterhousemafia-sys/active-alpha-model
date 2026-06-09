#!/usr/bin/env python3
"""Wall Street institutional audit — performance, prediction quality, daily growth loop."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    import os

    root = Path(os.environ.get("AA_PROJECT_ROOT", ROOT))
    if sys.platform.startswith("linux"):
        from execution.linux_security_boundary import apply_native_app_env

        apply_native_app_env(root)

    from analytics.wallstreet_performance_audit import run_wallstreet_audit

    try:
        from analytics.learning_cycle_audit import run_learning_cycle_audit

        run_learning_cycle_audit(root)
    except ImportError as exc:
        print(json.dumps({"learning_cycle_skipped": str(exc)[:120]}, ensure_ascii=False), file=sys.stderr)
    report = run_wallstreet_audit(root)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report.get("verdict") == "INSTITUTIONAL_READY" else 1


if __name__ == "__main__":
    raise SystemExit(main())

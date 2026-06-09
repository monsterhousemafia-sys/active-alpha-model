#!/usr/bin/env python3
"""Daily public learning cycle — capture, outcomes, audit, quality report."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Public learning daily cycle")
    parser.add_argument("--root", type=Path, default=Path(os.environ.get("AA_PROJECT_ROOT", ROOT)))
    parser.add_argument("--no-sync", action="store_true")
    parser.add_argument("--capture-only", action="store_true")
    args = parser.parse_args()
    root = Path(args.root)

    if sys.platform.startswith("linux"):
        from execution.linux_security_boundary import apply_native_app_env

        apply_native_app_env(root)

    from analytics.public_learning_kernel import run_capture_only, run_daily_learning

    if args.capture_only:
        out = run_capture_only(root)
        print(json.dumps(out, indent=2, ensure_ascii=False, default=str))
        return 0 if out.get("readiness", {}).get("learning_healthy", True) else 1

    report = run_daily_learning(root, sync_outcomes=not args.no_sync)
    print(json.dumps(report, indent=2, ensure_ascii=False, default=str))
    return 0 if report.get("daily_cycle", {}).get("all_ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Generate missing mom_1_top12 naive benchmark CSV for DAILY_ALPHA_H1 seal."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from analytics.h1_king_runtime import configure_king_h1_process, king_h1_subprocess_env

    import os

    for key, val in king_h1_subprocess_env().items():
        os.environ[key] = val
    configure_king_h1_process()
except Exception:
    pass

from analytics.h1_benchmark import run_benchmark_sync


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wait", action="store_true", help="Run synchronously until benchmark exists")
    args = parser.parse_args()
    if not args.wait:
        from analytics.h1_benchmark import ensure_h1_benchmark

        report = ensure_h1_benchmark(ROOT, wait=False)
        print(json.dumps(report, indent=2, ensure_ascii=False), flush=True)
        return 0 if report.get("ok") else 1
    report = run_benchmark_sync(ROOT)
    print(json.dumps(report, indent=2, ensure_ascii=False), flush=True)
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())

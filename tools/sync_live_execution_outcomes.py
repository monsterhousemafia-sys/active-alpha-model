#!/usr/bin/env python3
"""Sync T212 live fills into prediction_ledger (observe-only)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    import argparse

    from execution.live_learning.live_execution_outcome_bridge import sync_live_execution_outcomes

    parser = argparse.ArgumentParser(description="Live fill → prediction outcome ledger")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--no-history", action="store_true", help="Skip T212 history API pull")
    args = parser.parse_args()
    report = sync_live_execution_outcomes(Path(args.root), refresh_history=not args.no_history)
    print(json.dumps(report, indent=2, ensure_ascii=False, default=str))
    return 0 if report.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())

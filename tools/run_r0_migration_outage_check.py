#!/usr/bin/env python3
"""CLI: M1 outage/stall check and repair."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.r0_migration_outage_guard import run_outage_check  # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser(description="R0 M1 outage guard check/repair.")
    p.add_argument("--no-repair", action="store_true", help="Detect only, do not remove locks.")
    p.add_argument("--force-lock-clear", action="store_true", help="Always try stale lock removal.")
    p.add_argument("--json", action="store_true")
    args = p.parse_args()
    try:
        result = run_outage_check(ROOT, repair=not args.no_repair, force=args.force_lock_clear)
    except Exception as exc:
        print(exc, file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        stall = result.get("stall") or {}
        print(f"status={result.get('status', 'REPAIRED')}")
        print(f"stalled={stall.get('stalled')} reason={stall.get('reason')}")
        print(f"unblocked={result.get('unblocked')}")
        stall = result.get("stall") or {}
        if stall.get("stalled"):
            print(f"STALL detected: {stall.get('reason')} -> {stall.get('recommended_action')}")
        print("health: evidence/r0_migration/m1_health.json")
    if result.get("status") == "M1_SEALED":
        return 0
    if (result.get("stall") or {}).get("stalled") and not result.get("unblocked"):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

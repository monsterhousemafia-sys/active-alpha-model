#!/usr/bin/env python3
"""Verify and seal an R0 migration phase (fail-closed)."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.r0_migration_phase_guard import seal_phase, verify_phase  # noqa: E402


def _print_human(result: dict) -> None:
    phase = result.get("phase")
    status = result.get("status")
    print("=" * 60)
    print(f"  Phase:  {phase}")
    print(f"  Status: {status}")
    ver = result.get("verification") or {}
    if ver:
        print(f"  Pass:   {ver.get('pass')}")
        blockers = ver.get("blockers") or []
        if blockers:
            print(f"  Blocker: {blockers}")
        for c in ver.get("checks") or []:
            mark = "OK" if c.get("pass") else "FAIL"
            print(f"    [{mark}] {c.get('check')}: {c.get('detail')}")
    if result.get("seal_path"):
        print(f"  Seal:   {result.get('seal_path')}")
    if result.get("next_phase"):
        print(f"  Next:   {result.get('next_phase')}")
    print("=" * 60)


def main() -> int:
    p = argparse.ArgumentParser(description="Verify and seal R0 migration phase (M0–M12).")
    p.add_argument("--phase", required=True, help="Phase id, e.g. M0, M1, … M12")
    p.add_argument("--verify-only", action="store_true", help="Verify gates without writing seal.")
    p.add_argument("--dry-run", action="store_true", help="Show seal payload without writing.")
    p.add_argument("--skip-optional-m4", action="store_true", help="Skip optional M4 when verifying.")
    p.add_argument("--json", action="store_true", help="Machine-readable output only.")
    args = p.parse_args()

    phase = args.phase.strip().upper()
    try:
        if args.verify_only:
            result = verify_phase(ROOT, phase, skip_optional=args.skip_optional_m4)
            result = {"phase": phase, "status": "PASS" if result.get("pass") else "VERIFY_FAILED", "verification": result}
        else:
            result = seal_phase(ROOT, phase, skip_optional=args.skip_optional_m4, dry_run=args.dry_run)
    except Exception as exc:
        print(exc, file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        _print_human(result)

    if args.verify_only:
        return 0 if (result.get("verification") or {}).get("pass") else 2
    return 0 if result.get("status") in ("SEALED", "SEAL_DRY_RUN") else 2


if __name__ == "__main__":
    raise SystemExit(main())

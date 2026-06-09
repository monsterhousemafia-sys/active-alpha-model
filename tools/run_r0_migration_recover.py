#!/usr/bin/env python3
"""One-shot M1 recovery: stale lock, matrix_job reconcile, phase_status, crash_recovery.json."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.r0_migration_crash_guard import ensure_m1_unblocked  # noqa: E402


def main() -> int:
    result = ensure_m1_unblocked(ROOT)
    snap = result.get("snapshot") or {}
    print("=" * 60)
    print("R0-M1 Recovery")
    print("=" * 60)
    print(f"  Unblocked (ready to start): {result.get('unblocked')}")
    print(f"  Batch active:              {snap.get('batch_active')}")
    print(f"  Returns complete:          {snap.get('returns_complete')}")
    print(f"  Matrix job status:         {(snap.get('matrix_job') or {}).get('status')}")
    print(f"  Blockers:                  {snap.get('m1_blockers') or []}")
    print(f"  Resume:                    {snap.get('resume_hint')}")
    print(f"  Snapshot:                  evidence/r0_migration/crash_recovery.json")
    print("=" * 60)
    if "--json" in sys.argv:
        print(json.dumps(result, indent=2))
    blockers = snap.get("m1_blockers") or []
    if snap.get("batch_active"):
        return 0
    if blockers and not snap.get("returns_complete"):
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

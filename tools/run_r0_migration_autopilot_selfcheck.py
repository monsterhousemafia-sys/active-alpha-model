#!/usr/bin/env python3
"""Autopilot scorecard: M1 success criteria and readiness for M2+."""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

OUT = ROOT / "evidence" / "r0_migration" / "autopilot_selfcheck.json"


def run_selfcheck(root: Path) -> Dict[str, Any]:
    from aa_runtime_profile import is_batch_work_active
    from tools.r0_migration_crash_guard import _m1_returns_complete
    from tools.r0_migration_outage_guard import detect_matrix_stall
    from tools.r0_migration_phase_guard import is_phase_sealed
    from tools.run_r0_migration_phase_m1 import build_returns_manifest

    manifest = build_returns_manifest(root)
    stall = detect_matrix_stall(root)
    checks = {
        "m1_sealed": is_phase_sealed(root, "M1"),
        "returns_integrity_pass": bool(manifest.get("all_m1_variants_integrity_pass")),
        "batch_active": is_batch_work_active(root),
        "stall_detected": bool(stall.get("stalled")),
        "m0_sealed": is_phase_sealed(root, "M0"),
    }
    success = checks["m1_sealed"]
    verdict = "SUCCESS" if success else ("STALLED" if checks["stall_detected"] else "IN_PROGRESS")
    if checks["returns_integrity_pass"] and not checks["m1_sealed"]:
        verdict = "READY_TO_SEAL"
    return {
        "schema_version": 1,
        "checked_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "verdict": verdict,
        "autopilot_success": success,
        "may_advance_to_m2": success,
        "checks": checks,
        "stall": stall,
        "blockers": [] if success else ["M1_NOT_SEALED"],
        "scope_doc": "docs/R0_MIGRATION_M1_ACTIVE_SCOPE.md",
        "next_action": (
            "run_orchestrator_for_M2_after_M1_seal"
            if success
            else __import__("tools.r0_migration_m1_control", fromlist=["M1_ENTRY"]).M1_ENTRY
        ),
        "trading_step": "M1_baseline" if not success else "M2_aligned_comparison",
    }


def main() -> int:
    from aa_safe_io import atomic_write_json

    payload = run_selfcheck(ROOT)
    atomic_write_json(OUT, payload)
    print(json.dumps(payload, indent=2))
    return 0 if payload.get("autopilot_success") else 2


if __name__ == "__main__":
    raise SystemExit(main())

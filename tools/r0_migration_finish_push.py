#!/usr/bin/env python3
"""Aggressive M1 completion push: hold live runs, resume dead ones, ensure automation."""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

REPORT = ROOT / "evidence" / "r0_migration" / "finish_push.json"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def run_finish_push(root: Path) -> Dict[str, Any]:
    from aa_runtime_profile import cleanup_stale_batch_lock, is_batch_work_active
    from aa_safe_io import atomic_write_json
    from tools.r0_migration_outage_guard import detect_matrix_stall, run_outage_check
    from tools.r0_migration_phase_guard import is_phase_sealed, try_seal_phase
    from tools.r0_migration_runtime import matrix_work_in_progress
    from tools.run_r0_migration_phase_m1 import build_returns_manifest, write_m1_backtest_waiver

    report: Dict[str, Any] = {"at_utc": _utc_now(), "actions": []}
    write_m1_backtest_waiver(root, reason="M1 finish_push: evidence-only matrix to completion.")

    if is_phase_sealed(root, "M1"):
        report["verdict"] = "M1_ALREADY_SEALED"
        atomic_write_json(REPORT, report)
        return report

    manifest = build_returns_manifest(root)
    if manifest.get("all_m1_variants_integrity_pass"):
        from tools.run_r0_migration_phase_m1 import run_m1

        run_m1(apply_env_fix=False)
        seal = try_seal_phase(root, "M1")
        report["verdict"] = "SEALED" if seal.get("status") == "SEALED" else "SEAL_FAILED"
        report["seal"] = seal
        atomic_write_json(REPORT, report)
        return report

    from tools.r0_migration_hw import prevent_sleep_on

    report["actions"].append({"prevent_sleep": prevent_sleep_on()})

    cleanup_stale_batch_lock(root)
    stall = detect_matrix_stall(root.resolve())

    if matrix_work_in_progress(root):
        from tools.r0_migration_eliminate_blockers import _r0_log_stuck
        from tools.r0_migration_commander import _kill_orphan_matrix_processes, _migration_pids

        matrix_count = sum(
            1 for p in _migration_pids() if "run_validation_matrix.py" in p.get("cmd", "")
        )
        if matrix_count > 1 or _r0_log_stuck(root).get("stuck"):
            from tools.r0_migration_eliminate_blockers import eliminate_blockers

            report["actions"].append(
                {"eliminate_blockers": eliminate_blockers(root, restart_if_dead=_r0_log_stuck(root).get("stuck"))}
            )
            atomic_write_json(REPORT, report)
            return report
        if matrix_count > 1:
            orphans = _kill_orphan_matrix_processes(root)
            if orphans:
                report["actions"].append({"orphan_matrix_killed": orphans})
        report["verdict"] = "HOLD_LIVE_MATRIX"
        report["stall"] = stall
        report["returns"] = manifest.get("all_m1_variants_integrity_pass")
        atomic_write_json(REPORT, report)
        return report

    from tools.r0_migration_sla_enforce import canonical_r0_incomplete, enforce_sla_fast_path

    if canonical_r0_incomplete(root):
        sla = enforce_sla_fast_path(root)
        report["actions"].append({"sla_enforce": sla})
        report["verdict"] = str(sla.get("verdict", "SLA_FAST_PATH"))
        report["returns"] = manifest.get("all_m1_variants_integrity_pass")
        atomic_write_json(REPORT, report)
        return report

    if stall.get("stalled"):
        from tools.r0_migration_stop_hung_matrix import stop_hung_matrix

        report["actions"].append({"stop_hung": stop_hung_matrix(root)})
        cleanup_stale_batch_lock(root)

    from tools.r0_migration_commander import run_commander

    cmdr = run_commander(root, force_reset=bool(stall.get("stalled")))
    report["actions"].append({"commander": cmdr})
    report["verdict"] = cmdr.get("verdict", "COMMANDER")
    report["actions"].append({"outage": run_outage_check(root, repair=True)})
    atomic_write_json(REPORT, report)
    return report


def main() -> int:
    import argparse

    p = argparse.ArgumentParser(description="M1 finish push — resume or hold, never kill live workers.")
    p.add_argument("--json", action="store_true")
    args = p.parse_args()
    report = run_finish_push(ROOT)
    subprocess.run(
        [str(ROOT / ".venv" / "Scripts" / "python.exe"), str(ROOT / "tools" / "r0_migration_m1_status.py")],
        cwd=str(ROOT),
    )
    if args.json:
        print(json.dumps(report, indent=2, default=str))
    return 0 if report.get("verdict") in ("HOLD_LIVE_MATRIX", "RESET_AND_STARTED_MATRIX", "SEALED", "M1_ALREADY_SEALED") else 1


if __name__ == "__main__":
    raise SystemExit(main())

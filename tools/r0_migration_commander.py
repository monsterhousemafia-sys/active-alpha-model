#!/usr/bin/env python3
"""Single command post for M1: one matrix, one watch-loop, sleep on, status."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

REPORT = ROOT / "evidence" / "r0_migration" / "commander_report.json"
WATCH_PID = ROOT / "evidence" / "r0_migration" / "watch_loop.pid"

MATCH_KILL = (
    "validation_matrix",
    "active_alpha_model.py",
    "run_r0_migration_phase_m1",
    "run_r0_migration_watch_loop",
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _pid_alive(pid: int) -> bool:
    from tools.r0_migration_hw import pid_alive

    return pid_alive(pid)


def _migration_pids() -> List[Dict[str, Any]]:
    from tools.r0_migration_hw import list_processes

    return list_processes(cmd_markers=MATCH_KILL)


def _lock_holder_pid(root: Path) -> int:
    from aa_runtime_profile import BATCH_LOCK_FILE

    p = root / BATCH_LOCK_FILE
    if not p.is_file():
        return 0
    try:
        return int(p.read_text(encoding="utf-8").split()[0])
    except Exception:
        return 0


def _kill_orphan_matrix_processes(root: Path) -> List[int]:
    """Stop validation_matrix PIDs that do not hold the batch lock (never kill lock holder)."""
    lock_pid = _lock_holder_pid(root)
    matrix_pids = [
        x["pid"]
        for x in _migration_pids()
        if "run_validation_matrix.py" in x.get("cmd", "")
    ]
    if not matrix_pids:
        return []
    if lock_pid <= 0 or lock_pid not in matrix_pids:
        keep = max(matrix_pids)
    else:
        keep = lock_pid
    orphans = sorted(pid for pid in matrix_pids if pid != keep)
    stopped: List[int] = []
    for pid in orphans:
        stopped.extend(_kill_pids([pid]))
        if _pid_alive(keep):
            break
    if keep and not _pid_alive(keep):
        from aa_runtime_profile import cleanup_stale_batch_lock

        cleanup_stale_batch_lock(root)
    return stopped


def _kill_pids(pids: List[int]) -> List[int]:
    from tools.r0_migration_hw import kill_pids

    return kill_pids(pids)


def _returns_done(root: Path) -> int:
    variants = (
        "R0_LEGACY_ENSEMBLE",
        "R3_w075_q065_noexit",
        "M1_MOM_BLEND_MATCHED_CONTROLS",
    )
    n = 0
    for v in variants:
        if list(root.glob(f"validation_runs/*{v}*/strategy_daily_returns.csv")):
            n += 1
    return n


def _clear_lock(root: Path) -> None:
    from aa_runtime_profile import BATCH_LOCK_FILE, cleanup_stale_batch_lock

    cleanup_stale_batch_lock(root)
    p = root / BATCH_LOCK_FILE
    if p.is_file():
        try:
            p.unlink(missing_ok=True)
        except OSError:
            pass
    if WATCH_PID.is_file():
        try:
            WATCH_PID.unlink(missing_ok=True)
        except OSError:
            pass


def _start_matrix(root: Path) -> Dict[str, Any]:
    from tools.r0_migration_runtime import count_validation_matrix_processes, matrix_work_in_progress
    from tools.run_r0_migration_phase_m1 import launch_validation_matrix, write_m1_backtest_waiver

    if matrix_work_in_progress(root) or count_validation_matrix_processes(root) > 0:
        return {"started": False, "reason": "matrix_already_running"}
    write_m1_backtest_waiver(root, reason="M1 commander: single validation matrix launch.")
    return launch_validation_matrix(root)


def _start_watch(root: Path) -> Dict[str, Any]:
    if (root / "control" / "r0_migration" / "m1_race_mode.json").is_file():
        return {"skipped": True, "reason": "m1_race_mode"}
    from tools.r0_migration_operational_setup import ensure_watch_loop

    return ensure_watch_loop(root, start=True)


def run_commander(root: Path, *, force_reset: bool = False) -> Dict[str, Any]:
    from aa_runtime_profile import is_batch_work_active
    from aa_safe_io import atomic_write_json
    from tools.r0_migration_phase_guard import is_phase_sealed, try_seal_phase
    from tools.r0_migration_outage_guard import run_outage_check

    report: Dict[str, Any] = {"at_utc": _utc_now(), "actions": []}
    done = _returns_done(root)

    from tools.run_r0_migration_phase_m1 import write_m1_backtest_waiver

    write_m1_backtest_waiver(
        root,
        reason="M1 commander: evidence-only validation matrix (R0/R3/M1).",
    )

    if is_phase_sealed(root, "M1"):
        report["verdict"] = "M1_SEALED"
        atomic_write_json(REPORT, report)
        return report

    if done == 3:
        report["actions"].append({"finish_m1": "starting"})
        from tools.run_r0_migration_phase_m1 import run_m1

        run_m1(apply_env_fix=False)
        seal = try_seal_phase(root, "M1")
        report["seal"] = seal
        report["verdict"] = "M1_FINISH_SEAL"
        atomic_write_json(REPORT, report)
        return report

    from tools.r0_migration_sla_enforce import canonical_r0_incomplete, enforce_sla_fast_path

    if canonical_r0_incomplete(root):
        sla = enforce_sla_fast_path(root)
        report["actions"].append({"sla_enforce": sla})
        report["verdict"] = str(sla.get("verdict", "SLA_FAST_PATH"))
        report["returns_done"] = f"{_returns_done(root)}/3"
        atomic_write_json(REPORT, report)
        return report

    from aa_runtime_profile import cleanup_stale_batch_lock

    cleanup_stale_batch_lock(root)
    before = _migration_pids()
    report["processes_before"] = len(before)

    duplicate_matrix = sum(1 for p in before if "run_validation_matrix.py" in p.get("cmd", "")) > 1
    duplicate_watch = sum(1 for p in before if "watch_loop" in p.get("cmd", "")) > 1
    duplicate_m1 = sum(1 for p in before if "run_r0_migration_phase_m1" in p.get("cmd", "")) > 1

    from tools.r0_migration_outage_guard import detect_matrix_stall

    stall = detect_matrix_stall(root)
    if duplicate_matrix:
        stopped = _kill_orphan_matrix_processes(root)
        report["actions"].append({"orphan_matrix_killed": stopped})
        if stopped and not stall.get("stalled"):
            report["verdict"] = "DEDUPED_MATRIX_KEPT_LOCK_HOLDER"
            report["actions"].append({"watch_loop": _start_watch(root)})
            report["returns_done"] = f"{_returns_done(root)}/3"
            report["processes_after"] = len(_migration_pids())
            atomic_write_json(REPORT, report)
            subprocess.run(
                [str(root / ".venv" / "Scripts" / "python.exe"), str(root / "tools" / "r0_migration_m1_status.py")],
                cwd=str(root),
            )
            return report

    from tools.r0_migration_runtime import matrix_work_in_progress

    in_progress = matrix_work_in_progress(root)
    need_reset = (
        force_reset
        or duplicate_watch
        or duplicate_m1
        or stall.get("stalled")
        or (done < 3 and not in_progress)
    )
    if not need_reset and in_progress:
        report["verdict"] = "HOLD_MATRIX_OR_WORKERS"
        report["actions"].append({"matrix": "keep_running", "stall": stall.get("reason")})
    else:
        if before or is_batch_work_active(root):
            stopped = _kill_pids([p["pid"] for p in before])
            report["actions"].append({"stopped_pids": stopped})
            time.sleep(2)
            _clear_lock(root)
        from tools.r0_migration_hw import prevent_sleep_on

        report["actions"].append({"prevent_sleep": prevent_sleep_on()})
        report["actions"].append({"matrix": _start_matrix(root)})
        report["verdict"] = "RESET_AND_STARTED_MATRIX"

    report["actions"].append({"watch_loop": _start_watch(root)})
    report["actions"].append({"outage": run_outage_check(root, repair=True)})
    report["returns_done"] = f"{_returns_done(root)}/3"
    report["processes_after"] = len(_migration_pids())
    atomic_write_json(REPORT, report)
    return report


def main() -> int:
    import argparse

    p = argparse.ArgumentParser(description="R0 M1 commander — enforce single matrix + watch.")
    p.add_argument("--force-reset", action="store_true")
    p.add_argument("--json", action="store_true")
    args = p.parse_args()
    report = run_commander(ROOT, force_reset=args.force_reset)
    from tools.r0_migration_hw import python_executable

    subprocess.run(
        [python_executable(ROOT), str(ROOT / "tools" / "r0_migration_m1_status.py")],
        cwd=str(ROOT),
    )
    if args.json:
        print(json.dumps(report, indent=2, default=str))
    return 0 if report.get("verdict") in (
        "HOLD_SINGLE_MATRIX",
        "HOLD_MATRIX_OR_WORKERS",
        "DEDUPED_MATRIX_KEPT_LOCK_HOLDER",
        "RESET_AND_STARTED_MATRIX",
        "M1_SEALED",
        "M1_FINISH_SEAL",
    ) else 1


if __name__ == "__main__":
    raise SystemExit(main())

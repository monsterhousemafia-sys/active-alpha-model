#!/usr/bin/env python3
"""Remove everything that blocks the single M1 matrix run (zombies, duplicates, loops)."""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

REPORT = ROOT / "evidence" / "r0_migration" / "eliminate_blockers.json"
LOG_STUCK_MIN = 10.0
# BIOS log often freezes at first ML % until the first rebalance task completes.
LOG_STUCK_EARLY_ML_IDLE_MIN = 10.0


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _r0_log_stuck(root: Path) -> Dict[str, Any]:
    import time

    from tools.r0_migration_runtime import newest_run_dir_for_variant

    d = newest_run_dir_for_variant(root, "R0_LEGACY_ENSEMBLE")
    if d is None:
        return {"stuck": False, "reason": "no_run_dir"}
    log = d / "validation_run.log"
    if not log.is_file():
        return {"stuck": False, "reason": "no_log"}
    idle_min = (time.time() - log.stat().st_mtime) / 60.0
    text = log.read_text(encoding="utf-8", errors="replace")
    tail = text[-4000:]
    path_phase = "Pfad-Simulation" in tail or "Pfad/Kosten" in tail
    if path_phase:
        return {
            "stuck": False,
            "idle_min": round(idle_min, 1),
            "run_dir": d.name,
            "reason": "path_phase_ignore_display",
        }
    early_ml = "Walk-forward ML" in text and "74%" not in text and (
        "26%" in text[-2500:] or "PROGRESS   0/186" in text[-800:]
    )
    from tools.r0_migration_runtime import backtest_workers_cpu_active, count_backtest_workers

    if backtest_workers_cpu_active(root, sample_sec=2.0).get("active"):
        return {
            "stuck": False,
            "idle_min": round(idle_min, 1),
            "run_dir": d.name,
            "reason": "workers_computing_ignore_log_idle",
        }
    # Stuck early in ML: long log idle only (workers may still be computing).
    stuck = early_ml and idle_min >= LOG_STUCK_EARLY_ML_IDLE_MIN
    if early_ml and not stuck:
        swarm = int(count_backtest_workers(root).get("worker_count") or 0) > 4
        stuck = swarm and idle_min >= 3.0
    return {"stuck": stuck, "idle_min": round(idle_min, 1), "run_dir": d.name, "early_ml": early_ml}


def _kill_orphan_backtests(root: Path, *, keep_lock_subtree: bool) -> List[int]:
    from tools.r0_migration_commander import _kill_pids, _lock_holder_pid, _migration_pids

    lock_pid = _lock_holder_pid(root)
    matrix_pids = {p["pid"] for p in _migration_pids() if "run_validation_matrix.py" in p.get("cmd", "")}
    targets: List[int] = []
    for p in _migration_pids():
        cmd = p.get("cmd", "")
        if "active_alpha_model.py" not in cmd or "validation_runs" not in cmd:
            continue
        pid = int(p["pid"])
        if keep_lock_subtree and lock_pid in matrix_pids and len(matrix_pids) == 1:
            # Cannot reliably map parent; if R0 log stuck, kill all backtests
            if not _r0_log_stuck(root).get("stuck"):
                continue
        targets.append(pid)
    return _kill_pids(targets)


def eliminate_blockers(root: Path, *, restart_if_dead: bool = True) -> Dict[str, Any]:
    from aa_runtime_profile import cleanup_stale_batch_lock, is_batch_work_active
    from aa_safe_io import atomic_write_json
    from tools.r0_migration_commander import (
        _kill_orphan_matrix_processes,
        _kill_pids,
        _migration_pids,
        _lock_holder_pid,
    )
    from tools.r0_migration_runtime import count_validation_matrix_processes, matrix_work_in_progress

    out: Dict[str, Any] = {"at_utc": _utc_now(), "actions": []}
    stuck = _r0_log_stuck(root)
    out["r0_log"] = stuck

    # 1) All watch-loop + phase_m1 launchers (race = single matrix only)
    dup: List[int] = []
    watches = [p for p in _migration_pids() if "watch_loop" in p.get("cmd", "")]
    m1_launch = [p for p in _migration_pids() if "run_r0_migration_phase_m1" in p.get("cmd", "")]
    dup += [p["pid"] for p in watches]
    dup += [p["pid"] for p in m1_launch]
    if dup:
        out["actions"].append({"killed_dup_launchers": _kill_pids(dup)})

    # 2) Duplicate validation_matrix (keep lock holder)
    killed_matrix = _kill_orphan_matrix_processes(root)
    if killed_matrix:
        out["actions"].append({"orphan_matrix": killed_matrix})

    from tools.r0_migration_runtime import count_backtest_workers

    worker_n = int(count_backtest_workers(root).get("worker_count") or 0)
    matrix_n = count_validation_matrix_processes(root)

    # 3) Zombie backtests — never kill active R0 path worker (path_phase + CPU)
    from tools.r0_migration_runtime import backtest_workers_cpu_active, newest_run_dir_for_variant

    r0_dir = newest_run_dir_for_variant(root, "R0_LEGACY_ENSEMBLE")
    r0_path_active = (
        r0_dir is not None
        and not (r0_dir / "strategy_daily_returns.csv").is_file()
        and bool(backtest_workers_cpu_active(root, sample_sec=1.0).get("active"))
        and _r0_log_stuck(root).get("reason") == "path_phase_ignore_display"
    )
    swarm_kill = worker_n > 4 or (worker_n > 2 and not r0_path_active)
    if stuck.get("stuck") or swarm_kill or matrix_n > 1:
        kb = _kill_orphan_backtests(root, keep_lock_subtree=False) if not r0_path_active else []
        if kb:
            out["actions"].append({"zombie_backtests": kb})
        # Matrix likely dead weight — reset if log stuck
        lock_pid = _lock_holder_pid(root)
        matrix_pids = [p["pid"] for p in _migration_pids() if "run_validation_matrix.py" in p.get("cmd", "")]
        extra = [pid for pid in matrix_pids if pid != lock_pid]
        if stuck.get("stuck") or matrix_n > 1 or worker_n > 4:
            extra = matrix_pids if stuck.get("stuck") else [pid for pid in matrix_pids if pid != lock_pid]
            if matrix_n > 1 and not extra:
                extra = [pid for pid in matrix_pids if pid != max(matrix_pids)]
        if extra:
            out["actions"].append({"killed_matrix": _kill_pids(extra)})
        if stuck.get("stuck") or matrix_n > 1:
            cleanup_stale_batch_lock(root)
    out["matrix_count_after"] = count_validation_matrix_processes(root)
    out["batch_active_after"] = is_batch_work_active(root)

    if matrix_n > 1 or (stuck.get("stuck") and matrix_n >= 1):
        all_mx = [p["pid"] for p in _migration_pids() if "run_validation_matrix.py" in p.get("cmd", "")]
        if all_mx:
            out["actions"].append({"killed_all_matrix": _kill_pids(all_mx)})
        cleanup_stale_batch_lock(root)
        guard = root / "control" / "r0_migration" / "matrix_launch_guard.lock"
        try:
            guard.unlink(missing_ok=True)
        except OSError:
            pass

    out["matrix_count_after"] = count_validation_matrix_processes(root)
    out["batch_active_after"] = is_batch_work_active(root)

    if restart_if_dead and not matrix_work_in_progress(root):
        from tools.r0_migration_runtime import backtest_workers_cpu_active, newest_run_dir_for_variant

        r0_dir = newest_run_dir_for_variant(root, "R0_LEGACY_ENSEMBLE")
        r0_active = bool(backtest_workers_cpu_active(root, sample_sec=1.5).get("active"))
        r0_done = r0_dir is not None and (r0_dir / "strategy_daily_returns.csv").is_file()
        if r0_active and not r0_done:
            out["restart"] = {"skipped": "r0_backtest_still_running"}
            atomic_write_json(REPORT, out)
            return out
        from tools.run_r0_migration_phase_m1 import launch_validation_matrix, write_m1_backtest_waiver
        from tools.run_validation_matrix import _is_pass_complete
        from tools.r0_migration_sla_enforce import CANONICAL_R0_STAMP, enforce_sla_fast_path

        write_m1_backtest_waiver(root, reason="eliminate_blockers: single matrix restart.")
        from tools.r0_migration_hw import prevent_sleep_on

        prevent_sleep_on()
        r0_dir = root / "validation_runs" / f"{CANONICAL_R0_STAMP}_R0_LEGACY_ENSEMBLE"
        if r0_dir.is_dir() and not _is_pass_complete(r0_dir):
            out["actions"].append({"restart": enforce_sla_fast_path(root)})
        else:
            out["actions"].append({"restart": launch_validation_matrix(root)})

    atomic_write_json(REPORT, out)
    return out


def main() -> int:
    import argparse

    p = argparse.ArgumentParser(description="Eliminate M1 matrix blockers.")
    p.add_argument("--no-restart", action="store_true")
    p.add_argument("--json", action="store_true")
    args = p.parse_args()
    result = eliminate_blockers(ROOT, restart_if_dead=not args.no_restart)
    if args.json:
        print(json.dumps(result, indent=2, default=str))
    else:
        print(json.dumps(result, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

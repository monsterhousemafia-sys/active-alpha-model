#!/usr/bin/env python3
"""Detect M1 stall/outage and repair stale locks (fail-closed, auditable)."""
from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from aa_runtime_profile import BATCH_LOCK_FILE, cleanup_stale_batch_lock, is_batch_work_active
from aa_safe_io import atomic_write_json

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "control" / "r0_migration" / "outage_guard_config.json"
HEALTH_PATH = ROOT / "evidence" / "r0_migration" / "m1_health.json"
VALIDATION_ROOT = ROOT / "validation_runs"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def load_config(root: Path = ROOT) -> Dict[str, Any]:
    p = root / CONFIG_PATH.relative_to(ROOT)
    if not p.is_file():
        return {"stall_detection": {"enabled": True, "max_idle_minutes_without_returns": 150}}
    return json.loads(p.read_text(encoding="utf-8"))


def _canonical_r0_run_dir(root: Path) -> Optional[Path]:
    sla = Path(root) / "control" / "r0_migration" / "m1_sla_6h.json"
    if not sla.is_file():
        return None
    try:
        stamp = str(json.loads(sla.read_text(encoding="utf-8")).get("canonical_r0_stamp") or "").strip()
    except Exception:
        return None
    if not stamp:
        return None
    preferred = Path(root) / "validation_runs" / f"{stamp}_R0_LEGACY_ENSEMBLE"
    return preferred if preferred.is_dir() else None


def _newest_run_dir(root: Path) -> Optional[Path]:
    preferred = _canonical_r0_run_dir(root)
    if preferred is not None:
        return preferred
    vr = (Path(root) / "validation_runs").resolve()
    if not vr.is_dir():
        return None
    dirs = [p for p in vr.iterdir() if p.is_dir()]
    if not dirs:
        return None
    return max(dirs, key=lambda p: p.stat().st_mtime)


def _lock_pid(root: Path) -> int:
    p = root / BATCH_LOCK_FILE
    if not p.is_file():
        return 0
    try:
        return int(p.read_text(encoding="utf-8").split()[0])
    except Exception:
        return 0


def _mtime_idle_minutes(path: Path) -> Optional[float]:
    if not path.is_file():
        return None
    return (time.time() - path.stat().st_mtime) / 60.0


def _matrix_log_idle_minutes(root: Path) -> Optional[float]:
    return _mtime_idle_minutes(root / "evidence" / "r0_migration" / "validation_matrix_run.log")


def _count_matrix_workers() -> Dict[str, Any]:
    if os.name != "nt":
        return {"worker_count": 0, "method": "non_windows"}
    try:
        import subprocess

        script = (
            "(Get-CimInstance Win32_Process -Filter \"name='python.exe'\" -ErrorAction SilentlyContinue | "
            "Where-Object { $_.CommandLine -match 'validation_matrix|validation_runs|active_alpha_model' }).Count"
        )
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-Command", script],
            capture_output=True,
            text=True,
            timeout=45,
            cwd=str(ROOT),
        )
        count = int((proc.stdout or "0").strip() or "0")
        return {"worker_count": count, "method": "cim_commandline"}
    except Exception as exc:
        return {"worker_count": 0, "method": "error", "error": str(exc)}


def _pid_cpu_seconds(pid: int) -> Optional[float]:
    if pid <= 0 or os.name != "nt":
        return None
    try:
        import ctypes

        class FILETIME(ctypes.Structure):
            _fields_ = [("dwLowDateTime", ctypes.c_uint32), ("dwHighDateTime", ctypes.c_uint32)]

        def ft_to_int(ft: FILETIME) -> int:
            return (ft.dwHighDateTime << 32) + ft.dwLowDateTime

        k = ctypes.windll.kernel32
        h = k.OpenProcess(0x1000, False, pid)
        if not h:
            return None
        c, e, s, u = FILETIME(), FILETIME(), FILETIME(), FILETIME()
        if not k.GetProcessTimes(h, ctypes.byref(c), ctypes.byref(e), ctypes.byref(s), ctypes.byref(u)):
            k.CloseHandle(h)
            return None
        k.CloseHandle(h)
        return (ft_to_int(s) + ft_to_int(u)) / 10_000_000.0
    except Exception:
        return None


def _matrix_worker_pids() -> List[int]:
    """PIDs of the actual backtest/matrix python workers (incl. mp forks)."""
    if os.name != "nt":
        return []
    try:
        import subprocess

        script = (
            "Get-CimInstance Win32_Process -Filter \"name='python.exe'\" -ErrorAction SilentlyContinue | "
            "Where-Object { $_.CommandLine -match 'active_alpha_model|validation_runs|multiprocessing.spawn' } | "
            "Select-Object -ExpandProperty ProcessId"
        )
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-Command", script],
            capture_output=True,
            text=True,
            timeout=45,
            cwd=str(ROOT),
        )
        pids: List[int] = []
        for ln in (proc.stdout or "").splitlines():
            ln = ln.strip()
            if ln.isdigit():
                pids.append(int(ln))
        return pids
    except Exception:
        return []


def _matrix_workers_cpu_active(*, window_s: float = 2.5, min_delta_s: float = 0.5) -> Dict[str, Any]:
    """Ground-truth liveness: sample summed worker CPU twice; alive if it climbs.

    The path-simulation phase writes no files and logs only to the console, so a
    stale run dir / log does NOT mean frozen. Burning CPU is the real signal.
    """
    pids = _matrix_worker_pids()
    if not pids:
        return {"cpu_active": False, "reason": "no_workers", "n_pids": 0}

    def _total() -> float:
        tot = 0.0
        for pid in pids:
            c = _pid_cpu_seconds(pid)
            if c is not None:
                tot += c
        return tot

    t0 = _total()
    time.sleep(window_s)
    t1 = _total()
    delta = t1 - t0
    return {
        "cpu_active": delta >= min_delta_s,
        "n_pids": len(pids),
        "cpu_delta_seconds": round(delta, 3),
        "window_seconds": window_s,
        "min_delta_seconds": min_delta_s,
    }


def detect_matrix_stall(root: Path, *, cfg: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    cfg = cfg or load_config(root)
    stall_cfg = cfg.get("stall_detection") or {}
    if not stall_cfg.get("enabled", True):
        return {"stalled": False, "reason": "detection_disabled"}

    from tools.r0_migration_crash_guard import _m1_returns_complete

    if _m1_returns_complete(root):
        return {"stalled": False, "reason": "returns_complete"}

    if not is_batch_work_active(root):
        return {"stalled": False, "reason": "batch_not_active"}

    # Ground-truth liveness: if backtest workers are genuinely burning CPU, the run
    # is NOT frozen — regardless of stale run-dir/log mtimes (path-sim writes no files
    # and logs only to the console for long stretches). This removes the false STALLED
    # signal without weakening real crash detection (0-CPU crashes still flagged below).
    if bool(stall_cfg.get("cpu_liveness_check", True)):
        cpu = _matrix_workers_cpu_active(
            window_s=float(stall_cfg.get("cpu_liveness_window_seconds", 2.5)),
            min_delta_s=float(stall_cfg.get("cpu_liveness_min_delta_seconds", 0.5)),
        )
        if cpu.get("cpu_active"):
            return {"stalled": False, "reason": "workers_cpu_active", "cpu_liveness": cpu}

    root = root.resolve()
    newest = _newest_run_dir(root)
    if newest is None:
        return {"stalled": False, "reason": "no_run_dir"}

    idle_min = (time.time() - newest.stat().st_mtime) / 60.0
    max_idle = float(stall_cfg.get("max_idle_minutes_without_returns", 90))
    max_log_idle = float(stall_cfg.get("max_log_idle_minutes", max_idle))
    run_log = newest / "validation_run.log"
    log_idle = _mtime_idle_minutes(run_log)
    matrix_log_idle = _matrix_log_idle_minutes(root)
    workers = _count_matrix_workers()
    worker_count = int(workers.get("worker_count") or 0)
    lock_pid = _lock_pid(root)
    cpu_s = _pid_cpu_seconds(lock_pid)
    min_cpu = float(stall_cfg.get("min_lock_holder_cpu_seconds", 30))

    log_stale = log_idle is not None and log_idle >= max_log_idle
    matrix_log_stale = matrix_log_idle is not None and matrix_log_idle >= max_log_idle
    dir_stale = idle_min >= max_idle
    lock_idle = cpu_s is None or cpu_s < min_cpu

    min_workers = int(stall_cfg.get("min_matrix_worker_processes_for_activity", 1))
    workers_active = worker_count >= min_workers

    # Hänger: Run-Ordner + Varianten-Log stale; keine Backtest-Worker
    stalled_workers_gone = dir_stale and log_stale and worker_count == 0
    # Hänger: Logs stale, keine Worker, Lock tot (Zombie)
    stalled_logs_frozen = (
        dir_stale and log_stale and worker_count == 0 and (matrix_log_stale or lock_idle)
    )
    # Lange Log-Pause trotz Workern = echter Hänger (unbuffered Logs können selten flushen)
    stalled_frozen_workers = (
        workers_active
        and log_idle is not None
        and log_idle >= max_log_idle * 2
        and dir_stale
    )

    stalled = bool(stalled_workers_gone or stalled_logs_frozen or stalled_frozen_workers)
    reason = "workers_active" if workers_active and not stalled else "activity_ok"
    if stalled_workers_gone:
        reason = "stale_run_dir_and_log_no_workers"
    elif stalled_logs_frozen:
        reason = "stale_logs_low_lock_activity"
    elif stalled_frozen_workers:
        reason = "stale_logs_despite_workers"

    return {
        "stalled": stalled,
        "reason": reason,
        "idle_minutes": round(idle_min, 1),
        "log_idle_minutes": round(log_idle, 1) if log_idle is not None else None,
        "matrix_log_idle_minutes": round(matrix_log_idle, 1) if matrix_log_idle is not None else None,
        "max_idle_minutes": max_idle,
        "max_log_idle_minutes": max_log_idle,
        "newest_run_dir": str(newest.relative_to(root.resolve())),
        "run_log_path": str(run_log.relative_to(root.resolve())) if run_log.is_file() else None,
        "lock_pid": lock_pid,
        "lock_cpu_seconds": cpu_s,
        "workers": workers,
        "recommended_action": (
            "python tools/r0_migration_outage_guard.py --repair then python tools/r0_migration_commander.py"
            if stalled
            else None
        ),
    }


def repair_outage(root: Path, *, force_stale_lock: bool = False) -> Dict[str, Any]:
    """Stale lock removal + full M1 reconcile. Optional stall-based lock clear."""
    from tools.r0_migration_crash_guard import ensure_m1_unblocked

    cfg = load_config(root)
    actions: List[Dict[str, Any]] = []
    stall = detect_matrix_stall(root, cfg=cfg)
    actions.append({"action": "detect_matrix_stall", **stall})

    if force_stale_lock or stall.get("stalled"):
        lock = cleanup_stale_batch_lock(root)
        actions.append({"action": "cleanup_stale_batch_lock_forced", **lock, "stall": stall.get("stalled")})
        if stall.get("stalled") and not lock.get("removed") and bool((cfg.get("auto_repair") or {}).get("clear_lock_file_on_stall")):
            lock_path = root / BATCH_LOCK_FILE
            if lock_path.is_file():
                try:
                    lock_path.unlink(missing_ok=True)
                    actions.append(
                        {
                            "action": "clear_lock_file_on_stall",
                            "removed": True,
                            "warning": "lock_pid_was_alive_workers_may_still_run",
                        }
                    )
                except OSError as exc:
                    actions.append({"action": "clear_lock_file_on_stall", "removed": False, "error": str(exc)})

    result = ensure_m1_unblocked(root)
    actions.append({"action": "ensure_m1_unblocked", "unblocked": result.get("unblocked")})

    from tools.r0_migration_m1_control import m1_hints
    from tools.r0_migration_status_sync import sync_m1_status_artifacts

    sync = sync_m1_status_artifacts(root)
    actions.append({"action": "sync_m1_status_artifacts", **sync})

    health = {
        "schema_version": 1,
        "updated_at_utc": _utc_now(),
        "stall": stall,
        "repair_actions": actions,
        "unblocked": result.get("unblocked"),
        "snapshot": result.get("snapshot"),
        **m1_hints(),
        "m1_completion_summary": sync.get("m1_completion_summary"),
    }
    atomic_write_json(root / HEALTH_PATH.relative_to(ROOT), health)
    return health


def run_outage_check(root: Path, *, repair: bool = True, force: bool = False) -> Dict[str, Any]:
    from tools.r0_migration_phase_guard import is_phase_sealed

    if is_phase_sealed(root, "M1"):
        payload = {"status": "M1_SEALED", "updated_at_utc": _utc_now()}
        atomic_write_json(root / HEALTH_PATH.relative_to(ROOT), payload)
        return payload
    if repair:
        return repair_outage(root, force_stale_lock=force)
    stall = detect_matrix_stall(root)
    payload = {"status": "CHECK_ONLY", "stall": stall, "updated_at_utc": _utc_now()}
    atomic_write_json(root / HEALTH_PATH.relative_to(ROOT), payload)
    return payload

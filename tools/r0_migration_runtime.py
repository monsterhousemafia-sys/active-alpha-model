#!/usr/bin/env python3
"""Shared M1 runtime signals (workers, resume) without duplicating logic."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]


def backtest_workers_cpu_active(root: Path | None = None, *, sample_sec: float = 2.0) -> Dict[str, Any]:
    """Detect CPU growth on validation_runs backtest workers (ignore frozen plain log)."""
    from tools.r0_migration_hw import cpu_delta, list_processes

    root = root or ROOT
    pids = [
        int(p["pid"])
        for p in list_processes()
        if "active_alpha_model.py" in p.get("cmd", "") and "validation_runs" in p.get("cmd", "")
    ]
    if not pids:
        return {"active": False, "pids": [], "delta": 0.0}
    delta = cpu_delta(pids, sample_sec)
    return {"active": delta > 1.0, "pids": pids, "delta": delta}


def count_backtest_workers(root: Path | None = None) -> Dict[str, Any]:
    from tools.r0_migration_hw import list_processes

    root = root or ROOT
    count = sum(
        1
        for p in list_processes()
        if "active_alpha_model.py" in p.get("cmd", "") and "validation_runs" in p.get("cmd", "")
    )
    return {"worker_count": count, "method": "r0_migration_hw"}


def count_validation_matrix_processes(root: Path | None = None) -> int:
    from tools.r0_migration_commander import _lock_holder_pid, _migration_pids, _pid_alive

    root = root or ROOT
    marker = "run_validation_matrix.py"
    pids = [p["pid"] for p in _migration_pids() if marker in p.get("cmd", "")]
    lock_pid = _lock_holder_pid(root)
    if lock_pid > 0 and lock_pid in pids and _pid_alive(lock_pid):
        return 1
    return len(pids)


def matrix_work_in_progress(root: Path) -> bool:
    from aa_runtime_profile import is_batch_work_active

    if count_validation_matrix_processes(root) > 0:
        return True
    if is_batch_work_active(root):
        return True
    return False


def newest_run_dir_for_variant(root: Path, variant_key: str) -> Path | None:
    if variant_key == "R0_LEGACY_ENSEMBLE":
        sla = root / "control" / "r0_migration" / "m1_sla_6h.json"
        if sla.is_file():
            try:
                import json

                stamp = str(json.loads(sla.read_text(encoding="utf-8")).get("canonical_r0_stamp") or "").strip()
                if stamp:
                    preferred = root / "validation_runs" / f"{stamp}_{variant_key}"
                    if preferred.is_dir():
                        return preferred
            except Exception:
                pass
    dirs = sorted(
        [p for p in root.glob(f"validation_runs/*{variant_key}*") if p.is_dir()],
        key=lambda p: p.stat().st_mtime,
    )
    return dirs[-1] if dirs else None

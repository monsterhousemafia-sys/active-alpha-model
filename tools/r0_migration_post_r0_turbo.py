#!/usr/bin/env python3
"""After R0 PASS in-session, relaunch matrix so R3+M1 pick up turbo code (32 cores)."""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

FLAG_DIR = ROOT / "control" / "r0_migration"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _lock_session_stamp(root: Path) -> Optional[str]:
    from aa_runtime_profile import BATCH_LOCK_FILE

    p = root / BATCH_LOCK_FILE
    if not p.is_file():
        return None
    try:
        parts = p.read_text(encoding="utf-8").split()
        for part in parts:
            if part.startswith("validation_") and part.endswith("Z"):
                return part.replace("validation_", "", 1)
    except Exception:
        return None
    return None


def maybe_relaunch_matrix_turbo_after_r0(root: Path) -> Dict[str, Any]:
    """Kill stale matrix parent after R0 PASS; relaunch with skip R0 (turbo R3+M1)."""
    from tools.run_r0_migration_phase_m1 import launch_validation_matrix
    from tools.run_validation_matrix import _is_pass_complete
    from tools.r0_migration_commander import _kill_pids, _migration_pids
    from tools.r0_migration_runtime import count_validation_matrix_processes, matrix_work_in_progress
    from aa_runtime_profile import cleanup_stale_batch_lock, is_batch_work_active

    out: Dict[str, Any] = {"at_utc": _utc_now(), "action": "none"}
    stamp = _lock_session_stamp(root)
    if not stamp:
        out["reason"] = "no_lock_stamp"
        return out

    flag = FLAG_DIR / f"post_r0_turbo_relaunch_{stamp}.json"
    if flag.is_file():
        out["reason"] = "already_relaunched"
        return out

    r0_dir = root / "validation_runs" / f"{stamp}_R0_LEGACY_ENSEMBLE"
    r3_dir = root / "validation_runs" / f"{stamp}_R3_w075_q065_noexit"
    if not r0_dir.is_dir() or not _is_pass_complete(r0_dir):
        out["reason"] = "r0_not_pass_complete"
        return out
    if r3_dir.is_dir() and _is_pass_complete(r3_dir):
        out["reason"] = "r3_already_pass"
        flag.write_text(json.dumps({"skipped": "r3_done", "at_utc": _utc_now()}), encoding="utf-8")
        return out

    if not matrix_work_in_progress(root) and not is_batch_work_active(root):
        out["reason"] = "matrix_not_running"
        return out

    matrix_pids = [p["pid"] for p in _migration_pids() if "run_validation_matrix.py" in p.get("cmd", "")]
    if matrix_pids:
        out["killed_matrix"] = _kill_pids(matrix_pids)
    cleanup_stale_batch_lock(root)
    out["relaunch"] = launch_validation_matrix(
        root,
        no_warm_cache=True,
        cpu_cores=max(1, int(os.cpu_count() or 16)),
        variants=["R3_w075_q065_noexit", "M1_MOM_BLEND_MATCHED_CONTROLS"],
    )
    atomic_write = json.dumps({"at_utc": _utc_now(), "stamp": stamp, "relaunch": out["relaunch"]}, indent=2)
    flag.write_text(atomic_write, encoding="utf-8")
    out["action"] = "relaunched_turbo_r3_m1"
    return out

#!/usr/bin/env python3
"""Stop duplicate matrix/backtest/launcher processes; keep canonical R0 path-only only."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

CANONICAL_R0_STAMP = "20260604T153044Z"
REPORT = ROOT / "evidence" / "r0_migration" / "stop_unnecessary.json"


def stop_unnecessary(root: Path, *, keep_canonical_r0: bool = True) -> Dict[str, Any]:
    from aa_runtime_profile import cleanup_stale_batch_lock
    from aa_safe_io import atomic_write_json
    from tools.r0_migration_commander import _kill_pids, _lock_holder_pid, _migration_pids

    out: Dict[str, Any] = {"actions": []}
    canonical_tag = CANONICAL_R0_STAMP if keep_canonical_r0 else ""

    kills: List[int] = []
    for p in _migration_pids():
        cmd = p.get("cmd", "")
        pid = int(p["pid"])
        if any(
            x in cmd
            for x in (
                "run_validation_matrix.py",
                "run_r0_migration_watch_loop",
                "run_r0_migration_phase_m1",
                "run_r0_migration_m1_matrix",
                "finish_push",
                "eliminate_blockers",
            )
        ):
            kills.append(pid)
            continue
        if "active_alpha_model.py" in cmd and "validation_runs" in cmd:
            if canonical_tag and canonical_tag in cmd:
                continue
            kills.append(pid)

    lock_pid = _lock_holder_pid(root)
    if lock_pid > 0 and lock_pid not in kills:
        kills.append(lock_pid)

    kills = sorted(set(kills))
    if kills:
        out["actions"].append({"killed": _kill_pids(kills)})
    cleanup_stale_batch_lock(root)
    guard = root / "control" / "r0_migration" / "matrix_launch_guard.lock"
    try:
        guard.unlink(missing_ok=True)
    except OSError:
        pass

    from tools.r0_migration_runtime import count_backtest_workers, count_validation_matrix_processes

    out["after"] = {
        "matrix": count_validation_matrix_processes(root),
        "workers": count_backtest_workers(root),
    }
    atomic_write_json(REPORT, out)
    return out


def main() -> int:
    print(json.dumps(stop_unnecessary(ROOT), indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

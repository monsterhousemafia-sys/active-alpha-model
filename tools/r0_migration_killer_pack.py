#!/usr/bin/env python3
"""Last ~5% SLA performance: power plan, affinity, priority, dedupe executives."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

CANONICAL_R0_STAMP = "20260604T153044Z"
REPORT = ROOT / "evidence" / "r0_migration" / "killer_pack.json"


def _migration_pids() -> List[Dict[str, Any]]:
    from tools.r0_migration_commander import _migration_pids as _p

    return _p()


def _boost_process_windows(pid: int, *, affinity_mask: int) -> Dict[str, Any]:
    out: Dict[str, Any] = {"pid": pid}
    if os.name != "nt" or pid <= 0:
        return out
    try:
        import ctypes

        k32 = ctypes.windll.kernel32
        h = k32.OpenProcess(0x1F0FFF, False, int(pid))
        if not h:
            out["error"] = "open_process_failed"
            return out
        k32.SetPriorityClass(h, 0x00000080)  # HIGH_PRIORITY_CLASS
        out["priority"] = "high"
        if affinity_mask > 0:
            prev = ctypes.c_ulonglong()
            if k32.SetProcessAffinityMask(h, ctypes.c_ulonglong(affinity_mask)):
                out["affinity_mask"] = affinity_mask
            else:
                out["affinity_error"] = "set_mask_failed"
        k32.CloseHandle(h)
    except Exception as exc:
        out["error"] = repr(exc)
    return out


def _power_plan_performance() -> Dict[str, Any]:
    if os.name != "nt":
        return {"skipped": "non_windows"}
    out: Dict[str, Any] = {}
    cmds: List[List[str]] = [
        ["/setactive", "8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c"],
        ["/change", "disk-timeout-ac", "0"],
        ["/change", "disk-timeout-dc", "0"],
        # Keep CPU at max P-state on AC (helps single-thread turbo during path-sim).
        ["/setacvalueindex", "SCHEME_CURRENT", "SUB_PROCESSOR", "PROCTHROTTLEMIN", "100"],
        ["/setacvalueindex", "SCHEME_CURRENT", "SUB_PROCESSOR", "PROCTHROTTLEMAX", "100"],
        ["/setacvalueindex", "SCHEME_CURRENT", "SUB_PROCESSOR", "PERFBOOSTMODE", "2"],
        ["/setacvalueindex", "SCHEME_CURRENT", "SUB_PROCESSOR", "PERFINCPOL", "2"],
        ["/setacvalueindex", "SCHEME_CURRENT", "SUB_PROCESSOR", "CPMINCORES", "100"],
        ["/setactive", "SCHEME_CURRENT"],
    ]
    for args in cmds:
        try:
            proc = subprocess.run(
                ["powercfg", *args],
                capture_output=True,
                text=True,
                timeout=15,
            )
            out[" ".join(args)] = proc.returncode
        except Exception as exc:
            out[" ".join(args)] = repr(exc)
    return out


def _dedupe_executives() -> List[int]:
    execs = [
        int(p["pid"])
        for p in _migration_pids()
        if "r0_migration_executive.py" in p.get("cmd", "")
    ]
    if len(execs) <= 1:
        return []
    keep = max(execs)
    from tools.r0_migration_commander import _kill_pids

    return _kill_pids([p for p in execs if p != keep])


def _productive_backtest_pids() -> List[int]:
    """PIDs for active backtest workers in validation_runs (M1 path-sim safe boost)."""
    return sorted(
        {
            int(p["pid"])
            for p in _migration_pids()
            if "active_alpha_model.py" in p.get("cmd", "")
            and "validation_runs" in p.get("cmd", "")
        }
    )


def _canonical_worker_pids() -> List[int]:
    tag = CANONICAL_R0_STAMP
    legacy = [
        int(p["pid"])
        for p in _migration_pids()
        if "active_alpha_model.py" in p.get("cmd", "") and tag in p.get("cmd", "")
    ]
    if legacy:
        return legacy
    return _productive_backtest_pids()


def apply_killer_pack(root: Path, *, affinity: bool = False) -> Dict[str, Any]:
    """Safe runtime boost: power plan + HIGH priority. Affinity off by default (no restart needed)."""
    from aa_safe_io import atomic_write_json

    cpus = max(1, int(os.cpu_count() or 32))
    affinity_mask = ((1 << min(cpus, 64)) - 1) if affinity else 0
    targets = _productive_backtest_pids()
    result: Dict[str, Any] = {
        "cpus": cpus,
        "affinity_enabled": affinity,
        "target_pids": targets,
        "power": _power_plan_performance(),
        "executive_deduped": _dedupe_executives(),
        "boosted": [_boost_process_windows(pid, affinity_mask=affinity_mask) for pid in targets],
    }
    atomic_write_json(REPORT, result)
    return result


def killer_subprocess_env(base: Dict[str, str]) -> Dict[str, str]:
    """Extra env for turbo children (last 5%)."""
    env = dict(base)
    cpus = str(max(1, int(os.cpu_count() or 32)))
    env["AA_CPU_CORES"] = cpus
    env["AA_RESERVE_CPU_CORES"] = "0"
    env["AA_PROCESS_PRIORITY"] = "high"
    env["AA_PLAIN_PROGRESS_QUIET"] = "1"
    env["PYTHONUNBUFFERED"] = "1"
    env["AA_KILLER_PACK"] = "1"
    for key in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
        env.setdefault(key, "1")
    return env


def main() -> int:
    import argparse

    p = argparse.ArgumentParser(description="Safe M1 hardware boost (power + priority, no n_jobs change).")
    p.add_argument("--affinity", action="store_true", help="Also pin to all CPU cores (optional).")
    args = p.parse_args()
    from tools.r0_migration_hw import prevent_sleep_on

    out = apply_killer_pack(ROOT, affinity=args.affinity)
    out["prevent_sleep"] = prevent_sleep_on()
    print(json.dumps(out, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

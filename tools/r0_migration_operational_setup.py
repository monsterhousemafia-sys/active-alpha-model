#!/usr/bin/env python3
"""Remove M1 operational blockers: sleep, scheduler (no admin), watch-loop singleton."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

SETUP_JSON = ROOT / "evidence" / "r0_migration" / "operational_setup.json"
WATCH_PID = ROOT / "evidence" / "r0_migration" / "watch_loop.pid"
HKCU_RUN_NAME = "R0MigrationM1Logon"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        import ctypes

        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        handle = ctypes.windll.kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if handle:
            ctypes.windll.kernel32.CloseHandle(handle)
            return True
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _watch_loop_running(root: Path) -> Optional[int]:
    if not WATCH_PID.is_file():
        return None
    try:
        pid = int(WATCH_PID.read_text(encoding="utf-8").strip().split()[0])
    except Exception:
        return None
    if _pid_alive(pid):
        return pid
    return None


def register_scheduled_tasks(root: Path) -> Dict[str, Any]:
    return {"ok": False, "method": "retired", "reason": "use tools/_m1_autoseal.py or wsl_conductor.sh autoseal"}


def register_hkcu_logon_fallback(root: Path) -> Dict[str, Any]:
    if os.name != "nt":
        return {"ok": False, "reason": "non_windows"}
    from tools.r0_migration_hw import python_executable

    py = python_executable(root)
    worker_cmd = f'"{py}" -u "{root / "tools" / "r0_migration_scheduled_worker.py"}"'
    script = (
        f'$k = "HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Run"; '
        f'Set-ItemProperty -Path $k -Name "{HKCU_RUN_NAME}" -Value {json.dumps(worker_cmd)} -Force'
    )
    proc = subprocess.run(
        ["powershell", "-NoProfile", "-Command", script],
        capture_output=True,
        text=True,
        timeout=30,
        cwd=str(root),
    )
    return {
        "ok": proc.returncode == 0,
        "exit_code": proc.returncode,
        "method": "hkcu_run",
        "value": worker_cmd,
    }


def ensure_prevent_sleep(root: Path) -> Dict[str, Any]:
    from tools.r0_migration_hw import prevent_sleep_on

    return prevent_sleep_on()


def ensure_watch_loop(root: Path, *, start: bool = True) -> Dict[str, Any]:
    WATCH_PID.parent.mkdir(parents=True, exist_ok=True)
    existing = _watch_loop_running(root)
    if existing:
        return {"ok": True, "started": False, "pid": existing, "reason": "already_running"}
    if not start:
        return {"ok": False, "started": False, "reason": "not_started"}
    from tools.r0_migration_hw import python_executable

    py = Path(python_executable(root))
    script = root / "tools" / "run_r0_migration_watch_loop.py"
    proc = subprocess.Popen(
        [str(py), str(script)],
        cwd=str(root),
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
        if os.name == "nt"
        else 0,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
    )
    WATCH_PID.write_text(f"{proc.pid}\n", encoding="utf-8")
    return {"ok": True, "started": True, "pid": proc.pid}


def run_operational_setup(root: Path, *, start_watch_loop: bool = True) -> Dict[str, Any]:
    from aa_safe_io import atomic_write_json
    from tools.r0_migration_outage_guard import run_outage_check
    from tools.r0_migration_phase_guard import is_phase_sealed

    result: Dict[str, Any] = {
        "started_at_utc": _utc_now(),
        "steps": [],
    }
    result["steps"].append({"prevent_sleep": ensure_prevent_sleep(root)})
    sched = register_scheduled_tasks(root)
    result["steps"].append({"scheduled_tasks": sched})
    if not sched.get("ok"):
        hkcu = register_hkcu_logon_fallback(root)
        result["steps"].append({"hkcu_logon_fallback": hkcu})
    race = root / "control" / "r0_migration" / "m1_race_mode.json"
    if start_watch_loop and not race.is_file():
        result["steps"].append({"watch_loop": ensure_watch_loop(root)})
    elif start_watch_loop:
        result["steps"].append({"watch_loop": {"skipped": True, "reason": "m1_race_mode"}})
    if not is_phase_sealed(root, "M1"):
        result["steps"].append({"outage_repair": run_outage_check(root, repair=True)})
        from tools.r0_migration_scheduled_worker import run_worker

        result["steps"].append({"worker_tick": run_worker(root)})
    result["finished_at_utc"] = _utc_now()
    result["blockers_remaining"] = _remaining_blockers(root)
    atomic_write_json(SETUP_JSON, result)
    return result


def _remaining_blockers(root: Path) -> List[str]:
    from tools.r0_migration_crash_guard import _m1_blockers, _m1_returns_complete
    from aa_runtime_profile import is_batch_work_active

    blockers: List[str] = []
    if not _m1_returns_complete(root):
        blockers.append("M1_VARIANT_RETURNS_MISSING")
    if is_batch_work_active(root):
        blockers.append("MATRIX_RUNNING")
    blockers.extend(b for b in _m1_blockers(root) if b not in blockers)
    return blockers


def main() -> int:
    import argparse

    p = argparse.ArgumentParser(description="R0 M1 operational setup (no admin where possible).")
    p.add_argument("--no-watch-loop", action="store_true")
    p.add_argument("--json", action="store_true")
    args = p.parse_args()
    result = run_operational_setup(ROOT, start_watch_loop=not args.no_watch_loop)
    if args.json:
        print(json.dumps(result, indent=2, default=str))
    else:
        print(json.dumps(result.get("blockers_remaining"), default=str))
        for step in result.get("steps") or []:
            print(step)
    sched = next((s for s in result.get("steps") or [] if "scheduled_tasks" in s), {})
    if not (sched.get("scheduled_tasks") or {}).get("ok"):
        return 1
    # Exit 0 when automation is wired; M1 evidence blockers are expected until matrix finishes.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

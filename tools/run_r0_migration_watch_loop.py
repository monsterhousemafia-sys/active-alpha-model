#!/usr/bin/env python3
"""Background watch: run scheduled worker every 30 min until M1 sealed."""
from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

LOG = ROOT / "evidence" / "r0_migration" / "watch_loop.log"
PID_FILE = ROOT / "evidence" / "r0_migration" / "watch_loop.pid"
INTERVAL_SEC = 30 * 60
TICK_INTERVAL_SEC = 5 * 60


def _log(msg: str) -> None:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    with LOG.open("a", encoding="utf-8") as f:
        f.write(f"{ts} {msg}\n")
    print(msg, flush=True)


def _enforce_singularity() -> None:
    """Kill duplicate matrix/watch/M1 launchers (commander-lite)."""
    from tools.r0_migration_commander import _migration_pids, _kill_pids

    pids = _migration_pids()
    matrix = [p for p in pids if "run_validation_matrix.py" in p.get("cmd", "")]
    watches = [p for p in pids if "watch_loop" in p.get("cmd", "")]
    m1 = [p for p in pids if "run_r0_migration_phase_m1" in p.get("cmd", "")]
    import os

    my = os.getpid()
    dup: list[int] = []
    if len(matrix) > 1:
        from tools.r0_migration_commander import _kill_orphan_matrix_processes

        stopped = _kill_orphan_matrix_processes(ROOT)
        if stopped:
            _log(f"singularity: orphan_matrix_killed={stopped}")
    if len(watches) > 1:
        dup += [p["pid"] for p in watches if p["pid"] != my]
    if len(m1) > 1:
        dup += [p["pid"] for p in m1[1:]]
    if dup:
        _log(f"singularity: stopping duplicate pids={dup}")
        _kill_pids(dup)


def _tick() -> str:
    from tools.r0_migration_active_scope import sync_program_focus
    from tools.r0_migration_phase_guard import is_phase_sealed
    from tools.r0_migration_scheduled_worker import run_worker

    sync_program_focus(ROOT)
    _enforce_singularity()

    if is_phase_sealed(ROOT, "M2"):
        return "DONE_M2_SEALED"
    if is_phase_sealed(ROOT, "M1"):
        _log("M1 SEALED — starting post-M1 orchestrator")
        from tools.run_r0_migration_phase_orchestrator import run_orchestrator

        orch = run_orchestrator(ROOT)
        _log(f"orchestrator status={orch.get('status')}")
        return str(orch.get("status") or "ORCH")
    from tools.r0_migration_runtime import matrix_work_in_progress

    if matrix_work_in_progress(ROOT):
        _log("tick HOLD matrix active")
        return "HOLD_MATRIX_ACTIVE"
    from tools.r0_migration_finish_push import run_finish_push

    push = run_finish_push(ROOT)
    _log(f"finish_push verdict={push.get('verdict')}")
    result = run_worker(ROOT)
    _log(f"worker action={result.get('action')}")
    if str(result.get("action")) == "DONE_M1_SEALED":
        from tools.run_r0_migration_phase_orchestrator import run_orchestrator

        orch = run_orchestrator(ROOT)
        _log(f"orchestrator after seal status={orch.get('status')}")
    return str(result.get("action") or "TICK")


def _pid_alive(pid: int) -> bool:
    import os

    if pid <= 0:
        return False
    if os.name == "nt":
        import ctypes

        h = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
        if h:
            ctypes.windll.kernel32.CloseHandle(h)
            return True
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _acquire_singleton() -> bool:
    import os

    PID_FILE.parent.mkdir(parents=True, exist_ok=True)
    if PID_FILE.is_file():
        try:
            old = int(PID_FILE.read_text(encoding="utf-8").strip().split()[0])
        except Exception:
            old = 0
        if old > 0 and old != os.getpid() and _pid_alive(old):
            return False
    PID_FILE.write_text(f"{os.getpid()}\n", encoding="utf-8")
    return True


def main() -> int:
    import os

    from tools.r0_migration_outage_guard import run_outage_check
    from tools.r0_migration_phase_guard import is_phase_sealed

    if (ROOT / "control" / "r0_migration" / "m1_race_mode.json").is_file():
        print("watch_loop disabled (m1_race_mode)", flush=True)
        return 0

    if not _acquire_singleton():
        print("watch_loop already running — exit", flush=True)
        return 0
    from tools.r0_migration_active_scope import sync_program_focus

    sync_program_focus(ROOT)
    _log(f"watch_loop started pid={os.getpid()} (5m tick, finish_push; M2 only after M1 seal)")
    run_outage_check(ROOT, repair=True)
    _tick()
    elapsed = 0
    while True:
        if is_phase_sealed(ROOT, "M2"):
            _log("M2 SEALED — watch_loop done")
            return 0
        if is_phase_sealed(ROOT, "M1"):
            _tick()
        else:
            try:
                _tick()
            except Exception as exc:
                _log(f"tick error={exc!r}")
        time.sleep(TICK_INTERVAL_SEC)
        elapsed += TICK_INTERVAL_SEC
        if elapsed >= INTERVAL_SEC:
            run_outage_check(ROOT, repair=True)
            elapsed = 0


if __name__ == "__main__":
    raise SystemExit(main())

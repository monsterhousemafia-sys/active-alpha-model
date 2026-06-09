#!/usr/bin/env python3
"""Executive M1 keepalive: one matrix, dedupe only, restart only when dead/stuck."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

LOG = ROOT / "evidence" / "r0_migration" / "executive_keepalive.log"
PID_FILE = ROOT / "evidence" / "r0_migration" / "executive_keepalive.pid"
def _executive_tick_sec(root: Path) -> int:
    sla = root / "control" / "r0_migration" / "m1_sla_6h.json"
    if sla.is_file():
        try:
            data = json.loads(sla.read_text(encoding="utf-8"))
            if data.get("deadline_enforced"):
                race = root / "control" / "r0_migration" / "m1_race_mode.json"
                if race.is_file() and json.loads(race.read_text(encoding="utf-8")).get("killer_pack"):
                    return 60
                return 90
        except Exception:
            pass
    return 180


TICK_SEC = 180


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _log(msg: str) -> None:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(f"{_utc_now()} {msg}\n")
    print(msg, flush=True)


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name != "nt":
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False
    import ctypes

    h = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
    if h:
        ctypes.windll.kernel32.CloseHandle(h)
        return True
    return False


def _acquire_singleton() -> bool:
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


def executive_tick(root: Path) -> Dict[str, Any]:
    from aa_runtime_profile import cleanup_stale_batch_lock, is_batch_work_active
    from aa_safe_io import atomic_write_json
    from tools.r0_migration_active_scope import sync_program_focus
    from tools.r0_migration_phase_guard import is_phase_sealed, try_seal_phase
    from tools.r0_migration_runtime import count_validation_matrix_processes, matrix_work_in_progress
    from tools.run_r0_migration_phase_m1 import build_returns_manifest

    sync_program_focus(root)
    sla_path = root / "control" / "r0_migration" / "m1_sla_6h.json"
    if sla_path.is_file():
        sla = json.loads(sla_path.read_text(encoding="utf-8"))
        deadline = datetime.fromisoformat(str(sla["sla_deadline_utc"]).replace("Z", "+00:00"))
        remaining_h = (deadline - datetime.now(timezone.utc)).total_seconds() / 3600.0
        out_sla = {"remaining_h": round(remaining_h, 2), "deadline_utc": sla["sla_deadline_utc"]}
    else:
        out_sla = {}
    from tools.r0_migration_commander import _kill_pids, _migration_pids

    blockers = [
        p["pid"]
        for p in _migration_pids()
        if "watch_loop" in p.get("cmd", "")
        or "run_r0_migration_phase_m1" in p.get("cmd", "")
        or "eliminate_blockers" in p.get("cmd", "")
    ]
    if blockers:
        _kill_pids(blockers)

    out: Dict[str, Any] = {"at_utc": _utc_now(), "verdict": "UNKNOWN", "sla": out_sla}

    if is_phase_sealed(root, "M1"):
        out["verdict"] = "M1_SEALED"
        return out

    from tools.r0_migration_hw import prevent_sleep_on

    prevent_sleep_on()

    manifest = build_returns_manifest(root)
    if manifest.get("all_m1_variants_integrity_pass"):
        from tools.run_r0_migration_phase_m1 import run_m1

        run_m1(apply_env_fix=False)
        seal = try_seal_phase(root, "M1")
        out["verdict"] = "SEALED" if seal.get("status") == "SEALED" else "SEAL_FAILED"
        out["seal"] = seal
        return out

    matrix_n = count_validation_matrix_processes(root)
    if matrix_n > 1:
        from tools.r0_migration_commander import _kill_orphan_matrix_processes

        out["dedupe"] = _kill_orphan_matrix_processes(root)
        matrix_n = count_validation_matrix_processes(root)
        if matrix_n > 1:
            from tools.r0_migration_commander import _lock_holder_pid, _kill_pids, _migration_pids

            keep = _lock_holder_pid(root) or max(
                p["pid"] for p in _migration_pids() if "run_validation_matrix.py" in p.get("cmd", "")
            )
            extra = [
                p["pid"]
                for p in _migration_pids()
                if "run_validation_matrix.py" in p.get("cmd", "") and p["pid"] != keep
            ]
            if extra:
                out["dedupe_force"] = _kill_pids(extra[:1])
        out["verdict"] = "DEDUPED_MATRIX"
        if matrix_work_in_progress(root):
            return out

    from tools.r0_migration_sla_enforce import enforce_sla_fast_path

    sla_run = enforce_sla_fast_path(root)
    out["sla_enforce"] = sla_run
    if sla_run.get("verdict") in {
        "HOLD_CANONICAL_R0",
        "DEDUPED_WAIT_CANONICAL_R0",
        "PATH_ONLY_R0_STARTED",
        "TURBO_RELAUNCH_R3_M1",
        "READY_FOR_SEAL",
    }:
        out["verdict"] = str(sla_run.get("verdict"))
        if sla_run.get("verdict") == "READY_FOR_SEAL":
            from tools.run_r0_migration_phase_m1 import run_m1

            run_m1(apply_env_fix=False)
            seal = try_seal_phase(root, "M1")
            out["seal"] = seal
            out["verdict"] = "SEALED" if seal.get("status") == "SEALED" else "SEAL_FAILED"
        return out

    from tools.run_validation_matrix import _is_pass_complete
    from tools.r0_migration_sla_enforce import CANONICAL_R0_STAMP

    r0_dir = root / "validation_runs" / f"{CANONICAL_R0_STAMP}_R0_LEGACY_ENSEMBLE"
    if r0_dir.is_dir() and not _is_pass_complete(r0_dir):
        out["verdict"] = "CANONICAL_R0_FAST_PATH_ONLY"
        out["note"] = "no_full_matrix_until_r0_pass"
        return out

    if matrix_work_in_progress(root) or is_batch_work_active(root):
        cleanup_stale_batch_lock(root)
        if matrix_work_in_progress(root) or is_batch_work_active(root):
            out["verdict"] = "HOLD_LIVE"
            out["matrix_n"] = count_validation_matrix_processes(root)
            return out

    from tools.r0_migration_eliminate_blockers import eliminate_blockers

    out["eliminate"] = eliminate_blockers(root, restart_if_dead=True)
    out["verdict"] = str(out["eliminate"].get("matrix_count_after", 0)) + "_after_restart"
    if count_validation_matrix_processes(root) > 0 or is_batch_work_active(root):
        out["verdict"] = "MATRIX_RUNNING"
    return out


def run_loop(root: Path, *, once: bool = False) -> int:
    if not once and not _acquire_singleton():
        _log("executive already running")
        return 0
    tick_sec = _executive_tick_sec(root)
    _log(f"executive started pid={os.getpid()} tick={tick_sec}s")
    while True:
        try:
            tick = executive_tick(root)
            _log(f"tick verdict={tick.get('verdict')}")
            from aa_safe_io import atomic_write_json

            atomic_write_json(ROOT / "evidence" / "r0_migration" / "executive_last_tick.json", tick)
        except Exception as exc:
            _log(f"tick error={exc!r}")
        if once:
            return 0
        if tick.get("verdict") == "M1_SEALED":
            _log("M1 sealed — executive done")
            return 0
        time.sleep(_executive_tick_sec(root))


def main() -> int:
    import argparse

    from aa_safe_io import atomic_write_json

    p = argparse.ArgumentParser(description="M1 executive keepalive.")
    p.add_argument("--once", action="store_true")
    p.add_argument("--json", action="store_true")
    args = p.parse_args()
    if args.once:
        result = executive_tick(ROOT)
        atomic_write_json(ROOT / "evidence" / "r0_migration" / "executive_last_tick.json", result)
        if args.json:
            print(json.dumps(result, indent=2, default=str))
        return 0
    return run_loop(ROOT, once=False)


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Autonomous M1 progress loop: SLA fast-path only, no full-matrix restarts."""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

LOG = ROOT / "evidence" / "r0_migration" / "progress_guard.log"
REPORT = ROOT / "evidence" / "r0_migration" / "progress_guard_latest.json"
PID_FILE = ROOT / "evidence" / "r0_migration" / "progress_guard.pid"
TICK_SEC = 90


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

    h = ctypes.windll.kernel32.OpenProcess(0x1000, False, int(pid))
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


def _r0_path_progress(root: Path) -> Dict[str, Any]:
    from tools.r0_migration_sla_enforce import canonical_r0_dir

    r0 = canonical_r0_dir(root)
    turbo = r0 / "validation_run_path_turbo.log"
    out: Dict[str, Any] = {"returns": (r0 / "strategy_daily_returns.csv").is_file()}
    if turbo.is_file():
        text = turbo.read_text(encoding="utf-8", errors="replace")
        pct = re.findall(r"PROGRESS.*?\s+(\d+)%", text)
        out["path_pct"] = int(pct[-1]) if pct else 0
        out["log_idle_min"] = round((time.time() - turbo.stat().st_mtime) / 60.0, 1)
    return out


def progress_tick(root: Path) -> Dict[str, Any]:
    from aa_safe_io import atomic_write_json
    from tools.r0_migration_phase_guard import is_phase_sealed, try_seal_phase
    from tools.r0_migration_sla_enforce import enforce_sla_fast_path, sla_fast_path_active
    from tools.run_r0_migration_phase_m1 import build_returns_manifest, run_m1

    out: Dict[str, Any] = {"at_utc": _utc_now(), "progress": _r0_path_progress(root)}

    if is_phase_sealed(root, "M1"):
        out["verdict"] = "M1_SEALED"
        atomic_write_json(REPORT, out)
        return out

    manifest = build_returns_manifest(root)
    out["returns_pass"] = sum(
        1
        for vid in ("R0_LEGACY_ENSEMBLE", "R3_w075_q065_noexit", "M1_MOM_BLEND_MATCHED_CONTROLS")
        if (manifest.get("variants") or {}).get(vid, {}).get("integrity_pass")
    )

    if manifest.get("all_m1_variants_integrity_pass"):
        run_m1(apply_env_fix=False)
        seal = try_seal_phase(root, "M1")
        out["verdict"] = "SEALED" if seal.get("status") == "SEALED" else "SEAL_FAILED"
        out["seal"] = seal
        atomic_write_json(REPORT, out)
        return out

    if sla_fast_path_active(root):
        out["sla_enforce"] = enforce_sla_fast_path(root)
        out["verdict"] = str(out["sla_enforce"].get("verdict", "SLA"))
    else:
        from tools.r0_migration_executive import executive_tick

        out["executive"] = executive_tick(root)
        out["verdict"] = str(out["executive"].get("verdict", "EXEC"))

    atomic_write_json(REPORT, out)
    return out


def run_loop(root: Path, *, once: bool = False, tick_sec: int = TICK_SEC) -> int:
    if not once and not _acquire_singleton():
        _log("progress_guard already running")
        return 0
    _log(f"progress_guard started pid={os.getpid()} tick={tick_sec}s")
    while True:
        try:
            tick = progress_tick(root)
            _log(
                f"tick verdict={tick.get('verdict')} returns={tick.get('returns_pass', '?')}/3 "
                f"path_pct={tick.get('progress', {}).get('path_pct', '-')}"
            )
        except Exception as exc:
            _log(f"tick error={exc!r}")
        if once:
            return 0
        if tick.get("verdict") == "M1_SEALED":
            _log("M1 sealed — guard done")
            return 0
        time.sleep(max(30, int(tick_sec)))


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--once", action="store_true")
    p.add_argument("--tick-sec", type=int, default=TICK_SEC)
    args = p.parse_args()
    return run_loop(ROOT, once=args.once, tick_sec=args.tick_sec)


if __name__ == "__main__":
    raise SystemExit(main())

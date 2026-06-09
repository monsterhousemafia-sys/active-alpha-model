#!/usr/bin/env python3
"""Stop hung M1 validation-matrix Python workers and release batch lock (M1 only)."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aa_runtime_profile import BATCH_LOCK_FILE, cleanup_stale_batch_lock  # noqa: E402
from aa_safe_io import atomic_write_json  # noqa: E402

LOG = ROOT / "evidence" / "r0_migration" / "stop_hung_matrix.json"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _matrix_pids_windows() -> List[int]:
    script = (
        "Get-CimInstance Win32_Process -Filter \"name='python.exe'\" -ErrorAction SilentlyContinue | "
        "Where-Object { $_.CommandLine -match 'validation_matrix|validation_runs|active_alpha_model' } | "
        "Select-Object -ExpandProperty ProcessId"
    )
    proc = subprocess.run(
        ["powershell", "-NoProfile", "-Command", script],
        capture_output=True,
        text=True,
        timeout=60,
        cwd=str(ROOT),
    )
    pids: List[int] = []
    for line in (proc.stdout or "").splitlines():
        line = line.strip()
        if line.isdigit():
            pids.append(int(line))
    return sorted(set(pids))


def stop_hung_matrix(root: Path, *, dry_run: bool = False) -> Dict[str, Any]:
    lock_pid = 0
    lock_path = root / BATCH_LOCK_FILE
    if lock_path.is_file():
        try:
            lock_pid = int(lock_path.read_text(encoding="utf-8").split()[0])
        except Exception:
            lock_pid = 0

    worker_pids = _matrix_pids_windows() if os.name == "nt" else []
    targets = sorted(set(worker_pids + ([lock_pid] if lock_pid > 0 else [])))

    stopped: List[int] = []
    errors: List[Dict[str, Any]] = []
    if not dry_run:
        for pid in targets:
            if pid <= 0:
                continue
            try:
                subprocess.run(
                    ["taskkill", "/PID", str(pid), "/F", "/T"],
                    capture_output=True,
                    timeout=30,
                )
                stopped.append(pid)
            except Exception as exc:
                errors.append({"pid": pid, "error": str(exc)})
        cleanup_stale_batch_lock(root)
        if lock_path.is_file():
            try:
                lock_path.unlink(missing_ok=True)
            except OSError as exc:
                errors.append({"lock_unlink": str(exc)})

    payload = {
        "stopped_at_utc": _utc_now(),
        "dry_run": dry_run,
        "target_pids": targets,
        "stopped_pids": stopped,
        "errors": errors,
        "lock_cleared": not (root / BATCH_LOCK_FILE).is_file(),
    }
    if not dry_run:
        atomic_write_json(LOG, payload)
    return payload


def main() -> int:
    import argparse

    p = argparse.ArgumentParser()
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--json", action="store_true")
    args = p.parse_args()
    result = stop_hung_matrix(ROOT, dry_run=args.dry_run)
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"stopped={len(result.get('stopped_pids') or [])} lock_cleared={result.get('lock_cleared')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

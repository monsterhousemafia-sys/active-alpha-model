"""Kernel Observer — eBPF wenn verfügbar, sonst /proc-Fallback."""
from __future__ import annotations

import json
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from aa_safe_io import atomic_write_json

_EVIDENCE_REL = Path("evidence/ebpf_observer_latest.json")


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _proc_fallback() -> Dict[str, Any]:
    out: Dict[str, Any] = {"mode": "proc", "samples": []}
    try:
        proc = subprocess.run(
            ["ps", "-eo", "pid,pcpu,pmem,args"],
            capture_output=True,
            text=True,
            timeout=4,
            check=False,
        )
        for line in (proc.stdout or "").splitlines()[1:]:
            if "active_alpha" not in line.lower() and "preview_hub" not in line:
                continue
            if "grep" in line:
                continue
            parts = line.split(None, 3)
            if len(parts) >= 4:
                out["samples"].append(
                    {"pid": parts[0], "cpu": parts[1], "mem": parts[2], "cmd": parts[3][:200]}
                )
    except (OSError, subprocess.TimeoutExpired):
        pass
    return out


def _bpftrace_probe() -> Dict[str, Any]:
    if not shutil.which("bpftrace"):
        return {"mode": "unavailable", "detail_de": "bpftrace optional — proc fallback"}
    try:
        proc = subprocess.run(
            ["bpftrace", "-e", 'BEGIN { printf("ok"); exit(); }'],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if proc.returncode == 0:
            return {"mode": "bpftrace", "available": True}
    except (OSError, subprocess.TimeoutExpired):
        pass
    return {"mode": "bpftrace", "available": False}


def run_kernel_observer(root: Path) -> Dict[str, Any]:
    root = Path(root)
    bpf = _bpftrace_probe()
    proc = _proc_fallback()
    fd_pressure: List[Dict[str, str]] = []
    for pid_dir in Path("/proc").glob("[0-9]*"):
        try:
            fd_path = pid_dir / "fd"
            if not fd_path.is_dir():
                continue
            cmdline = (pid_dir / "cmdline").read_bytes().replace(b"\x00", b" ").decode("utf-8", errors="replace")
            if "preview_hub" not in cmdline and "run_validation_matrix" not in cmdline:
                continue
            count = sum(1 for _ in fd_path.iterdir())
            if count > 200:
                fd_pressure.append({"pid": pid_dir.name, "fds": str(count), "cmd": cmdline[:120]})
        except OSError:
            continue

    doc = {
        "schema_version": 1,
        "observed_at_utc": _utc_now(),
        "ebpf": bpf,
        "processes": proc,
        "fd_pressure": fd_pressure[:10],
        "headline_de": (
            "FD-Druck erkannt" if fd_pressure else "Kernel-Observer OK (proc/bpftrace)"
        ),
        "ok": len(fd_pressure) == 0,
    }
    atomic_write_json(root / _EVIDENCE_REL, doc)
    return doc

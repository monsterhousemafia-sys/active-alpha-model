#!/usr/bin/env python3
"""Cross-platform process + CPU probes for r0_migration (WSL/Linux + Windows).

Single source of truth — no PowerShell in call sites. Replaces scattered CIM/taskkill
fragments that returned empty stubs on Linux.
"""
from __future__ import annotations

import os
import signal
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

MIGRATION_CMD_MARKERS = (
    "validation_matrix",
    "active_alpha_model.py",
    "run_r0_migration_phase_m1",
    "run_r0_migration_watch_loop",
    "_m1_autoseal",
)


def _clk_tck() -> float:
    try:
        return float(os.sysconf("SC_CLK_TCK"))  # type: ignore[attr-defined]
    except (AttributeError, ValueError, OSError):
        return 100.0


def pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        try:
            import ctypes

            h = ctypes.windll.kernel32.OpenProcess(0x1000, False, int(pid))
            if h:
                ctypes.windll.kernel32.CloseHandle(h)
                return True
            return False
        except Exception:
            return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _linux_cmdline(pid: int) -> str:
    p = Path(f"/proc/{pid}/cmdline")
    if not p.is_file():
        return ""
    try:
        return p.read_bytes().replace(b"\0", b" ").decode("utf-8", errors="replace").strip()
    except OSError:
        return ""


def _linux_ppid(pid: int) -> int:
    stat = Path(f"/proc/{pid}/stat")
    if not stat.is_file():
        return 0
    try:
        # comm may contain spaces/parens — parse from last ')'
        raw = stat.read_text(encoding="utf-8", errors="replace")
        _, rest = raw.split(")", 1)
        parts = rest.split()
        return int(parts[1])  # ppid after state
    except (OSError, ValueError, IndexError):
        return 0


def _linux_cpu_seconds(pid: int) -> float:
    stat = Path(f"/proc/{pid}/stat")
    if not stat.is_file():
        return 0.0
    try:
        raw = stat.read_text(encoding="utf-8", errors="replace")
        _, rest = raw.split(")", 1)
        parts = rest.split()
        utime = float(parts[11])
        stime = float(parts[12])
        return (utime + stime) / _clk_tck()
    except (OSError, ValueError, IndexError):
        return 0.0


def _win_cpu_seconds(pid: int) -> float:
    script = (
        f"(Get-Process -Id {int(pid)} -ErrorAction SilentlyContinue | "
        "Select-Object -ExpandProperty CPU)"
    )
    try:
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-Command", script],
            capture_output=True,
            text=True,
            timeout=10,
        )
        raw = (proc.stdout or "0").strip().replace(",", ".")
        return float(raw or "0")
    except Exception:
        return 0.0


def process_cpu_seconds(pid: int) -> float:
    if pid <= 0:
        return 0.0
    if os.name == "nt":
        return _win_cpu_seconds(pid)
    return _linux_cpu_seconds(pid)


def cpu_total(pids: Sequence[int]) -> float:
    return sum(process_cpu_seconds(int(p)) for p in pids if int(p) > 0)


def cpu_delta(pids: Sequence[int], sample_sec: float = 2.0) -> float:
    c0 = cpu_total(pids)
    time.sleep(max(0.5, min(float(sample_sec), 8.0)))
    c1 = cpu_total(pids)
    return round(c1 - c0, 2)


def list_processes(
    *,
    name_substrings: Optional[Sequence[str]] = None,
    cmd_markers: Optional[Sequence[str]] = None,
) -> List[Dict[str, Any]]:
    """Return [{pid, cmd, ppid}] for processes matching filters."""
    markers = list(cmd_markers or MIGRATION_CMD_MARKERS)
    subs = [s.lower() for s in (name_substrings or ("python",))]
    out: List[Dict[str, Any]] = []

    if os.name == "nt":
        script = (
            "Get-CimInstance Win32_Process -Filter \"name='python.exe'\" | "
            "ForEach-Object { $_.ProcessId.ToString() + '|' + $_.ParentProcessId.ToString() + '|' + $_.CommandLine }"
        )
        try:
            proc = subprocess.run(
                ["powershell", "-NoProfile", "-Command", script],
                capture_output=True,
                text=True,
                timeout=60,
            )
            for line in (proc.stdout or "").splitlines():
                if "|" not in line:
                    continue
                parts = line.split("|", 2)
                if len(parts) < 3:
                    continue
                pid_s, ppid_s, cmd = parts[0].strip(), parts[1].strip(), parts[2].strip()
                if not pid_s.isdigit():
                    continue
                cmd_l = cmd.lower()
                if subs and not any(s in cmd_l for s in subs):
                    continue
                if markers and not any(m in cmd for m in markers):
                    continue
                out.append({"pid": int(pid_s), "ppid": int(ppid_s) if ppid_s.isdigit() else 0, "cmd": cmd[:4000]})
        except Exception:
            return []
        return out

    proc_root = Path("/proc")
    if not proc_root.is_dir():
        return []
    for entry in proc_root.iterdir():
        if not entry.name.isdigit():
            continue
        pid = int(entry.name)
        cmd = _linux_cmdline(pid)
        if not cmd:
            continue
        cmd_l = cmd.lower()
        if subs and not any(s in cmd_l for s in subs):
            continue
        if markers and not any(m in cmd for m in markers):
            continue
        out.append({"pid": pid, "ppid": _linux_ppid(pid), "cmd": cmd[:4000]})
    return out


def count_processes(cmd_contains: str) -> int:
    n = 0
    for p in list_processes(cmd_markers=(cmd_contains,)):
        if cmd_contains in p.get("cmd", ""):
            n += 1
    return n


def kill_pids(pids: Sequence[int], *, force: bool = True) -> List[int]:
    stopped: List[int] = []
    for pid in sorted(set(int(p) for p in pids if int(p) > 0)):
        try:
            if os.name == "nt":
                subprocess.run(
                    ["taskkill", "/PID", str(pid), "/F"],
                    capture_output=True,
                    timeout=30,
                )
            else:
                sig = signal.SIGKILL if force else signal.SIGTERM
                os.kill(pid, sig)
            stopped.append(pid)
        except (OSError, subprocess.SubprocessError):
            continue
    return stopped


def nproc() -> int:
    if hasattr(os, "cpu_count") and os.cpu_count():
        return int(os.cpu_count())
    return 4


def python_executable(root: Path) -> str:
    if os.name == "nt":
        venv = root / ".venv" / "Scripts" / "python.exe"
        if venv.is_file():
            return str(venv)
    else:
        venv = root / ".venv" / "bin" / "python3"
        if venv.is_file():
            return str(venv)
    return "python3" if os.name != "nt" else "python"


def prevent_sleep_on() -> Dict[str, Any]:
    """Keep PC awake during long matrix runs (Windows only; no-op on Linux/WSL)."""
    if os.name != "nt":
        return {"skipped": "non_windows"}
    cmds = [
        ["/change", "standby-timeout-ac", "0"],
        ["/change", "hibernate-timeout-ac", "0"],
        ["/change", "monitor-timeout-ac", "0"],
        ["/change", "standby-timeout-dc", "0"],
        ["/change", "hibernate-timeout-dc", "0"],
        ["/change", "monitor-timeout-dc", "0"],
        ["/setacvalueindex", "SCHEME_CURRENT", "SUB_SLEEP", "HYBRIDSLEEP", "0"],
        ["/setdcvalueindex", "SCHEME_CURRENT", "SUB_SLEEP", "HYBRIDSLEEP", "0"],
        ["/setactive", "SCHEME_CURRENT"],
    ]
    for args in cmds:
        subprocess.run(["powercfg", *args], capture_output=True, timeout=15)
    subprocess.run(["powercfg", "/hibernate", "off"], capture_output=True, timeout=15)
    return {"ok": True}


def prevent_sleep_off() -> Dict[str, Any]:
    if os.name != "nt":
        return {"skipped": "non_windows"}
    for args in (
        ["/change", "standby-timeout-ac", "30"],
        ["/change", "monitor-timeout-ac", "15"],
        ["/change", "standby-timeout-dc", "15"],
        ["/change", "monitor-timeout-dc", "10"],
        ["/setactive", "SCHEME_CURRENT"],
    ):
        subprocess.run(["powercfg", *args], capture_output=True, timeout=15)
    return {"ok": True}

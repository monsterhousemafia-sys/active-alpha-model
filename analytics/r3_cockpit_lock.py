"""R3 Cockpit — Single-Instance Lock (Qt-Prozess, kein Hub).

Hub/Mirror/Orchestrierung: analytics.stack_integrity
"""
from __future__ import annotations

import fcntl
import os
import subprocess
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Iterator, Optional

_PID_NAME = "cockpit.pid"
_LAUNCH_LOCK_NAME = "cockpit.launch.lock"
_SPAWN_VERIFY_SEC = 2.5


def _share_dir() -> Path:
    p = Path.home() / ".local/share/r3-os"
    p.mkdir(parents=True, exist_ok=True)
    return p


def cockpit_pid_path() -> Path:
    return _share_dir() / _PID_NAME


def _launch_lock_path() -> Path:
    return _share_dir() / _LAUNCH_LOCK_NAME


@contextmanager
def _cockpit_launch_lock() -> Iterator[bool]:
    path = _launch_lock_path()
    fh = path.open("a+", encoding="utf-8")
    acquired = False
    try:
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        acquired = True
        yield True
    except BlockingIOError:
        yield False
    finally:
        if acquired:
            try:
                fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
            except OSError:
                pass
        try:
            fh.close()
        except OSError:
            pass


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    try:
        proc = subprocess.run(
            ["ps", "-p", str(pid), "-o", "args="],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
        cmd = (proc.stdout or "").strip()
        return "r3_local_cockpit" in cmd or "run_native_cockpit_app" in cmd
    except (OSError, subprocess.TimeoutExpired):
        return False


def read_cockpit_pid() -> Optional[int]:
    path = cockpit_pid_path()
    if not path.is_file():
        return None
    try:
        return int(path.read_text(encoding="utf-8").strip().split()[0])
    except (ValueError, OSError):
        return None


def write_cockpit_pid(pid: int) -> None:
    from aa_safe_io import atomic_write_text

    atomic_write_text(cockpit_pid_path(), f"{int(pid)}\n")


def clear_cockpit_pid() -> None:
    path = cockpit_pid_path()
    if not path.is_file():
        return
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass


def clear_cockpit_pid_if_self() -> None:
    try:
        pid = read_cockpit_pid()
        if pid is not None and pid == os.getpid():
            clear_cockpit_pid()
    except OSError:
        pass


def is_cockpit_running() -> bool:
    try:
        pid = read_cockpit_pid()
        if pid is None:
            return False
        if not _pid_alive(pid):
            clear_cockpit_pid()
            return False
        return True
    except OSError:
        return False


def _spawn_alive(pid: int, *, grace_sec: float = _SPAWN_VERIFY_SEC) -> bool:
    if pid <= 0:
        return False
    deadline = time.monotonic() + max(0.2, float(grace_sec))
    while time.monotonic() < deadline:
        try:
            os.kill(pid, 0)
        except OSError:
            return False
        time.sleep(0.15)
    return True


def launch_cockpit_once(
    root: Path,
    *,
    surface_path: Optional[str] = None,
    block: bool = False,
) -> Dict[str, Any]:
    """Maximal ein Qt-Cockpit — kein Hub-Start."""
    from analytics.r3_runtime import default_surface_path

    root = Path(root)
    path = surface_path or default_surface_path(root)
    with _cockpit_launch_lock() as locked:
        if not locked:
            return {
                "ok": True,
                "already_running": True,
                "surface_path": path,
                "pid": read_cockpit_pid(),
                "message_de": "R3 Start läuft bereits — bitte kurz warten.",
            }
        if is_cockpit_running():
            return {
                "ok": True,
                "already_running": True,
                "surface_path": path,
                "pid": read_cockpit_pid(),
                "message_de": "R3 Cockpit läuft bereits — kein zweites Fenster.",
            }
        try:
            from analytics.r3_local_cockpit import launch_session_cockpit

            doc = launch_session_cockpit(root, hub_path=path, fullscreen=True, block=block)
        except Exception as exc:
            clear_cockpit_pid()
            return {
                "ok": False,
                "surface_path": path,
                "error_de": f"Cockpit-Start fehlgeschlagen: {exc}"[:200],
            }
        pid = doc.get("pid")
        if doc.get("ok") and pid:
            try:
                pid_i = int(pid)
            except (TypeError, ValueError):
                pid_i = 0
            if pid_i > 0 and _spawn_alive(pid_i):
                write_cockpit_pid(pid_i)
            elif not block:
                doc = {
                    **doc,
                    "ok": False,
                    "error_de": "Cockpit-Prozess beendet sich sofort — Qt/Display prüfen.",
                }
                clear_cockpit_pid()
        elif not doc.get("ok"):
            clear_cockpit_pid()
        return {**doc, "surface_path": path}


def register_cockpit_pid_at_start() -> None:
    write_cockpit_pid(os.getpid())

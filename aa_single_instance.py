"""Ensure only one Marktanalyse.exe main window runs at a time."""
from __future__ import annotations

import hashlib
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from aa_runtime_guards import multi_instance_bypass_allowed

APP_LOCK_FILE = ".marktanalyse_app.lock"
APP_MUTEX_PREFIX = "Global\\MarktanalyseR3_"


class SingleInstanceGuard:
    """Holds a Windows mutex (or file lock) until release/exit."""

    def __init__(self, *, handle: Optional[int] = None, lock_path: Optional[Path] = None) -> None:
        self._handle = handle
        self._lock_path = lock_path

    def release(self) -> None:
        if sys.platform == "win32" and self._handle:
            try:
                ctypes = __import__("ctypes")
                ctypes.windll.kernel32.CloseHandle(self._handle)
            except Exception:
                pass
            self._handle = None
        if self._lock_path is not None and self._lock_path.is_file():
            try:
                self._lock_path.unlink(missing_ok=True)
            except OSError:
                pass

    def __enter__(self) -> "SingleInstanceGuard":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.release()


def _mutex_name(root: Path) -> str:
    try:
        key = os.path.normcase(str(root.resolve()))
    except OSError:
        key = os.path.normcase(str(Path(root)))
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]
    return f"{APP_MUTEX_PREFIX}{digest}"


def _try_windows_mutex(name: str) -> tuple[Optional[int], bool]:
    """Return (handle, already_exists). handle is set only for the owning process."""
    if sys.platform != "win32":
        return None, False
    import ctypes

    kernel32 = ctypes.windll.kernel32
    ERROR_ALREADY_EXISTS = 183
    kernel32.SetLastError(0)
    handle = kernel32.CreateMutexW(None, True, name)
    last_error = kernel32.GetLastError()
    if not handle:
        return None, False
    if last_error == ERROR_ALREADY_EXISTS:
        kernel32.CloseHandle(handle)
        return None, True
    return int(handle), False


def _write_instance_lock_file(root: Path) -> Optional[Path]:
    path = root / APP_LOCK_FILE
    try:
        path.write_text(f"{os.getpid()} {datetime.now(timezone.utc).isoformat()}\n", encoding="utf-8")
        return path
    except OSError:
        return None


def _lock_file_held_by_other(root: Path) -> bool:
    path = root / APP_LOCK_FILE
    if not path.is_file():
        return False
    try:
        pid = int(path.read_text(encoding="utf-8").strip().split()[0])
        return _pid_alive(pid) and pid != os.getpid()
    except Exception:
        return False


def _try_file_lock(root: Path) -> Optional[Path]:
    path = root / APP_LOCK_FILE
    if path.is_file():
        try:
            raw = path.read_text(encoding="utf-8").strip()
            pid = int(raw.split()[0])
            if _pid_alive(pid):
                return None
        except Exception:
            return None
        path.unlink(missing_ok=True)
    try:
        path.write_text(f"{os.getpid()} {datetime.now(timezone.utc).isoformat()}\n", encoding="utf-8")
    except OSError:
        return None
    return path


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if sys.platform == "win32":
        import ctypes

        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        handle = ctypes.windll.kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            return False
        ctypes.windll.kernel32.CloseHandle(handle)
        return True
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def try_activate_existing_window(*, title: str = "Marktanalyse") -> bool:
    """Bring an already running Marktanalyse window to the foreground."""
    if sys.platform != "win32":
        return False
    import ctypes

    user32 = ctypes.windll.user32

    found: list[int] = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    def _enum_cb(hwnd, _lparam):
        if not user32.IsWindowVisible(hwnd):
            return True
        buf = ctypes.create_unicode_buffer(512)
        user32.GetWindowTextW(hwnd, buf, 512)
        text = buf.value or ""
        if title in text or "Marktanalyse" in text:
            found.append(int(hwnd))
            return False
        return True

    user32.EnumWindows(_enum_cb, 0)
    hwnd = found[0] if found else 0
    if not hwnd:
        hwnd = user32.FindWindowW(None, title)
    if not hwnd:
        for suffix in (" — Ergebnis", " — Marktanalyse", "Investment Cockpit"):
            hwnd = user32.FindWindowW(None, f"{title}{suffix}")
            if hwnd:
                break
    if not hwnd:
        return False
    SW_RESTORE = 9
    user32.ShowWindow(hwnd, SW_RESTORE)
    user32.SetForegroundWindow(hwnd)
    return True


def note_duplicate_start(root: Path) -> None:
    path = root / "marktanalyse_last_run.log"
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    line = f"[INFO] Zweite Instanz übersprungen — bestehendes Fenster aktiviert ({ts})\n"
    try:
        with path.open("a", encoding="utf-8", newline="\n") as fh:
            fh.write(line)
    except OSError:
        pass


def is_interactive_session_running(root: Path) -> bool:
    """True when Marktanalyse.exe (or equivalent) holds the app instance lock."""
    if str(os.environ.get("AA_SINGLE_INSTANCE", "1")).strip().lower() in {"0", "false", "no", "off"}:
        return False
    name = _mutex_name(root)
    if sys.platform == "win32":
        import ctypes

        SYNCHRONIZE = 0x00100000
        handle = ctypes.windll.kernel32.OpenMutexW(SYNCHRONIZE, False, name)
        if handle:
            ctypes.windll.kernel32.CloseHandle(handle)
            return True
    path = root / APP_LOCK_FILE
    if path.is_file():
        try:
            pid = int(path.read_text(encoding="utf-8").split()[0])
            return _pid_alive(pid)
        except Exception:
            pass
    return False


def acquire_single_instance(root: Path, *, window_title: str = "R3") -> Optional[SingleInstanceGuard]:
    """Return guard when this process owns the app instance; None if another runs."""
    if str(os.environ.get("AA_SINGLE_INSTANCE", "1")).strip().lower() in {"0", "false", "no", "off"}:
        return SingleInstanceGuard()
    if multi_instance_bypass_allowed():
        return SingleInstanceGuard()

    if _lock_file_held_by_other(root):
        try_activate_existing_window(title=window_title)
        note_duplicate_start(root)
        return None

    name = _mutex_name(root)
    use_mutex = str(os.environ.get("AA_SINGLE_INSTANCE_MUTEX", "1")).strip().lower() not in {"0", "false", "no", "off"}
    if sys.platform == "win32" and use_mutex:
        handle, already_exists = _try_windows_mutex(name)
        if handle is not None:
            lock_path = _write_instance_lock_file(root)
            return SingleInstanceGuard(handle=handle, lock_path=lock_path)
        if already_exists:
            try_activate_existing_window(title=window_title)
            note_duplicate_start(root)
            return None

    lock_path = _try_file_lock(root)
    if lock_path is not None:
        return SingleInstanceGuard(lock_path=lock_path)

    try_activate_existing_window(title=window_title)
    note_duplicate_start(root)
    return None

"""Non-blocking process locks for background jobs and batch work."""
from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


def pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if sys.platform == "win32":
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
    except ProcessLookupError:
        return False
    except PermissionError:
        # EPERM: process exists but signal not allowed (sandbox / other user).
        return True
    except OSError as exc:
        import errno

        if getattr(exc, "errno", None) in (errno.EPERM, errno.EACCES):
            return True
        return False


class JobLock:
    """File lock under `.active_alpha_jobs/<job>.lock` (non-blocking)."""

    def __init__(self, root: Path, job: str) -> None:
        self.root = Path(root)
        self.job = str(job)
        self.lock_dir = self.root / ".active_alpha_jobs"
        self.lock_path = self.lock_dir / f"{self.job}.lock"
        self._held = False

    def acquire(self) -> bool:
        self.lock_dir.mkdir(parents=True, exist_ok=True)
        if self.lock_path.is_file():
            try:
                raw = self.lock_path.read_text(encoding="utf-8").strip().split()
                pid = int(raw[0])
                if pid_alive(pid):
                    return False
            except Exception:
                pass
            try:
                self.lock_path.unlink(missing_ok=True)
            except OSError:
                return False
        try:
            self.lock_path.write_text(
                f"{os.getpid()} {datetime.now(timezone.utc).isoformat()}\n",
                encoding="utf-8",
            )
            self._held = True
            return True
        except OSError:
            return False

    def release(self) -> None:
        if self._held and self.lock_path.is_file():
            try:
                self.lock_path.unlink(missing_ok=True)
            except OSError:
                pass
        self._held = False

    def __enter__(self) -> "JobLock":
        self.acquire()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.release()


def read_lock_owner(lock_path: Path) -> Optional[int]:
    if not Path(lock_path).is_file():
        return None
    try:
        return int(Path(lock_path).read_text(encoding="utf-8").strip().split()[0])
    except Exception:
        return None

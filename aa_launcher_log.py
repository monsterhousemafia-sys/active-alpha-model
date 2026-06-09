"""File logging for Marktanalyse.exe runs."""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, TextIO

_LOG_HANDLE: Optional[TextIO] = None
_LOG_PATH: Optional[Path] = None


def log_file_path(root: Path) -> Path:
    return Path(root) / "marktanalyse_last_run.log"


def start_run_log(root: Path) -> Path:
    global _LOG_HANDLE, _LOG_PATH
    path = log_file_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    if _LOG_HANDLE is not None:
        try:
            _LOG_HANDLE.close()
        except Exception:
            pass
    _LOG_HANDLE = path.open("w", encoding="utf-8", newline="\n")
    _LOG_PATH = path
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    _LOG_HANDLE.write(f"=== Marktanalyse run {ts} ===\n")
    _LOG_HANDLE.flush()
    return path


def log_line(message: str) -> None:
    if _LOG_HANDLE is None:
        return
    _LOG_HANDLE.write(message.rstrip() + "\n")
    _LOG_HANDLE.flush()


def close_run_log() -> None:
    global _LOG_HANDLE
    if _LOG_HANDLE is not None:
        try:
            _LOG_HANDLE.write("=== end ===\n")
            _LOG_HANDLE.flush()
            _LOG_HANDLE.close()
        except Exception:
            pass
        _LOG_HANDLE = None


class TeeStream:
    """Mirror stdout/stderr to the run log file."""

    def __init__(self, original, log_fn) -> None:
        self._original = original
        self._log_fn = log_fn

    def write(self, data: str) -> int:
        if not data:
            return 0
        if data.strip():
            for line in data.splitlines():
                self._log_fn(line)
        if self._original is None:
            return len(data)
        return self._original.write(data)

    def flush(self) -> None:
        if self._original is not None:
            self._original.flush()

    def isatty(self) -> bool:
        return False


def install_log_tee() -> None:
    if _LOG_HANDLE is None:
        return
    # PyInstaller --windowed sets stdout/stderr to None; wrap anyway so print() works.
    sys.stdout = TeeStream(sys.stdout, log_line)  # type: ignore[assignment]
    sys.stderr = TeeStream(sys.stderr, log_line)  # type: ignore[assignment]

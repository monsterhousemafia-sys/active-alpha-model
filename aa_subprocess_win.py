"""Windows subprocess helpers — no extra console windows beside the launcher."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def hidden_subprocess_kwargs(**extra: object) -> dict:
    kw = dict(extra)
    if sys.platform == "win32":
        kw.setdefault("creationflags", subprocess.CREATE_NO_WINDOW)
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        kw["startupinfo"] = si
    return kw


def prefer_pythonw(python: Path) -> Path:
    """Use pythonw.exe for background work when available (no console flash)."""
    if python.name.lower() == "python.exe":
        pyw = python.with_name("pythonw.exe")
        if pyw.is_file():
            return pyw
    return python

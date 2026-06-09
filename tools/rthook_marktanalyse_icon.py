"""PyInstaller runtime hook: Win11 taskbar identity before Qt starts."""
from __future__ import annotations

import sys

if sys.platform == "win32":
    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("ActiveAlpha.Marktanalyse.R5")
    except Exception:
        pass

#!/usr/bin/env python3
"""DEPRECATED — do not run after PyInstaller onedir builds.

Post-patching icon resources on a finished EXE can truncate/corrupt the
binary. PyInstaller already embeds the icon via --icon during the build.
Use build_active_alpha_launcher.bat instead.
"""
from __future__ import annotations

import sys


def main() -> int:
    print(
        "[WARN] patch_exe_icon.py ist deaktiviert — Icon wird nur noch via "
        "PyInstaller --icon eingebettet.",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

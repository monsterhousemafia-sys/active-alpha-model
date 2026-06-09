#!/usr/bin/env python3
"""Smoke tests: launcher env, Fast-Path validation, batch return codes."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _run(cmd: list[str], *, cwd: Path | None = None) -> int:
    print("[cmd]", " ".join(cmd))
    return int(subprocess.run(cmd, cwd=str(cwd or ROOT)).returncode)


def main() -> int:
    py = sys.executable
    failures = 0

    failures += _run([py, "-m", "pytest", "tests/test_integrity.py", "tests/test_aa_ops.py", "-q", "--tb=line"]) != 0
    failures += _run([py, str(ROOT / "tools" / "run_validation_matrix.py"), "--dry-run", "--phase", "reference"]) != 0
    failures += _run([py, str(ROOT / "check_active_alpha_core.py")]) != 0

    bat = ROOT / "run_active_alpha_launcher.bat"
    if bat.is_file() and bat.read_text(encoding="utf-8", errors="ignore").strip():
        print("[skip] launcher bat smoke (non-interactive)")

    print(f"\nSmoke summary: {'FAIL' if failures else 'OK'} ({failures} failed steps)")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())

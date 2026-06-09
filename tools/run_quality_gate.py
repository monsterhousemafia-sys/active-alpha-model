#!/usr/bin/env python3
"""Run the local quality gate: pytest, self-test, core check, and launcher smoke."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _run(label: str, cmd: list[str], *, optional: bool = False) -> None:
    print(f"\n=== {label} ===")
    proc = subprocess.run(cmd, cwd=ROOT, text=True)
    if proc.returncode != 0:
        if optional:
            print(f"[WARN] Optional step failed: {label}")
            return
        raise SystemExit(proc.returncode)


def main() -> int:
    py = sys.executable
    _run("pytest", [py, "-m", "pytest", "tests", "-q", "--cache-clear"])
    _run("self-test", [py, "active_alpha_model.py", "--self-test"])
    _run("check_active_alpha_core", [py, "check_active_alpha_core.py"])
    _run("smoke_test_launcher", [py, "tools/smoke_test_launcher.py"], optional=True)
    print("\nQuality gate passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

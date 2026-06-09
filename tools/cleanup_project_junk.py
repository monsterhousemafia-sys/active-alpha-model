#!/usr/bin/env python3
"""Remove development clutter from the project root (safe, no model/paper data)."""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Root-level dev artifacts only — never model_output, paper_output, Marktanalyse bundle.
REMOVE_FILES = (
    "active_alpha_model.diff",
    "active_alpha_control_center.diff",
    "aa_dashboard.diff",
    "run_active_alpha_model.diff",
    "build_launcher.log",
    ".marktanalyse_setup_hint",
)

REMOVE_DIRS = (
    ".pytest_cache",
    "__pycache__",
)

ARCHIVE_NAME = "active_alpha_model_monolith_backup.py"


def _purge_pycache(base: Path) -> list[str]:
    removed: list[str] = []
    for path in base.rglob("__pycache__"):
        if ".venv" in path.parts or "Marktanalyse" in path.parts:
            continue
        shutil.rmtree(path, ignore_errors=True)
        removed.append(str(path.relative_to(ROOT)))
    return removed


def main() -> int:
    deleted: list[str] = []
    for name in REMOVE_FILES:
        path = ROOT / name
        if path.is_file():
            path.unlink(missing_ok=True)
            deleted.append(name)
    for name in REMOVE_DIRS:
        path = ROOT / name
        if path.is_dir():
            shutil.rmtree(path, ignore_errors=True)
            deleted.append(name + "/")
    deleted.extend(_purge_pycache(ROOT))

    backup = ROOT / ARCHIVE_NAME
    if backup.is_file():
        archive_dir = ROOT / "archive"
        archive_dir.mkdir(exist_ok=True)
        target = archive_dir / ARCHIVE_NAME
        if target.is_file():
            target.unlink()
        backup.replace(target)
        deleted.append(f"{ARCHIVE_NAME} -> archive/")

    if not deleted:
        print("[CLEANUP OK] Nichts zu entfernen.")
        return 0
    print("[CLEANUP OK] Entfernt/archiviert:")
    for item in deleted:
        print(f"  - {item}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Export the Active Alpha project as ZIP with folder structure preserved."""
from __future__ import annotations

import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DEST = ROOT / "active_alpha_model_export.zip"
EXCLUDE_DIR_NAMES = {".venv", "__pycache__", ".pytest_cache"}
EXCLUDE_DIR_PREFIXES = ("model_output", "robustness_results")


def should_skip(rel: Path) -> bool:
    if EXCLUDE_DIR_NAMES.intersection(rel.parts):
        return True
    return any(part.startswith(EXCLUDE_DIR_PREFIXES) for part in rel.parts)


def export_project(dest: Path = DEFAULT_DEST) -> int:
    if dest.exists():
        dest.unlink()
    count = 0
    with zipfile.ZipFile(dest, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for path in sorted(ROOT.rglob("*")):
            if not path.is_file():
                continue
            rel = path.relative_to(ROOT)
            if should_skip(rel):
                continue
            zf.write(path, arcname=rel.as_posix())
            count += 1
    print(f"Export: {dest}")
    print(f"Files: {count}")
    print(f"Size bytes: {dest.stat().st_size}")
    return count


if __name__ == "__main__":
    export_project()

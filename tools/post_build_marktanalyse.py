#!/usr/bin/env python3
"""Finalize onedir PyInstaller output: root launcher EXE + _internal junction."""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "Marktanalyse"
BUNDLE_EXE = BUNDLE / "Marktanalyse.exe"
BUNDLE_INTERNAL = BUNDLE / "_internal"
ROOT_EXE = ROOT / "Marktanalyse.exe"
ROOT_INTERNAL = ROOT / "_internal"
ICON_SRC = ROOT / "assets" / "marktanalyse_r3.ico"
MIN_INTERNAL_BYTES = 80_000_000


def _fail(msg: str) -> int:
    print(f"[POST-BUILD FAIL] {msg}", file=sys.stderr)
    return 1


def _dir_size(path: Path) -> int:
    total = 0
    for item in path.rglob("*"):
        if item.is_file():
            try:
                total += item.stat().st_size
            except OSError:
                pass
    return total


def _remove_path(path: Path) -> None:
    if not path.exists() and not path.is_symlink():
        return
    if path.is_symlink() or path.is_junction():
        path.unlink()
        return
    if path.is_dir():
        shutil.rmtree(path, ignore_errors=True)
        return
    path.unlink(missing_ok=True)


def _is_junction(path: Path) -> bool:
    try:
        return path.is_symlink() or bool(getattr(path, "is_junction", lambda: False)())
    except OSError:
        return False


def _create_internal_junction(link: Path, target: Path) -> None:
    _remove_path(link)
    proc = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(link), str(target)],
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or b"").decode("utf-8", errors="replace").strip()
        raise RuntimeError(err or "mklink failed")


def _copy_if_changed(src: Path, dst: Path) -> None:
    if not src.is_file():
        return
    if dst.is_file() and src.resolve() == dst.resolve():
        return
    try:
        shutil.copy2(src, dst)
    except PermissionError:
        if dst.is_file() and dst.stat().st_size == src.stat().st_size:
            return
        raise


def main() -> int:
    if not BUNDLE_EXE.is_file():
        return _fail(f"Bundle-EXE fehlt: {BUNDLE_EXE}")
    if not BUNDLE_INTERNAL.is_dir():
        return _fail(f"Bundle _internal fehlt: {BUNDLE_INTERNAL}")

    internal_size = _dir_size(BUNDLE_INTERNAL)
    if internal_size < MIN_INTERNAL_BYTES:
        return _fail(f"_internal zu klein ({internal_size // 1_000_000} MB)")

    shutil.copy2(BUNDLE_EXE, ROOT_EXE)
    _create_internal_junction(ROOT_INTERNAL, BUNDLE_INTERNAL)

    assets = ROOT / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    if ICON_SRC.is_file():
        _copy_if_changed(ICON_SRC, assets / "marktanalyse_r3.ico")
        _copy_if_changed(ICON_SRC, ROOT / "Marktanalyse.ico")

    exe_size = ROOT_EXE.stat().st_size
    print(f"[POST-BUILD OK] Root-Launcher: {ROOT_EXE} ({exe_size // 1_000_000} MB)")
    print(f"[POST-BUILD OK] Laufzeit-Bibliotheken: {BUNDLE_INTERNAL} ({internal_size // 1_000_000} MB)")
    print(f"[POST-BUILD OK] Junction: {ROOT_INTERNAL} -> {BUNDLE_INTERNAL}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

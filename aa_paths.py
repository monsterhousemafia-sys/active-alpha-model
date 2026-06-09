"""Resolve project root and canonical Marktanalyse.exe (repo root onefile only)."""
from __future__ import annotations

import os
import sys
from pathlib import Path

CANONICAL_MARKTANALYSE_EXE = "Marktanalyse.exe"


def _find_project_root(start: Path) -> Path | None:
    for candidate in (start, *start.parents):
        if (candidate / "active_alpha_model.py").is_file():
            return candidate
    return None


def frozen_user_data_root() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local"))
        return base / "Marktanalyse" / "active_alpha_data"
    return Path.home() / ".local" / "share" / "Marktanalyse" / "active_alpha_data"


def resolve_venv_python(root: Path | None = None) -> Path:
    """Project venv interpreter; falls back to the running interpreter."""
    root = root or project_root()
    if sys.platform == "win32":
        py = root / ".venv" / "Scripts" / "python.exe"
        if py.is_file():
            from aa_subprocess_win import prefer_pythonw

            return prefer_pythonw(py)
    else:
        for name in ("python3", "python"):
            py = root / ".venv" / "bin" / name
            if py.is_file():
                return py
    return Path(sys.executable)


def venv_python_ok(root: Path | None = None) -> bool:
    """True when project venv exists and pip is usable (required for ops/tests)."""
    import subprocess

    py = resolve_venv_python(root)
    if py == Path(sys.executable) and not (root or project_root()).joinpath(".venv").is_dir():
        return False
    if not py.is_file():
        return False
    try:
        proc = subprocess.run(
            [str(py), "-m", "pip", "--version"],
            capture_output=True,
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return proc.returncode == 0


def project_root() -> Path:
    override = os.environ.get("AA_PROJECT_ROOT", "").strip()
    if override:
        forced = Path(override)
        if forced.is_dir() and (
            (forced / "active_alpha_model.py").is_file()
            or (forced / "control" / "marktanalyse_runtime_layout.json").is_file()
        ):
            return forced

    if getattr(sys, "frozen", False):
        exe = Path(sys.executable).resolve()
        exe_parent = exe.parent
        if any(
            (exe_parent / marker).exists()
            for marker in (
                "live_pilot",
                "trading212_zugangsdaten.env",
                "control/marktanalyse_runtime_layout.json",
                "active_alpha_model.py",
            )
        ):
            return exe_parent
        for start in (exe_parent, Path.cwd()):
            found = _find_project_root(start)
            if found is not None:
                return found
        return frozen_user_data_root()

    here = Path(__file__).resolve().parent
    cwd = Path.cwd()
    if (cwd / "active_alpha_model.py").is_file():
        return cwd
    if (here / "active_alpha_model.py").is_file():
        return here
    return here


def canonical_marktanalyse_exe(root: Path | None = None) -> Path:
    """Single product EXE at repository root — no dist/, no Marktanalyse/ onedir."""
    return (root or project_root()) / CANONICAL_MARKTANALYSE_EXE


def resolve_marktanalyse_exe(root: Path | None = None) -> Path:
    return canonical_marktanalyse_exe(root)


def resolve_submission_marktanalyse_exe(root: Path | None = None) -> Path:
    return canonical_marktanalyse_exe(root)


def marktanalyse_bundle_dir(root: Path | None = None) -> Path:
    """Deprecated: onedir bundle removed; path kept for compatibility."""
    return (root or project_root()) / "Marktanalyse"


def marktanalyse_internal_dir(root: Path | None = None) -> Path:
    """PyInstaller onefile has no _internal next to root; returns path if legacy layout exists."""
    root = root or project_root()
    direct = root / "_internal"
    if direct.is_dir():
        return direct
    legacy = root / "Marktanalyse" / "_internal"
    return legacy if legacy.is_dir() else direct


def bundle_size_bytes(root: Path | None = None) -> int:
    internal = marktanalyse_internal_dir(root)
    if not internal.is_dir():
        return 0
    total = 0
    for item in internal.rglob("*"):
        if item.is_file():
            try:
                total += item.stat().st_size
            except OSError:
                pass
    return total

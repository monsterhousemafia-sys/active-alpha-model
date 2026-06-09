"""Marktanalyse.exe — direkter Doppelklick ohne .bat (Arbeitsverzeichnis + OS-Profil)."""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Optional

# Spiegel active_alpha_marktanalyse_os.bat — zentral für EXE und Launcher.
_OS_PROFILE: dict[str, str] = {
    "AA_RUN_MODE": "signal",
    "AA_RUNTIME_PROFILE": "exe",
    "AA_SIGNAL_REFRESH_ON_STALE_DATA": "1",
    "AA_FAST_PATH": "1",
    "AA_REUSE_FEATURE_CACHE": "1",
    "AA_REUSE_PREDICTION_CACHE": "1",
    "AA_SKIP_DOWNLOAD_IF_CACHED": "1",
    "AA_SKIP_NAIVE_MOMENTUM_BASELINE": "1",
    "AA_SKIP_STATISTICAL_DIAGNOSTICS": "1",
    "AA_SKIP_CUSTOM_BENCHMARKS": "1",
    "AA_SKIP_FEATURE_PARQUET_WRITE": "1",
    "AA_NO_PLOT": "1",
    "AA_PARALLEL_BACKTEST_BACKEND": "thread",
    "AA_N_JOBS": "auto",
}


def apply_marktanalyse_os_profile(*, overwrite: bool = False) -> None:
    for key, val in _OS_PROFILE.items():
        if overwrite or not os.environ.get(key):
            os.environ[key] = val


def resolve_direct_exe_root() -> Optional[Path]:
    """Projektroot neben Marktanalyse.exe (nicht AppData-Fallback wenn Repo neben EXE)."""
    if not getattr(sys, "frozen", False):
        return None
    exe_dir = Path(sys.executable).resolve().parent
    if (exe_dir / "active_alpha_model.py").is_file():
        return exe_dir
    if (exe_dir / "control").is_dir() and (exe_dir / "Marktanalyse.exe").is_file():
        return exe_dir
    return None


def configure_direct_exe_startup() -> Path:
    """
    Einmal beim EXE-Start: Root setzen, chdir, OS-Profil, frozen defaults.
    Signal/Rebalance nutzen weiter .venv im gleichen Ordner (nicht im Onefile).
    """
    from aa_frozen import apply_frozen_env_defaults, is_frozen_exe
    from aa_paths import project_root

    direct = resolve_direct_exe_root()
    if direct is not None:
        os.environ["AA_PROJECT_ROOT"] = str(direct)
        try:
            os.chdir(direct)
        except OSError:
            pass

    root = project_root()
    apply_marktanalyse_os_profile()
    os.environ.setdefault("AA_INTERACTIVE_COCKPIT", "1")
    os.environ.setdefault("AA_MINIMAL_INVEST_APP", "1")

    if is_frozen_exe():
        merged = apply_frozen_env_defaults(dict(os.environ), force=True, root=root)
        os.environ.update(merged)
        try:
            from execution.confirmed_live.p17_review_mode_preferences import (
                apply_saved_review_mode_to_environment,
            )

            apply_saved_review_mode_to_environment(root)
        except Exception:
            pass

    return root


def _venv_ok(root: Path) -> bool:
    from aa_paths import venv_python_ok

    return venv_python_ok(root)


def direct_exe_requirements(root: Path) -> dict[str, bool]:
    root = Path(root)
    return {
        "project_root": root.is_dir(),
        "active_alpha_model": (root / "active_alpha_model.py").is_file(),
        "venv_python": _venv_ok(root),
        "marktanalyse_exe": (root / "Marktanalyse.exe").is_file(),
    }


def direct_exe_ready_message(req: dict[str, bool]) -> str:
    if not req.get("active_alpha_model"):
        return (
            "Marktanalyse.exe muss im Projektordner liegen (neben active_alpha_model.py).\n"
            "Kopieren Sie die EXE nicht auf den Desktop allein."
        )
    if not req.get("venv_python"):
        return (
            "Für Signal und Rebalance wird .venv im Projektordner benötigt.\n"
            "Einmalig: setup_active_alpha_env.bat (Windows) oder bash tools/setup_linux_native.sh (Linux)."
        )
    return ""

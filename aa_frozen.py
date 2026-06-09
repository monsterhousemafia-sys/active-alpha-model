"""PyInstaller frozen EXE guards — single window, thread-parallel backtest."""
from __future__ import annotations

import multiprocessing as mp
import sys
from pathlib import Path
from typing import Dict, Mapping


def is_frozen_exe() -> bool:
    return getattr(sys, "frozen", False)


def is_main_process() -> bool:
    return mp.current_process().name == "MainProcess"


def guard_frozen_worker_exit() -> None:
    """Child re-spawns of Marktanalyse.exe must exit before Qt/subprocess UI."""
    if is_frozen_exe() and not is_main_process():
        raise SystemExit(0)


def effective_parallel_backend(cfg=None, requested: str = "process") -> str:
    """Process pools spawn extra windows in one-file EXE; use threads instead."""
    if is_frozen_exe():
        return "thread"
    return str(requested or "process").lower().strip() or "process"


def apply_frozen_runtime_config(cfg) -> None:
    """Safe parallel settings for Marktanalyse.exe (threads, no child processes)."""
    if not is_frozen_exe():
        return
    cfg.parallel_backtest_backend = "thread"
    raw = str(getattr(cfg, "n_jobs", "auto") or "auto").strip().lower()
    if raw in {"", "0", "false", "no", "serial", "off"}:
        cfg.n_jobs = "auto"


def apply_frozen_env_defaults(
    env: Dict[str, str],
    *,
    force: bool = False,
    root: Path | None = None,
) -> Dict[str, str]:
    """Thread-parallel EXE with caches; no multiprocessing spawn."""
    if not force and not is_frozen_exe():
        return env
    out = dict(env)
    out["AA_PARALLEL_BACKTEST_BACKEND"] = "thread"
    out.setdefault("AA_N_JOBS", "auto")
    out.setdefault("AA_REUSE_FEATURE_CACHE", "1")
    out.setdefault("AA_REUSE_PREDICTION_CACHE", "1")
    out.setdefault("AA_SKIP_DOWNLOAD_IF_CACHED", "1")
    out.setdefault("AA_AUTO_OPS_REFRESH", "1")
    out.setdefault("AA_OPS_REFRESH_INTERVAL_HOURS", "24")
    out.setdefault("AA_FAST_PATH", "1")
    out.setdefault("AA_FROZEN_LIGHT_ENV", "1")
    out.setdefault("AA_SINGLE_INSTANCE", "1")
    out.setdefault("AA_SKIP_PNG_CHARTS", "1")
    out.setdefault("AA_STARTUP_CACHE_PRICES", "1")
    out.setdefault("AA_DEFER_PAPER_ON_FAST_PATH", "1")
    out.setdefault("AA_SKIP_VENV_PROBE", "1")
    out.setdefault("AA_RUN_MODE", "signal")
    out.setdefault("AA_SIGNAL_REFRESH_ON_STALE_DATA", "1")
    out["AA_RUNTIME_PROFILE"] = "exe"
    out["AA_RESERVE_CPU_CORES"] = "0"
    shared = out.get("AA_SHARED_CACHE_DIR", "").strip()
    if shared:
        base = root or Path.cwd()
        if not (base / shared).is_dir():
            out.pop("AA_SHARED_CACHE_DIR", None)
    return out


def frozen_parallel_disabled(cfg) -> bool:
    """Multiprocessing pools stay off in the EXE; thread pools are allowed."""
    return is_frozen_exe()

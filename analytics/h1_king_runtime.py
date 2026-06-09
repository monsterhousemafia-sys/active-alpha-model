"""König-H1 Runtime — stabil auf König-Host (Ollama 32B + RTX 3090, 60 GB RAM).

Crash-Ursache (behoben): 30 Process-Spawn-Worker duplizierten feature_by_date
(~0,6 GB × 30 ≈ 18 GB+) und pressten RAM neben Ollama/OS — OOM/Absturz.
König-H1 nutzt Thread-Prep (shared memory) + harte Worker-Caps.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from aa_config import BacktestConfig
from aa_parallel import _configure_blas_threading, resolve_parallel_workers
from aa_runtime_profile import get_profile, subprocess_env_for_profile

# Headroom für Ollama qwen2.5-coder:32b, OS, Cursor, König-Chat
_KING_RAM_RESERVE_GB = 22.0
# Thread-Prep: kein RAM-Duplikat pro Worker (spawn würde feature_by_date kopieren)
_PREP_BACKEND = "thread"
_PREP_MAX_THREADS = 10
_PREP_MAX_PROCESS = 4


def _detect_ram_gb() -> int:
    env = os.environ.get("AA_SYSTEM_RAM_GB", "").strip()
    if env.isdigit():
        return max(4, int(env))
    try:
        with open("/proc/meminfo", encoding="utf-8") as fh:
            for line in fh:
                if line.startswith("MemTotal:"):
                    kb = int(line.split()[1])
                    return max(4, kb // (1024 * 1024))
    except OSError:
        pass
    return 60


def _detect_logical_cores() -> int:
    env = os.environ.get("AA_CPU_CORES", "").strip()
    if env.isdigit():
        return max(1, int(env))
    return max(1, os.cpu_count() or 16)


def _physical_cores(logical: int) -> int:
    if logical >= 8 and logical % 2 == 0:
        return max(1, logical // 2)
    return logical


def detect_host_resources() -> Dict[str, Any]:
    """IST-Ressourcen für König-H1 (CPU, RAM, GPU)."""
    ram_gb = _detect_ram_gb()
    logical = _detect_logical_cores()
    physical = _physical_cores(logical)
    gpu_doc: Dict[str, Any] = {"gpu_returns": False}
    try:
        from aa_gpu_returns import gpu_device_summary, gpu_returns_available

        gpu_doc = {"gpu_returns": gpu_returns_available(), **gpu_device_summary()}
    except Exception as exc:
        gpu_doc = {"gpu_returns": False, "reason_de": str(exc)[:120]}
    return {
        "logical_cores": logical,
        "physical_cores": physical,
        "ram_gb": ram_gb,
        "gpu_available": bool(gpu_doc.get("gpu_returns")),
        "gpu": gpu_doc,
    }


def resolve_king_h1_prep_workers(
    cfg: BacktestConfig,
    *,
    feature_gb: float = 0.0,
    host: Optional[Dict[str, Any]] = None,
) -> Tuple[int, str]:
    """Sichere Prep-Worker — Thread bevorzugt (kein spawn-RAM-Duplikat)."""
    host = host or detect_host_resources()
    profile = get_profile("king_h1")
    reserve_cores = int(profile.reserve_cpu_cores)
    physical = int(host["physical_cores"])
    ram_gb = float(host["ram_gb"])

    cpu_budget = max(1, physical - reserve_cores)

    if _PREP_BACKEND == "thread":
        # Shared memory: limit by CPU, not RAM duplication
        workers = min(_PREP_MAX_THREADS, cpu_budget)
        return max(1, workers), "thread"

    # Process spawn: each worker ≈ feature_gb copy via initargs
    spawn_per_worker = max(float(feature_gb) * 1.6, 1.2)
    usable_ram = max(4.0, ram_gb - _KING_RAM_RESERVE_GB - max(float(feature_gb), 0.5))
    max_by_ram = max(1, int(usable_ram / spawn_per_worker))
    workers = min(_PREP_MAX_PROCESS, max_by_ram, cpu_budget)
    return max(1, workers), "process"


def apply_king_h1_profile(cfg: BacktestConfig, *, feature_gb: float = 0.0) -> Dict[str, Any]:
    """BacktestConfig für König-H1 — stabil, kein RAM-Kollaps."""
    host = detect_host_resources()
    prep_workers, prep_backend = resolve_king_h1_prep_workers(cfg, feature_gb=feature_gb, host=host)

    cfg.n_jobs = str(prep_workers)
    cfg.cpu_cores = int(host["physical_cores"])
    cfg.system_ram_gb = int(host["ram_gb"])
    cfg.parallel_profile = "normal"
    cfg.parallel_backtest_backend = "thread"
    setattr(cfg, "naive_benchmark_returns_only", True)
    setattr(cfg, "naive_parallel_prep", True)
    setattr(cfg, "naive_prep_backend", prep_backend)
    setattr(cfg, "naive_prep_max_workers", prep_workers)
    gpu_enabled = bool(host.get("gpu_available"))
    try:
        from analytics.king_hardware import resolve_gpu_returns_for_h1

        gpu_doc = resolve_gpu_returns_for_h1(Path(os.environ.get("AA_PROJECT_ROOT", ".")))
        gpu_enabled = bool(gpu_doc.get("enabled"))
        host["gpu_returns_resolve"] = gpu_doc
    except Exception:
        pass
    setattr(cfg, "naive_gpu_returns", gpu_enabled)
    return king_h1_runtime_summary(
        cfg,
        feature_gb=feature_gb,
        host=host,
        prep_workers=prep_workers,
        prep_backend=prep_backend,
    )


def king_h1_runtime_summary(
    cfg: BacktestConfig,
    *,
    feature_gb: float = 0.0,
    host: Optional[Dict[str, Any]] = None,
    prep_workers: Optional[int] = None,
    prep_backend: Optional[str] = None,
) -> Dict[str, Any]:
    host = host or detect_host_resources()
    if prep_workers is None or prep_backend is None:
        prep_workers, prep_backend = resolve_king_h1_prep_workers(cfg, feature_gb=feature_gb, host=host)
    return {
        **host,
        "prep_workers": prep_workers,
        "prep_backend": prep_backend,
        "profile": "king_h1",
        "reserve_cores": get_profile("king_h1").reserve_cpu_cores,
        "ram_reserve_gb": _KING_RAM_RESERVE_GB,
        "naive_gpu_returns": bool(getattr(cfg, "naive_gpu_returns", False)),
        "crash_guard_de": "Thread-Prep + RAM-Cap — kein 30× spawn-Duplikat",
    }


def king_h1_subprocess_env(*, base: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    """Umgebung für H1-Benchmark-Subprozess — König-sicher + NVMe + GPU."""
    host = detect_host_resources()
    profile = get_profile("king_h1")
    env = subprocess_env_for_profile(profile, base=dict(base or os.environ))
    env["AA_CPU_CORES"] = str(host["physical_cores"])
    env["AA_SYSTEM_RAM_GB"] = str(host["ram_gb"])
    env["AA_RUNTIME_PROFILE"] = "king_h1"
    env["AA_RESERVE_CPU_CORES"] = str(profile.reserve_cpu_cores)
    env["AA_VALIDATION_N_JOBS_CAP"] = str(_PREP_MAX_THREADS)
    env.setdefault("AA_H1_GPU_RETURNS", "1")
    env.setdefault("AA_H1_UNLOAD_OLLAMA", "1")
    for key in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
        env[key] = "1"
    root_raw = env.get("AA_PROJECT_ROOT", "").strip()
    if root_raw:
        try:
            from execution.linux_nvme_storage import apply_nvme_storage_env

            for k, v in apply_nvme_storage_env(Path(root_raw)).items():
                env[k] = v
        except Exception:
            pass
    return env


def configure_king_h1_process() -> None:
    """Benchmark-Prozess: niedrige Priorität, König/Ollama bleibt stabil."""
    _configure_blas_threading(1)
    if sys.platform == "linux":
        try:
            os.nice(8)
        except (OSError, PermissionError):
            pass

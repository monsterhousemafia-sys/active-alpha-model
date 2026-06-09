"""Hardware/runtime profiles — EXE vs batch research vs validation matrix.

Profiles centralize CPU/RAM budgets so Marktanalyse.exe stays responsive while
validation/research can use the remaining capacity. Extend PROFILES for future
optimizations (GPU tiers, cloud agents, etc.) without touching orchestrators.
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional, Tuple

BATCH_LOCK_FILE = ".active_alpha_batch.lock"


@dataclass(frozen=True)
class RuntimeProfileSpec:
    name: str
    parallel_backend: str  # process | thread
    reserve_cpu_cores: int
    max_variant_parallel: int
    process_priority: str  # normal | below_normal | idle
    n_jobs_cap: Optional[int] = None
    description: str = ""


PROFILES: Dict[str, RuntimeProfileSpec] = {
    "exe": RuntimeProfileSpec(
        name="exe",
        parallel_backend="thread",
        reserve_cpu_cores=0,
        max_variant_parallel=1,
        process_priority="normal",
        n_jobs_cap=None,
        description="Marktanalyse.exe — threads only, no process spawn.",
    ),
    "research": RuntimeProfileSpec(
        name="research",
        parallel_backend="process",
        reserve_cpu_cores=2,
        max_variant_parallel=1,
        process_priority="normal",
        n_jobs_cap=None,
        description="Single full backtest from BAT/CLI.",
    ),
    "validation": RuntimeProfileSpec(
        name="validation",
        parallel_backend="process",
        reserve_cpu_cores=4,
        max_variant_parallel=3,
        process_priority="below_normal",
        n_jobs_cap=None,
        description="Validation matrix — leaves headroom for GUI/EXE.",
    ),
    "turbo": RuntimeProfileSpec(
        name="turbo",
        parallel_backend="process",
        reserve_cpu_cores=0,
        max_variant_parallel=2,
        process_priority="high",
        n_jobs_cap=None,
        description="Max CPU for batch validation — R3+M1 parallel, high priority.",
    ),
    "background": RuntimeProfileSpec(
        name="background",
        parallel_backend="process",
        reserve_cpu_cores=6,
        max_variant_parallel=1,
        process_priority="idle",
        n_jobs_cap=4,
        description="Yield when Marktanalyse.exe is active.",
    ),
    "king_h1": RuntimeProfileSpec(
        name="king_h1",
        parallel_backend="thread",
        reserve_cpu_cores=4,
        max_variant_parallel=1,
        process_priority="below_normal",
        n_jobs_cap=10,
        description="H1-Seal-Benchmark — Thread-Prep, RAM-Cap, 4 Kerne für König/Ollama.",
    ),
}


def profile_from_env(default: str = "research") -> str:
    raw = str(os.environ.get("AA_RUNTIME_PROFILE", default) or default).strip().lower()
    return raw if raw in PROFILES else default


def get_profile(name: str) -> RuntimeProfileSpec:
    key = str(name or "research").strip().lower()
    return PROFILES.get(key, PROFILES["research"])


def resolve_effective_profile(
    requested: str,
    *,
    interactive_active: bool = False,
) -> RuntimeProfileSpec:
    """Downgrade batch work when the EXE session is running."""
    if interactive_active and requested in {"validation", "research"}:
        return PROFILES["background"]
    if requested == "turbo":
        return PROFILES["turbo"]
    return get_profile(requested)


def usable_cpu_cores(total: int, reserve: int) -> int:
    total = max(1, int(total))
    reserve = max(0, int(reserve))
    return max(1, total - min(reserve, total - 1))


def variant_worker_budget(
    total_cores: int,
    parallel_variants: int,
    *,
    profile: RuntimeProfileSpec,
) -> Tuple[int, int]:
    """Return (n_parallel_variants, cores_per_variant) within profile limits."""
    cores = usable_cpu_cores(total_cores, profile.reserve_cpu_cores)
    jobs = max(1, min(int(parallel_variants), profile.max_variant_parallel, 4))
    per_job = max(1, cores // jobs)
    if profile.n_jobs_cap is not None:
        per_job = min(per_job, int(profile.n_jobs_cap))
    return jobs, per_job


def reserve_cpu_cores_from_env(default: int = 0) -> int:
    raw = os.environ.get("AA_RESERVE_CPU_CORES", "").strip()
    if raw.isdigit():
        return max(0, int(raw))
    prof = profile_from_env()
    return get_profile(prof).reserve_cpu_cores if default == 0 else default


def apply_process_priority_from_env() -> None:
    """Lower batch priority so Marktanalyse.exe stays snappy (Windows)."""
    if sys.platform != "win32":
        return
    level = str(os.environ.get("AA_PROCESS_PRIORITY", "") or "").strip().lower()
    if not level:
        prof = profile_from_env(default="")
        if prof and prof in PROFILES:
            level = PROFILES[prof].process_priority
        else:
            return
    if level in {"", "normal", "default"}:
        return
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetCurrentProcess()
        cls = {
            "high": 0x00000080,
            "below_normal": 0x00004000,
            "idle": 0x00000040,
        }.get(level)
        if cls is not None:
            kernel32.SetPriorityClass(handle, cls)
    except Exception:
        pass


def subprocess_env_for_profile(
    profile: RuntimeProfileSpec,
    *,
    base: Optional[Dict[str, str]] = None,
) -> Dict[str, str]:
    """Env vars for child Python processes (validation matrix workers)."""
    env = dict(base or os.environ)
    env["AA_RUNTIME_PROFILE"] = profile.name
    env["AA_RESERVE_CPU_CORES"] = str(profile.reserve_cpu_cores)
    env["AA_PROCESS_PRIORITY"] = profile.process_priority
    env["AA_PARALLEL_BACKTEST_BACKEND"] = profile.parallel_backend
    if profile.n_jobs_cap is not None:
        env["AA_VALIDATION_N_JOBS_CAP"] = str(profile.n_jobs_cap)
    env.setdefault("AA_SKIP_DOWNLOAD_IF_CACHED", "1")
    env.setdefault("AA_REUSE_FEATURE_CACHE", "1")
    cores = max(1, int(os.environ.get("AA_CPU_CORES", "") or os.cpu_count() or 16))
    env["AA_CPU_CORES"] = str(cores)
    return env


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if sys.platform == "win32":
        import ctypes

        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        handle = ctypes.windll.kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            return False
        ctypes.windll.kernel32.CloseHandle(handle)
        return True
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


@dataclass
class BatchWorkGuard:
    path: Path

    def release(self) -> None:
        if self.path.is_file():
            try:
                self.path.unlink(missing_ok=True)
            except OSError:
                pass

    def __enter__(self) -> "BatchWorkGuard":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.release()


def is_batch_work_active(root: Path) -> bool:
    """True when validation/research holds the batch lock (EXE may prefer Fast-Path)."""
    path = Path(root) / BATCH_LOCK_FILE
    if not path.is_file():
        return False
    try:
        pid = int(path.read_text(encoding="utf-8").split()[0])
    except Exception:
        return False
    return _pid_alive(pid)


def cleanup_stale_batch_lock(root: Path) -> Dict[str, object]:
    """Remove batch lock when holder PID is dead or invalid (crash / power-loss recovery)."""
    path = Path(root) / BATCH_LOCK_FILE
    if not path.is_file():
        return {"removed": False, "reason": "no_lock", "path": str(path)}
    pid = 0
    try:
        pid = int(path.read_text(encoding="utf-8").split()[0])
    except Exception:
        pid = 0
    if pid > 0 and _pid_alive(pid):
        return {"removed": False, "reason": "lock_active", "pid": pid, "path": str(path)}
    try:
        path.unlink(missing_ok=True)
        return {"removed": True, "reason": "stale_lock_removed", "pid": pid, "path": str(path)}
    except OSError as exc:
        return {"removed": False, "reason": str(exc), "pid": pid, "path": str(path)}


def acquire_batch_work(root: Path, *, label: str = "batch") -> Optional[BatchWorkGuard]:
    """Mark heavy batch work so EXE can defer optional downloads."""
    cleanup_stale_batch_lock(root)
    path = Path(root) / BATCH_LOCK_FILE
    if path.is_file():
        try:
            pid = int(path.read_text(encoding="utf-8").split()[0])
            if _pid_alive(pid) and pid != os.getpid():
                return None
        except Exception:
            pass
        try:
            path.unlink(missing_ok=True)
        except OSError:
            return None
    try:
        from datetime import datetime, timezone

        path.write_text(
            f"{os.getpid()} {label} {datetime.now(timezone.utc).isoformat()}\n",
            encoding="utf-8",
        )
    except OSError:
        return None
    return BatchWorkGuard(path=path)

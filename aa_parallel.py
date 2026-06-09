from __future__ import annotations

import multiprocessing as mp
import os
import platform
import sys
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Tuple

import numpy as np
import pandas as pd

from aa_config import BacktestConfig

try:
    from aa_frozen import effective_parallel_backend, is_frozen_exe
except ImportError:
    def is_frozen_exe() -> bool:  # type: ignore[misc]
        return False

    def effective_parallel_backend(cfg=None, requested: str = "process") -> str:  # type: ignore[misc]
        return str(requested or "process").lower().strip() or "process"


@dataclass
class ParallelRunContext:
    """Mutable singleton for Windows-spawn worker state (features, returns, cfg)."""

    features: Optional[pd.DataFrame] = None
    feature_by_date: Optional[Dict[pd.Timestamp, pd.DataFrame]] = None
    dates: Optional[List[pd.Timestamp]] = None
    cfg: Optional[BacktestConfig] = None
    returns: Optional[pd.DataFrame] = None
    feat_bench_close: Optional[pd.Series] = None
    feat_bench_features: Optional[pd.DataFrame] = None
    feat_sector_index: Optional[Dict[str, pd.Series]] = None
    feat_cfg: Optional[BacktestConfig] = None
    boot_strategy: Optional[pd.Series] = None
    boot_bench: Optional[Dict[str, Optional[pd.Series]]] = None


_CTX = ParallelRunContext()
_ACTIVE_POOL: Optional[mp.pool.Pool] = None


def _set_prediction_worker_state(
    features: pd.DataFrame,
    dates: List[pd.Timestamp],
    cfg: BacktestConfig,
) -> None:
    from aa_features import build_feature_by_date

    _CTX.features = features
    _CTX.dates = [pd.Timestamp(d) for d in dates]
    _CTX.cfg = cfg
    _CTX.feature_by_date = build_feature_by_date(features)


def _set_combined_worker_state(
    features: pd.DataFrame,
    returns: pd.DataFrame,
    dates: List[pd.Timestamp],
    cfg: BacktestConfig,
) -> None:
    _set_prediction_worker_state(features, dates, cfg)
    _CTX.returns = returns


def _is_64bit_runtime() -> bool:
    return sys.maxsize > 2**32 and platform.machine().lower() in {"amd64", "x86_64", "arm64"}


def _configure_blas_threading(n_threads: int = 1) -> None:
    """Prevent nested BLAS/OpenMP threads when many process workers run sklearn."""
    value = str(max(1, int(n_threads)))
    for key in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
        os.environ[key] = value


def _parallel_worker_bootstrap() -> None:
    _configure_blas_threading(1)


def _resolve_cpu_cores(cfg: Optional[BacktestConfig]) -> int:
    """Physical core count for worker pools (ignore SMT/hyper-thread duplicates)."""
    from aa_runtime_profile import reserve_cpu_cores_from_env

    reserve = reserve_cpu_cores_from_env()
    if cfg is not None:
        cores = int(getattr(cfg, "cpu_cores", 0) or 0)
        if cores > 0:
            return max(1, cores - min(reserve, cores - 1))
    env = os.environ.get("AA_CPU_CORES", "").strip()
    if env.isdigit():
        cores = max(1, int(env))
        return max(1, cores - min(reserve, cores - 1))
    logical = max(1, os.cpu_count() or 1)
    if logical >= 8 and logical % 2 == 0:
        physical = max(1, logical // 2)
    else:
        physical = logical
    return max(1, physical - min(reserve, physical - 1))


def reserve_cpu_cores_from_env(cfg: Optional[BacktestConfig] = None) -> int:
    from aa_runtime_profile import reserve_cpu_cores_from_env as _reserve

    return _reserve()


def _resolve_system_ram_gb(cfg: Optional[BacktestConfig]) -> int:
    if cfg is not None:
        ram = int(getattr(cfg, "system_ram_gb", 0) or 0)
        if ram > 0:
            return ram
    env = os.environ.get("AA_SYSTEM_RAM_GB", "").strip()
    if env.isdigit():
        return max(4, int(env))
    return 16


def _parallel_profile(cfg: Optional[BacktestConfig]) -> str:
    if cfg is not None:
        profile = str(getattr(cfg, "parallel_profile", "auto") or "auto").strip().lower()
        if profile not in {"", "auto"}:
            return profile
    if _resolve_system_ram_gb(cfg) >= 48 and _is_64bit_runtime():
        return "high"
    return "normal"


def _estimate_dataframe_gb(df: pd.DataFrame) -> float:
    if df is None or df.empty:
        return 0.0
    return float(df.memory_usage(deep=True).sum()) / (1024 ** 3)


def _compact_features_table(df: pd.DataFrame) -> pd.DataFrame:
    """Shrink numeric columns to float32 on x64 to fit more process workers in RAM."""
    if df is None or df.empty or not _is_64bit_runtime():
        return df
    out = df.copy()
    for col in out.columns:
        if col in {"ticker", "sector", "issuer", "correlation_cluster", "date"}:
            continue
        if pd.api.types.is_float_dtype(out[col]):
            out[col] = out[col].astype(np.float32)
        elif pd.api.types.is_integer_dtype(out[col]) and col not in {"universe_rank", "universe_history_days"}:
            out[col] = pd.to_numeric(out[col], downcast="integer")
    return out


def prepare_features_for_parallel_runtime(features: pd.DataFrame, cfg: BacktestConfig) -> pd.DataFrame:
    if _parallel_profile(cfg) == "high":
        return _compact_features_table(features)
    return features


def resolve_n_jobs(
    value: object,
    cfg: Optional[BacktestConfig] = None,
    *,
    feature_table_gb: float = 0.0,
    backend: str = "process",
) -> int:
    """Resolve --n-jobs for Windows x64 multiprocessing pools.

    With auto/all, worker count is min(physical CPU cores, RAM budget). SMT threads
    are intentionally excluded so a 3950X uses 16 workers, not 32 competing processes.
    """
    raw = str(value if value is not None else "1").strip().lower()
    if raw in {"", "0", "1", "false", "no", "serial", "off"}:
        return 1
    physical_cores = _resolve_cpu_cores(cfg)
    if raw not in {"auto", "all", "-1"}:
        try:
            return max(1, int(float(raw)))
        except Exception:
            return 1

    ram_gb = _resolve_system_ram_gb(cfg)
    profile = _parallel_profile(cfg)
    reserve_gb = 6.0 if profile == "high" else 8.0
    usable_gb = max(4.0, float(ram_gb) * 0.88 - reserve_gb)

    backend_norm = str(backend or "process").strip().lower()
    if backend_norm == "process" and feature_table_gb > 0.05:
        per_worker_gb = feature_table_gb * (1.12 if profile == "high" else 1.25)
        per_worker_gb = max(per_worker_gb, 0.75)
        workers = max(1, min(physical_cores, int(usable_gb / per_worker_gb)))
    elif backend_norm == "process" and ram_gb >= 48:
        per_worker_gb = 1.75 if profile == "high" else 2.25
        workers = max(1, min(physical_cores, int(usable_gb / per_worker_gb)))
    else:
        workers = physical_cores
    cap_raw = os.environ.get("AA_VALIDATION_N_JOBS_CAP", "").strip()
    if cap_raw.isdigit():
        workers = min(workers, max(1, int(cap_raw)))
    return workers


def resolve_pool_chunksize(n_tasks: int, n_workers: int, cfg: Optional[BacktestConfig]) -> int:
    n_tasks = max(int(n_tasks), 1)
    n_workers = max(int(n_workers), 1)
    divisor = 2 if _parallel_profile(cfg) == "high" else 4
    return max(1, n_tasks // (n_workers * divisor))


def _mp_pool(processes: int, initializer: Any, initargs: Tuple[Any, ...]) -> mp.pool.Pool:
    """Spawn a 64-bit-safe process pool (Windows uses spawn)."""
    if is_frozen_exe():
        raise RuntimeError("Process pools are disabled inside Marktanalyse.exe")
    ctx = mp.get_context("spawn")
    return ctx.Pool(processes=processes, initializer=initializer, initargs=initargs)


def _combined_run_pool_initializer(
    features: pd.DataFrame,
    returns: pd.DataFrame,
    dates: List[pd.Timestamp],
    cfg: BacktestConfig,
) -> None:
    """Load shared read-only tables once per worker (rank, cluster, ML, naive)."""
    _parallel_worker_bootstrap()
    _set_combined_worker_state(features, returns, dates, cfg)


def _apply_worker_payload(payload: Tuple[str, Tuple[Any, ...]]) -> int:
    """Reconfigure an existing pool worker without respawning (Windows spawn safe)."""
    kind, args = payload
    if kind == "feature_engineering":
        from aa_features import _feature_engineering_initializer

        _feature_engineering_initializer(*args)
    elif kind == "combined":
        features, returns, dates, cfg = args
        _parallel_worker_bootstrap()
        _set_combined_worker_state(features, returns, dates, cfg)
    elif kind == "bootstrap":
        _parallel_worker_bootstrap()
    else:
        raise ValueError(f"Unknown worker payload kind: {kind!r}")
    return 1


class ProcessPoolSession:
    """One process pool for feature build → rank → cluster → ML → naive."""

    def __init__(
        self,
        cfg: BacktestConfig,
        features: Optional[pd.DataFrame] = None,
        returns: Optional[pd.DataFrame] = None,
        dates: Optional[List[pd.Timestamp]] = None,
    ) -> None:
        self.cfg = cfg
        self.features = features
        self.returns = returns
        self.dates = dates
        self.workers = 0
        self._pool: Optional[mp.pool.Pool] = None
        self._state_kind: str = ""

    def _shutdown_pool(self, *, terminate: bool = False) -> None:
        global _ACTIVE_POOL
        if self._pool is None:
            _ACTIVE_POOL = None
            self._state_kind = ""
            return
        try:
            if terminate:
                self._pool.terminate()
            else:
                self._pool.close()
            self._pool.join()
        finally:
            self._pool = None
            _ACTIVE_POOL = None
            self._state_kind = ""

    def _start_pool(self, initializer: Any, initargs: Tuple[Any, ...], state_kind: str) -> None:
        global _ACTIVE_POOL
        if self.workers <= 1:
            return
        if self._pool is not None:
            if self._state_kind == state_kind:
                return
            self._shutdown_pool()
        self._pool = _mp_pool(self.workers, initializer, initargs)
        _ACTIVE_POOL = self._pool
        self._state_kind = state_kind

    def _broadcast_payload(self, payload: Tuple[str, Tuple[Any, ...]]) -> None:
        if self._pool is None:
            _apply_worker_payload(payload)
            return
        list(self._pool.map(_apply_worker_payload, [payload] * self.workers))

    def load_feature_engineering_state(
        self,
        bench_close: pd.Series,
        bench_features: pd.DataFrame,
        sector_index: Dict[str, pd.Series],
    ) -> None:
        """Load benchmark/sector context into workers for per-ticker feature tasks."""
        payload: Tuple[str, Tuple[Any, ...]] = (
            "feature_engineering",
            (bench_close, bench_features, sector_index, self.cfg),
        )
        if self.workers <= 1:
            _apply_worker_payload(payload)
            return
        if self._pool is None or self._state_kind != "feature_engineering":
            from aa_features import _feature_engineering_initializer

            self._start_pool(
                _feature_engineering_initializer,
                (bench_close, bench_features, sector_index, self.cfg),
                "feature_engineering",
            )
            return
        self._broadcast_payload(payload)

    def load_backtest_state(
        self,
        features: pd.DataFrame,
        returns: pd.DataFrame,
        dates: Optional[List[pd.Timestamp]] = None,
    ) -> None:
        """Rebind workers to the compacted feature table for cluster/ML/naive phases."""
        self.features = features
        self.returns = returns
        dlist = dates or [pd.Timestamp(x) for x in features["date"].dropna().unique()]
        self.dates = list(dlist)
        payload: Tuple[str, Tuple[Any, ...]] = (
            "combined",
            (features, returns, self.dates, self.cfg),
        )
        if self.workers <= 1:
            _apply_worker_payload(payload)
            return
        if self._pool is None or self._state_kind != "combined":
            self._start_pool(
                _combined_run_pool_initializer,
                (features, returns, self.dates, self.cfg),
                "combined",
            )
            return
        self._broadcast_payload(payload)

    def __enter__(self) -> "ProcessPoolSession":
        if is_frozen_exe():
            self.workers = 1
            return self
        gb = _estimate_dataframe_gb(self.features) if self.features is not None else 0.0
        self.workers = resolve_parallel_workers(self.cfg, feature_table_gb=gb, backend="process")
        # Start the process pool lazily, with the correct phase initializer.
        # Creating a bootstrap-only pool here caused a second full pool to be
        # spawned during feature engineering on Windows.
        if self.features is not None and self.returns is not None:
            self.load_backtest_state(self.features, self.returns, self.dates)
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self._shutdown_pool(terminate=exc_type is not None)


def resolve_parallel_workers(
    cfg: Optional[BacktestConfig] = None,
    *,
    feature_table_gb: float = 0.0,
    backend: str = "process",
) -> int:
    """Single entry point for physical-core worker counts (Ryzen 3950X → 16)."""
    backend = effective_parallel_backend(cfg, backend)
    return resolve_n_jobs(
        getattr(cfg, "n_jobs", "1") if cfg is not None else "1",
        cfg,
        feature_table_gb=feature_table_gb,
        backend=backend,
    )


def parallel_execution_enabled(
    cfg: Optional[BacktestConfig] = None,
    *,
    feature_table_gb: float = 0.0,
    backend: str = "process",
) -> bool:
    backend = effective_parallel_backend(cfg, backend)
    if backend == "process" and is_frozen_exe():
        return False
    return resolve_parallel_workers(cfg, feature_table_gb=feature_table_gb, backend=backend) > 1


def _parallel_map_unordered(
    cfg: Optional[BacktestConfig],
    func: Any,
    tasks: Iterable[Any],
    *,
    initializer: Optional[Any] = None,
    initargs: Tuple[Any, ...] = (),
    feature_table_gb: float = 0.0,
    backend: str = "process",
) -> List[Any]:
    """Run independent tasks with process or thread workers."""
    task_list = list(tasks)
    backend = effective_parallel_backend(cfg, backend)
    workers = resolve_parallel_workers(cfg, feature_table_gb=feature_table_gb, backend=backend)
    if workers <= 1 or not task_list:
        return [func(t) for t in task_list]

    if backend == "thread" or is_frozen_exe():
        if initializer is not None:
            initializer(*initargs)
        from concurrent.futures import ThreadPoolExecutor, as_completed

        results: List[Any] = []
        with ThreadPoolExecutor(max_workers=workers) as ex:
            futs = [ex.submit(func, t) for t in task_list]
            for fut in as_completed(futs):
                results.append(fut.result())
        return results

    chunksize = resolve_pool_chunksize(len(task_list), workers, cfg)
    if _ACTIVE_POOL is not None and initializer is None:
        return list(_ACTIVE_POOL.imap_unordered(func, task_list, chunksize=chunksize))
    init = initializer or _parallel_worker_bootstrap
    args = initargs if initializer is not None else ()
    with _mp_pool(workers, init, args) as pool:
        return list(pool.imap_unordered(func, task_list, chunksize=chunksize))


def _parallel_prediction_initializer(features: pd.DataFrame, dates: List[pd.Timestamp], cfg: BacktestConfig) -> None:
    _parallel_worker_bootstrap()
    _set_prediction_worker_state(features, dates, cfg)

"""Optional GPU (CuPy) acceleration for portfolio period returns."""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import numpy as np

_GPU_AVAILABLE: Optional[bool] = None


def gpu_returns_available() -> bool:
    global _GPU_AVAILABLE
    if _GPU_AVAILABLE is not None:
        return _GPU_AVAILABLE
    try:
        import cupy as cp

        _GPU_AVAILABLE = cp.cuda.runtime.getDeviceCount() > 0
    except Exception:
        _GPU_AVAILABLE = False
    return bool(_GPU_AVAILABLE)


def gpu_device_summary() -> Dict[str, Any]:
    if not gpu_returns_available():
        return {"ok": False, "reason_de": "CuPy/CUDA nicht verfügbar"}
    try:
        import cupy as cp

        dev = cp.cuda.Device()
        with dev:
            mem = dev.mem_info
        return {
            "ok": True,
            "device_id": int(dev.id),
            "name": cp.cuda.runtime.getDeviceProperties(dev.id)["name"].decode(),
            "memory_free_mb": int(mem[0] // (1024 * 1024)),
            "memory_total_mb": int(mem[1] // (1024 * 1024)),
        }
    except Exception as exc:
        return {"ok": False, "reason_de": str(exc)[:120]}


def as_gpu_returns(ret_np: np.ndarray):
    import cupy as cp

    return cp.asarray(ret_np, dtype=cp.float32)


def _weights_to_gpu_arrays(weights, col_to_j: Dict[str, int]) -> Tuple[Optional[list], Optional[np.ndarray]]:
    if weights is None or getattr(weights, "empty", True):
        return None, None
    active = [
        (str(t), float(weights.get(t, 0.0)))
        for t in weights.index
        if str(t) in col_to_j and float(weights.get(t, 0.0)) != 0.0
    ]
    if not active:
        return None, None
    j_idx = [col_to_j[t] for t, _ in active]
    w_vec = np.asarray([w for _, w in active], dtype=np.float32)
    return j_idx, w_vec


def accumulate_period_returns_gpu(
    weights,
    *,
    ret_gpu,
    ret_index,
    col_to_j: Dict[str, int],
    period_bounds: Tuple[int, int],
    tx_cost: float,
) -> Tuple[List, List[float], float]:
    """One rebalance period — returns matrix stays on GPU (CuPy/cuBLAS)."""
    import cupy as cp

    i0, i1 = period_bounds
    if i1 <= i0:
        return [], [], 1.0
    dates_out = [ret_index[i] for i in range(i0, i1)]
    j_idx, w_vec = _weights_to_gpu_arrays(weights, col_to_j)
    if j_idx is None:
        return dates_out, [0.0] * len(dates_out), 1.0

    w_gpu = cp.asarray(w_vec)
    R = ret_gpu[i0:i1, j_idx]
    pr = (R @ w_gpu).astype(cp.float32)
    if pr.size:
        pr[0] = pr[0] - cp.float32(tx_cost)
    pr_cpu = pr.get()
    growth = float(np.prod(np.maximum(1.0 + pr_cpu, 0.0)))
    return dates_out, pr_cpu.astype(float).tolist(), growth

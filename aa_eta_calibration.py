"""ETA estimation using historical phase_timings.json profiles."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

from aa_dashboard_core import BACKTEST_PIPELINE_WEIGHTS, LAUNCHER_STEP_WEIGHTS

# Map pipeline step keys to phase_timings.json section names.
_PIPELINE_TO_TIMING: Dict[str, tuple[str, ...]] = {
    "universe": ("tickers_load",),
    "features": ("download", "feature_build", "feature_cache_load", "cluster_overlay"),
    "ml": ("walkforward_phase_a_ml",),
    "path": ("walkforward_phase_b_path", "walkforward_phase_c_naive"),
    "export": ("reporting", "signal", "feature_file_write"),
}

_LAUNCHER_TO_TIMING: Dict[str, tuple[str, ...]] = {
    "env": (),
    "libs": (),
    "core": (),
    "paper": (),
    "run": (
        "tickers_load",
        "download",
        "feature_build",
        "feature_cache_load",
        "cluster_overlay",
        "walkforward_phase_a_ml",
        "walkforward_phase_b_path",
        "walkforward_phase_c_naive",
        "reporting",
        "signal",
    ),
}

# Fallback seconds when no profile exists (typical warm-cache EXE run).
_DEFAULT_BACKTEST_SECONDS: Dict[str, float] = {
    "universe": 30.0,
    "features": 120.0,
    "ml": 900.0,
    "path": 600.0,
    "export": 45.0,
}

_DEFAULT_LAUNCHER_SECONDS: Dict[str, float] = {
    "env": 90.0,
    "libs": 30.0,
    "core": 15.0,
    "paper": 45.0,
    "run": 1500.0,
}


def load_timing_profile(out_dir: Path) -> Dict[str, float]:
    """Load section seconds from the latest phase_timings.json in out_dir."""
    path = Path(out_dir) / "phase_timings.json"
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        sections = data.get("sections_seconds") or {}
        return {str(k): float(v) for k, v in sections.items() if _is_finite(v)}
    except Exception:
        return {}


def _is_finite(val: Any) -> bool:
    try:
        f = float(val)
        return f == f and f >= 0.0
    except Exception:
        return False


def _step_budget(
    step_key: str,
    *,
    pipeline: bool,
    profile: Dict[str, float],
) -> float:
    if pipeline:
        timing_keys = _PIPELINE_TO_TIMING.get(step_key, ())
        default = _DEFAULT_BACKTEST_SECONDS.get(step_key, 60.0)
        weight = BACKTEST_PIPELINE_WEIGHTS.get(step_key, 0.0)
    else:
        timing_keys = _LAUNCHER_TO_TIMING.get(step_key, ())
        default = _DEFAULT_LAUNCHER_SECONDS.get(step_key, 30.0)
        weight = LAUNCHER_STEP_WEIGHTS.get(step_key, 0.0)
    if timing_keys:
        measured = sum(profile.get(k, 0.0) for k in timing_keys)
        if measured > 1.0:
            return measured
    if profile.get("total_run", 0.0) > 1.0 and weight > 0:
        return float(profile["total_run"]) * weight
    return default


def build_backtest_budgets(out_dir: str = "") -> Dict[str, float]:
    profile = load_timing_profile(Path(out_dir)) if out_dir else {}
    return {k: _step_budget(k, pipeline=True, profile=profile) for k in BACKTEST_PIPELINE_WEIGHTS}


def build_launcher_budgets() -> Dict[str, float]:
    return {k: _step_budget(k, pipeline=False, profile={}) for k in LAUNCHER_STEP_WEIGHTS}


def estimate_backtest_remaining(
    *,
    pipeline_status: Dict[str, str],
    active_key: Optional[str],
    sub_completed: int,
    sub_total: int,
    elapsed: float,
    out_dir: str = "",
) -> Optional[float]:
    profile = load_timing_profile(Path(out_dir)) if out_dir else {}
    budgets = {k: _step_budget(k, pipeline=True, profile=profile) for k in BACKTEST_PIPELINE_WEIGHTS}
    total = sum(budgets.values())
    if total <= 0:
        return None
    done = 0.0
    for key, budget in budgets.items():
        status = pipeline_status.get(key, "pending")
        if status in {"done", "skipped"}:
            done += budget
        elif status == "active" and key == active_key and sub_total > 0:
            frac = min(max(sub_completed / sub_total, 0.0), 1.0)
            done += budget * frac
    remaining = max(total - done, 0.0)
    if done <= 0 and elapsed > 0:
        ratio = min(max(elapsed / total, 0.01), 0.99)
        remaining = max(total * (1.0 - ratio), 0.0)
    return remaining


def estimate_launcher_remaining(
    *,
    status: Dict[str, str],
    active_key: Optional[str],
    run_sub_ratio: float,
    elapsed: float,
) -> Optional[float]:
    budgets = build_launcher_budgets()
    total = sum(budgets.values())
    done = 0.0
    for key, budget in budgets.items():
        st = status.get(key, "pending")
        if st == "done":
            done += budget
        elif st == "active" and key == active_key:
            partial = 0.35 if key != "run" else max(min(run_sub_ratio, 1.0), 0.05)
            done += budget * partial
    remaining = max(total - done, 0.0)
    if done <= 0 and elapsed > 30:
        remaining = max(total - elapsed, 0.0)
    return remaining

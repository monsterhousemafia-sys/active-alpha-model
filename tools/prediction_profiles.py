"""Signal prediction profiles — matrix variant keys → AA_* environment."""
from __future__ import annotations

from typing import Any, Dict, Optional

from tools.run_validation_matrix import MATRIX


def _variant_by_key(key: str) -> Dict[str, Any]:
    for row in MATRIX:
        if str(row.get("key")) == key:
            return dict(row)
    raise KeyError(f"unknown variant key: {key}")


def profile_env(profile: str) -> Dict[str, str]:
    """Build environment overlay for signal/backtest from a named profile."""
    ops = {
        "daily_alpha_h1": "DAILY_ALPHA_H1",
        "r3_w075_production": "R3_w075_q065_noexit",
        "r0_governance": "R0_LEGACY_ENSEMBLE",
    }
    key = ops.get(profile)
    if not key:
        raise KeyError(f"unknown profile: {profile}")
    v = _variant_by_key(key)
    env: Dict[str, str] = {
        "AA_VARIANT_ID": key,
        "AA_PREDICTION_PROFILE": profile,
    }
    if v.get("horizon") is not None:
        env["AA_HORIZON"] = str(v["horizon"])
    if v.get("rebalance_every") is not None:
        env["AA_REBALANCE_EVERY"] = str(v["rebalance_every"])
    if v.get("alpha_model_mode"):
        env["AA_ALPHA_MODEL_MODE"] = str(v["alpha_model_mode"])
    if v.get("train_years") is not None:
        env["AA_TRAIN_YEARS"] = str(v["train_years"])
    if v.get("top_k") is not None:
        env["AA_TOP_K"] = str(v["top_k"])
    env["AA_RISK_OFF_SELECTION_MODE"] = str(v.get("risk_off_selection_mode", "legacy"))
    env["AA_RISK_OFF_GATE_MODE"] = str(v.get("risk_off_gate_mode", "legacy"))
    if v.get("risk_off_momentum_variant"):
        env["AA_RISK_OFF_MOMENTUM_VARIANT"] = str(v["risk_off_momentum_variant"])
    if v.get("risk_off_momentum_weight") is not None:
        env["AA_RISK_OFF_MOMENTUM_WEIGHT"] = str(v["risk_off_momentum_weight"])
    if v.get("risk_off_momentum_rescue_quantile") is not None:
        env["AA_RISK_OFF_MOMENTUM_RESCUE_QUANTILE"] = str(v["risk_off_momentum_rescue_quantile"])
    env["AA_RISK_OFF_FORCE_EXIT_ENABLED"] = "J" if v.get("risk_off_force_exit_enabled") else "N"
    if v.get("force_rebuild_features"):
        env["AA_FORCE_REBUILD_FEATURES"] = "1"
        env["AA_SKIP_DOWNLOAD_IF_CACHED"] = "0"
    if v.get("benchmark_variant"):
        env["AA_SKIP_NAIVE_MOMENTUM_BASELINE"] = "0"
        env["AA_NAIVE_DETAILED_REPORTING"] = "1"
        env["AA_NAIVE_DETAILED_VARIANTS"] = str(v["benchmark_variant"])
    env.setdefault("AA_NO_PLOT", "1")
    env.setdefault("AA_GUI", "0")
    env.setdefault("AA_AUTO_OPS_REFRESH", "1")
    return env


def list_profiles() -> Dict[str, str]:
    return {
        "daily_alpha_h1": "DAILY_ALPHA_H1",
        "r3_w075_production": "R3_w075_q065_noexit",
        "r0_governance": "R0_LEGACY_ENSEMBLE",
    }

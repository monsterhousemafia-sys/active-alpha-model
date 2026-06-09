"""Canonical variant identifiers for risk-off research matrix."""
from __future__ import annotations

from typing import Any, Dict, Optional

from aa_config import BacktestConfig


def _pct_tag(value: float) -> str:
    return f"{int(round(float(value) * 100)):03d}"


def resolve_canonical_variant_id(cfg: BacktestConfig) -> str:
    """Map config to a unique variant ID including all behavior-relevant risk-off params."""
    alpha_mode = str(getattr(cfg, "alpha_model_mode", "ensemble") or "ensemble").lower()
    if alpha_mode == "rank_only":
        train_years = int(getattr(cfg, "train_years", 5) or 5)
        return f"R5_rank_only_train{train_years}"

    mode = str(getattr(cfg, "risk_off_selection_mode", "legacy") or "legacy").lower()
    gate = str(getattr(cfg, "risk_off_gate_mode", "legacy") or "legacy").lower()
    force_exit = bool(getattr(cfg, "risk_off_force_exit_enabled", False))

    if bool(getattr(cfg, "naive_detailed_reporting", False)):
        raw = str(getattr(cfg, "naive_detailed_variants", "") or "")
        variants = [x.strip().lower() for x in raw.split(",") if x.strip()]
        if variants == ["mom_blend_matched_controls"]:
            return "M1_MOM_BLEND_MATCHED_CONTROLS"

    if mode == "legacy" and gate == "legacy" and not force_exit:
        return "R0_LEGACY_ENSEMBLE"
    if mode == "legacy" and gate == "base_only":
        return "R1_GATE_BASE_ONLY"
    if mode == "mom_blend_replace":
        return "R2_MOM_BLEND_REPLACE"

    w = float(getattr(cfg, "risk_off_momentum_weight", 0.70) or 0.70)
    q = float(getattr(cfg, "risk_off_momentum_rescue_quantile", 0.70) or 0.70)
    exit_tag = "forceexit" if force_exit else "noexit"

    if mode in {"mom_blend_blend", "momentum_rescue", "mom_rescue"} or gate == "momentum_rescue":
        base = "R4" if force_exit else "R3"
        return f"{base}_w{_pct_tag(w)}_q{_pct_tag(q)}_{exit_tag}"

    return f"CUSTOM_{mode}_{gate}_{exit_tag}"


def legacy_research_key_map() -> Dict[str, str]:
    """Map legacy experiment keys to canonical IDs (backward compatibility)."""
    return {
        "R0_LEGACY_ENSEMBLE": "R0_LEGACY_ENSEMBLE",
        "R1_GATE_BASE_ONLY": "R1_GATE_BASE_ONLY",
        "R2_MOM_BLEND_REPLACE": "R2_MOM_BLEND_REPLACE",
        "R3_RISK_OFF_MOMENTUM_RESCUE": "R3_w070_q070_noexit",
        "R4_RISK_OFF_MOMENTUM_RESCUE_FORCE_EXIT": "R4_w070_q070_forceexit",
        "M1_MOM_BLEND_MATCHED_CONTROLS": "M1_MOM_BLEND_MATCHED_CONTROLS",
    }


def normalize_variant_label(label: Optional[str], cfg: Optional[BacktestConfig] = None) -> str:
    if cfg is not None:
        return resolve_canonical_variant_id(cfg)
    if not label:
        return "UNKNOWN"
    return legacy_research_key_map().get(str(label), str(label))

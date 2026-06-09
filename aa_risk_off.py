"""Risk-off momentum rescue helpers shared by portfolio, backtest, and reporting."""
from __future__ import annotations

from typing import Any, Dict, Optional

import pandas as pd

from aa_config import BacktestConfig

VALID_RISK_OFF_SELECTION_MODES = frozenset({"legacy", "mom_blend_replace", "mom_blend_blend"})
VALID_RISK_OFF_GATE_MODES = frozenset({"legacy", "base_only", "momentum_rescue"})


def validate_risk_off_config(cfg: BacktestConfig) -> None:
    sel = str(getattr(cfg, "risk_off_selection_mode", "legacy") or "legacy").lower().strip()
    gate = str(getattr(cfg, "risk_off_gate_mode", "legacy") or "legacy").lower().strip()
    if sel not in VALID_RISK_OFF_SELECTION_MODES:
        raise ValueError(f"risk_off_selection_mode must be one of {sorted(VALID_RISK_OFF_SELECTION_MODES)}, got {sel!r}")
    if gate not in VALID_RISK_OFF_GATE_MODES:
        raise ValueError(f"risk_off_gate_mode must be one of {sorted(VALID_RISK_OFF_GATE_MODES)}, got {gate!r}")
    w = float(getattr(cfg, "risk_off_momentum_weight", 0.70) or 0.70)
    q = float(getattr(cfg, "risk_off_momentum_rescue_quantile", 0.70) or 0.70)
    if not (0.0 <= w <= 1.0):
        raise ValueError(f"risk_off_momentum_weight must be between 0.0 and 1.0, got {w}")
    if not (0.0 <= q <= 1.0):
        raise ValueError(f"risk_off_momentum_rescue_quantile must be between 0.0 and 1.0, got {q}")


def compute_eligibility_reason(
    snap: pd.DataFrame,
    cfg: BacktestConfig,
    *,
    risk_on: bool,
    base_ok: pd.Series,
    legacy_ok: pd.Series,
    rescue_ok: pd.Series,
    eligible: pd.Series,
) -> pd.Series:
    """Per-name eligibility reason for research diagnostics."""
    reasons = pd.Series("rejected_risk_off_gate", index=snap.index, dtype=object)
    if risk_on:
        reasons.loc[base_ok.fillna(False)] = "risk_on_base_ok"
        reasons.loc[~base_ok.fillna(False) & ~snap.get("in_universe", pd.Series(True, index=snap.index)).fillna(False).astype(bool)] = "rejected_membership"
        adv = pd.to_numeric(snap.get("adv_20", 0.0), errors="coerce").fillna(0.0)
        reasons.loc[(~base_ok.fillna(False)) & (adv < cfg.min_adv) & snap.get("mu_hat", pd.Series(index=snap.index)).notna()] = "rejected_adv"
        vol = pd.to_numeric(snap.get("vol_20", 99.0), errors="coerce").fillna(99.0)
        reasons.loc[(~base_ok.fillna(False)) & (vol > cfg.max_ann_vol)] = "rejected_volatility"
        return reasons
    gate_mode = str(getattr(cfg, "risk_off_gate_mode", "legacy") or "legacy").lower().strip()
    if gate_mode == "base_only":
        reasons.loc[base_ok.fillna(False)] = "risk_on_base_ok"
    else:
        reasons.loc[legacy_ok.fillna(False)] = "risk_off_legacy_gate"
        reasons.loc[eligible.fillna(False) & rescue_ok.fillna(False) & ~legacy_ok.fillna(False)] = "risk_off_momentum_rescue"
    reasons.loc[~eligible.fillna(False) & ~snap.get("in_universe", pd.Series(True, index=snap.index)).fillna(False).astype(bool)] = "rejected_membership"
    adv = pd.to_numeric(snap.get("adv_20", 0.0), errors="coerce").fillna(0.0)
    reasons.loc[(~eligible.fillna(False)) & (adv < cfg.min_adv) & snap.get("mu_hat", pd.Series(index=snap.index)).notna()] = "rejected_adv"
    vol = pd.to_numeric(snap.get("vol_20", 99.0), errors="coerce").fillna(99.0)
    reasons.loc[(~eligible.fillna(False)) & (vol > cfg.max_ann_vol)] = "rejected_volatility"
    return reasons


def attach_risk_off_diagnostics(
    snap: pd.DataFrame,
    cfg: BacktestConfig,
    *,
    risk_on: bool,
    base_ok: pd.Series,
    legacy_ok: pd.Series,
    rescue_ok: pd.Series,
    eligible: pd.Series,
    ensemble_score: pd.Series,
    ensemble_rank: pd.Series,
    momentum_score: pd.Series,
    momentum_rank: pd.Series,
) -> pd.DataFrame:
    """Add standard risk-off research columns without changing legacy numeric paths."""
    out = snap.copy()
    out["risk_off_selection_mode"] = str(getattr(cfg, "risk_off_selection_mode", "legacy") or "legacy")
    out["risk_off_gate_mode"] = str(getattr(cfg, "risk_off_gate_mode", "legacy") or "legacy")
    out["risk_off_momentum_variant"] = str(getattr(cfg, "risk_off_momentum_variant", "mom_blend_top12") or "mom_blend_top12")
    out["risk_off_momentum_score"] = pd.to_numeric(momentum_score, errors="coerce")
    out["risk_off_momentum_rank"] = pd.to_numeric(momentum_rank, errors="coerce")
    out["mom_blend_score"] = out["risk_off_momentum_score"]
    out["mom_blend_rank"] = out["risk_off_momentum_rank"]
    out["ensemble_selection_score"] = pd.to_numeric(ensemble_score, errors="coerce")
    out["ensemble_selection_rank"] = pd.to_numeric(ensemble_rank, errors="coerce")
    out["eligible_legacy_risk_off"] = legacy_ok.fillna(False).astype(bool)
    out["eligible_momentum_rescue"] = rescue_ok.fillna(False).astype(bool)
    out["eligibility_reason"] = compute_eligibility_reason(
        out, cfg, risk_on=risk_on, base_ok=base_ok, legacy_ok=legacy_ok, rescue_ok=rescue_ok, eligible=eligible,
    )
    out["rescued_by_momentum"] = (not risk_on) & out["eligible_momentum_rescue"] & eligible & ~legacy_ok
    return out


def compute_forced_exit_diagnostics(
    forced_exit: set,
    prev_weights: pd.Series,
    target_before: pd.Series,
    target_after: pd.Series,
    final_weights: pd.Series,
    fee_diag: Dict[str, Any],
) -> Dict[str, float]:
    """Summarize forced-exit impact for one rebalance."""
    if not forced_exit or prev_weights.empty:
        return {
            "n_forced_exit_candidates": 0.0,
            "forced_exit_weight_before_controls": 0.0,
            "forced_exit_weight_after_controls": 0.0,
            "forced_exit_turnover": 0.0,
            "forced_exit_cost": 0.0,
        }
    prev = prev_weights.reindex(list(forced_exit)).fillna(0.0)
    before = target_before.reindex(list(forced_exit)).fillna(0.0)
    after = target_after.reindex(list(forced_exit)).fillna(0.0)
    final = final_weights.reindex(list(forced_exit)).fillna(0.0)
    forced_turnover = float((final - prev).abs().sum())
    total_turnover = float(fee_diag.get("turnover", fee_diag.get("raw_turnover", 0.0)) or 0.0)
    tx_cost = float(fee_diag.get("tx_cost", 0.0) or 0.0)
    share = forced_turnover / total_turnover if total_turnover > 1e-12 else 0.0
    return {
        "n_forced_exit_candidates": float(len(forced_exit)),
        "forced_exit_weight_before_controls": float(prev.sum()),
        "forced_exit_weight_after_controls": float(final.sum()),
        "forced_exit_turnover": forced_turnover,
        "forced_exit_cost": tx_cost * share,
    }

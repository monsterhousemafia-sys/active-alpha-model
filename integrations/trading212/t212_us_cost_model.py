"""Trading 212 US-equity cost estimates (FX fee + reservation buffer) for sizing and UI."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from integrations.trading212.t212_limit_order_constraints import US_EQUITY_RESERVATION_BUFFER

DEFAULT_US_FX_FEE_PCT = 0.0015  # ~0.15% on USD→EUR conversion (Invest plan)


def default_cost_policy() -> Dict[str, Any]:
    return {
        "schema_version": 1,
        "enabled": True,
        "us_equity_fx_fee_pct": DEFAULT_US_FX_FEE_PCT,
        "us_equity_reservation_buffer": US_EQUITY_RESERVATION_BUFFER,
        "show_fx_fee_in_playbook": True,
    }


def load_t212_cost_policy(root: Path | None = None) -> Dict[str, Any]:
    if root is None:
        return default_cost_policy()
    from analytics.pilot_day_trading_policy import policy_section

    base = default_cost_policy()
    sec = policy_section(Path(root), "costs")
    if not isinstance(sec, dict):
        return base
    out = dict(base)
    for key, val in sec.items():
        if val is not None:
            out[key] = val
    return out


def effective_reservation_buffer(policy: Optional[Dict[str, Any]] = None) -> float:
    pol = policy or default_cost_policy()
    return float(pol.get("us_equity_reservation_buffer") or US_EQUITY_RESERVATION_BUFFER)


def effective_fx_fee_pct(policy: Optional[Dict[str, Any]] = None) -> float:
    pol = policy or default_cost_policy()
    if not pol.get("enabled", True):
        return 0.0
    return float(pol.get("us_equity_fx_fee_pct") or DEFAULT_US_FX_FEE_PCT)


def effective_cost_per_share(
    limit_price_eur: float,
    policy: Optional[Dict[str, Any]] = None,
) -> float:
    """Per-share cash need: limit × reservation buffer × (1 + FX fee)."""
    if limit_price_eur <= 0:
        return 0.0
    pol = policy or default_cost_policy()
    buf = effective_reservation_buffer(pol)
    fee = effective_fx_fee_pct(pol)
    return float(limit_price_eur) * buf * (1.0 + fee)


def estimate_buy_cost_breakdown(
    *,
    notional_eur: float,
    limit_price_eur: float,
    quantity: float,
    policy: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Estimated T212 costs for a US equity limit buy (display + audit)."""
    pol = policy or default_cost_policy()
    notional = max(0.0, float(notional_eur))
    limit = max(0.0, float(limit_price_eur))
    qty = max(0.0, float(quantity))
    fee_pct = effective_fx_fee_pct(pol)
    buf = effective_reservation_buffer(pol)
    fx_fee_eur = round(notional * fee_pct, 4)
    base_notional = qty * limit if limit > 0 else notional
    reserved_extra_eur = round(base_notional * max(0.0, buf - 1.0), 2)
    all_in_notional_eur = round(base_notional * buf * (1.0 + fee_pct), 2)
    return {
        "fx_fee_pct": fee_pct,
        "reservation_buffer": buf,
        "estimated_fx_fee_eur": fx_fee_eur,
        "estimated_reservation_uplift_eur": reserved_extra_eur,
        "all_in_notional_eur": all_in_notional_eur,
        "cost_per_share_eur": round(effective_cost_per_share(limit, pol), 4) if limit > 0 else 0.0,
    }


def format_cost_step_de(
    root: Path,
    *,
    notional_eur: float,
    limit_price_eur: float = 0.0,
    quantity: float = 0.0,
) -> str | None:
    pol = load_t212_cost_policy(root)
    if not pol.get("show_fx_fee_in_playbook", True) or not pol.get("enabled", True):
        return None
    if notional_eur <= 0:
        return None
    est = estimate_buy_cost_breakdown(
        notional_eur=notional_eur,
        limit_price_eur=limit_price_eur or (notional_eur / max(quantity, 0.01)),
        quantity=quantity or (notional_eur / max(limit_price_eur, 0.01)),
        policy=pol,
    )
    fee_pct = est["fx_fee_pct"] * 100.0
    return (
        f"T212-Kosten (Schätzung): FX ~{fee_pct:.2f}% ≈ {est['estimated_fx_fee_eur']:.2f} € · "
        f"Reservierung +{(est['reservation_buffer'] - 1) * 100:.0f}% · "
        f"All-in ~{est['all_in_notional_eur']:.2f} €"
    )

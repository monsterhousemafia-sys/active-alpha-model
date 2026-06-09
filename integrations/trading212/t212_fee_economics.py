"""T212 fee economics for live pilot — aligned with backtest assumptions, blocks uneconomic trades."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

# Defaults match aa_config.BacktestConfig / trading212_fx_bps=15 (0.15% per FX leg).
DEFAULT_FX_BPS = 15.0
DEFAULT_SLIPPAGE_BPS = 5.0  # conservative live guard (backtest champion often uses 0)
DEFAULT_MIN_TRADE_COST_MULTIPLE = 3.0  # trade only if notional >= N × est. round-trip cost
DEFAULT_STRESS_FX_BPS_ADD = 25.0
DEFAULT_STRESS_SLIPPAGE_BPS_ADD = 10.0


def default_fee_economics_policy() -> Dict[str, Any]:
    return {
        "fx_bps": DEFAULT_FX_BPS,
        "slippage_bps": DEFAULT_SLIPPAGE_BPS,
        "market_impact_bps": 0.0,
        "sec_fee_rate": 0.0000278,
        "finra_taf_per_share": 0.000195,
        "min_trade_cost_multiple": DEFAULT_MIN_TRADE_COST_MULTIPLE,
        "min_trade_eur_floor": 12.0,
        "include_sell_regulatory_fees": True,
        "stress_fx_bps_add": DEFAULT_STRESS_FX_BPS_ADD,
        "stress_slippage_bps_add": DEFAULT_STRESS_SLIPPAGE_BPS_ADD,
        "require_stress_pass_for_trade": True,
    }


def load_fee_economics_policy(root: Path | None = None) -> Dict[str, Any]:
    base = default_fee_economics_policy()
    if root is None:
        return base
    from analytics.pilot_day_trading_policy import policy_section

    costs = policy_section(Path(root), "costs")
    if not isinstance(costs, dict):
        return base
    out = dict(base)
    if costs.get("us_equity_fx_fee_pct") is not None:
        out["fx_bps"] = float(costs["us_equity_fx_fee_pct"]) * 10_000.0
    for key in (
        "slippage_bps",
        "market_impact_bps",
        "min_trade_cost_multiple",
        "min_trade_eur_floor",
        "include_sell_regulatory_fees",
        "stress_fx_bps_add",
        "stress_slippage_bps_add",
        "require_stress_pass_for_trade",
    ):
        if costs.get(key) is not None:
            out[key] = costs[key]
    return out


def _stress_policy(pol: Dict[str, Any]) -> Dict[str, Any]:
    stressed = dict(pol)
    stressed["fx_bps"] = float(pol.get("fx_bps") or DEFAULT_FX_BPS) + float(
        pol.get("stress_fx_bps_add") or DEFAULT_STRESS_FX_BPS_ADD
    )
    stressed["slippage_bps"] = float(pol.get("slippage_bps") or 0.0) + float(
        pol.get("stress_slippage_bps_add") or DEFAULT_STRESS_SLIPPAGE_BPS_ADD
    )
    return stressed


def estimate_stress_round_trip_cost_eur(
    notional_eur: float,
    *,
    price_eur: float = 0.0,
    policy: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    pol = policy or default_fee_economics_policy()
    stressed = _stress_policy(pol)
    out = estimate_round_trip_cost_eur(
        notional_eur, price_eur=price_eur, policy=stressed
    )
    out["stress_add_bps"] = float(pol.get("stress_fx_bps_add") or DEFAULT_STRESS_FX_BPS_ADD) + float(
        pol.get("stress_slippage_bps_add") or DEFAULT_STRESS_SLIPPAGE_BPS_ADD
    )
    return out


def is_notional_worth_trading_stress(
    notional_eur: float,
    root: Path | None = None,
    *,
    price_eur: float = 0.0,
) -> tuple[bool, str]:
    pol = load_fee_economics_policy(root)
    est = estimate_stress_round_trip_cost_eur(
        notional_eur, price_eur=price_eur, policy=pol
    )
    multiple = float(pol.get("min_trade_cost_multiple") or DEFAULT_MIN_TRADE_COST_MULTIPLE)
    floor = float(pol.get("min_trade_eur_floor") or 12.0)
    hurdle = max(floor, est["round_trip_cost_eur"] * multiple)
    n = float(notional_eur)
    if n < hurdle:
        return (
            False,
            f"Stress: Notional {n:.2f} € < Hürde {hurdle:.2f} € "
            f"(~{est['round_trip_cost_eur']:.2f} €, {est['round_trip_pct']:.2f} %)",
        )
    return True, ""


def _bps_cost(notional_eur: float, bps: float) -> float:
    return abs(float(notional_eur)) * float(bps) / 10_000.0


def estimate_round_trip_cost_eur(
    notional_eur: float,
    *,
    price_eur: float = 0.0,
    policy: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Estimated full round-trip on a US equity position (EUR account):
    FX buy + FX sell + slippage both legs + optional US sell regulatory.
    """
    pol = policy or default_fee_economics_policy()
    n = max(0.0, float(notional_eur))
    fx_bps = float(pol.get("fx_bps") or DEFAULT_FX_BPS)
    slip_bps = float(pol.get("slippage_bps") or 0.0)
    impact_bps = float(pol.get("market_impact_bps") or 0.0)
    fx_total = _bps_cost(n, fx_bps) * 2.0
    slippage_total = _bps_cost(n, slip_bps) * 2.0
    impact_total = _bps_cost(n, impact_bps) * 2.0
    regulatory = 0.0
    if pol.get("include_sell_regulatory_fees", True) and n > 0:
        price = float(price_eur) if price_eur > 0 else n
        shares = n / price if price > 0 else 0.0
        regulatory = n * float(pol.get("sec_fee_rate") or 0.0) + shares * float(
            pol.get("finra_taf_per_share") or 0.0
        )
    total = round(fx_total + slippage_total + impact_total + regulatory, 4)
    return {
        "notional_eur": round(n, 2),
        "fx_cost_eur": round(fx_total, 4),
        "slippage_cost_eur": round(slippage_total, 4),
        "market_impact_cost_eur": round(impact_total, 4),
        "sell_regulatory_cost_eur": round(regulatory, 4),
        "round_trip_cost_eur": total,
        "round_trip_pct": round(100.0 * total / n, 3) if n > 0 else 0.0,
    }


def trade_fee_hurdle_eur(
    root: Path | None,
    *,
    notional_eur: float,
    price_eur: float = 0.0,
) -> float:
    """Minimum notional so expected trade is not dominated by T212 fees."""
    pol = load_fee_economics_policy(root)
    est = estimate_round_trip_cost_eur(notional_eur, price_eur=price_eur, policy=pol)
    multiple = float(pol.get("min_trade_cost_multiple") or DEFAULT_MIN_TRADE_COST_MULTIPLE)
    floor = float(pol.get("min_trade_eur_floor") or 12.0)
    hurdle = est["round_trip_cost_eur"] * multiple
    return round(max(floor, hurdle), 2)


def is_notional_worth_trading(
    notional_eur: float,
    root: Path | None = None,
    *,
    price_eur: float = 0.0,
) -> tuple[bool, str]:
    n = float(notional_eur)
    if n <= 0:
        return False, "NOTIONAL_ZERO"
    hurdle = trade_fee_hurdle_eur(root, notional_eur=n, price_eur=price_eur)
    if n < hurdle:
        est = estimate_round_trip_cost_eur(n, price_eur=price_eur, policy=load_fee_economics_policy(root))
        return (
            False,
            f"Notional {n:.2f} € < Kostenhürde {hurdle:.2f} € "
            f"(Round-trip ~{est['round_trip_cost_eur']:.2f} €, {est['round_trip_pct']:.2f} %)",
        )
    return True, ""


def net_buy_target_after_costs(
    target_eur: float,
    root: Path | None = None,
) -> Dict[str, Any]:
    """Reduce planned buy notional by one-way FX+slippage (conservative plan sizing)."""
    pol = load_fee_economics_policy(root)
    gross = max(0.0, float(target_eur))
    one_way_bps = float(pol.get("fx_bps") or DEFAULT_FX_BPS) + float(pol.get("slippage_bps") or 0.0)
    one_way = _bps_cost(gross, one_way_bps)
    net = round(max(0.0, gross - one_way), 2)
    return {
        "gross_target_eur": round(gross, 2),
        "estimated_one_way_cost_eur": round(one_way, 4),
        "net_target_eur": net,
    }


def round_trip_summary_de(notional_eur: float, root: Path | None = None) -> str:
    est = estimate_round_trip_cost_eur(
        notional_eur, policy=load_fee_economics_policy(root)
    )
    return (
        f"geschätzte Round-trip-Kosten ~{est['round_trip_cost_eur']:.2f} € "
        f"({est['round_trip_pct']:.2f} % vom Volumen)"
    )

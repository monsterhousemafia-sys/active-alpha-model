"""T212 Währungs- und Gebührenkontext für Berechnungsgrundlage und Plan-Skalierung."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from integrations.trading212.t212_fee_economics import (
    estimate_round_trip_cost_eur,
    load_fee_economics_policy,
    net_buy_target_after_costs,
    round_trip_summary_de,
)


def extract_currency_context(broker: Dict[str, Any]) -> Dict[str, Any]:
    """
    Währungslage aus T212-Broker-Snapshot.

    T212 EU: Kontowert und walletImpact.currentValue sind in EUR gebucht;
    US-Aktienkäufe lösen Broker-FX (USD↔EUR) aus — siehe Fee-Policy.
    """
    bd = broker.get("cash_breakdown") or {}
    account_ccy = str(bd.get("currency") or "EUR").upper()
    planning = bd.get("planning_cash_eur")
    if planning is None:
        planning = broker.get("r3_planning_cash_eur")
    if planning is None:
        planning = broker.get("cash_eur")

    reserved = bd.get("reserved_for_orders_eur")
    in_pies = bd.get("in_pies_eur")
    total = bd.get("total_account_value_eur")
    invested = bd.get("invested_current_value_eur")

    held_ccys: List[str] = []
    for pos in broker.get("positions") or []:
        if not isinstance(pos, dict):
            continue
        inst = pos.get("instrument") if isinstance(pos.get("instrument"), dict) else {}
        qc = str(inst.get("currency") or inst.get("quoteCurrency") or "").upper()
        if qc and qc not in held_ccys:
            held_ccys.append(qc)

    notes: List[str] = []
    if account_ccy != "EUR":
        notes.append(f"Kontowährung {account_ccy} — EUR-Felder aus API-Breakdown")
    if reserved not in (None, 0, 0.0):
        notes.append(f"{float(reserved):.2f} € für offene Orders reserviert (nicht planbar)")
    if in_pies not in (None, 0, 0.0):
        notes.append(f"{float(in_pies):.2f} € in Pies (nicht Einzelaktien-Plan)")
    if held_ccys:
        notes.append(f"Instrument-Währungen: {', '.join(sorted(held_ccys))} — Bewertung EUR (walletImpact)")

    return {
        "account_currency": account_ccy,
        "position_quote_currencies": held_ccys,
        "planning_cash_eur": planning,
        "reserved_for_orders_eur": reserved,
        "in_pies_eur": in_pies,
        "total_account_value_eur": total,
        "invested_current_value_eur": invested,
        "valuation_currency": "EUR",
        "us_equity_fx_on_trade": True,
        "cash_source": bd.get("source") or broker.get("live_picture_source"),
        "note_de": " · ".join(notes) if notes else "EUR-Konto — US-Trades mit T212-FX laut Kostenmodell",
    }


def fee_policy_summary(root: Any) -> Dict[str, Any]:
    """Aktive T212-Gebührenannahmen (aus pilot_day_trading.costs)."""
    from pathlib import Path

    pol = load_fee_economics_policy(Path(root) if root else None)
    fx_pct = round(float(pol.get("fx_bps") or 0) / 100.0, 4)
    slip_pct = round(float(pol.get("slippage_bps") or 0) / 100.0, 4)
    return {
        "fx_bps": pol.get("fx_bps"),
        "fx_pct_per_leg": fx_pct,
        "slippage_bps": pol.get("slippage_bps"),
        "min_trade_cost_multiple": pol.get("min_trade_cost_multiple"),
        "min_trade_eur_floor": pol.get("min_trade_eur_floor"),
        "require_stress_pass_for_trade": pol.get("require_stress_pass_for_trade"),
        "include_sell_regulatory_fees": pol.get("include_sell_regulatory_fees"),
        "summary_de": (
            f"T212 US-Equity: FX ~{fx_pct:.2f}% pro Leg · Slippage ~{slip_pct:.2f}% · "
            f"Min-Trade-Floor {float(pol.get('min_trade_eur_floor') or 0):.0f} €"
        ),
    }


def apply_buy_target_fee_adjustment(
    target_gross_eur: float,
    root: Any,
) -> Dict[str, Any]:
    """Einweg-FX+Slippage von Kauf-Ziel abziehen (konservative Plan-Skalierung)."""
    adj = net_buy_target_after_costs(target_gross_eur, Path(root) if root else None)
    return {
        "target_eur_gross": round(max(0.0, float(target_gross_eur)), 2),
        "target_eur": float(adj.get("net_target_eur") or 0),
        "estimated_one_way_cost_eur": adj.get("estimated_one_way_cost_eur"),
    }


def build_broker_economics_context(
    root: Any,
    broker: Dict[str, Any],
    *,
    plan_capital_eur: float | None = None,
) -> Dict[str, Any]:
    """Währung + Gebühren für Evidence und R3-Anzeige."""
    from pathlib import Path

    root_p = Path(root) if root else None
    currency = extract_currency_context(broker)
    fees = fee_policy_summary(root_p)
    capital = float(plan_capital_eur or 0)
    sample_notional = round(max(25.0, capital * 0.05), 2) if capital > 0 else 50.0
    rt = estimate_round_trip_cost_eur(sample_notional, policy=load_fee_economics_policy(root_p))
    return {
        "currency": currency,
        "fees": fees,
        "sample_round_trip": {
            "notional_eur": sample_notional,
            **rt,
            "summary_de": round_trip_summary_de(sample_notional, root_p),
        },
        "headline_de": (
            f"{currency.get('note_de')} · {fees.get('summary_de')}"
        ),
    }

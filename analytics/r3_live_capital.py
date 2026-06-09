"""Aktueller T212-Kontostand als Berechnungsbasis + lohnende Positionen."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from aa_safe_io import atomic_write_json

_EVIDENCE_REL = Path("evidence/r3_live_capital_latest.json")
_WORTHWHILE_REL = Path("evidence/r3_worthwhile_positions_latest.json")

_BUY_CODES = frozenset({"NACHKAUF", "KAUFEN", "ERHÖHEN"})
_SELL_CODES = frozenset({"REDUZIEREN", "ABBAUEN", "VERKAUFEN"})


def _utc_now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def sync_live_capital_basis(root: Path, *, force: bool = True, sync_owner: str = "live_capital") -> Dict[str, Any]:
    """
    T212 live lesen — nur trusted Cash/Positionen als Berechnungsbasis (fail-closed).
    """
    root = Path(root)
    broker: Dict[str, Any] = {"sync_errors": []}
    try:
        from analytics.king_plan_integration import sync_t212_realtime_for_plan

        broker = sync_t212_realtime_for_plan(root, force=force, owner=sync_owner)
    except Exception as exc:
        broker["sync_errors"] = [str(exc)[:120]]

    trust: Dict[str, Any] = {}
    try:
        from integrations.trading212.t212_trust_gate import assess_t212_trust_from_root

        trust = assess_t212_trust_from_root(root, persist=True)
    except Exception as exc:
        return {
            "ok": False,
            "message_de": f"T212 Trust Gate — {str(exc)[:80]}",
            "sync_errors": broker.get("sync_errors") or [],
        }

    planning = broker.get("r3_planning_cash_eur")
    investable = broker.get("r3_investable_eur")
    cash = broker.get("cash_eur")

    if not trust.get("trusted"):
        return {
            "ok": False,
            "trusted": False,
            "message_de": trust.get("message_de") or "T212 nicht vertrauenswürdig — kein Live-Kontostand",
            "t212_trust_reason": trust.get("reason_code"),
            "last_sync_utc": broker.get("last_sync_utc"),
            "cash_eur": cash,
            "sync_errors": broker.get("sync_errors") or [],
        }

    if planning is None and cash is None:
        return {
            "ok": False,
            "trusted": True,
            "message_de": "Kontostand fehlt nach Sync — API prüfen",
            "sync_errors": broker.get("sync_errors") or [],
        }

    from analytics.prediction_operations import resolve_planning_basis_eur
    from execution.confirmed_live.planning_cash import resolve_planning_cash_eur

    live_planning = planning
    if live_planning is None and cash is not None:
        live_planning = resolve_planning_cash_eur(
            cash, broker=broker, root=root, subtract_pending_orders=True
        )
    basis = resolve_planning_basis_eur(root, live_planning)
    planning = basis.get("planning_cash_eur")
    investable = basis.get("investable_eur")
    planning_override = bool(basis.get("planning_override"))

    doc = {
        "schema_version": 1,
        "updated_at_utc": _utc_now(),
        "ok": True,
        "trusted": True,
        "planning_cash_eur": round(float(planning), 2) if planning is not None else None,
        "investable_eur": round(float(investable), 2) if investable is not None else None,
        "cash_eur": round(float(cash), 2) if cash is not None else None,
        "positions_count": int(broker.get("positions_count") or 0),
        "positions": broker.get("positions") or [],
        "last_sync_utc": broker.get("last_sync_utc"),
        "budget_source": "fixed_preview" if planning_override else "t212_live_sync",
        "planning_override": planning_override,
        "live_planning_cash_eur": basis.get("live_planning_cash_eur"),
        "message_de": (
            f"✓ Vorschau-Basis {float(planning or 0):.0f} € · "
            f"{float(investable or 0):.0f} € investierbar · "
            f"{int(broker.get('positions_count') or 0)} Positionen (fixed_preview)"
            if planning_override
            else (
                f"✓ Live-Kontostand {float(planning or cash or 0):.0f} € · "
                f"{float(investable or 0):.0f} € investierbar · "
                f"{int(broker.get('positions_count') or 0)} Positionen"
            )
        ),
        "broker": {
            "cash_eur": cash,
            "cash_breakdown": broker.get("cash_breakdown") or {},
            "positions": broker.get("positions") or [],
            "positions_count": int(broker.get("positions_count") or 0),
            "last_successful_sync_utc": broker.get("last_sync_utc"),
            "status": broker.get("status"),
            "credentials_configured": bool(broker.get("credentials_configured", True)),
            "r3_planning_cash_eur": planning,
            "r3_investable_eur": investable,
            "source": "t212_live_sync",
        },
    }
    atomic_write_json(root / _EVIDENCE_REL, doc)
    return doc


def _worthwhile_from_reeval(reeval: Dict[str, Any], *, flat_depot: bool) -> Dict[str, List[Dict[str, Any]]]:
    pol_min = 8.0
    rows = list(reeval.get("recommended_actions") or [])
    buys: List[Dict[str, Any]] = []
    sells: List[Dict[str, Any]] = []
    for row in rows:
        code = str(row.get("action_code") or "").upper()
        score = float(row.get("priority_score") or 0)
        gap = abs(float(row.get("gap_eur") or 0))
        if code in _BUY_CODES and gap > 0:
            if flat_depot or score >= pol_min:
                buys.append({**row, "side": "BUY", "worthwhile": True})
        elif code in _SELL_CODES and gap > 0:
            if score >= pol_min * 0.85:
                sells.append({**row, "side": "SELL", "worthwhile": True})
    buys.sort(key=lambda r: float(r.get("priority_score") or 0), reverse=True)
    sells.sort(key=lambda r: float(r.get("priority_score") or 0), reverse=True)
    return {"buys": buys, "sells": sells}


def _worthwhile_from_plan(plan: Dict[str, Any]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for row in plan.get("allocations") or []:
        sym = str(row.get("symbol") or "").upper()
        target = float(row.get("target_eur") or 0)
        if not sym or target <= 0:
            continue
        out.append(
            {
                "symbol": sym,
                "side": "BUY",
                "action_code": "KAUFEN",
                "action_de": row.get("rationale_de") or f"{sym}: Ziel {target:.0f} €",
                "gap_eur": target,
                "target_eur": target,
                "model_weight_pct": row.get("model_weight_pct"),
                "alpha_lcb": row.get("alpha_lcb"),
                "worthwhile": True,
                "priority_score": float(row.get("alpha_lcb") or 0) * 1000 + float(row.get("model_weight_pct") or 0),
                "source": "investment_plan",
            }
        )
    out.sort(key=lambda r: float(r.get("priority_score") or 0), reverse=True)
    return out


def compute_worthwhile_positions(
    root: Path, *, force_sync: bool = True, persist: bool = True, sync_owner: str = "prognosis_pipeline"
) -> Dict[str, Any]:
    """
    1) Aktuellen Kontostand syncen
    2) Plan auf Live-Cash skalieren
    3) Reevaluation vs. Champion
    4) Lohnende Käufe/Umschichtungen extrahieren
    """
    root = Path(root)
    capital = sync_live_capital_basis(root, force=force_sync, sync_owner=sync_owner)
    if not capital.get("ok"):
        doc = {
            "schema_version": 1,
            "updated_at_utc": _utc_now(),
            "ok": False,
            "headline_de": capital.get("message_de") or "Live-Kontostand ausstehend",
            "capital": capital,
        }
        if persist:
            atomic_write_json(root / _WORTHWHILE_REL, doc)
        return doc

    broker = dict(capital.get("broker") or {})
    from analytics.t212_live_portfolio_basis import (
        build_plan_on_live_basis,
        persist_live_basis_evidence,
    )

    plan, basis_meta = build_plan_on_live_basis(
        root,
        broker,
        planning_cash_eur=float(capital.get("planning_cash_eur") or capital.get("cash_eur") or 0),
        rebalance_to_holdings=True,
    )
    basis = basis_meta.get("basis") or {}
    from aa_safe_io import atomic_write_json as awj

    awj(
        root / "evidence/pilot_investment_plan_latest.json",
        {**plan, "updated_at_utc": _utc_now()},
    )
    persist_live_basis_evidence(root, basis, plan)

    from analytics.pilot_portfolio_reevaluation import evaluate_live_portfolio_vs_champion

    reeval = evaluate_live_portfolio_vs_champion(root, broker=broker, plan=plan)
    pos_n = int(
        basis.get("positions_count")
        or capital.get("positions_count")
        or (plan.get("t212_live") or {}).get("positions_count")
        or 0
    )
    flat = pos_n == 0
    split = _worthwhile_from_reeval(reeval, flat_depot=flat)
    risk_on = bool(reeval.get("risk_on", True))
    signals_ok = bool(reeval.get("signals_ok")) and bool(reeval.get("champion_ok", True))
    trade_required = bool(reeval.get("trade_required"))

    if plan.get("rebalanced_to_t212"):
        from analytics.t212_live_portfolio_basis import _worthwhile_from_rebalanced_plan

        reb_buys, reb_sells = _worthwhile_from_rebalanced_plan(plan)
        worthwhile_buys = reb_buys if risk_on and signals_ok else []
        worthwhile_sells = reb_sells + split["sells"]
    elif flat and risk_on and signals_ok:
        plan_buys = _worthwhile_from_plan(plan)
        worthwhile_buys = plan_buys
        worthwhile_sells = split["sells"]
    else:
        worthwhile_buys = split["buys"]
        worthwhile_sells = split["sells"]

    try:
        from analytics.r3_trading_functions import build_r3_trading_functions

        build_r3_trading_functions(root, persist=True)
    except Exception:
        pass

    if not risk_on and flat:
        headline = (
            f"Risk-off — kein Initial-Kauf auf {float(capital.get('investable_eur') or 0):.0f} € "
            f"(Signal {reeval.get('signal_date') or plan.get('signal_date') or '—'})"
        )
    elif worthwhile_buys or worthwhile_sells:
        headline = (
            f"✓ {len(worthwhile_buys)} Kauf · {len(worthwhile_sells)} Umschichtung "
            f"auf {float(capital.get('investable_eur') or 0):.0f} € Basis"
        )
    else:
        headline = (
            f"Keine lohnende Zeile auf {float(capital.get('investable_eur') or 0):.0f} € — "
            "Gebühren/Drift/Risk-off prüfen"
        )

    doc = {
        "schema_version": 1,
        "updated_at_utc": _utc_now(),
        "ok": True,
        "headline_de": headline,
        "risk_on": risk_on,
        "signals_ok": signals_ok,
        "signal_date": reeval.get("signal_date") or plan.get("signal_date"),
        "trade_required": trade_required,
        "capital_basis": {
            "planning_cash_eur": capital.get("planning_cash_eur"),
            "investable_eur": capital.get("investable_eur"),
            "cash_eur": capital.get("cash_eur"),
            "positions_count": capital.get("positions_count"),
            "last_sync_utc": capital.get("last_sync_utc"),
            "budget_source": "t212_live_sync",
        },
        "worthwhile_buys": worthwhile_buys,
        "worthwhile_sells": worthwhile_sells,
        "worthwhile_buy_count": len(worthwhile_buys),
        "worthwhile_sell_count": len(worthwhile_sells),
        "reevaluation_summary_de": reeval.get("summary_de"),
        "under_invested": (reeval.get("exposure_check") or {}).get("under_invested"),
        "trade_required": reeval.get("trade_required"),
        "calculation_basis": basis.get("calculation_basis"),
        "calculation_basis_de": basis.get("basis_de") or plan.get("calculation_basis_de"),
        "broker_economics": basis.get("broker_economics") or plan.get("broker_economics"),
        "currency_context": basis.get("currency_context") or plan.get("currency_context"),
        "fee_policy": basis.get("fee_policy") or plan.get("fee_policy"),
        "t212_holdings": basis.get("holdings"),
        "live_picture_source": basis.get("live_picture_source"),
        "rebalanced_to_t212": plan.get("rebalanced_to_t212"),
        "refs": {
            "capital": str(_EVIDENCE_REL),
            "plan": "evidence/pilot_investment_plan_latest.json",
            "reeval": "evidence/pilot_portfolio_reevaluation_latest.json",
            "live_basis": "evidence/t212_live_portfolio_basis_latest.json",
        },
    }
    if persist:
        atomic_write_json(root / _WORTHWHILE_REL, doc)
        atomic_write_json(root / _EVIDENCE_REL, {**capital, "worthwhile_ref": str(_WORTHWHILE_REL)})
    return doc

"""König 32B → Modell-Plan (Hintergrund) + Umschichtung gegen T212-Live-Depot."""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from aa_safe_io import atomic_write_json

_KING_EVIDENCE = Path("evidence/king_trading_assist_latest.json")
_PLAN_EVIDENCE = Path("evidence/pilot_investment_plan_latest.json")
_KING_POLICY = Path("control/king_trading_assist_policy.json")


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _load_json(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
        return doc if isinstance(doc, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def _normalize_symbol(symbol: str) -> str:
    return str(symbol or "").upper().replace(".US", "").strip()


def load_king_plan_policy(root: Path) -> Dict[str, Any]:
    doc = _load_json(Path(root) / _KING_POLICY)
    integration = dict(doc.get("plan_integration") or {})
    if not integration:
        integration = {
            "enabled": True,
            "weight_boost_pct_per_priority": 0.15,
            "max_weight_boost_pct": 2.0,
        }
    return integration


def sync_t212_realtime_for_plan(root: Path, *, force: bool = False, owner: str = "plan") -> Dict[str, Any]:
    """T212 readonly + R3-Bond — aktuelles Depot für Plan-Umschichtung (coalesced)."""
    root = Path(root)
    broker: Dict[str, Any] = {"sync_errors": []}
    try:
        from analytics.r3_t212_sync_coordinator import (
            record_t212_sync,
            resolve_t212_sync_force,
            should_coalesce_t212_sync,
        )

        skip, skip_de = should_coalesce_t212_sync(root, owner=owner, force=force)
        effective_force = resolve_t212_sync_force(root, owner=owner, force=force)
    except Exception:
        skip = False
        skip_de = ""
        effective_force = force

    try:
        from analytics.r3_t212_api_bond import sync_r3_t212_api_bond

        bond = sync_r3_t212_api_bond(root, force=effective_force and not skip, persist=True)
        broker.update(
            {
                "cash_eur": bond.get("cash_eur"),
                "cash_breakdown": bond.get("cash_breakdown") or {},
                "positions": bond.get("positions") or [],
                "positions_count": int(bond.get("positions_count") or 0),
                "credentials_configured": bool(bond.get("credentials_configured")),
                "last_sync_utc": bond.get("last_sync_utc"),
                "connected": bool(bond.get("connected")),
                "r3_investable_eur": bond.get("investable_eur"),
                "source": "r3_t212_api_bond",
                "bond_sync_ok": True,
                "status": bond.get("broker_status"),
            }
        )
        if skip:
            broker["sync_coalesced"] = True
            broker["sync_coalesce_de"] = skip_de[:120]
        else:
            try:
                record_t212_sync(root, owner=owner, ok=bool(bond.get("connected")), throttled=not effective_force)
            except Exception:
                pass
    except Exception as exc:
        broker["sync_errors"].append(f"bond:{str(exc)[:80]}")
        broker["bond_sync_ok"] = False

    if not broker.get("positions") and not broker.get("cash_eur"):
        try:
            from integrations.trading212.t212_readonly_connection_service import load_cached_broker_status

            cached = load_cached_broker_status(root)
            if cached:
                d = cached.to_dict() if hasattr(cached, "to_dict") else dict(cached or {})
                broker["positions"] = d.get("positions") or []
                broker["positions_count"] = len(broker["positions"])
                if d.get("cash_eur") is not None:
                    broker["cash_eur"] = d.get("cash_eur")
                broker["last_sync_utc"] = d.get("last_successful_sync_utc") or broker.get("last_sync_utc")
                broker["status"] = d.get("status")
        except Exception as exc:
            broker["sync_errors"].append(f"cache:{str(exc)[:80]}")

    from execution.confirmed_live.planning_cash import resolve_planning_cash_eur
    from analytics.prediction_operations import resolve_planning_basis_eur

    live_planning = resolve_planning_cash_eur(
        broker.get("cash_eur"),
        broker=broker,
        root=root,
        subtract_pending_orders=True,
    )
    basis = resolve_planning_basis_eur(root, live_planning)
    planning = basis.get("planning_cash_eur")
    if planning is not None:
        broker["r3_planning_cash_eur"] = planning
        broker["r3_investable_eur"] = basis.get("investable_eur")
        broker["planning_override"] = bool(basis.get("planning_override"))
        broker["live_planning_cash_eur"] = basis.get("live_planning_cash_eur")
        broker["budget_mode"] = basis.get("budget_mode")

    return broker


def _held_values_eur(broker: Dict[str, Any]) -> Dict[str, float]:
    from analytics.human_vs_base_comparison import human_portfolio_from_broker

    human = human_portfolio_from_broker(
        {
            "cash_eur": broker.get("cash_eur"),
            "positions": broker.get("positions") or [],
            "credentials_configured": bool(broker.get("credentials_configured", True)),
        }
    )
    held: Dict[str, float] = {}
    for h in human.get("holdings") or []:
        sym = _normalize_symbol(str(h.get("symbol") or h.get("ticker") or ""))
        if sym:
            held[sym] = round(float(h.get("value_eur") or 0), 2)
    return held


def apply_king_follow_on_to_plan(
    plan: Dict[str, Any],
    king_doc: Dict[str, Any],
    root: Path,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """König-Vorschläge als Gewichts-Boost in den Plan einbringen (Hintergrund)."""
    root = Path(root)
    policy = load_king_plan_policy(root)
    if not policy.get("enabled", True):
        return plan, {"applied": 0, "reason_de": "plan_integration deaktiviert"}

    suggestions = [
        s
        for s in (king_doc.get("follow_on_suggestions") or [])
        if isinstance(s, dict) and s.get("worth_follow_on", True)
    ]
    if not suggestions:
        return plan, {"applied": 0, "reason_de": "keine Follow-on-Vorschläge"}

    boost_per = float(policy.get("weight_boost_pct_per_priority") or 0.15)
    max_boost = float(policy.get("max_weight_boost_pct") or 2.0)
    boost_map: Dict[str, float] = {}
    for s in suggestions:
        sym = _normalize_symbol(str(s.get("symbol") or ""))
        if not sym:
            continue
        pr = float(s.get("priority") or 1.0)
        boost_map[sym] = round(min(max_boost, pr * boost_per), 3)

    allocations = list(plan.get("allocations") or [])
    if not allocations:
        return plan, {"applied": 0, "reason_de": "Plan ohne Allokationen"}

    applied = 0
    for alloc in allocations:
        sym = _normalize_symbol(str(alloc.get("symbol") or ""))
        boost = boost_map.get(sym)
        if not boost:
            continue
        base_w = float(alloc.get("model_weight_pct") or 0)
        alloc["model_weight_pct"] = round(base_w + boost, 3)
        alloc["king_boost_pct"] = boost
        reason = str(alloc.get("rationale_de") or "")
        king_reason = ""
        for s in suggestions:
            if _normalize_symbol(str(s.get("symbol") or "")) == sym:
                king_reason = str(s.get("reason_de") or "")[:80]
                break
        alloc["rationale_de"] = f"{reason} · König +{boost:.1f}% {king_reason}".strip()[:200]
        applied += 1

    if applied == 0:
        return plan, {"applied": 0, "reason_de": "keine Plan-Symbole für König-Boost"}

    investable = float(plan.get("investable_eur") or 0)
    total_w = sum(float(a.get("model_weight_pct") or 0) for a in allocations)
    if investable <= 0 or total_w <= 0:
        return plan, {"applied": applied, "reason_de": "Boost ohne Neuskalierung (investable=0)"}

    from integrations.trading212.t212_fee_economics import net_buy_target_after_costs

    for alloc in allocations:
        sym = _normalize_symbol(str(alloc.get("symbol") or ""))
        if not sym:
            continue
        share = float(alloc.get("model_weight_pct") or 0) / total_w
        target_gross = round(investable * share, 2)
        fee_adj = net_buy_target_after_costs(target_gross, root)
        alloc["target_eur_gross"] = target_gross
        alloc["target_eur"] = round(float(fee_adj.get("net_target_eur") or target_gross), 2)
        alloc["estimated_one_way_cost_eur"] = fee_adj.get("estimated_one_way_cost_eur")

    plan["allocations"] = allocations
    plan["king_plan_merged"] = True
    plan["king_boost_applied"] = applied
    plan["king_merged_at_utc"] = _utc_now()
    return plan, {"applied": applied, "symbols": sorted(boost_map.keys())}


def rebalance_plan_to_t212_holdings(
    plan: Dict[str, Any],
    broker: Dict[str, Any],
    root: Path,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Plan-Allokationen → Kauf/Verkauf-Gaps gegen T212-Live-Positionen."""
    root = Path(root)
    meta: Dict[str, Any] = {"ok": True}
    pos_count = int(broker.get("positions_count") or len(broker.get("positions") or []))
    held = _held_values_eur(broker)

    if pos_count > 0 and not held:
        plan["rebalanced_to_t212"] = False
        plan["holdings_parse_failed"] = True
        plan["allocations"] = []
        plan["t212_positions_count"] = pos_count
        meta = {
            "ok": False,
            "error_de": "T212 meldet Positionen — Parsing fehlgeschlagen (fail-closed)",
            "holdings_parse_failed": True,
        }
        return plan, meta

    if not held:
        plan["rebalanced_to_t212"] = False
        plan["t212_positions_count"] = 0
        plan["rebalance_mode_de"] = "flat_depot_full_targets"
        meta["reason_de"] = "Leeres Depot — volle Plan-Ziele"
        return plan, meta

    try:
        from analytics.r3_trading_functions import load_functions_policy

        min_trade = float(load_functions_policy(root).get("min_trade_eur") or 12.0)
    except Exception:
        min_trade = 12.0

    rebalanced: List[Dict[str, Any]] = []
    for alloc in list(plan.get("allocations") or []):
        sym = _normalize_symbol(str(alloc.get("symbol") or ""))
        if not sym:
            continue
        plan_target = round(float(alloc.get("target_eur") or 0), 2)
        current = round(float(held.get(sym, 0)), 2)
        gap = round(plan_target - current, 2)
        if gap >= min_trade:
            side = "BUY"
            from analytics.t212_broker_economics import apply_buy_target_fee_adjustment

            fee_row = apply_buy_target_fee_adjustment(gap, root)
            target_eur = float(fee_row.get("target_eur") or gap)
            side_de = "Nachkauf" if current > 0 else "Neue Aktie"
        elif gap <= -min_trade:
            side = "SELL"
            target_eur = round(abs(gap), 2)
            side_de = "Verkauf"
        else:
            continue
        row_out = {
            **alloc,
            "symbol": sym,
            "side": side,
            "side_de": side_de,
            "target_eur": target_eur,
            "plan_target_eur": plan_target,
            "held_eur": current,
            "gap_eur": gap,
            "rebalance_source_de": "t212_live_positions",
        }
        if side == "BUY":
            row_out["gap_eur_gross"] = gap
            row_out["target_eur_gross"] = gap
            row_out["estimated_one_way_cost_eur"] = fee_row.get("estimated_one_way_cost_eur")
        rebalanced.append(row_out)

    plan["allocations"] = rebalanced
    plan["rebalanced_to_t212"] = True
    plan["t212_positions_count"] = len(held)
    plan["t212_rebalanced_at_utc"] = _utc_now()
    plan["rebalance_mode_de"] = "gap_vs_live_holdings"
    meta["gap_rows"] = len(rebalanced)
    return plan, meta


def rebuild_investment_plan_with_king(
    root: Path,
    *,
    force_t212_sync: bool = False,
) -> Dict[str, Any]:
    """
    Hintergrund-Pipeline (atomar, fail-closed):
    1. T212 live lesen
    2. Basis-Modell-Plan
    3. König Follow-on einbringen
    4. Umschichtung vs. Depot
    5. Reevaluation + Orders synchronisieren
    """
    root = Path(root)
    run_id = uuid.uuid4().hex[:12]
    warnings: List[str] = []
    errors: List[str] = []

    broker = sync_t212_realtime_for_plan(root, force=force_t212_sync, owner="king_plan")
    for err in broker.get("sync_errors") or []:
        warnings.append(str(err))

    trust: Dict[str, Any] = {}
    try:
        from integrations.trading212.t212_trust_gate import assess_t212_trust_from_root

        trust = assess_t212_trust_from_root(root, persist=True)
        if not trust.get("plan_capital_allowed", True):
            return {
                "ok": False,
                "pipeline_run_id": run_id,
                "error_de": trust.get("message_de") or "T212 nicht vertrauenswürdig — Plan-Skalierung blockiert",
                "t212_trust_reason": trust.get("reason_code"),
                "broker_source": broker.get("source"),
                "sync_errors": broker.get("sync_errors") or [],
            }
    except Exception as exc:
        return {
            "ok": False,
            "pipeline_run_id": run_id,
            "error_de": f"T212 Trust Gate — {str(exc)[:80]}",
        }

    planning = broker.get("r3_planning_cash_eur")
    investable = broker.get("r3_investable_eur")

    if planning is None or investable is None:
        return {
            "ok": False,
            "pipeline_run_id": run_id,
            "error_de": "T212-Kontostand fehlt — zuerst API-Bond/Sync",
            "broker_source": broker.get("source"),
            "sync_errors": broker.get("sync_errors") or [],
        }

    if broker.get("connected") and not broker.get("bond_sync_ok"):
        errors.append("T212-Bond-Sync fehlgeschlagen")

    from analytics.pilot_investment_plan import build_investment_plan, ensure_plan_symbols_in_scope
    from analytics.r3_closed_loop import load_r3_account_for_engine, record_closed_loop_tick, resolve_r3_plan_capital_eur

    capital = resolve_r3_plan_capital_eur(root, broker, float(planning))
    plan_capital = float(capital.get("plan_capital_eur") or investable)

    plan = build_investment_plan(
        root,
        float(planning),
        investable_eur=plan_capital,
        budget_source=str(capital.get("basis") or "r3_investable_t212_live"),
    )
    plan["t212_live"] = {
        "cash_eur": broker.get("cash_eur"),
        "planning_cash_eur": planning,
        "cash_investable_eur": investable,
        "plan_capital_eur": plan_capital,
        "plan_capital_basis": capital.get("basis"),
        "total_account_value_eur": capital.get("total_account_value_eur"),
        "invested_eur": capital.get("invested_eur"),
        "positions_count": capital.get("positions_count"),
        "last_sync_utc": broker.get("last_sync_utc"),
        "connected": bool(broker.get("connected")),
    }
    plan["plan_capital_eur"] = plan_capital
    plan["plan_capital_basis"] = capital.get("basis")

    king_doc = _load_json(root / _KING_EVIDENCE)
    plan, merge_meta = apply_king_follow_on_to_plan(plan, king_doc, root)
    plan, rebalance_meta = rebalance_plan_to_t212_holdings(plan, broker, root)

    if not rebalance_meta.get("ok", True):
        account = load_r3_account_for_engine(root)
        record_closed_loop_tick(
            root,
            account=account,
            plan=None,
            step="rebalance_plan",
            loop_ok=False,
            stale_reason_de=str(rebalance_meta.get("error_de") or "")[:120],
        )
        return {
            "ok": False,
            "pipeline_run_id": run_id,
            "error_de": rebalance_meta.get("error_de"),
            "holdings_parse_failed": True,
            "warnings": warnings,
            "errors": errors,
        }

    plan["plan_pipeline_de"] = "champion → könig_follow_on → t212_umschichtung"
    plan["t212_last_sync_utc"] = broker.get("last_sync_utc")
    plan["pipeline_run_id"] = run_id
    plan["updated_at_utc"] = _utc_now()

    ensure_plan_symbols_in_scope(root, plan)

    reeval_ok = False
    reeval_err: Optional[str] = None
    snapshot_health_ok = False
    try:
        from analytics.pilot_day_trading_facade import DayTradingSnapshotError, refresh_trading_snapshot

        snap = refresh_trading_snapshot(
            root,
            broker=broker,
            plan=plan,
            force_reevaluation=True,
            fail_closed=False,
        )
        snapshot_health_ok = bool((snap.health or {}).get("ok"))
        reeval_ok = snapshot_health_ok
        if not snapshot_health_ok:
            reeval_err = "; ".join((snap.health or {}).get("errors_de") or ["snapshot_unhealthy"])[:120]
            warnings.append(f"snapshot:{reeval_err}")
    except DayTradingSnapshotError as exc:
        reeval_err = str(exc)[:120]
        warnings.append(f"snapshot:{reeval_err}")
    except Exception as exc:
        reeval_err = str(exc)[:120]
        warnings.append(f"reeval:{reeval_err}")

    orders_ok = False
    orders_err: Optional[str] = None
    try:
        from analytics.r3_stock_orders import refresh_stock_order_evidence

        refresh_stock_order_evidence(root)
        orders_ok = True
    except Exception as exc:
        orders_err = str(exc)[:120]
        warnings.append(f"orders:{orders_err}")

    pipeline_synced = reeval_ok and orders_ok
    plan["pipeline_synced"] = pipeline_synced
    plan["pipeline_partial"] = not pipeline_synced
    if warnings:
        plan["pipeline_warnings"] = warnings[:8]

    from analytics.pilot_investment_plan import _merge_plan_pipeline_metadata

    atomic_write_json(root / _PLAN_EVIDENCE, _merge_plan_pipeline_metadata(root, plan))

    account = load_r3_account_for_engine(root)
    record_closed_loop_tick(
        root,
        account=account,
        plan=plan,
        step="rebalance_plan",
        loop_ok=pipeline_synced and not errors,
        pipeline_partial=not pipeline_synced,
    )

    partial = not pipeline_synced or bool(warnings)
    return {
        "ok": True,
        "partial": partial,
        "pipeline_synced": pipeline_synced,
        "pipeline_run_id": run_id,
        "investable_eur": float(investable),
        "plan_capital_eur": plan_capital,
        "plan_capital_basis": capital.get("basis"),
        "allocation_count": len(plan.get("allocations") or []),
        "king_boost_applied": merge_meta.get("applied", 0),
        "rebalanced_to_t212": bool(plan.get("rebalanced_to_t212")),
        "rebalance_mode_de": plan.get("rebalance_mode_de"),
        "t212_positions_count": int(plan.get("t212_positions_count") or broker.get("positions_count") or 0),
        "reeval_refreshed": reeval_ok,
        "orders_refreshed": orders_ok,
        "reeval_error_de": reeval_err,
        "orders_error_de": orders_err,
        "warnings": warnings,
        "errors": errors,
        "plan_ref": str(_PLAN_EVIDENCE),
        "detail_de": str(plan.get("summary_de") or "")[:120],
    }

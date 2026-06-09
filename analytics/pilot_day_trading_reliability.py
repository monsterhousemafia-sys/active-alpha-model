"""Day-Trading — Fail-closed Validierung, Broker/Plan-Auflösung, All-in-Schutz."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

_PLAN_EVIDENCE = Path("evidence/pilot_investment_plan_latest.json")
_BOND_EVIDENCE = Path("evidence/r3_t212_api_bond_latest.json")


def _load_json(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
        return doc if isinstance(doc, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def reliability_policy(root: Path) -> Dict[str, Any]:
    from analytics.pilot_day_trading_policy import load_unified_policy

    pol = load_unified_policy(root)
    defaults = {
        "require_t212_live_in_plan": True,
        "require_pipeline_synced_for_execute": True,
        "min_buy_allocation_rows": 1,
        "max_single_buy_pct": 0.12,
        "fail_closed_missing_broker": True,
        "fail_closed_stale_plan": True,
    }
    rel = dict(pol.get("reliability") or {})
    return {**defaults, **rel}


def resolve_broker_for_day_trading(
    root: Path,
    broker: Optional[Dict[str, Any]],
) -> Tuple[Dict[str, Any], List[str]]:
    """Autoritativer T212-Broker — Bond hat Vorrang vor veraltetem Snapshot."""
    root = Path(root)
    warnings: List[str] = []
    merged = dict(broker or {})

    bond = _load_json(root / _BOND_EVIDENCE)
    if bond.get("cash_eur") is not None or bond.get("connected"):
        rb = {
            "cash_eur": bond.get("cash_eur"),
            "cash_breakdown": bond.get("cash_breakdown") or {},
            "positions": bond.get("positions") or [],
            "positions_count": int(bond.get("positions_count") or 0),
            "credentials_configured": bool(bond.get("credentials_configured")),
            "last_sync_utc": bond.get("last_sync_utc"),
            "connected": bool(bond.get("connected")),
            "source": "r3_t212_api_bond",
        }
        if not merged:
            merged = rb
        else:
            if merged.get("cash_eur") is None and rb.get("cash_eur") is not None:
                merged.update(rb)
                warnings.append("broker:aus_bond_ergänzt")
            elif merged.get("source") != "r3_t212_api_bond":
                merged = {**merged, **{k: v for k, v in rb.items() if v is not None}}
                warnings.append("broker:bond_merge")

    try:
        from analytics.r3_closed_loop import load_r3_account_for_engine

        acct = load_r3_account_for_engine(root)
        if acct.get("ok"):
            rb = dict(acct.get("broker") or {})
            if rb.get("cash_eur") is not None:
                merged.setdefault("cash_eur", rb.get("cash_eur"))
                merged["r3_planning_cash_eur"] = acct.get("planning_cash_eur")
                merged["r3_investable_eur"] = acct.get("investable_eur")
                merged["positions"] = rb.get("positions") or merged.get("positions") or []
                merged["positions_count"] = int(
                    rb.get("positions_count") or len(merged.get("positions") or [])
                )
                merged["source"] = rb.get("source") or merged.get("source") or "r3_closed_loop"
    except Exception:
        warnings.append("broker:closed_loop_unavailable")

    return merged, warnings


def resolve_plan_for_day_trading(
    root: Path,
    plan: Optional[Dict[str, Any]],
) -> Tuple[Dict[str, Any], List[str]]:
    root = Path(root)
    warnings: List[str] = []
    doc = dict(plan or {})
    if not doc:
        doc = _load_json(root / _PLAN_EVIDENCE)
        if doc:
            warnings.append("plan:aus_evidence")
    return doc, warnings


def assess_plan_trade_safety(
    root: Path,
    plan: Dict[str, Any],
) -> Dict[str, Any]:
    """All-in-Schutz und Plan-Integrität für Day-Trading."""
    root = Path(root)
    pol = reliability_policy(root)
    investable = float(
        plan.get("plan_capital_eur") or plan.get("investable_eur") or 0
    )
    buys = [
        a
        for a in (plan.get("allocations") or [])
        if isinstance(a, dict)
        and str(a.get("side") or "BUY").upper() == "BUY"
        and float(a.get("target_eur") or 0) > 0
    ]
    errors: List[str] = []
    warns: List[str] = []

    if pol.get("require_t212_live_in_plan") and not plan.get("t212_live"):
        errors.append("Plan ohne t212_live — Live-Basis fehlt")

    if investable <= 0:
        errors.append("investable_eur=0")

    min_rows = int(pol.get("min_buy_allocation_rows") or 1)
    if len(buys) < min_rows:
        errors.append(f"weniger als {min_rows} BUY-Zeile(n)")

    max_pct = float(pol.get("max_single_buy_pct") or 0.12)
    if investable > 0 and buys:
        top = max(float(b.get("target_eur") or 0) for b in buys)
        share = top / investable
        if len(buys) == 1 or share >= max(0.9, max_pct * 3):
            errors.append(f"All-in-Risiko — eine Zeile {share * 100:.0f}% des Budgets")
        elif share > max_pct:
            warns.append(f"Einzelkauf {share * 100:.1f}% > Limit {max_pct * 100:.0f}%")

    if pol.get("require_pipeline_synced_for_execute") and plan.get("pipeline_partial"):
        warns.append("pipeline_partial — Plan/Orders nicht synchron")

    if plan.get("holdings_parse_failed"):
        errors.append("T212-Positionen nicht parsebar")

    blocks_execute = bool(errors)
    if pol.get("require_pipeline_synced_for_execute") and not plan.get("pipeline_synced", True):
        blocks_execute = True
        if "pipeline nicht synchron" not in errors:
            errors.append("pipeline nicht synchron")

    return {
        "ok": not errors,
        "blocks_execute": blocks_execute,
        "errors_de": errors,
        "warnings_de": warns,
        "buy_rows": len(buys),
        "investable_eur": investable,
        "max_single_buy_pct": max_pct,
    }


def build_snapshot_health(
    *,
    broker: Dict[str, Any],
    plan: Dict[str, Any],
    reevaluation: Dict[str, Any],
    playbook: Dict[str, Any],
    broker_warnings: List[str],
    plan_warnings: List[str],
    step_errors: List[str],
    root: Path,
) -> Dict[str, Any]:
    pol = reliability_policy(root)
    plan_safety = assess_plan_trade_safety(root, plan)
    errors = list(plan_safety.get("errors_de") or [])
    warnings = list(plan_safety.get("warnings_de") or [])
    warnings.extend(broker_warnings)
    warnings.extend(plan_warnings)
    warnings.extend(step_errors)

    if pol.get("fail_closed_missing_broker") and not broker.get("cash_eur"):
        errors.append("T212-Broker/Cash fehlt")

    if pol.get("fail_closed_stale_plan") and plan and not plan.get("updated_at_utc"):
        warnings.append("Plan ohne updated_at_utc")

    reeval_status = str(reevaluation.get("status") or "")
    if reeval_status in {"MODEL_CSV_MISSING", "NOT_EVALUABLE"}:
        errors.append(f"Reeval: {reeval_status}")

    action = str(playbook.get("next_action") or "")
    if action in {"EXECUTE_NOW", "EXECUTE_DEFERRED"} and plan_safety.get("blocks_execute"):
        errors.append(f"Playbook {action} blockiert — Plan unsicher")

    ok = not errors
    return {
        "ok": ok,
        "blocks_execute": bool(plan_safety.get("blocks_execute")) or not ok,
        "errors_de": errors[:8],
        "warnings_de": warnings[:12],
        "plan_safety": plan_safety,
        "playbook_action": action,
        "broker_source": broker.get("source"),
        "plan_pipeline_synced": plan.get("pipeline_synced"),
        "plan_run_id": plan.get("pipeline_run_id"),
    }

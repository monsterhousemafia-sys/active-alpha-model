"""Geschlossener Kreislauf: R3-Kontostand → Active Alpha Model → R3-Anzeige/Orders."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from aa_safe_io import atomic_write_json

_POLICY_REL = Path("control/r3_closed_loop_policy.json")
_BOND_EVIDENCE = Path("evidence/r3_t212_api_bond_latest.json")
_LOOP_EVIDENCE = Path("evidence/r3_closed_loop_latest.json")
_PLAN_EVIDENCE = Path("evidence/pilot_investment_plan_latest.json")
_KING_EVIDENCE = Path("evidence/king_trading_assist_latest.json")
_ORDERS_EVIDENCE = Path("evidence/r3_stock_orders_latest.json")
_ENGINE_STATE = Path("control/alpha_model_background_engine_state.json")


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


def load_closed_loop_policy(root: Path) -> Dict[str, Any]:
    return _load_json(Path(root) / _POLICY_REL)


def parse_evidence_utc(raw: str) -> Optional[datetime]:
    text = str(raw or "").strip()
    if not text:
        return None
    try:
        ts = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return ts
    except ValueError:
        return None


def rebalance_plan_inputs_stale(root: Path) -> Tuple[bool, List[str]]:
    """True wenn Bond/König/Plan neuer als letzter erfolgreicher rebalance_plan-Lauf."""
    root = Path(root)
    state = _load_json(root / _ENGINE_STATE)
    last_reb = parse_evidence_utc(str((state.get("last_step_utc") or {}).get("rebalance_plan") or ""))
    reasons: List[str] = []

    bond = _load_json(root / _BOND_EVIDENCE)
    bond_ts = parse_evidence_utc(str(bond.get("last_sync_utc") or bond.get("updated_at_utc") or ""))
    if bond_ts and (last_reb is None or bond_ts > last_reb):
        reasons.append("bond_sync_newer")

    king = _load_json(root / _KING_EVIDENCE)
    king_ts = parse_evidence_utc(str(king.get("updated_at_utc") or ""))
    if king_ts and (last_reb is None or king_ts > last_reb):
        reasons.append("king_evidence_newer")

    plan = _load_json(root / _PLAN_EVIDENCE)
    plan_ts = parse_evidence_utc(str(plan.get("updated_at_utc") or ""))
    if bond_ts and (plan_ts is None or bond_ts > plan_ts):
        reasons.append("plan_behind_bond")

    orders = _load_json(root / _ORDERS_EVIDENCE)
    orders_ts = parse_evidence_utc(str(orders.get("updated_at_utc") or ""))
    if plan_ts and (orders_ts is None or plan_ts > orders_ts):
        reasons.append("orders_behind_plan")

    if plan and not plan.get("t212_live"):
        reasons.append("plan_missing_t212_live")

    return bool(reasons), reasons


def _broker_from_readonly_cache(root: Path) -> Dict[str, Any]:
    try:
        from integrations.trading212.t212_readonly_connection_service import load_cached_broker_status

        st = load_cached_broker_status(root)
        if st is None:
            return {}
        d = st.to_dict() if hasattr(st, "to_dict") else {}
        return {
            "cash_eur": d.get("cash_eur"),
            "cash_breakdown": d.get("cash_breakdown") or {},
            "positions": d.get("positions") or [],
            "positions_count": len(d.get("positions") or []),
            "credentials_configured": bool(d.get("credentials_configured")),
            "last_sync_utc": d.get("last_successful_sync_utc"),
            "environment": d.get("environment"),
            "status": d.get("status"),
            "source": "readonly_cache",
        }
    except Exception:
        return {}


def resolve_r3_investable_eur(root: Path, planning_cash_eur: float) -> float:
    """Investierbar aus R3-Kontostand — gleiche Budget-Regeln wie R3-Anzeige."""
    from analytics.prediction_operations import budget_config

    cash = max(0.0, float(planning_cash_eur or 0))
    buffer_pct = float(budget_config(root).get("cash_buffer_pct", 5.0))
    return round(cash * (1.0 - buffer_pct / 100.0), 2)


def resolve_r3_plan_capital_eur(
    root: Path,
    broker: Dict[str, Any],
    planning_cash_eur: float,
) -> Dict[str, Any]:
    """
    Live-Kapitalbasis für Modell-Plan:
    Gesamtdepot (Cash + Positionen) wenn Holdings vorhanden, sonst freies Cash investierbar.
    """
    from analytics.human_vs_base_comparison import human_portfolio_from_broker
    from analytics.prediction_operations import budget_config, fixed_preview_capital_eur

    fixed = fixed_preview_capital_eur(root)
    if fixed is not None:
        cash_investable = resolve_r3_investable_eur(root, fixed)
        pos_count = int(broker.get("positions_count") or len(broker.get("positions") or []))
        return {
            "plan_capital_eur": cash_investable,
            "basis": "fixed_preview",
            "total_account_value_eur": fixed,
            "invested_eur": 0.0,
            "cash_investable_eur": cash_investable,
            "positions_count": pos_count,
        }

    buffer_pct = float(budget_config(root).get("cash_buffer_pct", 5.0))
    bd = broker.get("cash_breakdown") or {}
    positions = broker.get("positions") or []
    pos_count = int(broker.get("positions_count") or len(positions))

    invested = bd.get("invested_current_value_eur")
    if invested is None and positions:
        invested = human_portfolio_from_broker(broker).get("invested_eur")
    try:
        invested_f = float(invested or 0)
    except (TypeError, ValueError):
        invested_f = 0.0

    total = bd.get("total_account_value_eur")
    if total is None and positions:
        total = human_portfolio_from_broker(broker).get("total_value_eur")
    try:
        total_f = float(total or 0) if total is not None else 0.0
    except (TypeError, ValueError):
        total_f = 0.0

    cash_investable = resolve_r3_investable_eur(root, planning_cash_eur)

    if pos_count > 0 or invested_f > 0:
        basis_total = total_f if total_f > 0 else max(0.0, float(planning_cash_eur or 0) + invested_f)
        plan_capital = round(basis_total * (1.0 - buffer_pct / 100.0), 2)
        return {
            "plan_capital_eur": plan_capital,
            "basis": "t212_total_account_live",
            "total_account_value_eur": round(basis_total, 2),
            "invested_eur": round(invested_f, 2),
            "cash_investable_eur": cash_investable,
            "positions_count": pos_count,
        }

    return {
        "plan_capital_eur": cash_investable,
        "basis": "r3_cash_investable_live",
        "total_account_value_eur": round(float(planning_cash_eur or 0), 2),
        "invested_eur": 0.0,
        "cash_investable_eur": cash_investable,
        "positions_count": 0,
    }


def resolve_r3_investable_for_trading(root: Path) -> Optional[float]:
    """Autoritatives T212-Investierbar aus R3 API-Bond (None wenn nicht verfügbar)."""
    acct = load_r3_account_for_engine(root)
    if not acct.get("ok"):
        return None
    inv = acct.get("investable_eur")
    if inv is None:
        return None
    try:
        val = float(inv)
    except (TypeError, ValueError):
        return None
    return val if val > 0 else None


def load_r3_account_for_engine(root: Path) -> Dict[str, Any]:
    """
    Kontostand für Engine-Berechnungen — autoritativ aus R3 API-Bond-Evidence.
    Kein paralleler Broker-Sync im Hintergrund-Tick.
    """
    root = Path(root)
    bond = _load_json(root / _BOND_EVIDENCE)
    broker: Dict[str, Any] = {}
    source = "r3_t212_api_bond"

    if bond.get("cash_eur") is not None or bond.get("connected"):
        broker = {
            "cash_eur": bond.get("cash_eur"),
            "cash_breakdown": bond.get("cash_breakdown") or {},
            "positions": bond.get("positions") or [],
            "positions_count": int(bond.get("positions_count") or 0),
            "credentials_configured": bool(bond.get("credentials_configured")),
            "last_sync_utc": bond.get("last_sync_utc"),
            "environment": bond.get("environment"),
            "status": bond.get("broker_status"),
            "connected": bool(bond.get("connected")),
            "bonded": bool(bond.get("bonded")),
            "source": source,
        }

    if broker.get("cash_eur") is None:
        cached = _broker_from_readonly_cache(root)
        if cached.get("cash_eur") is not None:
            broker = {**cached, "source": "readonly_cache_fallback"}

    from execution.confirmed_live.planning_cash import resolve_planning_cash_eur
    from analytics.prediction_operations import resolve_planning_basis_eur

    live_planning = resolve_planning_cash_eur(
        broker.get("cash_eur") if broker else None,
        broker=broker or None,
        root=root,
        subtract_pending_orders=True,
    )
    basis = resolve_planning_basis_eur(root, live_planning)
    planning = basis.get("planning_cash_eur")
    investable = basis.get("investable_eur")
    plan_capital = (
        resolve_r3_plan_capital_eur(root, broker, planning)
        if planning is not None and broker
        else {}
    )
    trust: Dict[str, Any] = {}
    try:
        from integrations.trading212.t212_trust_gate import assess_t212_trust

        trust = assess_t212_trust(broker, root=root)
    except Exception:
        trust = {"trusted": False, "orders_allowed": False}

    ok = investable is not None and bool(trust.get("trusted"))
    pos_n = int(plan_capital.get("positions_count") or broker.get("positions_count") or 0)
    msg = (
        f"R3 · {float(investable):.0f} € investierbar · {pos_n} Pos. live"
        if ok and investable is not None
        else str(trust.get("message_de") or "R3 Kontostand ausstehend — bash tools/king_ops.sh r3-t212")
    )
    return {
        "ok": ok,
        "t212_trusted": bool(trust.get("trusted")),
        "t212_trust_reason": trust.get("reason_code"),
        "broker": broker,
        "planning_cash_eur": planning,
        "investable_eur": investable,
        "plan_capital_eur": plan_capital.get("plan_capital_eur"),
        "plan_capital_basis": plan_capital.get("basis"),
        "total_account_value_eur": plan_capital.get("total_account_value_eur"),
        "invested_eur": plan_capital.get("invested_eur"),
        "positions_count": pos_n,
        "cash_eur": broker.get("cash_eur"),
        "cash_source": broker.get("source") or source,
        "invest_source_de": (
            f"Vorschau-Basis {float(investable or 0):.0f} € (fixed_preview; Live T212 {float(basis.get('live_planning_cash_eur') or 0):.0f} €)"
            if basis.get("planning_override")
            else "R3 T212-Bond → volles Guthaben → investierbar"
        ),
        "planning_override": bool(basis.get("planning_override")),
        "live_planning_cash_eur": basis.get("live_planning_cash_eur"),
        "budget_mode": basis.get("budget_mode"),
        "bond_ref": str(_BOND_EVIDENCE).replace("\\", "/"),
        "message_de": msg,
        "t212_trust_message_de": trust.get("message_de"),
    }


def record_closed_loop_tick(
    root: Path,
    *,
    account: Dict[str, Any],
    plan: Optional[Dict[str, Any]] = None,
    step: str = "rebalance_plan",
    loop_ok: Optional[bool] = None,
    stale_reason_de: Optional[str] = None,
    pipeline_partial: Optional[bool] = None,
) -> Dict[str, Any]:
    root = Path(root)
    policy = load_closed_loop_policy(root)
    plan_doc = plan or {}
    synced = bool(plan_doc.get("pipeline_synced", True))
    if loop_ok is None:
        loop_ok = bool(account.get("ok")) and synced and not stale_reason_de
    doc: Dict[str, Any] = {
        "schema_version": 1,
        "updated_at_utc": _utc_now(),
        "step": step,
        "headline_de": str(policy.get("headline_de") or "Geschlossener Kreislauf"),
        "loop_ok": bool(loop_ok),
        "pipeline_synced": synced,
        "pipeline_partial": bool(pipeline_partial) if pipeline_partial is not None else not synced,
        "stale_reason_de": stale_reason_de,
        "cash_source": account.get("cash_source"),
        "cash_eur": account.get("cash_eur"),
        "planning_cash_eur": account.get("planning_cash_eur"),
        "investable_eur": account.get("investable_eur") or (plan or {}).get("investable_eur"),
        "invest_source_de": account.get("invest_source_de"),
        "bond_ref": account.get("bond_ref"),
        "positions_count": account.get("positions_count"),
        "invested_eur": account.get("invested_eur"),
        "total_account_value_eur": account.get("total_account_value_eur"),
        "plan_capital_eur": account.get("plan_capital_eur") or (plan or {}).get("plan_capital_eur"),
        "plan_capital_basis": account.get("plan_capital_basis") or (plan or {}).get("plan_capital_basis"),
        "t212_live": (plan or {}).get("t212_live") or {},
        "signal_date": (plan or {}).get("signal_date"),
        "king_plan_merged": bool(plan_doc.get("king_plan_merged")),
        "rebalanced_to_t212": bool(plan_doc.get("rebalanced_to_t212")),
        "pipeline_run_id": plan_doc.get("pipeline_run_id"),
        "message_de": account.get("message_de"),
        "policy_ref": str(_POLICY_REL).replace("\\", "/"),
    }
    atomic_write_json(root / _LOOP_EVIDENCE, doc)
    return doc

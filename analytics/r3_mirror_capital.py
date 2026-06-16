"""R3 Mirror — autoritatives Kapital & Trust (eine Quelle für State + View + Orders)."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from analytics.r3_crash_guard import safe_float
from analytics.r3_operator_surface_text import OPERATOR_API_ENTER, OPERATOR_SYNC_WAIT, start_hint_de

EVIDENCE_ORDERS = Path("evidence/r3_stock_orders_latest.json")
OPERATOR_SYNC_HINT_DE = OPERATOR_SYNC_WAIT


def resolve_mirror_account(root: Path) -> Dict[str, Any]:
    """T212-Kontostand für Mirror — investierbar nur bei Trust + Operator-API."""
    root = Path(root)
    from analytics.r3_t212_operator_api import resolve_operator_api_state

    api_state = resolve_operator_api_state(root)
    try:
        from analytics.r3_closed_loop import load_r3_account_for_engine

        account = load_r3_account_for_engine(root)
    except Exception:
        account = {}
    needs_api = bool(api_state.get("needs_api_setup"))
    creds_ok = bool(api_state.get("credentials_configured"))
    trusted = bool(account.get("t212_trusted")) and not needs_api
    investable = _as_optional_float(account.get("investable_eur")) if trusted else None
    reason_code = str(account.get("t212_trust_reason") or "")
    if needs_api:
        capital_message_de = OPERATOR_API_ENTER
    elif not trusted:
        capital_message_de = start_hint_de(
            needs_api=False,
            trusted=False,
            reason_code=reason_code or None,
        )
    else:
        capital_message_de = ""
    return {
        "t212_trusted": trusted,
        "credentials_configured": creds_ok,
        "needs_api_setup": needs_api,
        "operator_api_ready": bool(api_state.get("operator_api_ready")),
        "investable_eur": investable,
        "cash_eur": account.get("cash_eur") if trusted else None,
        "positions_count": account.get("positions_count"),
        "capital_message_de": capital_message_de,
        "t212_trust_reason": reason_code or None,
        "account": account,
    }


def collect_model_allocations(
    plan: Dict[str, Any],
    reeval: Dict[str, Any],
    *,
    trusted_investable: Optional[float],
    t212_trusted: bool,
) -> Tuple[Optional[float], List[Dict[str, Any]]]:
    del reeval
    if not t212_trusted or trusted_investable is None:
        return None, []
    plan_total = max(0.0, round(float(trusted_investable), 2))
    if plan_total <= 0:
        return None, []
    rows: List[Dict[str, Any]] = []
    for alloc in plan.get("allocations") or []:
        if not isinstance(alloc, dict):
            continue
        w_pct = alloc.get("model_weight_pct")
        if w_pct is not None:
            try:
                tgt = round(plan_total * float(w_pct) / 100.0, 2)
            except (TypeError, ValueError):
                tgt = 0.0
        else:
            tgt = round(safe_float(alloc.get("target_eur")), 2)
        if tgt <= 0:
            continue
        pct = round((tgt / plan_total * 100.0), 1) if plan_total > 0 else 0.0
        rows.append(
            {
                "symbol": str(alloc.get("symbol") or "—")[:32],
                "notional_eur": tgt,
                "pct": pct,
            }
        )
    rows.sort(key=lambda r: (-float(r.get("notional_eur") or 0), str(r.get("symbol") or "")))
    return plan_total, rows


def empty_execution_package() -> Dict[str, Any]:
    return {
        "active": False,
        "source_de": str(EVIDENCE_ORDERS),
        "notional_eur": 0.0,
        "sell_notional_eur": None,
        "buy_count": 0,
        "sell_count": 0,
        "lines": [],
        "sell_lines": [],
    }


def collect_execution_package(orders: Dict[str, Any]) -> Dict[str, Any]:
    initial_pkg = orders.get("initial_package") or {}
    buy_lines: List[Dict[str, Any]] = []
    sell_lines: List[Dict[str, Any]] = []
    for row in orders.get("stocks") or []:
        if not isinstance(row, dict):
            continue
        side = str(row.get("side") or "").upper()
        if side not in ("BUY", "SELL"):
            continue
        raw = row.get("notional_eur")
        if raw is None:
            continue
        notional = round(float(raw), 2)
        if notional <= 0:
            continue
        entry = {"symbol": str(row.get("symbol") or "—")[:32], "notional_eur": notional, "side": side}
        if side == "SELL":
            sell_lines.append(entry)
        else:
            buy_lines.append(entry)
    buy_lines.sort(key=lambda r: (-float(r.get("notional_eur") or 0), str(r.get("symbol") or "")))
    sell_lines.sort(key=lambda r: (-float(r.get("notional_eur") or 0), str(r.get("symbol") or "")))
    exec_total = round(sum(float(r.get("notional_eur") or 0) for r in buy_lines), 2)
    sell_total = round(sum(float(r.get("notional_eur") or 0) for r in sell_lines), 2)
    pkg_notional = initial_pkg.get("notional_eur")
    if pkg_notional is not None:
        notional = round(float(pkg_notional), 2)
    elif buy_lines:
        notional = exec_total
    else:
        notional = 0.0
    return {
        "active": bool(initial_pkg.get("active")),
        "source_de": str(EVIDENCE_ORDERS),
        "notional_eur": notional,
        "sell_notional_eur": sell_total if sell_lines else None,
        "buy_count": len(buy_lines),
        "sell_count": len(sell_lines),
        "lines": buy_lines,
        "sell_lines": sell_lines,
    }


def gate_execution_package(exec_pkg: Dict[str, Any], *, t212_trusted: bool) -> Dict[str, Any]:
    return exec_pkg if t212_trusted else empty_execution_package()


def gate_orders_doc_for_display(orders: Dict[str, Any], *, t212_trusted: bool) -> Dict[str, Any]:
    if t212_trusted:
        return orders
    initial = dict(orders.get("initial_package") or {})
    initial.update({"active": False, "notional_eur": 0.0, "budget_eur": 0.0})
    return {
        **orders,
        "stocks": [],
        "stock_groups": {},
        "initial_package": initial,
    }


def _as_optional_float(raw: Any) -> Optional[float]:
    if raw is None:
        return None
    try:
        val = float(raw)
    except (TypeError, ValueError):
        return None
    return val if val >= 0 else None

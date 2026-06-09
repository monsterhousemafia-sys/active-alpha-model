"""Order preflight gates — all must pass before review/submit."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from execution.confirmed_live.confirmed_execution_mode_controller import (
    CORE_LIVE_MAX_SINGLE_POSITION_EUR,
    CORE_LIVE_MIN_RESERVE_EUR,
    can_submit_orders,
)
from execution.confirmed_live.order_sizing import MARKET_ORDER_SLIPPAGE_BUFFER
from execution.confirmed_live.global_kill_switch import is_active as kill_active
from execution.confirmed_live.managed_scope_service import baseline_exists, is_instrument_managed, load_baseline
from execution.confirmed_live.unknown_broker_state_guard import blocks_submission as unknown_blocks
from execution.confirmed_live.fail_closed_runtime_guard import is_paused as fail_closed_paused


def _blocked(reason: str) -> Dict[str, Any]:
    return {"passed": False, "blockers": [reason]}


def run_preflight(root: Path, draft: Dict[str, Any], *, readonly_cash: float | None, account_currency: str | None) -> Dict[str, Any]:
    blockers: List[str] = []

    sym = str(draft.get("instrument", "")).upper()
    if kill_active(root):
        blockers.append("PAUSED_BY_USER_KILL_SWITCH")
    if fail_closed_paused(root):
        blockers.append("PAUSED_FAIL_CLOSED_REQUIRES_USER_REVIEW")
    if unknown_blocks(root, instrument=sym or None):
        blockers.append("OPEN_UNKNOWN_BROKER_STATE_RECONCILIATION_REQUIRED")
    if not can_submit_orders(root):
        blockers.append("CORE_LIVE_MODE_NOT_ACTIVE")
    if not baseline_exists(root):
        blockers.append("MANAGED_LIVE_PILOT_BASELINE_REQUIRED")
    if account_currency and account_currency.upper() != "EUR":
        blockers.append("BLOCKED_ACCOUNT_CURRENCY_POLICY_REQUIRED")
    if readonly_cash is None:
        blockers.append("READONLY_BROKER_CASH_NOT_VERIFIED")
    if sym == "VUSD":
        blockers.append("INSTRUMENT_BLOCKED_AMBIGUOUS_OR_UNSUPPORTED")
    try:
        from analytics.prediction_operations import evaluate_prediction_readiness_for_orders

        pred = evaluate_prediction_readiness_for_orders(root)
        if not pred.get("ok") and not pred.get("skipped"):
            blockers.append("PREDICTION_NOT_READY")
    except Exception:
        blockers.append("PREDICTION_GATE_CHECK_FAILED")
    if not is_instrument_managed(root, sym):
        blockers.append("INSTRUMENT_NOT_IN_MANAGED_SCOPE")
    notional = float(draft.get("max_notional_eur") or 0)
    if CORE_LIVE_MAX_SINGLE_POSITION_EUR > 0 and notional > CORE_LIVE_MAX_SINGLE_POSITION_EUR:
        blockers.append("MAX_SINGLE_POSITION_EXCEEDED")
    order_type = str(draft.get("order_type") or "")
    is_market = order_type.startswith("MARKET")
    allowed_types = (
        ("MARKET_BUY", "MARKET_SELL_COVERED")
        if is_market
        else ("LIMIT_BUY", "LIMIT_SELL_COVERED")
    )
    if order_type not in allowed_types:
        blockers.append("ORDER_TYPE_NOT_ALLOWED_IN_P16H")
    if order_type == "MARKET":
        blockers.append("MARKET_ORDERS_DISABLED")
    reserve = CORE_LIVE_MIN_RESERVE_EUR
    if reserve > 0 and readonly_cash is not None and draft.get("side") == "BUY":
        if readonly_cash - notional < reserve:
            blockers.append("CASH_RESERVE_WOULD_BE_VIOLATED")
    if is_market:
        ref = float(draft.get("reference_price_eur") or draft.get("limit_price") or 0)
        if ref <= 0:
            blockers.append("REFERENCE_PRICE_REQUIRED")
    elif not draft.get("limit_price"):
        blockers.append("LIMIT_PRICE_REQUIRED")
    if not draft.get("t212_instrument_id"):
        blockers.append("T212_INSTRUMENT_ID_REQUIRED")

    from execution.confirmed_live.order_daily_limit import can_submit_more_orders_today

    allowed_day, day_reason = can_submit_more_orders_today(root)
    if not allowed_day:
        blockers.append(day_reason)

    if (
        MARKET_ORDER_SLIPPAGE_BUFFER > 1.0
        and reserve > 0
        and is_market
        and draft.get("side") == "BUY"
        and readonly_cash is not None
    ):
        buffered = notional * MARKET_ORDER_SLIPPAGE_BUFFER
        if readonly_cash - buffered < reserve:
            blockers.append("CASH_RESERVE_WOULD_BE_VIOLATED_MARKET_SLIPPAGE")

    return {"passed": len(blockers) == 0, "blockers": blockers, "checked_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat()}

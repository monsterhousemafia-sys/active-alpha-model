"""Order submission orchestration — token + preflight + single attempt."""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

from aa_safe_io import atomic_write_json
from execution.confirmed_live.order_confirmation_token_service import validate_and_consume
from execution.confirmed_live.order_preflight_gate import run_preflight
from integrations.trading212.t212_confirmed_execution_client import T212ConfirmedExecutionClient, T212ExecutionBlockedError


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _ledger_path(root: Path) -> Path:
    p = root / "live_pilot/confirmed_execution/live_execution_audit_ledger.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _append_ledger(root: Path, entry: Dict[str, Any]) -> None:
    with _ledger_path(root).open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry) + "\n")


def format_broker_submission_error(message: str) -> str:
    """Plain German + symbol for T212 order errors (no bare HTTP codes)."""
    from integrations.trading212.t212_user_messages import humanize_t212_error

    return humanize_t212_error(message)


def _is_market_draft(draft: Dict[str, Any]) -> bool:
    return str(draft.get("order_type") or "").startswith("MARKET")


def build_market_order_body(draft: Dict[str, Any]) -> Dict[str, Any]:
    """Build T212 POST /equity/orders/market JSON."""
    qty = float(draft.get("quantity") or 0)
    if draft.get("side") == "SELL":
        qty = -abs(qty)
    else:
        qty = abs(qty)
    ticker = str(draft.get("t212_instrument_id") or "").strip()
    if not ticker:
        raise ValueError("MISSING_T212_INSTRUMENT_ID")
    if qty == 0:
        raise ValueError("INVALID_QUANTITY")
    return {
        "ticker": ticker,
        "quantity": round(qty, 4),
        "extendedHours": False,
    }


def resolve_limit_time_validity(root: Path, draft: Dict[str, Any]) -> str:
    explicit = str(draft.get("limit_time_validity") or "").strip().upper()
    if explicit in ("DAY", "GOOD_TILL_CANCEL", "GTC"):
        return "DAY" if explicit == "DAY" else "GOOD_TILL_CANCEL"
    try:
        from analytics.live_trading_operations import load_policy

        pol = str(load_policy(root).get("limit_time_validity") or "DAY").strip().upper()
        return "DAY" if pol == "DAY" else "GOOD_TILL_CANCEL"
    except Exception:
        return "DAY"


def build_limit_order_body(draft: Dict[str, Any], *, root: Path | None = None) -> Dict[str, Any]:
    """Build T212 POST /equity/orders/limit JSON (account-currency limitPrice)."""
    qty = float(draft.get("quantity") or 0)
    if draft.get("side") == "SELL":
        qty = -abs(qty)
    else:
        qty = abs(qty)
    ticker = str(draft.get("t212_instrument_id") or "").strip()
    if not ticker:
        raise ValueError("MISSING_T212_INSTRUMENT_ID")
    limit = round(float(draft.get("limit_price") or 0), 2)
    if limit <= 0:
        raise ValueError("INVALID_LIMIT_PRICE")
    validity = "GOOD_TILL_CANCEL"
    if root is not None:
        validity = resolve_limit_time_validity(root, draft)
    elif draft.get("limit_time_validity"):
        validity = resolve_limit_time_validity(Path("."), draft)
    return {
        "ticker": ticker,
        "quantity": round(qty, 4),
        "limitPrice": limit,
        "timeValidity": validity,
    }


def submit_confirmed_order(
    root: Path,
    draft: Dict[str, Any],
    *,
    one_time_token: str,
    readonly_cash: float | None,
    account_currency: str | None,
    dry_run: bool = False,
    execution_style: str | None = None,
) -> Dict[str, Any]:
    root = Path(root)
    preflight = run_preflight(root, draft, readonly_cash=readonly_cash, account_currency=account_currency)
    if not preflight.get("passed"):
        return {"ok": False, "stage": "preflight", "blockers": preflight.get("blockers")}

    token_result = validate_and_consume(root, one_time_token, draft)
    if not token_result.get("valid"):
        return {"ok": False, "stage": "token", "error": token_result.get("error")}

    live_submit = not dry_run and os.environ.get("AA_EXECUTION_DRY_RUN", "").strip() != "1"
    if live_submit:
        from execution.confirmed_live.gui_execution_confirmation import (
            consume_execution_slot,
            lease_status,
        )

        lease = lease_status(root)
        if lease.get("active") and lease.get("source"):
            from analytics.r3_order_execution_gate import check_gui_lease_source_allowed

            lease_gate = check_gui_lease_source_allowed(root, str(lease.get("source")))
            if not lease_gate.get("allowed"):
                return {
                    "ok": False,
                    "stage": "r3_order_surface",
                    "error": lease_gate.get("error"),
                    "message_de": lease_gate.get("message_de"),
                }

        gui_gate = consume_execution_slot(root)
        if not gui_gate.get("ok"):
            return {
                "ok": False,
                "stage": "gui_confirmation",
                "error": gui_gate.get("error"),
                "message_de": gui_gate.get("message_de"),
            }

    use_market = str(execution_style or "").lower() == "market" or _is_market_draft(draft)
    body = build_market_order_body(draft) if use_market else build_limit_order_body(draft, root=root)
    entry = {
        "timestamp_utc": _utc_now(),
        "draft_id": draft.get("draft_id"),
        "instrument": draft.get("instrument"),
        "side": draft.get("side"),
        "status": "SUBMISSION_IN_PROGRESS",
        "payload_hash": token_result.get("record", {}).get("payload_hash_sha256"),
    }

    from execution.confirmed_live.p17_review_mode_guard import review_mode_active
    from execution.confirmed_live.pilot_live_trading_policy import live_submission_allowed
    from execution.linux_security_boundary import live_order_submission_blocked

    try:
        if live_order_submission_blocked():
            response = T212ConfirmedExecutionClient.from_execution_profile(root).dry_run_submit(body)
            entry["status"] = "BLOCKED_LINUX_COMPUTE_HOST"
            entry["response_summary"] = {"dry_run": True, "linux_compute_host": True}
            _append_ledger(root, entry)
            return {
                "ok": False,
                "stage": "submission",
                "error": "LINUX_COMPUTE_HOST_LIVE_ORDERS_FORBIDDEN",
                "response": response,
                "mock": True,
            }
        if dry_run or os.environ.get("AA_EXECUTION_DRY_RUN", "").strip() == "1":
            response = T212ConfirmedExecutionClient.from_execution_profile(root).dry_run_submit(body)
            if review_mode_active() and not live_submission_allowed(root):
                entry["status"] = "BLOCKED_LIVE_REVIEW_MODE"
                entry["response_summary"] = {"dry_run": True, "p17_review_mode": True}
                _append_ledger(root, entry)
                return {"ok": True, "status": "BLOCKED_LIVE_REVIEW_MODE", "response": response, "mock": True}
        else:
            if review_mode_active() and not live_submission_allowed(root):
                entry["status"] = "BLOCKED_LIVE_REVIEW_MODE"
                entry["error"] = "P17_REVIEW_MODE_NO_LIVE_NETWORK_SUBMISSION"
                _append_ledger(root, entry)
                return {"ok": False, "stage": "submission", "error": "P17_REVIEW_MODE_NO_LIVE_NETWORK_SUBMISSION"}
            client = T212ConfirmedExecutionClient.from_execution_profile(root)
            if use_market:
                from integrations.trading212.t212_order_pacing import (
                    acquire_market_order_slot,
                    can_place_market_order_now,
                    record_market_order_result,
                )

                allowed, block_msg = can_place_market_order_now(root)
                if not allowed:
                    entry["status"] = "FAILED_UNKNOWN_BROKER_STATE_RECONCILIATION_REQUIRED"
                    entry["error"] = block_msg[:200]
                    _append_ledger(root, entry)
                    return {"ok": False, "stage": "rate_limit", "error": block_msg}
                acquire_market_order_slot(root)
                try:
                    response = client.submit_market_order(body, root=root)
                    record_market_order_result(root, success=True)
                except T212ExecutionBlockedError as exc:
                    record_market_order_result(root, success=False, error=str(exc))
                    raise
            else:
                from integrations.trading212.t212_order_pacing import (
                    acquire_limit_order_slot,
                    can_place_limit_order_now,
                    record_limit_order_result,
                )

                allowed, block_msg = can_place_limit_order_now(root)
                if not allowed:
                    entry["status"] = "FAILED_UNKNOWN_BROKER_STATE_RECONCILIATION_REQUIRED"
                    entry["error"] = block_msg[:200]
                    _append_ledger(root, entry)
                    return {"ok": False, "stage": "rate_limit", "error": block_msg}

                acquire_limit_order_slot(root)
                try:
                    response = client.submit_limit_order(body, root=root)
                    record_limit_order_result(root, success=True)
                except T212ExecutionBlockedError as exc:
                    record_limit_order_result(root, success=False, error=str(exc))
                    raise
        entry["status"] = "SUBMITTED_AWAITING_READONLY_RECONCILIATION"
        entry["response_summary"] = {"keys": list(response.keys()) if isinstance(response, dict) else []}
        _append_ledger(root, entry)
        try:
            from integrations.trading212.t212_order_readiness import mark_api_execute_scope_proven, record_stock_buy_attempt

            mark_api_execute_scope_proven(root)
            record_stock_buy_attempt(root, ok=True)
        except Exception:
            pass
        out_path = root / "live_pilot/confirmed_execution/submitted_orders" / f"{draft.get('draft_id', 'unknown')}.json"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_json(out_path, {"draft": draft, "body": body, "response": response, "submitted_at_utc": _utc_now()})
        try:
            from execution.confirmed_live.order_daily_limit import record_successful_submission

            record_successful_submission(root, draft_id=str(draft.get("draft_id") or ""))
        except Exception:
            pass
        try:
            from execution.live_learning.live_execution_outcome_bridge import sync_live_execution_outcomes

            sync_live_execution_outcomes(root, refresh_history=False)
        except Exception:
            pass
        return {"ok": True, "status": entry["status"], "response": response, "sent_to_t212": True}
    except T212ExecutionBlockedError as exc:
        err = str(exc)
        from integrations.trading212.t212_order_error_parser import parse_t212_order_error

        parsed = parse_t212_order_error(err)
        if parsed.category == "insufficient":
            entry["status"] = "FAILED_INSUFFICIENT_STOCKS_BUY"
        elif parsed.category == "min_quantity":
            entry["status"] = "FAILED_MIN_QUANTITY"
        elif "429" in err or "too many requests" in err.lower():
            entry["status"] = "FAILED_RATE_LIMIT"
        else:
            entry["status"] = "FAILED_BROKER_SUBMISSION"
        entry["error"] = err[:200]
        _append_ledger(root, entry)
        try:
            from integrations.trading212.t212_order_readiness import record_stock_buy_attempt

            record_stock_buy_attempt(root, ok=False, error=err)
            if "403" not in err and "scope" not in err.lower():
                from integrations.trading212.t212_order_readiness import mark_api_execute_scope_proven

                mark_api_execute_scope_proven(root)
        except Exception:
            pass
        return {"ok": False, "stage": "submission", "error": err}

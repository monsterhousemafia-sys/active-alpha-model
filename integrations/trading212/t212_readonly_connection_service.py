"""Read-only Trading 212 connection orchestration for interactive cockpit."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from integrations.trading212.t212_connection_status_model import BrokerConnectionStatus
from integrations.trading212.t212_credentials_loader import T212Credentials, load_credentials
from integrations.trading212.t212_demo_readonly_client import T212DemoReadOnlyClient
from integrations.trading212.t212_live_readonly_client import T212LiveReadOnlyClient, T212LiveReadOnlyError
from integrations.trading212.t212_secret_redaction import redact_secrets
from integrations.trading212.t212_session_credential_store import get_session_state, session_configured
from integrations.trading212.t212_sync_throttle import (
    is_auth_error,
    is_rate_limit_error,
    rate_limit_user_message_de,
    read_throttle_state,
    record_sync_attempt,
    should_sync_now,
)
from integrations.trading212.t212_user_messages import humanize_t212_error


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _client_for_mode(creds: T212Credentials, mode: str):
    if mode == "DEMO_READ_ONLY":
        return T212DemoReadOnlyClient(creds)
    return T212LiveReadOnlyClient(creds)


def test_connection(
    creds: T212Credentials,
    mode: str,
    *,
    root: Optional[Path] = None,
) -> Tuple[bool, str]:
    from integrations.trading212.t212_sync_throttle import (
        can_test_connection_now,
        format_api_error_de,
        record_connection_test,
    )

    root_path = Path(root) if root is not None else None
    last_sync: Optional[str] = None
    if root_path is not None:
        allowed, block_msg = can_test_connection_now(root_path)
        if not allowed:
            return False, block_msg
        cached = load_cached_broker_status(root_path)
        if cached:
            last_sync = cached.last_successful_sync_utc

    try:
        client = _client_for_mode(creds, mode)
        client.get("/equity/account/summary")
        if root_path is not None:
            record_connection_test(root_path, success=True)
        from integrations.trading212.t212_user_messages import success_message

        return True, success_message("Trading 212 erreichbar — Verbindung OK.")
    except Exception as exc:
        err = redact_secrets(str(exc))[:200]
        if root_path is not None:
            record_connection_test(root_path, success=False, error=err)
        return False, format_api_error_de(err, last_sync_utc=last_sync)


def _sync_state_path(root: Path) -> Path:
    return root / "live_pilot/manual_execution/readonly_real_account_state/latest_sync.json"


def _positions_state_path(root: Path) -> Path:
    return root / "live_pilot/manual_execution/readonly_real_positions/positions_snapshot.json"


def load_cached_broker_status(root: Path) -> BrokerConnectionStatus | None:
    root = Path(root)
    sync_path = _sync_state_path(root)
    if not sync_path.is_file():
        return None
    try:
        doc = json.loads(sync_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None

    status = BrokerConnectionStatus()
    status.credentials_configured = True
    status.environment = str(doc.get("environment") or "LIVE_READ_ONLY")
    status.account_summary = doc.get("summary") if isinstance(doc.get("summary"), dict) else {}
    from integrations.trading212.t212_cash_parser import parse_cash_breakdown

    cached_breakdown = doc.get("cash_breakdown") if isinstance(doc.get("cash_breakdown"), dict) else {}
    if cached_breakdown:
        status.cash_breakdown = cached_breakdown
        status.cash_eur = cached_breakdown.get("planning_cash_eur") or cached_breakdown.get(
            "available_to_trade_eur"
        )
    else:
        breakdown = parse_cash_breakdown(account_summary=status.account_summary)
        status.cash_breakdown = breakdown.to_dict()
        status.cash_eur = breakdown.planning_cash_eur
    if status.cash_eur is None and doc.get("cash_eur") is not None:
        status.cash_eur = float(doc["cash_eur"])
    status.positions_count = int(doc.get("positions_count") or 0)
    status.last_successful_sync_utc = doc.get("synced_at_utc")
    status.status = str(doc.get("status") or "LIVE_READONLY_ACCOUNT_MONITORING_ACTIVE")
    status.last_error = doc.get("last_error")

    pos_path = _positions_state_path(root)
    if pos_path.is_file():
        try:
            pos_doc = json.loads(pos_path.read_text(encoding="utf-8"))
            status.positions = pos_doc.get("positions") or []
            status.positions_count = len(status.positions) if isinstance(status.positions, list) else status.positions_count
        except (json.JSONDecodeError, OSError):
            status.positions = doc.get("positions") or []
    else:
        status.positions = doc.get("positions") or []
    return status


def sync_readonly_account(root: Path, *, force: bool = False) -> BrokerConnectionStatus:
    root = Path(root)
    status = BrokerConnectionStatus()
    sess = get_session_state()
    creds = load_credentials(root)
    cached = load_cached_broker_status(root)

    if not creds or not creds.configured:
        status.status = "NOT_CONFIGURED_SETUP_AVAILABLE_IN_GUI"
        return status

    mode = (sess.mode if sess else "LIVE_READ_ONLY").upper()
    status.credentials_configured = True
    status.environment = mode
    status.connection_name = sess.connection_name if sess else "Trading 212"

    allow, throttle_reason = should_sync_now(
        root,
        force=force,
        last_successful_sync_utc=cached.last_successful_sync_utc if cached else None,
    )
    if not allow:
        if cached is not None:
            cached.last_error = throttle_reason
            cached.status = "CACHED_READONLY_DATA"
            return cached
        status.status = "CONNECTION_FAILED_RETRY_AVAILABLE"
        status.last_error = throttle_reason
        return status

    try:
        client = _client_for_mode(creds, mode)
        summary = client.get("/equity/account/summary")
        cash = client.get("/equity/account/cash")
        positions = client.get("/equity/positions")

        status.account_summary = summary if isinstance(summary, dict) else {}
        pos_list: List[Any] = positions if isinstance(positions, list) else (positions.get("items") if isinstance(positions, dict) else [])
        status.positions = pos_list or []
        status.positions_count = len(status.positions)

        from integrations.trading212.t212_cash_parser import parse_cash_breakdown, verify_cash_eur_matches_summary

        breakdown = parse_cash_breakdown(cash, account_summary=status.account_summary)
        status.cash_breakdown = breakdown.to_dict()
        status.cash_eur = breakdown.planning_cash_eur
        status.status = "LIVE_READONLY_ACCOUNT_MONITORING_ACTIVE" if mode == "LIVE_READ_ONLY" else "DEMO_READONLY_CONNECTED"
        status.last_successful_sync_utc = _utc_now()

        out = root / "live_pilot/manual_execution/readonly_real_account_state"
        out.mkdir(parents=True, exist_ok=True)
        alignment = verify_cash_eur_matches_summary(status.cash_eur, status.account_summary)
        (out / "latest_sync.json").write_text(
            json.dumps(
                {
                    "summary": status.account_summary,
                    "cash_eur": status.cash_eur,
                    "cash_breakdown": status.cash_breakdown,
                    "cash_alignment": alignment,
                    "positions_count": status.positions_count,
                    "positions": status.positions,
                    "synced_at_utc": status.last_successful_sync_utc,
                    "environment": mode,
                    "status": status.status,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        pos_out = root / "live_pilot/manual_execution/readonly_real_positions"
        pos_out.mkdir(parents=True, exist_ok=True)
        (pos_out / "positions_snapshot.json").write_text(
            json.dumps(
                {
                    "meta": {
                        "positions_verified": True,
                        "position_count": status.positions_count,
                        "observed_at_utc": status.last_successful_sync_utc,
                    },
                    "positions": status.positions,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        record_sync_attempt(root, success=True)
    except T212LiveReadOnlyError as exc:
        err = redact_secrets(str(exc))[:200]
        record_sync_attempt(root, success=False, error=err)
        if cached is not None and (is_rate_limit_error(err) or is_auth_error(err)):
            if is_auth_error(err):
                cached.status = "CREDENTIALS_EXPIRED_SHOWING_CACHED_DATA"
                cached.last_error = humanize_t212_error(err, last_sync_utc=cached.last_successful_sync_utc)
            else:
                cached.status = "RATE_LIMITED_SHOWING_CACHED_DATA"
                cached.last_error = rate_limit_user_message_de(cached.last_successful_sync_utc)
            cached.credentials_configured = True
            return cached
        status.status = "CONNECTION_FAILED_RETRY_AVAILABLE"
        status.last_error = err
    except Exception as exc:
        err = redact_secrets(str(exc))[:200]
        record_sync_attempt(root, success=False, error=err)
        if cached is not None and (is_rate_limit_error(err) or is_auth_error(err)):
            if is_auth_error(err):
                cached.status = "CREDENTIALS_EXPIRED_SHOWING_CACHED_DATA"
                cached.last_error = humanize_t212_error(err, last_sync_utc=cached.last_successful_sync_utc)
            else:
                cached.status = "RATE_LIMITED_SHOWING_CACHED_DATA"
                cached.last_error = rate_limit_user_message_de(cached.last_successful_sync_utc)
            cached.credentials_configured = True
            return cached
        status.status = "CONNECTION_FAILED_RETRY_AVAILABLE"
        status.last_error = err

    return status


def connection_status_summary(root: Path, *, force_sync: bool = False) -> BrokerConnectionStatus:
    if not session_configured() and load_credentials(root) is None:
        cached = load_cached_broker_status(root)
        return cached or BrokerConnectionStatus()
    if not force_sync:
        cached = load_cached_broker_status(root)
        if cached is not None:
            return cached
    return sync_readonly_account(root, force=force_sync)

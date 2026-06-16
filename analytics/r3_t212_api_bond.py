"""R3 ↔ Trading212 API — zentrale feste Verbindung mit Bestätigung auf R3."""
from __future__ import annotations

import html
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from aa_safe_io import atomic_write_json

_POLICY_REL = Path("control/r3_t212_api_bond_policy.json")
_BOND_LOCK_REL = Path("control/r3_t212_api_bond.json")
_EVIDENCE_REL = Path("evidence/r3_t212_api_bond_latest.json")

_CONNECTED_STATUSES = frozenset(
    {
        "LIVE_READONLY_ACCOUNT_MONITORING_ACTIVE",
        "DEMO_READONLY_CONNECTED",
        "CACHED_READONLY_DATA",
        "RATE_LIMITED_SHOWING_CACHED_DATA",
        "CREDENTIALS_EXPIRED_SHOWING_CACHED_DATA",
    }
)
_STALE_SYNC_WARN_S = 1800


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


def load_bond_policy(root: Path) -> Dict[str, Any]:
    return _load_json(Path(root) / _POLICY_REL)


def load_bond_lock(root: Path) -> Dict[str, Any]:
    return _load_json(Path(root) / _BOND_LOCK_REL)


def _broker_snapshot(root: Path, *, force_sync: bool = False) -> Dict[str, Any]:
    try:
        from integrations.trading212.t212_readonly_connection_service import (
            connection_status_summary,
            load_cached_broker_status,
        )

        if force_sync:
            st = connection_status_summary(root, force_sync=True)
        else:
            cached = load_cached_broker_status(root)
            st = cached if cached is not None else connection_status_summary(root, force_sync=False)
        return st.to_dict() if hasattr(st, "to_dict") else dict(st or {})
    except Exception as exc:
        return {"status": "CONNECTION_FAILED_RETRY_AVAILABLE", "last_error": str(exc)[:120]}


def _sync_age_seconds(broker: Dict[str, Any]) -> Optional[float]:
    raw = broker.get("last_successful_sync_utc")
    if not raw:
        return None
    try:
        ts = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - ts).total_seconds()
    except ValueError:
        return None


def _is_connected(broker: Dict[str, Any]) -> bool:
    status = str(broker.get("status") or "")
    if status in _CONNECTED_STATUSES:
        return True
    return bool(broker.get("credentials_configured")) and bool(broker.get("last_successful_sync_utc"))


def _broker_state(broker: Dict[str, Any], *, bonded: bool) -> str:
    status = str(broker.get("status") or "")
    if status == "CREDENTIALS_EXPIRED_SHOWING_CACHED_DATA":
        return "warn"
    age = _sync_age_seconds(broker)
    if age is not None and age > _STALE_SYNC_WARN_S:
        return "warn"
    if _is_connected(broker) and bonded:
        return "ok" if status in {"LIVE_READONLY_ACCOUNT_MONITORING_ACTIVE", "DEMO_READONLY_CONNECTED"} else "warn"
    if bonded:
        return "warn"
    return "fail"


def _confirmation_de(broker: Dict[str, Any], *, bonded: bool) -> str:
    env = str(broker.get("environment") or "—")
    positions = int(broker.get("positions_count") or 0)
    sync_at = str(broker.get("last_successful_sync_utc") or "")[:19].replace("T", " ")
    status = str(broker.get("status") or "")

    if not broker.get("credentials_configured"):
        from analytics.r3_operator_surface_text import OPERATOR_API_ENTER

        return OPERATOR_API_ENTER

    if _is_connected(broker) and bonded:
        cash = broker.get("cash_eur")
        cash_bit = f" · {float(cash):.0f} €" if cash is not None else ""
        if status == "CREDENTIALS_EXPIRED_SHOWING_CACHED_DATA":
            from analytics.r3_operator_surface_text import operator_status_de

            return operator_status_de("CREDENTIALS_EXPIRED_SHOWING_CACHED_DATA")
        age = _sync_age_seconds(broker)
        if age is not None and age > _STALE_SYNC_WARN_S:
            from analytics.r3_operator_surface_text import operator_status_de

            return operator_status_de("STALE_SYNC")
        if status in {"CACHED_READONLY_DATA", "RATE_LIMITED_SHOWING_CACHED_DATA"}:
            from analytics.r3_operator_surface_text import operator_status_de

            return operator_status_de(status)
        if status in {"LIVE_READONLY_ACCOUNT_MONITORING_ACTIVE", "DEMO_READONLY_CONNECTED"}:
            return ""
        return ""

    err = str(broker.get("last_error") or "")[:80]
    if bonded:
        from analytics.r3_operator_surface_text import operator_status_de

        return operator_status_de(str(broker.get("status") or "CONNECTION_FAILED_RETRY_AVAILABLE"))
    from analytics.r3_operator_surface_text import OPERATOR_API_ENTER

    return OPERATOR_API_ENTER


def _r3_investable_from_broker(root: Path, broker: Dict[str, Any]) -> Optional[float]:
    try:
        from analytics.r3_closed_loop import resolve_r3_investable_eur
        from execution.confirmed_live.planning_cash import resolve_planning_cash_eur

        planning = resolve_planning_cash_eur(
            broker.get("cash_eur"),
            broker=broker,
            root=Path(root),
            subtract_pending_orders=True,
        )
        if planning is None:
            return None
        return resolve_r3_investable_eur(root, float(planning))
    except Exception:
        return None


def build_r3_t212_api_bond(root: Path, *, persist: bool = False) -> Dict[str, Any]:
    root = Path(root)
    policy = load_bond_policy(root)
    lock = load_bond_lock(root)
    broker = _broker_snapshot(root, force_sync=False)

    from analytics.r3_t212_account_identity import (
        account_fingerprint,
        account_label,
        connection_label,
        credentials_fingerprint,
    )

    cred_fp = credentials_fingerprint(root)
    acct_fp = account_fingerprint(broker)
    acct_label = account_label(broker)
    conn_label = connection_label(broker, fingerprint=acct_fp)
    credentials_rotated_at = lock.get("credentials_rotated_at")
    if cred_fp and cred_fp != lock.get("credentials_fingerprint"):
        credentials_rotated_at = _utc_now()

    connected = _is_connected(broker)
    was_bonded = bool(lock.get("bonded"))
    bonded = was_bonded or connected
    if bonded and connected and not was_bonded:
        lock = {
            **lock,
            "bonded": True,
            "bonded_at_utc": _utc_now(),
        }

    trust: Dict[str, Any] = {}
    try:
        from integrations.trading212.t212_trust_gate import assess_t212_trust

        trust = assess_t212_trust(broker, root=root)
    except Exception:
        trust = {"trusted": False, "orders_allowed": False, "message_de": "T212 Trust Gate ausstehend"}

    confirm = _confirmation_de(broker, bonded=bonded)
    from analytics.r3_operator_surface_text import operator_status_de, sanitize_operator_text

    if not trust.get("trusted"):
        minimal = operator_status_de(str(trust.get("reason_code") or ""))
        confirm = minimal or sanitize_operator_text(confirm, fallback="")
    state = "fail" if not trust.get("trusted") and str(broker.get("status") or "") in {
        "CREDENTIALS_EXPIRED_SHOWING_CACHED_DATA",
        "CONNECTION_FAILED_RETRY_AVAILABLE",
        "NOT_CONFIGURED_SETUP_AVAILABLE_IN_GUI",
    } else _broker_state(broker, bonded=bonded)
    if not trust.get("trusted") and state == "ok":
        state = "warn"

    doc: Dict[str, Any] = {
        "schema_version": 1,
        "updated_at_utc": _utc_now(),
        "headline_de": str(policy.get("headline_de") or "R3 ↔ Trading212 API"),
        "broker_de": str(policy.get("broker_de") or "Trading212"),
        "bonded": bonded,
        "connected": connected,
        "state": state,
        "confirmation_de": confirm,
        "environment": broker.get("environment"),
        "env": str(broker.get("environment") or "").split("_")[0] or None,
        "account_fingerprint": acct_fp,
        "account_label": acct_label,
        "connection_label": conn_label,
        "credentials_fingerprint": cred_fp,
        "credentials_rotated_at": credentials_rotated_at,
        "credentials_configured": bool(broker.get("credentials_configured")),
        "needs_api_setup": False,
        "operator_api_ready": True,
        "positions_count": int(broker.get("positions_count") or 0),
        "positions": broker.get("positions") or [],
        "cash_eur": broker.get("cash_eur") if trust.get("trusted") else None,
        "cash_breakdown": broker.get("cash_breakdown") or {},
        "investable_eur": _r3_investable_from_broker(root, broker)
        if trust.get("trusted")
        else None,
        "last_sync_utc": broker.get("last_successful_sync_utc"),
        "broker_status": broker.get("status"),
        "t212_trusted": bool(trust.get("trusted")),
        "t212_orders_blocked": not bool(trust.get("orders_allowed", False)),
        "t212_trust_reason": trust.get("reason_code"),
        "t212_trust_message_de": trust.get("message_de"),
        "read_only": bool(policy.get("read_only", True)),
        "allow_live_orders": bool(policy.get("allow_live_orders", False)),
        "policy_ref": str(_POLICY_REL).replace("\\", "/"),
        "bond_lock_ref": str(_BOND_LOCK_REL).replace("\\", "/"),
        "api_route_de": "GET /api/r3/t212",
        "message_de": confirm,
    }

    if bonded:
        lock_update = {
            **lock,
            "bonded": True,
            "bonded_at_utc": lock.get("bonded_at_utc") or _utc_now(),
            "last_confirmed_at_utc": _utc_now(),
            "confirmation_de": confirm,
            "environment": broker.get("environment"),
            "last_sync_utc": broker.get("last_successful_sync_utc"),
            "account_fingerprint": acct_fp,
            "account_label": acct_label,
            "connection_label": conn_label,
            "credentials_fingerprint": cred_fp,
            "credentials_rotated_at": credentials_rotated_at,
        }
        atomic_write_json(root / _BOND_LOCK_REL, lock_update)

    if persist:
        atomic_write_json(root / _EVIDENCE_REL, doc)
    try:
        from analytics.r3_t212_operator_api import merge_operator_api_fields

        doc = merge_operator_api_fields(doc, root, persist_path=(root / _EVIDENCE_REL if persist else None))
    except Exception:
        pass
    return doc


def ensure_r3_t212_api_bond(root: Path, *, persist: bool = True) -> Dict[str, Any]:
    """
    Start-Kette — API fest einrichten:
    .env/DPAPI → Session → Live-Sync → Bond-Lock → Konto bestätigen.
    """
    root = Path(root)
    steps: List[Dict[str, Any]] = []

    from analytics.r3_t212_operator_api import ensure_operator_bond_lock, resolve_operator_api_state

    api_state = resolve_operator_api_state(root)
    if api_state.get("needs_api_setup"):
        from analytics.r3_operator_surface_text import OPERATOR_API_ENTER, OPERATOR_RETRY

        return {
            "schema_version": 1,
            "updated_at_utc": _utc_now(),
            "ok": False,
            "setup_ok": False,
            "needs_api_setup": True,
            "t212_trusted": False,
            "credentials_configured": bool(api_state.get("credentials_configured")),
            "operator_api_ready": False,
            "headline_de": OPERATOR_API_ENTER,
            "next_de": OPERATOR_API_ENTER,
            "steps": [{"step": "operator_api_setup", "ok": False}],
            "bond": {},
            "account_confirm": {},
            "bootstrap": {},
        }

    bootstrap: Dict[str, Any] = {}
    try:
        from integrations.trading212.t212_startup_bootstrap import bootstrap_trading212_credentials

        bootstrap = bootstrap_trading212_credentials(root)
        migration = bootstrap.get("migration") or {}
        session = bootstrap.get("session_restore") or {}
        from analytics.r3_t212_account_identity import credentials_fingerprint

        creds_ok = bool(credentials_fingerprint(root))
        steps.append(
            {
                "step": "credentials_bootstrap",
                "ok": creds_ok,
                "restored": bool(session.get("restored")),
                "migrated": bool(migration.get("migrated")),
                "detail_de": str(session.get("reason") or migration.get("reason") or "")[:120],
            }
        )
    except Exception as exc:
        steps.append({"step": "credentials_bootstrap", "ok": False, "error": str(exc)[:120]})

    bond = sync_r3_t212_api_bond(root, force=True, persist=persist)
    creds_ok = bool(bond.get("credentials_configured"))
    if not creds_ok:
        try:
            from analytics.r3_t212_account_identity import credentials_fingerprint

            creds_ok = bool(credentials_fingerprint(root))
        except Exception:
            creds_ok = False
    steps.append(
        {
            "step": "api_bond_sync",
            "ok": bool(bond.get("bonded")) and creds_ok,
            "bonded": bool(bond.get("bonded")),
            "connected": bool(bond.get("connected")),
            "trusted": bool(bond.get("t212_trusted")),
            "credentials_configured": creds_ok,
        }
    )

    confirm: Dict[str, Any] = {}
    if bond.get("account_fingerprint"):
        try:
            from analytics.r3_t212_account_identity import confirm_t212_account

            confirm = confirm_t212_account(root, bond=bond)
            steps.append({"step": "account_confirm", "ok": bool(confirm.get("ok"))})
        except Exception as exc:
            steps.append({"step": "account_confirm", "ok": False, "error": str(exc)[:80]})

    setup_ok = bool(api_state.get("operator_api_ready"))
    bond = ensure_operator_bond_lock(root, bond, api_state)
    trusted = bool(bond.get("t212_trusted"))
    from analytics.r3_operator_surface_text import OPERATOR_API_ENTER, OPERATOR_RETRY, OPERATOR_SYNC_WAIT

    if setup_ok and trusted:
        headline = ""
    elif setup_ok:
        headline = OPERATOR_SYNC_WAIT
    else:
        headline = OPERATOR_API_ENTER

    return {
        "schema_version": 1,
        "updated_at_utc": _utc_now(),
        "ok": setup_ok,
        "setup_ok": setup_ok,
        "needs_api_setup": False,
        "operator_api_ready": bool(api_state.get("operator_api_ready")),
        "t212_trusted": trusted,
        "credentials_configured": creds_ok,
        "bonded": bool(bond.get("bonded")),
        "connected": bool(bond.get("connected")),
        "investable_eur": bond.get("investable_eur"),
        "cash_eur": bond.get("cash_eur"),
        "confirmation_de": bond.get("confirmation_de"),
        "headline_de": headline,
        "next_de": OPERATOR_RETRY if not setup_ok else (OPERATOR_SYNC_WAIT if not trusted else ""),
        "steps": steps,
        "bond": bond,
        "account_confirm": confirm,
        "bootstrap": bootstrap,
    }


def sync_r3_t212_api_bond(root: Path, *, force: bool = False, persist: bool = True) -> Dict[str, Any]:
    """API-Sync (throttled) — Bond bleibt bei Cache/Rate-Limit fest."""
    root = Path(root)
    policy = load_bond_policy(root)
    lock = load_bond_lock(root)

    try:
        from integrations.trading212.t212_readonly_connection_service import sync_readonly_account
        from integrations.trading212.t212_sync_throttle import should_sync_now

        cached_sync = lock.get("last_sync_utc")
        allow, _reason = should_sync_now(root, force=force, last_successful_sync_utc=cached_sync)
        if allow or force:
            st = sync_readonly_account(root, force=force)
            sync_utc = getattr(st, "last_successful_sync_utc", None) or (
                st.to_dict().get("last_successful_sync_utc") if hasattr(st, "to_dict") else None
            )
            if sync_utc and lock.get("bonded"):
                lock = {**lock, "last_sync_utc": sync_utc}
                atomic_write_json(root / _BOND_LOCK_REL, lock)
    except Exception:
        pass

    doc = build_r3_t212_api_bond(root, persist=persist)
    if bool(policy.get("bond_mode") == "persistent") and lock.get("bonded"):
        doc["bonded"] = True
        if not doc.get("connected"):
            doc["state"] = "warn"
            doc["confirmation_de"] = _confirmation_de(
                _broker_snapshot(root, force_sync=False),
                bonded=True,
            )
            doc["message_de"] = doc["confirmation_de"]
            if persist:
                atomic_write_json(root / _EVIDENCE_REL, doc)
    return doc


R3_T212_BOND_CSS = """
.r3-t212-bond {
  text-align: center; font-size: 12px; font-weight: 600; margin: 0 0 10px;
  padding: 9px 14px; border-radius: 12px; line-height: 1.4;
}
.r3-t212-bond.ok {
  color: var(--ok, #32d74b);
  background: rgba(50,215,76,.1);
  border: 1px solid rgba(50,215,76,.28);
}
.r3-t212-bond.warn {
  color: var(--warn, #ffd60a);
  background: rgba(255,214,10,.08);
  border: 1px solid rgba(255,214,10,.28);
}
.r3-t212-bond.fail {
  color: var(--fail, #ff453a);
  background: rgba(255,69,58,.08);
  border: 1px solid rgba(255,69,58,.28);
}
"""


def render_r3_t212_bond_confirmation(root: Path, bond: Optional[Dict[str, Any]] = None) -> str:
    doc = bond or _load_json(Path(root) / _EVIDENCE_REL)
    if not doc:
        return ""
    state = str(doc.get("state") or "fail")
    text = html.escape(str(doc.get("confirmation_de") or doc.get("message_de") or "").strip())
    if not text:
        return ""
    return f'<p class="r3-t212-bond {state}" id="r3-t212-bond" aria-label="Trading212 API">{text}</p>'

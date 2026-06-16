"""T212 Trust Gate — fail-closed: kein Live-Cash/Orders ohne frischen, gültigen Sync."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from aa_safe_io import atomic_write_json

_POLICY_REL = Path("control/t212_trust_policy.json")
_EVIDENCE_REL = Path("evidence/t212_trust_latest.json")

_UNTRUSTED_STATUSES = frozenset(
    {
        "NOT_CONFIGURED_SETUP_AVAILABLE_IN_GUI",
        "CONNECTION_FAILED_RETRY_AVAILABLE",
        "CREDENTIALS_EXPIRED_SHOWING_CACHED_DATA",
        "CACHED_READONLY_DATA",
        "RATE_LIMITED_SHOWING_CACHED_DATA",
    }
)
_TRUSTED_LIVE_STATUSES = frozenset(
    {
        "LIVE_READONLY_ACCOUNT_MONITORING_ACTIVE",
        "DEMO_READONLY_CONNECTED",
    }
)


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


def load_trust_policy(root: Path) -> Dict[str, Any]:
    doc = _load_json(Path(root) / _POLICY_REL)
    if not doc:
        return {
            "schema_version": 1,
            "fail_closed": True,
            "max_stale_sync_s": 900,
            "max_stale_display_s": 1800,
            "block_orders_when_untrusted": True,
            "block_plan_scaling_when_untrusted": True,
        }
    return doc


def sync_age_seconds(last_sync_utc: Optional[str]) -> Optional[float]:
    if not last_sync_utc:
        return None
    try:
        ts = datetime.fromisoformat(str(last_sync_utc).replace("Z", "+00:00"))
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - ts).total_seconds()
    except ValueError:
        return None


def assess_t212_trust(broker: Dict[str, Any], *, root: Optional[Path] = None) -> Dict[str, Any]:
    """
    trusted=True nur bei frischem Live-Sync ohne Auth-/Cache-Fehler.
    orders_allowed / plan_capital_allowed folgen fail_closed Policy.
    """
    policy = load_trust_policy(root) if root is not None else load_trust_policy(Path("."))
    status = str(broker.get("status") or "")
    sync_utc = broker.get("last_successful_sync_utc") or broker.get("last_sync_utc")
    age = sync_age_seconds(sync_utc)
    max_stale = int(policy.get("max_stale_sync_s") or 900)
    max_display = int(policy.get("max_stale_display_s") or 1800)

    reason = ""
    code = "OK"
    if not broker.get("credentials_configured"):
        code, reason = "NOT_CONFIGURED", "T212 API nicht konfiguriert"
    elif status in _UNTRUSTED_STATUSES:
        code = status
        if status == "CREDENTIALS_EXPIRED_SHOWING_CACHED_DATA":
            reason = "API-Key ungültig — nur Cache"
        elif status == "RATE_LIMITED_SHOWING_CACHED_DATA":
            reason = "Rate-Limit — nur Cache"
        elif status == "CACHED_READONLY_DATA":
            reason = "Kein Live-Sync — nur Cache"
        else:
            reason = str(broker.get("last_error") or "T212-Verbindung fehlgeschlagen")[:120]
    elif not sync_utc:
        code, reason = "NO_SYNC", "Noch kein erfolgreicher T212-Sync"
    elif age is not None and age > max_stale:
        code, reason = "STALE_SYNC", f"Sync veraltet ({int(age)}s > {max_stale}s)"
    elif status not in _TRUSTED_LIVE_STATUSES:
        code, reason = "UNKNOWN_STATUS", f"Broker-Status unbekannt: {status or '—'}"
    elif broker.get("cash_eur") is None:
        code, reason = "NO_CASH", "Kontostand fehlt"

    trusted = code == "OK"
    fail_closed = bool(policy.get("fail_closed", True))
    block_orders = bool(policy.get("block_orders_when_untrusted", True))
    block_plan = bool(policy.get("block_plan_scaling_when_untrusted", True))

    display_ok = trusted or (age is not None and age <= max_display and broker.get("cash_eur") is not None)

    from analytics.r3_operator_surface_text import operator_status_de

    msg = operator_status_de(code if not trusted else "OK")

    doc = {
        "schema_version": 1,
        "updated_at_utc": _utc_now(),
        "trusted": trusted,
        "fail_closed": fail_closed,
        "orders_allowed": trusted if block_orders else True,
        "plan_capital_allowed": trusted if block_plan else True,
        "display_live_cash": display_ok,
        "reason_code": code,
        "reason_de": reason,
        "message_de": msg,
        "broker_status": status or None,
        "last_sync_utc": sync_utc,
        "sync_age_s": round(age, 1) if age is not None else None,
        "cash_eur": broker.get("cash_eur"),
        "positions_count": broker.get("positions_count"),
        "policy_ref": str(_POLICY_REL).replace("\\", "/"),
    }
    if root is not None:
        atomic_write_json(Path(root) / _EVIDENCE_REL, doc)
    return doc


def assess_t212_trust_from_root(root: Path, *, persist: bool = True) -> Dict[str, Any]:
    root = Path(root)
    try:
        from analytics.r3_t212_operator_api import needs_operator_api_setup

        if needs_operator_api_setup(root):
            return assess_t212_trust(
                {
                    "status": "NOT_CONFIGURED_SETUP_AVAILABLE_IN_GUI",
                    "credentials_configured": False,
                },
                root=root if persist else None,
            )
    except Exception:
        pass
    broker: Dict[str, Any] = {}
    try:
        from integrations.trading212.t212_readonly_connection_service import load_cached_broker_status

        st = load_cached_broker_status(root)
        if st is not None:
            broker = st.to_dict() if hasattr(st, "to_dict") else {}
    except Exception:
        pass
    if not broker:
        bond = _load_json(root / "evidence/r3_t212_api_bond_latest.json")
        if bond:
            broker = {
                "status": bond.get("broker_status"),
                "credentials_configured": bond.get("credentials_configured"),
                "last_successful_sync_utc": bond.get("last_sync_utc"),
                "cash_eur": bond.get("cash_eur"),
                "positions_count": bond.get("positions_count"),
                "last_error": bond.get("message_de"),
            }
    if not broker.get("credentials_configured"):
        try:
            from analytics.r3_t212_account_identity import credentials_fingerprint

            if credentials_fingerprint(root):
                broker = {**broker, "credentials_configured": True}
        except Exception:
            pass
    return assess_t212_trust(broker, root=root if persist else None)

"""R3 ↔ Trading212 API — zentrale feste Verbindung mit Bestätigung auf R3."""
from __future__ import annotations

import html
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

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
        return "Trading212 API ausstehend — Key in .env oder Order-Desk"

    if _is_connected(broker) and bonded:
        cash = broker.get("cash_eur")
        cash_bit = f" · {float(cash):.0f} €" if cash is not None else ""
        if status == "CREDENTIALS_EXPIRED_SHOWING_CACHED_DATA":
            return (
                f"⚠ T212 API-Key ungültig — Kontostand aus Cache · {env} · "
                f"{positions} Positionen{cash_bit} · Stand {sync_at or '—'}"
            )
        age = _sync_age_seconds(broker)
        if age is not None and age > _STALE_SYNC_WARN_S:
            return (
                f"⚠ Kontostand aus Cache (veraltet) · {env} · "
                f"{positions} Positionen{cash_bit} · Stand {sync_at or '—'}"
            )
        if status in {"CACHED_READONLY_DATA", "RATE_LIMITED_SHOWING_CACHED_DATA"}:
            return f"✓ Trading212 API verbunden (Cache) · {env} · Sync {sync_at or '—'}"
        return (
            f"✓ Trading212 API zentral verbunden · {env} · "
            f"{positions} Positionen{cash_bit} · Sync {sync_at or '—'}"
        )

    err = str(broker.get("last_error") or "Verbindung prüfen")[:80]
    if bonded:
        return f"✓ Trading212 Bond gehalten · {env} · {err}"
    return f"Trading212 API nicht bereit · {err}"


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
    if not trust.get("trusted"):
        confirm = str(trust.get("message_de") or confirm)
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
        "credentials_configured": bool(broker.get("credentials_configured")),
        "positions_count": int(broker.get("positions_count") or 0),
        "positions": broker.get("positions") or [],
        "cash_eur": broker.get("cash_eur"),
        "cash_breakdown": broker.get("cash_breakdown") or {},
        "investable_eur": _r3_investable_from_broker(root, broker),
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
        }
        atomic_write_json(root / _BOND_LOCK_REL, lock_update)

    if persist:
        atomic_write_json(root / _EVIDENCE_REL, doc)
    return doc


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
        doc = {"confirmation_de": "Trading212 API — Evidence ausstehend", "state": "warn"}
    state = str(doc.get("state") or "fail")
    text = html.escape(str(doc.get("confirmation_de") or doc.get("message_de") or "Trading212 API"))
    return f'<p class="r3-t212-bond {state}" id="r3-t212-bond" aria-label="Trading212 API">{text}</p>'
